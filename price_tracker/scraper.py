"""价格爬虫基类 + 名字匹配器"""
import logging
from typing import Optional
from dataclasses import dataclass, field

from cigars.models import Cigar
from .models import PriceSource

logger = logging.getLogger(__name__)


@dataclass
class ScrapedItem:
    """爬取的原始价格条目"""
    name: str                          # 品名（英文）
    price: Optional[float] = None       # 实际成交价（折后价/售价）
    original_price: Optional[float] = None  # 原价（划线价，无折扣则为None）
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
        """把爬到的名字匹配到 Cigar 模型（多维度验证）"""
        # 从 raw_data 提取品牌提示
        brand_hint = item.raw_data.get('brand') if item.raw_data else None
        
        # 名字匹配
        cigar = match_cigar_by_name(
            item.name,
            source_name=self.source.name,
            brand_hint=brand_hint,
        )
        
        if not cigar:
            return None
        
        # 多维度验证
        # 1. 品牌验证（如果爬虫提供了品牌）
        if brand_hint and cigar.brand:
            from price_tracker.matcher import _basic_normalize
            scraped_brand = _basic_normalize(brand_hint)
            db_brand = _basic_normalize(str(cigar.brand))
            if scraped_brand not in db_brand and db_brand not in scraped_brand:
                logger.warning(f'[brand-mismatch] {item.name} → {cigar.english_name} '
                              f'(scraped_brand={brand_hint}, db_brand={cigar.brand})')
                return None
        
        # 2. Box size 验证（如果双方都有）
        if item.box_size and cigar.packagings:
            import json
            try:
                pack = json.loads(cigar.packagings) if isinstance(cigar.packagings, str) else cigar.packagings
                db_box_sizes = pack.get('box_sizes', []) if isinstance(pack, dict) else []
                if db_box_sizes and item.box_size not in db_box_sizes:
                    # box_size 不匹配，但可能是不同包装，记录日志但不拒绝
                    logger.debug(f'[boxsize-mismatch] {item.name} → {cigar.english_name} '
                                f'(scraped={item.box_size}, db={db_box_sizes})')
            except (json.JSONDecodeError, AttributeError):
                pass
        
        return cigar


# --- 名字匹配（委托给独立匹配模块） ---

from price_tracker.matcher import match_cigar as _match_cigar, extract_brand_hint


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

    from .ingestion import ingest_items

    result = ingest_items(source, items, mode='scrape')

    return {
        'source': source_slug,
        'total_items': len(items),
        'matched': result.matched,
        'created': result.created,
        'skipped': result.skipped,
        'marked_oos': result.delisted,
        'cache_hits': result.cache_hits,
        'cache_misses': result.cache_misses,
    }
