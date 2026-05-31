"""
雪茄价格爬虫 — 独立名字匹配模块

问题背景：
  爬虫抓到的品名格式五花八门：(1) "Romeo y Julieta Churchills" ↔ DB "Churchills"
  (2) 口音差异 "Esplendidos" ↔ "Espléndidos" (3) 拼写差异 "Vitosos" ↔ "Vistosos"
  (4) 单复数 "Churchill" ↔ "Churchills" (5) No.X ↔ X

策略管线（按优先级）：
  1. 归一化 + 品牌剥离 → 精确匹配
  2. 品牌剥离 → 归一化 icontains 双向
  3. 单词级匹配（至少 2 个非停用词命中）
  4. 仅核心词匹配（去掉 Churchills/Coronas 等系列后缀）

用法：
  from price_tracker.matcher import match_cigar
  cigar = match_cigar("Romeo y Julieta Churchills", brand_hint="Romeo y Julieta")
"""

import re
import unicodedata
import logging
from typing import Optional
try:
    from rapidfuzz import fuzz
    HAS_RAPIDFUZZ = True
except ImportError:
    HAS_RAPIDFUZZ = False
from django.db.models import QuerySet

logger = logging.getLogger(__name__)

# ── 品牌名 → 规范化形式（用于剥离品牌前缀） ──────────────────

# 所有已知古巴品牌（含变体），key=规范化，value=原始名
BRAND_NORM_MAP = {}
_brand_map_built = False

def _ensure_brand_map():
    """懒加载品牌映射：从硬编码列表构建"""
    global BRAND_NORM_MAP, _brand_map_built
    if _brand_map_built:
        return

    # 硬编码 31 个古巴品牌（COH/EGM/iHavanas 用名）
    hardcoded = [
        'Belinda', 'Bolívar', 'Bolivar', 'Cohiba', 'Combinaciones', 'Cuaba',
        'Diplomáticos', 'Diplomaticos', 'El Rey del Mundo', 'Fonseca',
        'Guantanamera', 'H. Upmann', 'H Upmann', 'Hoyo de Monterrey',
        'José L. Piedra', 'Jose L. Piedra', 'Juan López', 'Juan Lopez',
        'La Flor de Cano', 'La Gloria Cubana', 'Montecristo',
        'Partagás', 'Partagas', 'Por Larrañaga', 'Por Larranaga',
        'Punch', 'Quai d\'Orsay', 'Quai dOrsay', 'Quintero',
        'Rafael González', 'Rafael Gonzalez', 'Ramón Allones', 'Ramon Allones',
        'Romeo y Julieta', 'Romeo Julieta', 'Saint Luis Rey',
        'San Cristóbal', 'San Cristobal de la Habana', 'Sancho Panza',
        'Trinidad', 'Troya', 'Vegas Robaina', 'Vegueros',
        'Vegas de Santiago',
    ]
    for b in hardcoded:
        BRAND_NORM_MAP[_basic_normalize(b)] = b
    _brand_map_built = True


# ── 工具函数（基础，先定义） ──────────────────────────────

def _basic_normalize(s: str) -> str:
    """基础归一化：小写 + 去空格 + 去标点 + 去重音（用于品牌比较）"""
    if not s:
        return ''
    # NFKD 分解重音
    nfkd = unicodedata.normalize('NFKD', s.strip())
    ascii_only = nfkd.encode('ascii', 'ignore').decode('ascii')
    s = ascii_only.lower()
    s = re.sub(r'[\s\-\.\']+', '', s)
    return s


# ── 希腊字母转写映射 ──────────────────────────────────────

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


# ── 已知拼写错误修正 ───────────────────────────────────────

# format: bad→good（已归一化后的形式）
NAME_FIXES = {
    'vitosos': 'vistosos',              # COH 经典: Cohiba Vistosos
    'connoisseur': 'connossieur',        # 双S vs 双N
    'omhros': 'omhpos',                 # 希腊字母差异
    'connosseur': 'connossieur',         # 单S+单N变体
    'conosseur': 'connossieur',
    'cetros': 'cedros',                 # COH 拼错: Cetros → Cedros (雪松)
    'supreme': 'supremos',              # COH: Robustos Supreme → Robustos Supremos (2014 EL)
    'omiros': 'omhpos',                 # 现代希腊语拼写 vs 古典希腊语转写: Omiros→ΟΜΗΡΟΣ→OMHPOS
}

# ── 复数/单数修正（归一化后） ──────────────────────────────

# 匹配后如果二者只有单复数差异，认为是同一款
PLURAL_SINGULAR = {
    'churchill': 'churchills',    # ↔
    'churchills': 'churchills',
    'robustos': 'robustos',
    'robusto': 'robustos',        # Robusto Extra → Robustos Extra
    'coronas': 'coronas',
    'corona': 'coronas',
    'piramides': 'piramides',
    'piramide': 'piramides',
    'petit churchill': 'petit churchills',
    'petit churchills': 'petit churchills',
    'petit robusto': 'petit robustos',
    'petit robustos': 'petit robustos',
    # VIP Cigars: 单复数差异（Sport → Sports, Largos→Largo 等）
    'sport': 'sports',
    'sports': 'sports',
}
# 也就是：如果两个归一化后的名字只差一个末尾's'，忽略差异


