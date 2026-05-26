"""价格爬虫基类 + 名字匹配器"""
import re
import logging
from typing import Optional
from dataclasses import dataclass, field

from django.db.models import Q
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


# --- 名字匹配 ---

def match_cigar_by_name(
    scraped_name: str,
    source_name: str = '',
    brand_hint: Optional[str] = None,
) -> Optional[Cigar]:
    """
    通用名字匹配器：模糊匹配 scraped_name → Cigar.english_name

    策略：
    1. 精确匹配 english_name
    2. 精确匹配 name（中文）
    3. english_name__icontains（双向）
    4. FTS5 全文搜索（如果是 SQLite）
    5. 带 brand_hint 缩小范围
    """
    name = scraped_name.strip()

    # 1. 精确匹配 english_name（大小写不敏感）
    qs = Cigar.objects.filter(english_name__iexact=name)
    if brand_hint:
        qs = qs.filter(brand__iexact=brand_hint)

    match = qs.first()
    if match:
        logger.debug(f'[exact] {name} → {match}')
        return match

    # 2. 中文名精确匹配
    qs = Cigar.objects.filter(name=name)
    if brand_hint:
        qs = qs.filter(brand__iexact=brand_hint)

    match = qs.first()
    if match:
        logger.debug(f'[cn-exact] {name} → {match}')
        return match

    # 3. icontains 双向
    qs = Cigar.objects.filter(english_name__icontains=name)
    if brand_hint:
        qs = qs.filter(brand__iexact=brand_hint)

    if qs.count() == 1:
        match = qs.first()
        logger.debug(f'[icontains] {name} → {match}')
        return match

    # 反向 icontains（scraped 名字包含 DB 名字）
    qs = Cigar.objects.all()
    if brand_hint:
        qs = qs.filter(brand__iexact=brand_hint)

    # 找 scraped_name 中包含 english_name 的
    for cigar in qs.only('id', 'english_name', 'brand'):
        if cigar.english_name and cigar.english_name.lower() in name.lower():
            logger.debug(f'[reverse-icontains] {name} → {cigar}')
            return cigar

    logger.warning(f'[no-match] {name} ({source_name})')
    return None


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

    exchange_rate = source.exchange_rate or 7.25

    for item in items:
        cigar = scraper.match_cigar(item) or match_cigar_by_name(item.name, source.name)
        if not cigar:
            skipped += 1
            continue
        matched += 1

        from django.utils import timezone
        today = timezone.now().date()
        existing = PriceSnapshot.objects.filter(
            source=source,
            cigar=cigar,
            scraped_date=today,
        ).first()

        if existing:
            existing.price = item.price
            existing.price_cny = round(item.price * exchange_rate, 2)
            existing.box_size = item.box_size
            existing.box_price = item.box_price
            existing.in_stock = item.in_stock
            existing.raw_data = item.raw_data
            existing.save()
            logger.debug(f'[updated] {cigar}: {item.price}')
        else:
            PriceSnapshot.objects.create(
                source=source,
                cigar=cigar,
                price=item.price,
                currency=source.currency,
                price_cny=round(item.price * exchange_rate, 2),
                box_size=item.box_size,
                box_price=item.box_price,
                url=item.url,
                in_stock=item.in_stock,
                raw_data=item.raw_data,
            )
            created += 1

    from django.utils import timezone
    source.last_scraped = timezone.now()
    source.save(update_fields=['last_scraped'])

    return {
        'source': source_slug,
        'total_items': len(items),
        'matched': matched,
        'created': created,
        'skipped': skipped,
    }
