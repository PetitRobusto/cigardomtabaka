"""搜索评分细则 — 纯算法，零 HTTP/Django request 依赖"""
import re

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
    BASE_RATIO_FACTOR,
)


def extract_abbreviations(cigar):
    """
    从雪茄名称中提取缩写别名，用于提升模糊搜索召回率。
    例如："Serie D No.4" → ["D4"]
    """
    abbreviations = []
    ename = cigar.english_name or ''
    name = cigar.name or ''

    # 英文名提取 Serie X No.Y → XY
    for m in re.finditer(r'\b([A-Z])\s*No\.\s*(\d+)', ename, re.I):
        abbreviations.append(f"{m.group(1)}{m.group(2)}")  # e.g. D4

    # 中文名提取 X系列 Y号 → XY
    for m in re.finditer(r'([A-Z])系列\s*(\d+)号', name):
        abbreviations.append(f"{m.group(1)}{m.group(2)}")  # e.g. D4

    # BHK 54 → BHK54
    for m in re.finditer(r'\b(BHK)\s+(\d+)', ename, re.I):
        abbreviations.append(f"{m.group(1)}{m.group(2)}")  # e.g. BHK54

    # Magnum 54 → Magnum54
    for m in re.finditer(r'\b(Magnum)\s+(\d+)', ename, re.I):
        abbreviations.append(f"{m.group(1)}{m.group(2)}")

    return abbreviations


def build_search_text(cigar):
    """
    构建聚合搜索文本，包含中/外文品牌、品名、型号、常见名 + 缩写别名。
    返回 (search_lower, search_compact)
    """
    brand = cigar.brand or ''
    brand_cn = BRAND_CN_MAP.get(brand, '')
    name = cigar.name or ''
    ename = cigar.english_name or ''
    vitola = cigar.vitola or ''
    vitola_cn = cigar.vitola_cn or ''
    common = cigar.common_name or ''
    common_cn = cigar.common_name_cn or ''

    abbreviations = extract_abbreviations(cigar)

    search_text = (
        f"{brand_cn} {brand} {name} {ename} "
        f"{vitola} {vitola_cn} {common} {common_cn} "
        f"{' '.join(abbreviations)}"
    )
    search_lower = search_text.lower()
    search_compact = search_lower.replace(' ', '')
    return search_lower, search_compact


def compute_base_score(q_lower, search_compact):
    """计算基础匹配分"""
    if not HAS_RAPIDFUZZ:
        return 0
    return max(
        fuzz.token_set_ratio(q_lower, search_compact),
        fuzz.partial_ratio(q_lower, search_compact),
        fuzz.ratio(q_lower, search_compact) * BASE_RATIO_FACTOR,
    )


def compute_multi_term_bonus(terms, search_compact, brand, brand_cn):
    """
    多词查询 AND 语义加分。
    返回 (bonus, all_terms_hit)
    """
    bonus = 0
    all_terms_hit = True
    brand_zone = f"{brand_cn} {brand}".lower().replace(' ', '')

    for term in terms:
        term_lower = term.lower()
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


def compute_single_term_bonus(q_lower, search_compact):
    """单查询词额外加分"""
    if q_lower in search_compact:
        return SINGLE_TERM_HIT_BONUS
    return 0


def compute_release_type_penalty(release_type):
    """根据 release_type 计算降权（返回负值或正值）"""
    if not release_type:
        return REGULAR_RELEASE_BONUS
    penalty = RELEASE_TYPE_PENALTY.get(release_type)
    if penalty is not None:
        return -penalty
    return -DEFAULT_RELEASE_TYPE_PENALTY


def score_cigar(cigar, q_lower, terms, is_multi_term):
    """
    对单条雪茄计算搜索匹配分。
    返回 float 分数，越高越匹配。
    """
    search_lower, search_compact = build_search_text(cigar)
    score = compute_base_score(q_lower, search_compact)

    if is_multi_term:
        bonus, _ = compute_multi_term_bonus(
            terms, search_compact, cigar.brand or '', BRAND_CN_MAP.get(cigar.brand, '')
        )
        score += bonus
    else:
        score += compute_single_term_bonus(q_lower, search_compact)

    score += compute_release_type_penalty(cigar.release_type)
    return score
