"""搜索评分细则 — 纯算法，零 HTTP/Django request 依赖"""
from functools import lru_cache
import re
import unicodedata

try:
    from rapidfuzz import fuzz
    HAS_RAPIDFUZZ = True
except ImportError:
    HAS_RAPIDFUZZ = False

from cigars.constants import BRAND_CN_MAP
from cigars.search.constants import (
    RELEASE_TYPE_PENALTY,
    DEFAULT_RELEASE_TYPE_PENALTY,
    REGULAR_RELEASE_BONUS,
    MULTI_TERM_HIT_BRAND_BONUS,
    MULTI_TERM_HIT_OTHER_BONUS,
    MULTI_TERM_ALL_HIT_BONUS,
    SINGLE_TERM_HIT_BONUS,
    PRODUCT_NAME_EXACT_BONUS,
    PRODUCT_NAME_HIT_BONUS,
    BASE_RATIO_FACTOR,
)


SERIE_NUMBER_PATTERN = re.compile(r'\b([A-Z])\s*No\.\s*(\d+)', re.I)
CHINESE_SERIE_NUMBER_PATTERN = re.compile(r'([A-Z])系列\s*(\d+)号')
BHK_NUMBER_PATTERN = re.compile(r'\b(BHK)\s+(\d+)', re.I)
MAGNUM_NUMBER_PATTERN = re.compile(r'\b(Magnum)\s+(\d+)', re.I)
NON_ALNUM_PATTERN = re.compile(r'[\W_]+')


def extract_abbreviations(english_name, name):
    """
    从雪茄名称中提取缩写别名，用于提升模糊搜索召回率。
    例如："Serie D No.4" → ["D4"]
    """
    abbreviations = []
    # 英文名提取 Serie X No.Y → XY
    for m in SERIE_NUMBER_PATTERN.finditer(english_name):
        abbreviations.append(f"{m.group(1)}{m.group(2)}")  # e.g. D4

    # 中文名提取 X系列 Y号 → XY
    for m in CHINESE_SERIE_NUMBER_PATTERN.finditer(name):
        abbreviations.append(f"{m.group(1)}{m.group(2)}")  # e.g. D4

    # BHK 54 → BHK54
    for m in BHK_NUMBER_PATTERN.finditer(english_name):
        abbreviations.append(f"{m.group(1)}{m.group(2)}")  # e.g. BHK54

    # Magnum 54 → Magnum54
    for m in MAGNUM_NUMBER_PATTERN.finditer(english_name):
        abbreviations.append(f"{m.group(1)}{m.group(2)}")

    return abbreviations


def normalize_search_text(value):
    """统一全角字符、大小写和品牌重音，保留中文语义。"""
    decomposed = unicodedata.normalize('NFKD', value or '')
    return ''.join(
        char for char in decomposed
        if unicodedata.category(char) != 'Mn'
    ).casefold()


def compact_search_text(value):
    """去掉空格和标点，便于中文/型号连写查询。"""
    return NON_ALNUM_PATTERN.sub('', value)


@lru_cache(maxsize=4096)
def _build_search_text(brand, name, english_name, vitola, vitola_cn, common, common_cn):
    brand_cn = BRAND_CN_MAP.get(brand, '')
    abbreviations = extract_abbreviations(english_name, name)

    search_text = normalize_search_text(
        f"{brand_cn} {brand} {name} {english_name} "
        f"{vitola} {vitola_cn} {common} {common_cn} "
        f"{' '.join(abbreviations)}"
    )
    search_lower = search_text
    search_compact = compact_search_text(search_text)
    return search_lower, search_compact


def build_search_text(cigar):
    """
    构建聚合搜索文本，包含中/外文品牌、品名、型号、常见名 + 缩写别名。
    字段值作为缓存键，目录内容更新后会自然生成新缓存项。
    """
    return _build_search_text(
        cigar.brand or '',
        cigar.name or '',
        cigar.english_name or '',
        cigar.vitola or '',
        cigar.vitola_cn or '',
        cigar.common_name or '',
        cigar.common_name_cn or '',
    )


