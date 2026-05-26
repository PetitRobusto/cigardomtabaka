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
    brand_hint: Optional[str] = None   # 品牌提示（品牌页爬取时提供，用于精准匹配）


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


# --- 名字归一化（处理口音/空格/前缀差异） ---

import unicodedata

# Known COH misspellings/aliases → corrected form
COH_NAME_FIXES = {
    'vitosos': 'vistosos',           # COH typo for Vistosos
    'connoisseur': 'connossieur',     # COH: double-S, DB: double-N
    'omhros': 'omhpos',              # COH Greek Ρ→R, DB Latin P
}

# Greek → Latin transliteration
GREEK_TO_LATIN = {
    'Α': 'A', 'Β': 'B', 'Γ': 'G', 'Δ': 'D', 'Ε': 'E', 'Ζ': 'Z',
    'Η': 'H', 'Θ': 'TH', 'Ι': 'I', 'Κ': 'K', 'Λ': 'L', 'Μ': 'M',
    'Ν': 'N', 'Ξ': 'X', 'Ο': 'O', 'Π': 'P', 'Ρ': 'R', 'Σ': 'S',
    'Τ': 'T', 'Υ': 'Y', 'Φ': 'F', 'Χ': 'CH', 'Ψ': 'PS', 'Ω': 'O',
    'α': 'a', 'β': 'b', 'γ': 'g', 'δ': 'd', 'ε': 'e', 'ζ': 'z',
    'η': 'h', 'θ': 'th', 'ι': 'i', 'κ': 'k', 'λ': 'l', 'μ': 'm',
    'ν': 'n', 'ξ': 'x', 'ο': 'o', 'π': 'p', 'ρ': 'r', 'σ': 's',
    'τ': 't', 'υ': 'y', 'φ': 'f', 'χ': 'ch', 'ψ': 'ps', 'ω': 'o',
}

def _transliterate_greek(s: str) -> str:
    """ΟΜΗΡΟΣ → HOMEROS"""
    return ''.join(GREEK_TO_LATIN.get(c, c) for c in s)

def _normalize_for_match(s: str) -> str:
    """归一化字符串以便匹配：去重音、strip 前缀、统一空格、希腊字母转写"""
    if not s:
        return ''
    s = s.strip()
    # Transliterate Greek characters FIRST (before NFKD eats them)
    s = _transliterate_greek(s)
    # Strip "5 Pack-" / "5 Pack -" anywhere in name (COH 5-pack variants)
    s = re.sub(r'\b\d+\s*Pack\s*-?\s*', '', s)
    # NFKD decomposes accented chars → base + combining diacritic
    nfkd = unicodedata.normalize('NFKD', s)
    ascii_only = nfkd.encode('ascii', 'ignore').decode('ascii')
    # Normalize spaces and numbering
    ascii_only = re.sub(r'\s+', ' ', ascii_only)
    ascii_only = re.sub(r'No\.\s+', 'No.', ascii_only)
    ascii_only = re.sub(r'No\s+(\d)', r'No.\1', ascii_only)
    ascii_only = ascii_only.replace('.', '')
    # Normalize Connoisseur/Connossieur spelling variance
    result = ascii_only.strip().lower()
    # Apply known COH typo fixes
    for bad, good in COH_NAME_FIXES.items():
        result = result.replace(bad, good)
    # Normalize "2" ↔ "No2": strip "no" prefix for comparison, then re-check
    # If one has "no2" and the other has just "2", normalize both to bare digit
    result = re.sub(r'\bno\s*(\d+)\b', r'\1', result)
    # Strip known brand prefixes to avoid brand-name substring matching
    # e.g. "romeo y julieta linea de oro nobles" → "linea de oro nobles"
    # This prevents "julieta" matching as a substring of the scraped name
    for brand in _KNOWN_BRAND_NORMS:
        prefix = brand + ' '
        if result.startswith(prefix):
            result = result[len(prefix):]
            break
        # Also try "brand - " pattern
        prefix2 = brand + ' - '
        if result.startswith(prefix2):
            result = result[len(prefix2):]
            break
    return result