# ── 停用词（匹配时忽略） ────────────────────────────────────

STOP_WORDS = {
    # 雪茄特殊停用词
    'edicion', 'edition', 'limitada', 'limited', 'regional', 'especial',
    'special', 'release', 'seleccion', 'reserva', 'coleccion',
    'lcdh', 'habanos', 'exclusive', 'humidor', 'jar', 'ceramic',
    # 通用虚词（防止跨名匹配，如 "Year of the Rabbit" vs "Year of the Horse"）
    'of', 'the', 'de', 'la', 'el', 'del', 'en', 'con', 'por', 'para',
    'y', 'a', 'an', 'and', 'or', 'in', 'on', 'at', 'to', 'for',
}


# ═══════════════════════════════════════════════════════════
#  归一化函数
# ═══════════════════════════════════════════════════════════

def _transliterate_greek(s: str) -> str:
    """ΟΜΗΡΟΣ → OMHPOS"""
    return ''.join(GREEK_TO_LATIN.get(c, c) for c in s)


def normalize(s: str) -> str:
    """
    完整归一化管线：去重音、去希腊字母、去前缀、修正拼写、统一编号格式。

    >>> normalize("Romeo y Julieta Churchills")
    'churchills'
    >>> normalize("Espléndidos")
    'esplendidos'
    >>> normalize("Cohiba Vitosos")
    'vistosos'       # via NAME_FIXES
    >>> normalize("Connossieur No.2")
    'connossieur 2'  # No.X → X
    >>> normalize("5 Pack- Montecristo No.4")
    'montecristo 4'  # strip pack prefix
    """
    if not s:
        return ''

    s = s.strip()

    # 1. 希腊字母转写（必须在 NFKD 之前！）
    s = _transliterate_greek(s)

    # 2. 去掉 "5 Pack-" / "10 Pack-" 等前缀
    s = re.sub(r'\b\d+\s*Pack\s*-?\s*', '', s)

    # 2b. 去掉 "EL 2011" / "EL 2005" 等限量版年份后缀
    s = re.sub(r'\bEL\s+\d{4}\b', '', s, flags=re.IGNORECASE)

    # 2c. 去掉品名末尾的盒装尺寸标注 "(25)" / "(5×20)" / "(10)" 等
    # 这些是爬虫页面上的包装尺寸，不是雪茄品名的一部分
    s = re.sub(r'\s*\(\s*\d+\s*(?:[x×]\s*\d+)?\s*\)\s*$', '', s)

    # 2d. 去掉 A/T（铝管）C/P（纸盒）SLB/SBN（滑动盖盒）Tubos（铝管装）后缀
    s = re.sub(r'\s+A/T(\s|$)', ' ', s)
    s = re.sub(r'\s+C/P(\s|$)', ' ', s)
    s = re.sub(r'\s+SLB(\s|$)', ' ', s)
    s = re.sub(r'\s+SBN(\s|$)', ' ', s)
    s = re.sub(r'\s+Tubos(\s|$)', ' ', s)

    # 2e. Siglo 数字 → 罗马数字转换（Siglo 6 → Siglo VI）
    ROMAN_MAP = {'1': 'I', '2': 'II', '3': 'III', '4': 'IV', '5': 'V', '6': 'VI'}
    s = re.sub(r'\bSiglo\s+(\d)\b', lambda m: f'Siglo {ROMAN_MAP.get(m.group(1), m.group(1))}', s, flags=re.IGNORECASE)

    # 2f. "N°" → "No." (必须在 NFKD 之前，因为 ° 会被分解)
    s = s.replace('N°', 'No.')

    # 3. NFKD 分解重音字符 → base + combining diacritic
    nfkd = unicodedata.normalize('NFKD', s)
    ascii_only = nfkd.encode('ascii', 'ignore').decode('ascii')

    # 4. 统一空格、去掉点和连字符
    ascii_only = re.sub(r'\s+', ' ', ascii_only)
    ascii_only = re.sub(r'No\.\s+', 'No.', ascii_only)
    ascii_only = re.sub(r'No\s+(\d)', r'No.\1', ascii_only)
    ascii_only = re.sub(r'\bN\s+(\d)\b', r'No.\1', ascii_only)  # "N 2" → "No.2"
    ascii_only = re.sub(r'N°', 'No.', ascii_only)                 # "N°2" → "No.2"
    ascii_only = ascii_only.replace('.', '')

    result = ascii_only.strip().lower()

    # 5. 拼写修正
    for bad, good in NAME_FIXES.items():
        result = result.replace(bad, good)

    # 6. No.X → noX（保留 no 前缀防止单数字误匹配，如 "4" 匹配 "2024"）
    result = re.sub(r'\bno\s*(\d+)\b', r'no\1', result)

    return result