def compute_base_score(q_lower, search_lower, search_compact, query_compact=None):
    """计算基础匹配分"""
    if not HAS_RAPIDFUZZ:
        return 0
    if query_compact is None:
        query_compact = compact_search_text(q_lower)
    return max(
        fuzz.token_set_ratio(q_lower, search_lower),
        fuzz.partial_ratio(query_compact, search_compact),
        fuzz.ratio(query_compact, search_compact) * BASE_RATIO_FACTOR,
    )


def compute_multi_term_bonus(terms, search_compact, brand, brand_cn):
    """
    多词查询 AND 语义加分。
    返回 (bonus, all_terms_hit)
    """
    bonus = 0
    all_terms_hit = True
    brand_zone = compact_search_text(normalize_search_text(f"{brand_cn} {brand}"))

    for term in terms:
        term_lower = normalize_search_text(term)
        # 纯数字要求非数字边界匹配，避免 "4" 匹配 "2024"
        if term.isdigit():
            has_term = bool(re.search(rf'(?<!\d){re.escape(term_lower)}(?!\d)', search_compact))
        else:
            has_term = term_lower in search_compact

        if has_term:
            if term_lower in brand_zone:
                bonus += MULTI_TERM_HIT_BRAND_BONUS
            else:
                bonus += MULTI_TERM_HIT_OTHER_BONUS
        else:
            all_terms_hit = False

    if all_terms_hit:
        bonus += MULTI_TERM_ALL_HIT_BONUS

    return bonus, all_terms_hit


def compute_single_term_bonus(query_compact, search_compact):
    """单查询词额外加分"""
    if query_compact in search_compact:
        return SINGLE_TERM_HIT_BONUS
    return 0


@lru_cache(maxsize=4096)
def _product_identity(brand, name, english_name):
    names = frozenset(
        compact_search_text(normalize_search_text(value))
        for value in (name, english_name)
        if value
    )
    brands = frozenset(
        compact_search_text(normalize_search_text(value))
        for value in (BRAND_CN_MAP.get(brand, ''), brand)
        if value
    )
    return names, brands


def compute_product_name_bonus(cigar, query_compact):
    """中英文产品名命中优先于只命中品型或常见名的候选。"""
    names, brands = _product_identity(
        cigar.brand or '', cigar.name or '', cigar.english_name or '',
    )
    if query_compact in names or any(
        query_compact == f'{brand}{name}' for brand in brands for name in names
    ):
        return PRODUCT_NAME_EXACT_BONUS

    query_names = {query_compact}
    query_names.update(
        query_compact[len(brand):]
        for brand in brands
        if query_compact.startswith(brand) and len(query_compact) > len(brand)
    )
    if any(
        len(name) >= 2 and (
            name in query_compact
            or any(
                len(query_name) >= 3
                and (name.startswith(query_name) or query_name.startswith(name))
                for query_name in query_names
            )
        )
        for name in names
    ):
        return PRODUCT_NAME_HIT_BONUS
    return 0


def compute_release_type_penalty(release_type):
    """根据 release_type 计算降权（返回负值或正值）"""
    if not release_type:
        return REGULAR_RELEASE_BONUS
    penalty = RELEASE_TYPE_PENALTY.get(release_type)
    if penalty is not None:
        return -penalty
    return -DEFAULT_RELEASE_TYPE_PENALTY


def score_cigar(cigar, q_lower, terms, is_multi_term, query_compact=None):
    """
    对单条雪茄计算搜索匹配分。
    返回 float 分数，越高越匹配。
    """
    if query_compact is None:
        query_compact = compact_search_text(q_lower)
    search_lower, search_compact = build_search_text(cigar)
    score = compute_base_score(
        q_lower, search_lower, search_compact, query_compact,
    )

    if is_multi_term:
        bonus, _ = compute_multi_term_bonus(
            terms, search_compact, cigar.brand or '', BRAND_CN_MAP.get(cigar.brand, '')
        )
        score += bonus
    else:
        score += compute_single_term_bonus(query_compact, search_compact)

    score += compute_product_name_bonus(cigar, query_compact)
    score += compute_release_type_penalty(cigar.release_type)
    return score