# Pre-compute normalized brand names for prefix stripping
_KNOWN_BRAND_NORMS = sorted([
    'belinda', 'bolivar', 'cohiba', 'combinaciones', 'cuaba',
    'diplomaticos', 'el rey del mundo', 'fonseca', 'guantanamera',
    'h upmann', 'hoyo de monterrey', 'jose l piedra', 'juan lopez',
    'la flor de cano', 'la gloria cubana', 'montecristo', 'partagas',
    'por larranaga', 'punch', 'quai dorsay', 'quintero y hermano',
    'rafael gonzalez', 'ramon allones', 'romeo y julieta',
    'saint luis rey', 'san cristobal de la habana', 'sancho panza',
    'trinidad', 'troya', 'vegas robaina', 'vegueros',
], key=len, reverse=True)  # Sort by length descending: strip longest match first


# --- 名字匹配 ---

def match_cigar_by_name(
    scraped_name: str,
    source_name: str = '',
    brand_hint: Optional[str] = None,
) -> Optional[Cigar]:
    """
    通用名字匹配器：模糊匹配 scraped_name → Cigar.english_name

    策略：
    1. 归一化后精确匹配（去重音/空格/前缀）
    2. 中文名精确匹配
    3. english_name__icontains（双向前缀匹配）
    4. 带 brand_hint 缩小范围
    """
    name = scraped_name.strip()

    # 0. 归一化 scraped name
    norm = _normalize_for_match(name)

    # 1. 归一化精确匹配：遍历同品牌雪茄，归一化 english_name 后比对
    qs = Cigar.objects.all()
    if brand_hint:
        from cigars.models import Cigar as CigarModel
        qs = CigarModel.objects.filter(brand__iexact=brand_hint)

    for cigar in qs.only('id', 'english_name', 'brand'):
        if cigar.english_name and _normalize_for_match(cigar.english_name) == norm:
            logger.debug(f'[norm-exact] {name} → {cigar}')
            return cigar

    # 2. 中文名精确匹配
    qs_ch = Cigar.objects.filter(name=name)
    if brand_hint:
        qs_ch = qs_ch.filter(brand__iexact=brand_hint)
    match = qs_ch.first()
    if match:
        logger.debug(f'[cn-exact] {name} → {match}')
        return match

    # 3. icontains 归一化后双向匹配（含品牌前缀剥离尝试）
    qs = Cigar.objects.all()
    if brand_hint:
        qs = qs.filter(brand__iexact=brand_hint)

    for cigar in qs.only('id', 'english_name', 'brand'):
        if not cigar.english_name:
            continue
        db_norm = _normalize_for_match(cigar.english_name)
        if brand_hint:
            # 有品牌范围：in 匹配安全
            if db_norm in norm or norm in db_norm:
                logger.debug(f'[norm-icontains] {name} → {cigar}')
                return cigar
        else:
            # 无品牌范围：收紧，只用 startswith/endswith（不用 in，避免跨品牌误匹配）
            if norm.startswith(db_norm) or db_norm.startswith(norm):
                logger.debug(f'[norm-icontains] {name} → {cigar}')
                return cigar

    # 4. 品牌前缀剥离后重试（"Cohiba Esplendidos" → "Esplendidos"）
    # 只在同品牌范围内搜索，避免 "Romeo y Julieta Churchills" 匹配到 Bolívar
    parts = norm.split(None, 1)
    if len(parts) == 2:
        without_brand = parts[1]
        # 只 scoped 搜索：强制使用 brand_hint 或当前已 scoped 的 qs
        search_qs = qs
        if not brand_hint:
            # 没有品牌提示时，不加限制，但收紧匹配：只用 == 
            search_qs = Cigar.objects.all()
        for cigar in search_qs.only('id', 'english_name', 'brand'):
            if not cigar.english_name:
                continue
            db_norm = _normalize_for_match(cigar.english_name)
            # 收紧：只用 ==（不用 in，避免 "y julieta churchills" 包含 "churchills"）
            if db_norm == without_brand:
                logger.debug(f'[brand-stripped] {name} → {cigar}')
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