def normalize_plural(s: str) -> str:
    """归一化 + 单复数统一（检查所有词，不只最后一个）"""
    n = normalize(s)
    words = n.split()
    changed = False
    for i, w in enumerate(words):
        if w in PLURAL_SINGULAR:
            words[i] = PLURAL_SINGULAR[w]
            changed = True
    if changed:
        n = ' '.join(words)
    return n


def strip_brand(name: str) -> str:
    """
    从爬虫品名中剥离品牌前缀（支持循环剥离，处理品牌名重复的情况）。
    "Romeo y Julieta Churchills" → "Churchills"
    "Cohiba Behike BHK 52" → "Behike BHK 52"
    "H. Upmann Connoisseur No.2" → "Connoisseur No.2"
    "H. Upmann H.Upmann Connossieur" → "Connossieur"（循环剥离）
    """
    stripped, _ = _strip_brand_with_hint(name)
    return stripped


def _strip_brand_with_hint(name: str):
    """剥离品牌前缀，返回 (剥离后品名, 匹配到的品牌原名 或 None)"""
    _ensure_brand_map()
    original_name = name
    hint = None
    
    # 循环剥离：处理品牌名重复的情况
    max_iterations = 3  # 防止无限循环
    for _ in range(max_iterations):
        name_norm = _basic_normalize(name)
        found = False
        
        # 按品牌长度降序排列（优先匹配长品牌名）
        for brand_norm, brand_original in sorted(
            BRAND_NORM_MAP.items(), key=lambda x: -len(x[0])
        ):
            if name_norm.startswith(brand_norm):
                # 用归一化计算切点
                cut = len(brand_norm)
                pos = 0
                acc = 0
                while pos < len(name) and acc < cut:
                    ch = name[pos]
                    nch = _basic_normalize(ch)
                    if nch:
                        acc += 1
                    pos += 1
                stripped = name[pos:].strip()
                stripped = re.sub(r'^[\s\-]+', '', stripped)
                if stripped:
                    name = stripped
                    hint = hint or brand_original
                    found = True
                    break
                else:
                    return original_name, brand_original
            elif name_norm == brand_norm:
                return original_name, brand_original
        
        if not found:
            break
    
    # 回退保护：如果多次剥离后只剩包装关键词（SLB/Tubos/Cabinet等），返回原名
    if len(name.strip()) <= 10:
        # 检查是否为纯包装关键词
        packaging_keywords = {'slb', 'tubos', 'tube', 'cabinet', 'box', 'pack', 'tin',
                              'bundle', 'jar', 'travel', 'humidor', 'gift'}
        remaining_words = set(name.strip().lower().split())
        if remaining_words.issubset(packaging_keywords):
            return original_name, hint
    
    return name, hint


def extract_brand_hint(name: str):
    """
    从品名自动提取品牌提示词。
    "Cuaba Salomones" → "Cuaba"
    "Romeo y Julieta Churchills" → "Romeo y Julieta"
    "Churchills" → None（无品牌前缀）
    
    用于 matcher 自动加品牌过滤，防止裸名单词跨品牌误匹配
    （如 "Salomones" 在 DB 中有 Cuaba/Partagás/Montecristo 三款）。
    """
    _, hint = _strip_brand_with_hint(name)
    return hint

# ═══════════════════════════════════════════════════════════
#  策略：单词级匹配
# ═══════════════════════════════════════════════════════════

def _word_tokens(s: str) -> set[str]:
    """提取单词令牌（已归一化，过滤停用词）"""
    return {w for w in normalize(s).split() if w not in STOP_WORDS and len(w) > 1}


def _word_overlap(scraped_tokens: set[str], db_tokens: set[str]) -> int:
    """两个令牌集的交集大小"""
    return len(scraped_tokens & db_tokens)


def _match_word_level(
    scraped_name: str,
    candidates: QuerySet,
    brand_hint: Optional[str] = None,
) -> Optional:
    """
    单词级匹配：至少需要 N 个共同词（非品牌、非停用词）。

    阈值：>= 2 个共同词（针对多词品名）或 1 个词 + 环径/尺寸匹配（暂不实现）。
    """
    scraped_tokens = _word_tokens(scraped_name)
    if len(scraped_tokens) < 1:
        return None

    # 品牌过滤
    hint_core = ''
    if brand_hint:
        hint_words = brand_hint.strip().split(None, 1)
        hint_core = hint_words[0].rstrip(',.;').lower()

    # 品牌匹配用 _basic_normalize（去空格），避免 "H.Upmann" vs "H. Upmann" 不匹配
    def _brand_check(cigar) -> bool:
        if not hint_core:
            return True
        return _basic_normalize(hint_core) in _basic_normalize(str(cigar.brand))

    best = None
    best_score = 0

    for cigar in candidates:
        if not cigar.english_name:
            continue
        # 品牌过滤
        if not _brand_check(cigar):
            continue
        db_tokens = _word_tokens(cigar.english_name)
        score = _word_overlap(scraped_tokens, db_tokens)

        if score >= 2 and score > best_score:
            best = cigar
            best_score = score

    if best and best_score >= 2:
        return best

    return None


