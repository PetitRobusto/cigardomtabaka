"""价格爬虫基类 + 名字匹配器"""
import logging
from typing import Optional
from dataclasses import dataclass, field

from cigars.models import Cigar
from .models import PriceSource, PriceSnapshot

logger = logging.getLogger(__name__)


@dataclass
class ScrapedItem:
    """爬取的原始价格条目"""
    name: str                          # 品名（英文）
    price: float                       # 售价
    box_size: Optional[int] = None     # 盒装支数
    box_price: Optional[float] = None  # 整盒价
    url: str = ''                      # 商品页链接
    in_stock: bool = True
    currency: str = 'USD'               # 原币种（CHF/EUR/USD等）
    raw_data: dict = field(default_factory=dict)


class BaseScraper:
    """每个网站实现这个基类"""

    source_slug: str                   # 对应 PriceSource.slug
    source: PriceSource                 # 运行时注入

    def __init__(self, source: PriceSource):
        self.source = source

    async def scrape_catalog(self) -> list[ScrapedItem]:
        """子类实现：爬取所有雪茄价格，返回 ScrapedItem 列表"""
        raise NotImplementedError

    def match_cigar(self, item: ScrapedItem) -> Optional[Cigar]:
        """把爬到的名字匹配到 Cigar 模型"""
        return match_cigar_by_name(
            item.name,
            source_name=self.source.name,
        )


# --- 名字匹配（委托给独立匹配模块） ---

from price_tracker.matcher import match_cigar as _match_cigar, extract_brand_hint
from .models import ExchangeRate


def match_cigar_by_name(
    scraped_name: str,
    source_name: str = '',
    brand_hint: Optional[str] = None,
) -> Optional[Cigar]:
    """
    薄封装：转发给 price_tracker.matcher.match_cigar()

    ⚠️ 自动品牌提取：如果 brand_hint 为空，会从 scraped_name 提取品牌前缀。
    这防止了 "Salomones"（Cuaba/Partagás/Montecristo 共有）跨品牌误匹配。

    策略管线（见 matcher.py）：
    1. 归一化精确匹配（Current 优先）
    2. icontains 收集+评分（选最优而非首匹配）
    3. no-prefix fallback
    4. 单词级匹配
    5. 中文名精确匹配
    6. 全量匹配（所有状态）
    """
    # 自动提取品牌提示词（如果调用方没传）
    if brand_hint is None:
        brand_hint = extract_brand_hint(scraped_name)

    return _match_cigar(
        scraped_name,
        brand_hint=brand_hint,
        source_name=source_name,
        prefer_current=True,
    )


# --- 批量抓取入库 ---


def run_scrape_sync(source_slug: str) -> dict:
    """同步版价格抓取（SQLite + Django ORM 兼容）"""
    from .scrapers import get_scraper

    source = PriceSource.objects.filter(slug=source_slug, active=True).first()
    if not source:
        return {'error': f'Source {source_slug} not found or inactive'}

    scraper_cls = get_scraper(source_slug)
    if not scraper_cls:
        return {'error': f'No scraper registered for {source_slug}'}

    scraper = scraper_cls(source)

    # 执行爬虫（爬虫内部如需 async 用 asyncio.run 包）
    try:
        import asyncio
        if asyncio.iscoroutinefunction(scraper.scrape_catalog):
            items = asyncio.run(scraper.scrape_catalog())
        else:
            items = scraper.scrape_catalog()
    except Exception as e:
        logger.exception(f'Scrape failed for {source_slug}')
        return {'error': str(e), 'source': source_slug}

    matched = 0
    created = 0
    skipped = 0

    exchange_rate = source.exchange_rate or None
    if exchange_rate is None:
        # 用实时汇率表（优先）→ 兜底
        rate_obj = ExchangeRate.get_rate(source.currency)
        exchange_rate = rate_obj if rate_obj else 7.0

    from django.utils import timezone
    scraped_combos = set()

    for item in items:
        cigar = scraper.match_cigar(item) or match_cigar_by_name(item.name, source.name)
        if not cigar:
            skipped += 1
            continue
        matched += 1

        box_size = item.box_size
        combo = (cigar.id, box_size)
        scraped_combos.add(combo)

        # Get latest snapshot for this combo
        latest = PriceSnapshot.objects.filter(
            source=source, cigar=cigar, box_size=box_size
        ).order_by('-scraped_at').first()

        should_create = False
        raw_data = dict(item.raw_data) if item.raw_data else {}

        if latest is None:
            # New product → create
            should_create = True
        elif not latest.in_stock:
            # Was delisted/OOS, now back → relisted
            should_create = True
            raw_data['relisted'] = True
            raw_data['relisted_at'] = timezone.now().isoformat()
        elif latest.price != item.price:
            # Price changed → create
            should_create = True
        # else: price unchanged → skip (dedup!)

        if should_create:
            # 币种：优先 item 自带的 → source 默认
            item_currency = getattr(item, 'currency', None) or source.currency or 'USD'
            # CNY 换算：用最新汇率表
            cny_rate = ExchangeRate.get_rate(item_currency)
            if cny_rate is None:
                cny_rate = exchange_rate  # fallback
            price_cny = round(item.price * cny_rate, 2) if item.price else None

            PriceSnapshot.objects.create(
                source=source,
                cigar=cigar,
                price=item.price,
                currency=item_currency,
                price_cny=price_cny,
                box_size=box_size,
                box_price=item.box_price,
                url=item.url,
                in_stock=item.in_stock,
                raw_data=raw_data,
            )
            created += 1

    # --- 下架检测 ---
    from .delisting import detect_delistings

    delisting_result = detect_delistings(source, scraped_combos)
    oos_count = delisting_result['newly_delisted']

    source.last_scraped = timezone.now()
    source.save(update_fields=['last_scraped'])

    return {
        'source': source_slug,
        'total_items': len(items),
        'matched': matched,
        'created': created,
        'skipped': skipped,
        'marked_oos': oos_count,
    }
