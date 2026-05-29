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

    # 3. NFKD 分解重音字符 → base + combining diacritic
    nfkd = unicodedata.normalize('NFKD', s)
    ascii_only = nfkd.encode('ascii', 'ignore').decode('ascii')

    # 4. 统一空格、去掉点和连字符
    ascii_only = re.sub(r'\s+', ' ', ascii_only)
    ascii_only = re.sub(r'No\.\s+', 'No.', ascii_only)
    ascii_only = re.sub(r'No\s+(\d)', r'No.\1', ascii_only)
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
    从爬虫品名中剥离品牌前缀。
    "Romeo y Julieta Churchills" → "Churchills"
    "Cohiba Behike BHK 52" → "Behike BHK 52"
    "H. Upmann Connoisseur No.2" → "Connoisseur No.2"
    """
    stripped, _ = _strip_brand_with_hint(name)
    return stripped


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


def _strip_brand_with_hint(name: str):
    """剥离品牌前缀，返回 (剥离后品名, 匹配到的品牌原名 或 None)"""
    _ensure_brand_map()
    name_norm = _basic_normalize(name)

    # 按品牌长度降序排列（优先匹配长品牌名，如 "El Rey del Mundo" 先于 "El Rey"）
    for brand_norm, brand_original in sorted(
        BRAND_NORM_MAP.items(), key=lambda x: -len(x[0])
    ):
        if name_norm.startswith(brand_norm):
            # 用归一化计算切点（避免 Partagás ≠ Partagas 偏移问题）
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
                return stripped, brand_original
            return name, brand_original

    return name, None

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
        elif db_norm in stripped:
            base = 5000 + len(db_norm)
            ratio = len(stripped) / max(len(db_norm), 1)
            if ratio > 1.5:
                base = int(base * 0.6)  # 长度差距>50% → 降40%分
            score = base
            reason = f'icontains-db-in-scraped({len(db_norm)}vs{len(stripped)},ratio={ratio:.1f})'
        elif stripped in db_norm:
            score = 5000 + len(stripped)
            reason = f'icontains-scraped-in-db({len(stripped)}vs{len(db_norm)})'
        elif db_plural in stripped_plural:
            base = 4999 + len(db_plural)
            ratio = len(stripped_plural) / max(len(db_plural), 1)
            if ratio > 1.5:
                base = int(base * 0.6)
            score = base
            reason = f'icontains-plural-db-in-scraped'
        elif stripped_plural in db_plural:
            score = 4999 + len(stripped_plural)
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

    if best:
        # ⚠️ 阈值守卫：低分匹配（长度惩罚后 < 5000）视为不可靠，返回 None
        # 场景：\"robustos supremos\" 匹配 \"robustos\" 得分 3004（被惩罚），
        # 应该 fall through 到下轮全量匹配，让 id=160 的 exact match 胜出
        if best_score < 5000 and best_score > 0 and best_reason != 'icontains-exact' and best_reason != 'icontains-plural-exact':
            logger.debug(f'[rejected-low-score] {scraped_name} → {best.english_name} score={best_score} < 5000')
            return None
        logger.debug(f'[{best_reason}] {scraped_name} → {best.english_name} '
                     f'({best.brand}, score={best_score})')
        return best
    return None


def match_cigar(
    scraped_name: str,
    brand_hint: Optional[str] = None,
    source_name: str = '',
    prefer_current: bool = True,
) -> Optional:
    """
    主入口：将爬虫抓到的品名匹配到 Cigar 模型。

    参数:
      scraped_name:  爬虫抓到的原始品名（如 "Romeo y Julieta Churchills"）
      brand_hint:    已知品牌名（如 "Romeo y Julieta"），可缩小搜索范围
      source_name:   爬虫来源名（仅用于日志）
      prefer_current: 优先匹配 Current 生产款（True）还是全量匹配

    返回:
      Cigar 实例 或 None
    """
    from cigars.models import Cigar

    name = scraped_name.strip()
    norm_full = normalize(name)

    # 自动提取品牌提示词（防止跨品牌误匹配，如 "Cuaba Salomones" 直接调 match_cigar 时）
    if brand_hint is None:
        brand_hint = extract_brand_hint(name)

    # 提取品牌核心词（用于 DB 过滤）
    hint_core = ''
    if brand_hint:
        hint_words = brand_hint.strip().split(None, 1)
        hint_core = hint_words[0].rstrip(',.;')

    # 构建候选集（不做 DB 品牌过滤，在 Python 中归一化后比对）
    qs = Cigar.objects.all()

    # ── 脆弱名单词检测 ──
    # 当 brand_hint 为空且剥离品牌后只剩1个短词（如 "Salomones"），
    # icontains 会跨品牌误匹配（Partagás/Cuaba/Montecristo 都有 Salomones）。
    # → 跳过 icontains，仅保留精确匹配 + 单词级匹配作为防线。
    stripped_norm = normalize(strip_brand(name))
    fragile = (
        brand_hint is None 
        and len(stripped_norm) <= 15 
        and len([w for w in stripped_norm.split() if w not in STOP_WORDS]) == 1
    )

    # Python 端品牌过滤（SQLite icontains 无法处理重音差异）
    # 必须用 _basic_normalize（去空格+去标点），因为 normalize 保留空格
    # 会导致 "H.Upmann"→"hupmann" vs "H. Upmann"→"h upmann" 不匹配！
    def _brand_match(cigar) -> bool:
        if not hint_core:
            return True
        return _basic_normalize(hint_core) in _basic_normalize(str(cigar.brand))

    # ── 辅助：精确匹配扫描（策略 1） ──
    def _exact_scan(candidates, tag=''):
        best = None
        best_status = 0
        status_rank = {'Current': 3, 'Special Releases': 2, 'Discontinued': 1}
        for cigar in candidates:
            if not cigar.english_name or not _brand_match(cigar):
                continue
            match = False
            if normalize(cigar.english_name) == norm_full:
                match = True
            elif normalize(cigar.english_name) == normalize(strip_brand(name)):
                match = True
            elif normalize_plural(cigar.english_name) == normalize_plural(name):
                match = True
            elif normalize_plural(cigar.english_name) == normalize_plural(strip_brand(name)):
                match = True
            if match:
                rank = status_rank.get(getattr(cigar, 'status', ''), 0)
                if rank > best_status:
                    best = cigar
                    best_status = rank
        if best:
            logger.debug(f'[exact-norm{tag}] {name} → {best.english_name} ({best.status})')
            return best
        return None

    if prefer_current:
        current_qs = qs.filter(status='Current')

        # 策略 1：精确匹配
        match = _exact_scan(current_qs.only('id','english_name','brand','status','name'))
        if match:
            return match

        # 策略 2：icontains 评分匹配（收集全部候选→选最优）
        # 脆弱名单词（无品牌+单裸词）跳过 icontains，防止跨品牌误匹配
        if not fragile:
            match = _collect_icontains_candidates(
                name, current_qs.only('id','english_name','brand','status','name'),
                _brand_match, source_tag='current'
            )
            if match:
                return match

    # ── 全量匹配（所有状态） ──
    # 策略 1：精确
    match = _exact_scan(qs.only('id','english_name','brand','status','name'), tag='-all')
    if match:
        return match

    # 策略 2：icontains 评分匹配
    if not fragile:
        match = _collect_icontains_candidates(
            name, qs.only('id','english_name','brand','status','name'),
            _brand_match, source_tag='all'
        )
        if match:
            return match

    # 策略 3：单词级
    match = _match_word_level(strip_brand(name), qs, brand_hint)
    if match:
        logger.debug(f'[word-match-all] {name} → {match.english_name}')
        return match

    # 策略 4：中文名精确匹配
    qs_cn = Cigar.objects.filter(name=name)
    if brand_hint:
        qs_cn = qs_cn.filter(brand__icontains=hint_core)
    match = qs_cn.first()
    if match:
        logger.debug(f'[cn-exact] {name} → {match.english_name}')
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