# ═══════════════════════════════════════════════════════════
#  核心匹配函数
# ═══════════════════════════════════════════════════════════

# ── icontains 辅助：收集+评分（不是第一个就返回） ──────────

def _collect_icontains_candidates(
    scraped_name: str,
    candidates: QuerySet,
    brand_match_fn,
    source_tag: str = '',
) -> Optional:
    """
    在候选集上做 icontains 匹配，收集所有候选后按分数排序，返回最佳。
    
    评分规则（按优先级）：
      1. 归一化精确匹配 → 直接返回（最高优先级）
      2. icontains 匹配：score = len(较短串) + (同品牌? 1000 : 0)
      3. 单词级匹配：score = 共同词数 * 100

    守卫：
      - 跳过 len ≤ 2 的归一化串（防止 "c" 误匹配 "club"）
    """
    name_stripped_raw = strip_brand(scraped_name)
    stripped = normalize(name_stripped_raw)
    stripped_plural = normalize_plural(name_stripped_raw)
    
    # 守卫：原始剥离名 ≤ 2 字符 → 跳过（如 strip_brand("Montecristo C") = "C"）
    # 注意：用原始长度而非归一化后，因为 normalize("No.4") → "4" 只有1字符
    if len(name_stripped_raw.strip()) <= 2:
        return None

    best = None
    best_score = 0
    best_reason = ''
    
    # 先收集所有匹配的候选，过滤掉被其他候选包含的子串
    matched_candidates = []
    for cigar in candidates:
        if not cigar.english_name:
            continue
        if not brand_match_fn(cigar):
            continue

        db_norm = normalize(cigar.english_name)
        db_plural = normalize_plural(cigar.english_name)

        # Guard: DB 名归一化后太短（如 "C" → "c"）
        if len(db_norm) <= 2 and len(db_plural) <= 2:
            continue
        
        # 检查是否匹配
        is_match = (db_norm == stripped or 
                    db_plural == stripped_plural or
                    db_norm in stripped or
                    stripped in db_norm or
                    db_plural in stripped_plural or
                    stripped_plural in db_plural)
        
        if is_match:
            matched_candidates.append((cigar, db_norm))
    
    # 过滤子串：如果一个 db_norm 是另一个 db_norm 的子串，且不是开头匹配，移除短的
    # 例如 "edmundo" 是 "double edmundo" 的子串，移除 "edmundo"
    filtered = []
    for i, (cigar_a, db_norm_a) in enumerate(matched_candidates):
        is_substring = False
        for j, (cigar_b, db_norm_b) in enumerate(matched_candidates):
            if i == j:
                continue
            # db_norm_a 是 db_norm_b 的真子串，且 db_norm_b 也匹配 stripped
            if db_norm_a != db_norm_b and db_norm_a in db_norm_b and db_norm_b in stripped:
                # 检查 db_norm_a 是否是 db_norm_b 的开头
                # 例如 "petit" 是 "petit coronas" 的开头，保留
                # 但 "edmundo" 不是 "double edmundo" 的开头，移除
                if not db_norm_b.startswith(db_norm_a):
                    is_substring = True
                    break
        if not is_substring:
            filtered.append((cigar_a, db_norm_a))
    
    # 对过滤后的候选评分
    for cigar, db_norm in filtered:
        db_plural = normalize_plural(cigar.english_name)

        score = 0
        reason = ''

        # ── 精确匹配（最高优先级） ──
        if db_norm == stripped:
            score = 10000 + len(db_norm)
            reason = f'icontains-exact'
        elif db_plural == stripped_plural:
            score = 9999 + len(db_plural)
            reason = f'icontains-plural-exact'
        # ── 子串包含 ──
        # ⚠️ 长度惩罚：当 scraped name 明显比 DB name 长时（如 "Robustos Supremos" vs "Robustos"），
        #     说明 scraped 多了区分词（Supremos/限量为），子串匹配不可靠，压低分数。
        #     这样 Current 优先通道匹配失败 → 掉落全量匹配 → 找到 Exact Match（如 Limited Edition）。
        # 
        # 🔑 关键改进：更长的 db_norm 应该优先（如 "Double Edmundo" 比 "Edmundo" 更精确）
        # 基础分 = 5000 + len(db_norm) * 10，让长匹配天然得分更高
        elif db_norm in stripped:
            base = 5000 + len(db_norm) * 10  # 长度权重从 1 提升到 10
            
            # 检查是否是"整词开头匹配"：db_norm 应该出现在 stripped 的开头
            # 或者是独立单词（前面有空格，后面有空格或结尾）
            # 例如 "double edmundo" 在 "double edmundo - 2018" 中是开头匹配 ✓
            # 而 "edmundo" 在 "double edmundo" 中不是开头匹配，虽然它是整词 ✗
            # （因为它是 "double edmundo" 的一部分，不是独立产品名）
            is_prefix = stripped.startswith(db_norm)
            is_standalone = re.search(rf'\b{re.escape(db_norm)}\b', stripped) is not None
            # 必须同时满足：是开头匹配 或 (是独立单词 且 前面没有其他产品词)
            is_whole_word = is_prefix or (is_standalone and stripped.startswith(db_norm))
            
            # 计算"额外后缀长度"比例：后缀越长，说明匹配越不精确
            extra_len = len(stripped) - len(db_norm)
            extra_ratio = extra_len / max(len(db_norm), 1)
            
            # 🔑 关键改进：如果是开头精确匹配（stripped 以 db_norm 开头），不施加长度惩罚
            # 例如 "fabulosos no2" 是 "fabulosos no2 coleccion habanos xvi - 2016" 的开头
            # 这是合理的匹配，不应该因为后缀长而被惩罚
            if not is_prefix:
                # 短品名（<10字符）或重复词天然容易被后缀拉长，放宽惩罚
                is_short = len(db_norm) < 10
                is_repeated_word = len(db_norm.split()) == 2 and db_norm.split()[0] == db_norm.split()[1]
                if is_short or is_repeated_word:
                    # 短品名/重复词：extra_ratio > 3 才惩罚
                    if extra_ratio > 3.0:
                        base = int(base * 0.7)
                    elif extra_ratio > 1.5:
                        base = int(base * 0.9)
                else:
                    # 正常品名：extra_ratio > 1.5 惩罚
                    if extra_ratio > 1.5:
                        base = int(base * 0.5)
                    elif extra_ratio > 0.8:
                        base = int(base * 0.8)
            score = base
            reason = f'icontains-db-in-scraped({len(db_norm)}vs{len(stripped)},extra={extra_ratio:.1f},whole={is_whole_word})'
        elif stripped in db_norm:
            score = 5000 + len(stripped) * 10
            reason = f'icontains-scraped-in-db({len(stripped)}vs{len(db_norm)})'
        elif db_plural in stripped_plural:
            base = 4999 + len(db_plural) * 10
            ratio = len(stripped_plural) / max(len(db_plural), 1)
            if len(db_plural) < 6:
                if ratio > 4.0:
                    base = int(base * 0.7)
                elif ratio > 2.5:
                    base = int(base * 0.9)
            else:
                if ratio > 2.5:
                    base = int(base * 0.5)
                elif ratio > 1.8:
                    base = int(base * 0.8)
            score = base
            reason = f'icontains-plural-db-in-scraped'
        elif stripped_plural in db_plural:
            score = 4999 + len(stripped_plural) * 10
            reason = f'icontains-plural-scraped-in-db'
        # ── Fallback: DB名去掉"no"前缀再试 ──
        # 场景：COH "Connoisseur 2" (无No.), DB "Connossieur No.2"→"connossieur no2"
        # 去掉no→"connossieur 2"，匹配scraped "connossieur 2"
        else:
            db_no_stripped = re.sub(r'\bno(\d+)\b', r'\1', db_norm)
            if db_no_stripped != db_norm:
                if db_no_stripped in stripped and len(db_no_stripped) > 2:
                    score = 4500 + len(db_no_stripped)
                    reason = f'icontains-db-nostrip-in-scraped'
                elif stripped in db_no_stripped and len(stripped) > 2:
                    score = 4500 + len(stripped)
                    reason = f'icontains-scraped-in-db-nostrip'

        # ── 状态优先级加成（同分或接近时，优先当前生产款）──
        if score > 0:
            status_bonus = {'Current': 300, 'Special Releases': 200}.get(
                getattr(cigar, 'status', ''), 100
            )
            score += status_bonus

        if score > best_score:
            best = cigar
            best_score = score
            best_reason = reason
        # 🔑 关键改进：同分时优先选择更长的 db_norm（更精确匹配）
        # 例如 "Double Edmundo"(14) 和 "Edmundo"(7) 都匹配时，优先选 "Double Edmundo"
        elif score == best_score and score > 0:
            if best and len(db_norm) > len(normalize(best.english_name)):
                best = cigar
                best_score = score
                best_reason = reason

    if best:
        # ⚠️ 阈值守卫：低分匹配视为不可靠，返回 None
        # 场景：\"robustos supremos\" 匹配 \"robustos\" 得分被惩罚后过低，
        # 应该 fall through 到下轮全量匹配，让 exact match 胜出
        # 阈值从 5000 降到 3500，允许更多合理后缀通过
        if best_score < 3500 and best_score > 0 and best_reason != 'icontains-exact' and best_reason != 'icontains-plural-exact':
            logger.debug(f'[rejected-low-score] {scraped_name} → {best.english_name} score={best_score} < 3500')
            return None
        logger.debug(f'[{best_reason}] {scraped_name} → {best.english_name} '
                     f'({best.brand}, score={best_score})')
        return best
    return None


