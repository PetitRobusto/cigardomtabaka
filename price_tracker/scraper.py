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

    # --- URL 匹配缓存：已见过的商品不重复匹配 ---
    # ⚠️ 缓存 key 是 (url, product_name)，不是纯 url
    #    COH 等站点 URL 是品牌页级别（所有 Cohiba 共享 /cigars-cohiba），
    #    纯 url 会导致同一品牌所有产品匹配到同一个 cigar！
    url_cache: dict[tuple, int] = {}
    for snap in PriceSnapshot.objects.filter(source=source, url__gt='').values('url', 'raw_data', 'cigar_id'):
        url = snap['url']
        product = snap['raw_data'].get('product', '') if isinstance(snap['raw_data'], dict) else ''
        key = (url, product) if product else (url, str(snap['cigar_id']))
        url_cache[key] = snap['cigar_id']
    logger.info(f'[url-cache] loaded {len(url_cache)} cached (url,product)→cigar mappings for {source.slug}')

    cache_hits = 0
    cache_misses = 0
    anomaly_groups = set()  # 本次爬取涉及的 (cigar_id, box_size)，用于批量重算异常

    for item in items:
        # 优先走 URL 缓存（双键：url + product name）
        cigar = None
        if item.url:
            product_hint = item.raw_data.get('product', '') if isinstance(item.raw_data, dict) else ''
            cache_key = (item.url, product_hint) if product_hint else (item.url, '')
            # 也尝试不带 product 的 fallback（兼容旧缓存）
            if cache_key in url_cache:
                cigar_id = url_cache[cache_key]
                try:
                    cigar = Cigar.objects.get(id=cigar_id)
                    cache_hits += 1
                except Cigar.DoesNotExist:
                    del url_cache[cache_key]
                    logger.debug(f'[url-cache] stale cache (cigar {cigar_id} deleted) for {cache_key}')
            elif product_hint and (item.url, '') in url_cache:
                # 新格式没命中，试旧格式（纯 url）
                pass  # 不走缓存，让 matcher 重新匹配并更新缓存

        if not cigar:
            cigar = scraper.match_cigar(item)
            if cigar:
                cache_misses += 1

        if not cigar:
            skipped += 1
            continue
        matched += 1

        box_size = item.box_size
        
        # 无盒装数 → 从历史数据推断唯一包装规格
        if box_size is None:
            from django.db.models import Count
            known_sizes = (
                PriceSnapshot.objects
                .filter(cigar=cigar, box_size__isnull=False)
                .values('box_size')
                .annotate(cnt=Count('id'))
                .order_by('-cnt')
            )
            unique_sizes = [s['box_size'] for s in known_sizes]
            if len(unique_sizes) == 1:
                box_size = unique_sizes[0]
                logger.info(f'[boxsize-infer] {item.name} → {cigar.english_name} '
                           f'box_size={box_size} (inferred from DB)')
            elif len(unique_sizes) == 0:
                logger.debug(f'[boxsize-skip] {item.name}: no known box_size in DB, skip')
                skipped += 1
                continue
            else:
                logger.debug(f'[boxsize-skip] {item.name}: multiple box_size {unique_sizes}, skip')
                skipped += 1
                continue
        
        combo = (cigar.id, box_size)
        scraped_combos.add(combo)

        # Get latest snapshot for this (cigar, box_size, URL) combo
        # ⚠️ CRITICAL: 同一个 (cigar_id, box_size) 可能有不同产品变体
        #   (如 Nyon: Gran Reserva vs Tubos, Vintage vs 普通 SLB)
        #   不加 URL 过滤会导致对比基准漂移，产生 ±1000% 的假波动
        base_qs = PriceSnapshot.objects.filter(
            source=source, cigar=cigar, box_size=box_size
        )
        if item.url:
            url_match = base_qs.filter(url=item.url).order_by('-scraped_at').first()
            if url_match:
                latest = url_match
            else:
                # 新 URL（首次出现）→ 当新品处理，不对比旧数据
                logger.info(f'[url-new] {item.name} → {cigar.english_name} '
                           f'(url={item.url[:60]}) — 首次出现，跳过价格对比')
                latest = None
        else:
            latest = base_qs.order_by('-scraped_at').first()

        should_create = False
        raw_data = dict(item.raw_data) if item.raw_data else {}

        if latest is None:
            # New product → create
            should_create = True
        elif latest.in_stock != item.in_stock:
            # Stock status changed → create
            should_create = True
            if not item.in_stock:
                raw_data['went_oos'] = True
                raw_data['went_oos_at'] = timezone.now().isoformat()
            else:
                raw_data['relisted'] = True
                raw_data['relisted_at'] = timezone.now().isoformat()
        elif item.price is not None and abs(latest.price - item.price) > 0.001:
            # Price changed (1/1000 tolerance for float rounding)
            should_create = True
        # else: price unchanged → skip (dedup!)

        # ⚠️ Time-window dedup guard: if latest snapshot was created within the
        # scrape interval AND nothing changed, skip even if comparison missed it.
        # This prevents silent duplicates from float edge cases or race conditions.
        if not should_create and latest is not None:
            gap_minutes = (timezone.now() - latest.scraped_at).total_seconds() / 60
            scrape_interval_hours = source.scrape_interval_hours or 24
            if gap_minutes < (scrape_interval_hours * 60 * 0.8):
                # Within the scrape window — keep dedup decision
                pass
            else:
                logger.debug(f'[dedup-skip] {item.name}: last snapshot {gap_minutes:.0f}min ago '
                           f'(price={item.price}, stock={item.in_stock}) — unchanged, skipping')

        if should_create:
            # 币种：优先 item 自带的 → source 默认
            item_currency = getattr(item, 'currency', None) or source.currency or 'USD'
            # CNY 换算：用最新汇率表
            cny_rate = ExchangeRate.get_rate(item_currency)
            if cny_rate is None:
                cny_rate = exchange_rate  # fallback
            price_cny = round(item.price * cny_rate, 2) if item.price else None

            # Skip if price is None (OOS with no price) — avoid NOT NULL constraint
            if item.price is None:
                skipped += 1
                continue

            PriceSnapshot.objects.create(
                source=source,
                cigar=cigar,
                price=item.price,
                original_price=item.original_price,
                currency=item_currency,
                price_cny=price_cny,
                box_size=box_size,
                box_price=item.box_price,
                url=item.url,
                in_stock=item.in_stock,
                scraped_date=timezone.now().date(),
                scraped_at=timezone.now(),
                raw_data=raw_data,
            )
            created += 1
            # 记录需要重算异常的 (cigar_id, box_size) 组合
            anomaly_groups.add((cigar.id, box_size))

    # --- 下架检测 ---
    from .delisting import detect_delistings

    delisting_result = detect_delistings(source, scraped_combos)
    oos_count = delisting_result['newly_delisted']

    # --- 异常检测：批量重算受影响的 (cigar_id, box_size) 组 ---
    if anomaly_groups:
        from .anomaly import detect_and_mark_group
        for cid, bs in anomaly_groups:
            detect_and_mark_group(cid, bs)

    source.last_scraped = timezone.now()
    source.save(update_fields=['last_scraped'])

    logger.info(f'[url-cache] {source_slug}: {cache_hits} hits / {cache_misses} misses '
                f'(cache={len(url_cache)}, items={len(items)})')

    return {
        'source': source_slug,
        'total_items': len(items),
        'matched': matched,
        'created': created,
        'skipped': skipped,
        'marked_oos': oos_count,
        'cache_hits': cache_hits,
        'cache_misses': cache_misses,
    }