# ═══════════════════════════════════════════════════════════
#  关键词后缀识别表 — 识别 EL/RE/LE/地区等后缀
# ═══════════════════════════════════════════════════════════

# (正则模式, 对应的DB release_type, 优先级)
# release_type=None 表示纯装饰后缀（包装标记）
SUFFIX_PATTERNS = [
    # 年限/限量 (EL/LE + 年份)
    (r'\bEL\s*\d{2,4}\b', 'Limited Edition Series', 10),
    (r'\bLE\s*\d{2,4}\b', 'Limited Edition Series', 10),
    (r'\bEdición\s+Limitada\b', 'Limited Edition Series', 10),
    (r'\bLimited\s+Edition\b', 'Limited Edition Series', 10),
    # 地限 (RE + 年份/地区关键词)
    (r'\bRE\s*\d{2,4}\b', 'Regional Edition Series', 10),
    (r'\bEdición\s+Regional\b', 'Regional Edition Series', 10),
    (r'\bRegional\s+Edition\b', 'Regional Edition Series', 10),
    # 地区关键词（地限后缀）
    (r'\bAsia\s+Pacifico?\b', 'Regional Edition Series', 5),
    (r'\bAsia\s+Pacific\b', 'Regional Edition Series', 5),
    (r'\bGran\s+Bretaña\b', 'Regional Edition Series', 5),
    (r'\bGreat\s+Britain\b', 'Regional Edition Series', 5),
    (r'\bEmiratos\s+Árabes\b', 'Regional Edition Series', 5),
    # LCDH
    (r'\bLCDH\b', 'La Casa del Habano Exclusivo', 8),
    (r'\bLa\s+Casa\s+del\s+Habano\b', 'La Casa del Habano Exclusivo', 8),
    # Colección Habanos
    (r'\bColección\s+Habanos?\b', 'Colección Habanos', 8),
    # 陈年
    (r'\bAnejados?\b', 'Anejados', 6),
    # GR / Gran Reserva / Reserva Cosecha / Grand Reserve
    (r'\bGran\s+Reserva\b', 'Grand Reserve Series', 10),
    (r'\bGrand\s+Reserve\b', 'Grand Reserve Series', 10),
    (r'\bReserva\s+Cosecha\b', 'Grand Reserve Series', 10),
    (r'\bReserva\b', 'Reserve Series', 8),
    # 包装标记（纯装饰, release_type=None）
    (r'\bEstuche\b', None, 1),
    (r'\bTravel\s+Humidor\b', None, 1),
    (r'\bGift\s+Box\b', None, 1),
    (r'\bJar\b', None, 1),
    (r'\bCaja\b', None, 1),
    # 陈年标记（装饰）
    (r'\bAGED\s*\d{4}\b', None, 1),
    # 年份残留（RE/EL/LE 被剥离后留下的裸年份）
    (r'\b\d{4}\b', None, 1),
]


def _extract_hints(name: str) -> list[str]:
    """
    识别品名中的类型提示词（EL/RE/LE/Anejados/LCDH 等），
    返回匹配到的 release_type 列表（用于后续加权打分）。

    与旧版 _strip_known_suffixes 的区别：
    - 不剥离，只识别
    - RapidFuzz 天然处理后缀噪声，不需要手动剥离

    例:
        '520 EL 12' → ['Limited Edition Series']
        '88 Asia Pacifico RE 16' → ['Regional Edition Series']
    """
    release_types = []
    sorted_patterns = sorted(SUFFIX_PATTERNS, key=lambda x: -x[2])
    for pattern, rel_type, _priority in sorted_patterns:
        if rel_type and re.search(pattern, name, re.IGNORECASE):
            release_types.append(rel_type)
    return list(set(release_types))


def _strip_known_suffixes(name: str) -> str:
    """剥离所有已知后缀（装饰性 + 类型标记），保留核心品名用于模糊匹配。
    
    类型标记（EL/RE/LE/LCDH等）虽然被剥离，但通过 _extract_hints() 
    识别的 release_type 会在后续加权打分（+15）中体现。
    
    例如:
        'Petit Robusto /25 AGED 2014' → 'Petit Robusto /25'
        'Superiores /10 LCDH AGED 2017' → 'Superiores /10'
        'Super Corona /25 Limited Edition 2014' → 'Super Corona /25'
        '898 /10 Regional Edition Asia Pacifico 2018' → '898 /10'
    """
    result = name
    for pattern, _rel_type, _priority in SUFFIX_PATTERNS:
        result = re.sub(pattern, '', result, flags=re.IGNORECASE)
    # 清理多余空格和尾部标点
    result = re.sub(r'\s+', ' ', result).strip()
    result = re.sub(r'\s*/\s*$', '', result)
    return result


def _token_fuzzy_match(stripped: str, qs, brand_filter) -> Optional:
    """
    策略6：RapidFuzz token_set_ratio 模糊匹配

    使用 RapidFuzz 的 token_set_ratio 算法：
    1. 分词 → 取交集 vs 并集
    2. Levenshtein 比较交集+剩余词
    3. 天然处理后缀噪声（SLB、EL 12、年份等会被归入剩余词）

    阈值: 85（比默认保守，因为品牌锁已过滤候选集）
    """
    if not HAS_RAPIDFUZZ or not stripped:
        return None

    best = None
    best_score = 0
    for cigar in qs.only('id', 'english_name', 'brand', 'status', 'name'):
        if not cigar.english_name or not brand_filter(cigar):
            continue
        db_norm = normalize(cigar.english_name)
        db_base = normalize(strip_brand(cigar.english_name))
        # 两个方向都比，取高的
        score = max(
            fuzz.token_set_ratio(stripped, db_base),
            fuzz.token_set_ratio(stripped, db_norm),
        )
        if score > best_score and score >= 85:
            best_score = score
            best = cigar

    if best:
        logger.debug(f'[rpf-fuzzy] {stripped[:40]} → {best.english_name} '
                     f'(score={best_score})')
    return best


def match_cigar(
    scraped_name: str,
    brand_hint: Optional[str] = None,
    source_name: str = '',
    prefer_current: bool = True,
) -> Optional:
    """
    主入口：将爬虫抓到的品名匹配到 Cigar 模型。

    新架构（信息分层）：
      1. 预处理：提取品牌 + 类型提示 + 归一化
      2. 精确匹配（fast path）
      3. RapidFuzz 主力模糊匹配
      4. Hint 加权打分 → 选最优
      5. 兜底：单词级 + 中文名

    参数:
      scraped_name:  爬虫抓到的原始品名
      brand_hint:    已知品牌名
      source_name:   爬虫来源名（日志用）
      prefer_current: 优先匹配 Current 生产款
    """
    from cigars.models import Cigar

    name = scraped_name.strip()
    norm_full = normalize(name)

    # ── 信息提取 ──
    if brand_hint is None:
        brand_hint = extract_brand_hint(name)

    hint_core = ''
    if brand_hint:
        hint_words = brand_hint.strip().split(None, 1)
        hint_core = hint_words[0].rstrip(',.;')

    # 提取类型提示（EL/RE/LE/Anejados/LCDH 等 → 对应 release_type）
    release_hints = _extract_hints(name)

    # 剥离品牌前缀
    stripped_norm = normalize(strip_brand(name))

    # 剥离装饰后缀（AGED、Estuche 等纯噪音），用于 RapidFuzz
    clean_norm = normalize(_strip_known_suffixes(strip_brand(name)))

    # 脆弱名单词检测
    fragile = (
        brand_hint is None
        and len(stripped_norm) <= 15
        and len([w for w in stripped_norm.split() if w not in STOP_WORDS]) == 1
    )

    # 品牌过滤
    def _brand_match(cigar) -> bool:
        if not brand_hint:
            return True
        brand_norm = _basic_normalize(brand_hint)
        cigar_brand_norm = _basic_normalize(str(cigar.brand))
        return brand_norm in cigar_brand_norm or cigar_brand_norm in brand_norm

    # 状态优先级
    STATUS_RANK = {'Current': 3, 'Special Releases': 2, 'Discontinued': 1}

    # ── 策略 1: 精确匹配（fast path） ──
    def _exact_scan(candidates, tag=''):
        best = None
        best_rank = 0
        for cigar in candidates:
            if not cigar.english_name or not _brand_match(cigar):
                continue
            if (normalize(cigar.english_name) == norm_full
                or normalize(cigar.english_name) == stripped_norm
                or normalize_plural(cigar.english_name) == normalize_plural(name)
                or normalize_plural(cigar.english_name) == normalize_plural(strip_brand(name))):
                rank = STATUS_RANK.get(getattr(cigar, 'status', ''), 0)
                if rank > best_rank:
                    best = cigar
                    best_rank = rank
        if best:
            logger.debug(f'[exact{tag}] {name} → {best.english_name} ({best.status})')
        return best

    qs = Cigar.objects.all()

    if prefer_current:
        current_qs = qs.filter(status='Current')
        match = _exact_scan(current_qs.only('id','english_name','brand','status','name'))
        if match:
            return match

    match = _exact_scan(qs.only('id','english_name','brand','status','name'), tag='-all')
    if match:
        return match

    # ── 策略 2: RapidFuzz 主力模糊匹配 ──
    if HAS_RAPIDFUZZ and clean_norm and not fragile:
        candidates = []
        for cigar in qs.only('id','english_name','brand','status','name','release_type'):
            if not cigar.english_name or not _brand_match(cigar):
                continue
            db_norm = normalize(cigar.english_name)
            db_base = normalize(strip_brand(cigar.english_name))
            # 双向取最高分（用 clean_norm 替代 stripped_norm）
            rpf_score = max(
                fuzz.token_set_ratio(clean_norm, db_base),
                fuzz.token_set_ratio(clean_norm, db_norm),
            )
            if rpf_score < 80:
                continue

            score = rpf_score

            # Hint 加权：类型提示匹配
            if release_hints and cigar.release_type:
                for hint_type in release_hints:
                    if hint_type.lower() in (cigar.release_type or '').lower():
                        score += 15
                        break

            # 精确包含加分（icontains）
            if db_norm in clean_norm or clean_norm in db_norm:
                score += 5

            # 长度惩罚（用 clean_norm 的长度）
            ratio = max(len(clean_norm), len(db_norm)) / max(min(len(clean_norm), len(db_norm)), 1)
            if ratio > 2.5:
                score -= int(5 * (ratio - 2.5))
            if len(clean_norm) < 10:
                score += 5

            # 状态加权
            status_bonus = {'Current': 5, 'Special Releases': 3, 'Discontinued': 0}
            score += status_bonus.get(getattr(cigar, 'status', ''), 0)

            if score >= 80:
                candidates.append((cigar, score))

        if candidates:
            candidates.sort(key=lambda x: -x[1])
            best, best_score = candidates[0]
            logger.debug(f'[rpf-main] {clean_norm[:30]} → {best.english_name} '
                         f'(score={best_score}, hints={release_hints})')
            return best

    # ── 策略 3: 单词级匹配（兜底） ──
    match = _match_word_level(strip_brand(name), qs, brand_hint)
    if match:
        logger.debug(f'[word] {name} → {match.english_name}')
        return match

    # ── 策略 4: 中文名精确匹配 ──
    qs_cn = Cigar.objects.filter(name=name)
    if brand_hint:
        qs_cn = qs_cn.filter(brand__icontains=hint_core)
    match = qs_cn.first()
    if match:
        logger.debug(f'[cn-exact] {name} → {match.english_name}')
        return match

    # ── 策略 5: RapidFuzz 兜底（更低阈值，无品牌过滤） ──
    if HAS_RAPIDFUZZ and stripped_norm and brand_hint is not None:
        match = _token_fuzzy_match(stripped_norm, qs, _brand_match)
        if match:
            return match

    logger.warning(f'[no-match] {name} ({source_name})')
    return None


# ═══════════════════════════════════════════════════════════
#  批量匹配 + 诊断
# ═══════════════════════════════════════════════════════════

def batch_match(
    names: list[str],
    brand_hint: Optional[str] = None,
    source_name: str = '',
) -> dict:
    """
    批量匹配，返回 {scraped_name: cigar_id or None}
    """
    results = {}
    for name in names:
        cigar = match_cigar(name, brand_hint=brand_hint, source_name=source_name)
        results[name] = cigar.id if cigar else None
    return results


def diagnostic(names: list[str], brand_hint: Optional[str] = None) -> list[dict]:
    """
    诊断模式：对每个名字，展示归一化链条 + 候选匹配 + 得分。
    用于排查为什么某个名字没匹配上。
    """
    from cigars.models import Cigar

    qs = Cigar.objects.all()
    if brand_hint:
        hint_words = brand_hint.strip().split(None, 1)
        hint_core = hint_words[0].rstrip(',.;')
        qs = qs.filter(brand__icontains=hint_core)

    rows = []
    for name in names:
        row = {
            'original': name,
            'stripped': strip_brand(name),
            'normalized': normalize(name),
            'normalized_stripped': normalize(strip_brand(name)),
            'candidates': [],
            'best_match': None,
            'best_reason': '',
        }

        # 找所有 icontains 候选
        stripped_norm = normalize(strip_brand(name))
        for cigar in qs.only('id', 'english_name', 'brand', 'status'):
            if not cigar.english_name:
                continue
            db_norm = normalize(cigar.english_name)
            if db_norm == stripped_norm:
                row['best_match'] = f'{cigar.english_name} ({cigar.brand}, id={cigar.id})'
                row['best_reason'] = 'exact-norm'
                break
            if db_norm in stripped_norm or stripped_norm in db_norm:
                row['candidates'].append({
                    'db_name': cigar.english_name,
                    'db_norm': db_norm,
                    'status': cigar.status,
                    'overlap': 'icontains',
                })

        if not row['best_match'] and row['candidates']:
            # 取第一个候选
            c = row['candidates'][0]
            row['best_match'] = f'{c["db_name"]} ({c["status"]})'
            row['best_reason'] = f'icontains ({len(row["candidates"])} candidates)'

        rows.append(row)

    return rows
