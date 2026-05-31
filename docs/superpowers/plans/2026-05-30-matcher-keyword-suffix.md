# Matcher 关键词后缀识别 + 多轮匹配 实施计划

> **For agentic workers:** 逐 task 执行，每步 checkbox 完成。

**Goal:** 在 match_cigar() 中增加关键词后缀识别，对 EL/RE/LE/地区等已知后缀先剥离再重试匹配，解决数字编号款（520, 88）因后缀过长无法 icontains 命中的问题。

**Architecture:** 在 matcher.py 中新增 `SUFFIX_PATTERNS` 映射表 + `_strip_known_suffixes()` 函数。match_cigar() 末段增加「后缀剥离回退匹配」：剥离后缀后重新走 icontains 评分，匹配到后优先选 release_type 一致的 DB 款。

**Tech Stack:** Python, Django ORM, 纯字符串处理

---

### Task 1: 添加后缀模式表 & 剥离函数

**Files:**
- Modify: `price_tracker/matcher.py` (在 match_cigar 上方)

- [ ] **Step 1: 添加 SUFFIX_PATTERNS 和 _strip_known_suffixes()**

在 `def match_cigar(` 之前（约559行）插入：

```python
# ═══════════════════════════════════════════════════════════
#  关键词后缀识别表
# ═══════════════════════════════════════════════════════════

# 格式: (正则模式, 对应的DB release_type, 优先级)
# release_type 为 None 表示纯装饰后缀（如包装标记）
# 优先级高的先匹配（更具体的模式排前面）
SUFFIX_PATTERNS = [
    # 年限/限量 (EL / LE / Edición Limitada / Limited Edition + 年份)
    (r'\bEL\s*\d{2,4}\b', 'Limited Edition Series', 10),
    (r'\bLE\s*\d{2,4}\b', 'Limited Edition Series', 10),
    (r'\bEdición\s+Limitada\b', 'Limited Edition Series', 10),
    (r'\bLimited\s+Edition\b', 'Limited Edition Series', 10),
    # 地限 (RE + 年份 / 地区关键词)
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
    # 包装标记（纯装饰，release_type=None）
    (r'\bEstuche\b', None, 1),
    (r'\bTravel\s+Humidor\b', None, 1),
    (r'\bGift\s+Box\b', None, 1),
    (r'\bJar\b', None, 1),
    (r'\bCaja\b', None, 1),
]

def _strip_known_suffixes(name: str) -> tuple[str, list[str]]:
    """
    识别并剥离已知关键词后缀。
    
    返回: (剥离后的名称, 匹配到的 release_type 列表)
    
    例:
        '520 EL 12' → ('520', ['Limited Edition Series'])
        '88 Asia Pacifico RE 16' → ('88', ['Regional Edition Series'])
    """
    import re as re_mod
    stripped = name
    release_types = []
    
    # 按优先级排序（高优先级的先识别）
    sorted_patterns = sorted(SUFFIX_PATTERNS, key=lambda x: -x[2])
    
    for pattern, rel_type, _priority in sorted_patterns:
        m = re_mod.search(pattern, stripped, re_mod.IGNORECASE)
        if m:
            if rel_type:
                release_types.append(rel_type)
            # 剥离匹配到的部分
            stripped = stripped[:m.start()] + ' ' + stripped[m.end():]
            stripped = re_mod.sub(r'\s+', ' ', stripped).strip()
    
    return stripped, list(set(release_types))
```

- [ ] **Step 2: 验证语法（Django check）**

```bash
cd /home/jason/moscow_cigar && python3 manage.py check
```

预期: "System check identified no issues"

- [ ] **Step 3: 单元测试 — 剥离函数**

```bash
cd /home/jason/moscow_cigar && python3 manage.py shell -c "
from price_tracker.matcher import _strip_known_suffixes

# Test 1: Montecristo 520 EL 12
stripped, types = _strip_known_suffixes('520 EL 12')
assert stripped == '520', f'Expected 520, got {stripped}'
assert 'Limited Edition Series' in types, f'Expected LE, got {types}'
print('Test 1 PASS: 520 EL 12')

# Test 2: Rafael Gonzalez 88 Asia Pacifico RE 16
stripped, types = _strip_known_suffixes('88 Asia Pacifico RE 16')
assert stripped == '88', f'Expected 88, got {stripped}'
assert 'Regional Edition Series' in types, f'Expected RE, got {types}'
print('Test 2 PASS: 88 Asia Pacifico RE 16')

# Test 3: No suffix — unchanged
stripped, types = _strip_known_suffixes('Siglo VI')
assert stripped == 'Siglo VI', f'Got {stripped}'
assert types == [], f'Got {types}'
print('Test 3 PASS: Siglo VI (no change)')

# Test 4: Anejados
stripped, types = _strip_known_suffixes('Montecristo Churchill Anejados')
assert 'Anejados' in types
print('Test 4 PASS: Anejados')

# Test 5: LCDH
stripped, types = _strip_known_suffixes('Robustos LCDH')
assert 'La Casa del Habano Exclusivo' in types
print('Test 5 PASS: LCDH')

print('All tests passed!')
"
```

预期: 5/5 PASS

- [ ] **Step 4: Commit**

```bash
cd /home/jason/moscow_cigar
git add price_tracker/matcher.py
git commit -m "feat: add keyword suffix patterns and _strip_known_suffixes()"
```

---

### Task 2: 在 match_cigar() 中增加后缀剥离回退匹配

**Files:**
- Modify: `price_tracker/matcher.py:689-699` (match_cigar 函数末段)

- [ ] **Step 1: 添加回退匹配策略**

在 match_cigar 函数中，策略4（中文名精确匹配）之后、`logger.warning('[no-match]')` 之前插入：

```python
    # 策略 5：后缀剥离回退匹配
    # 识别 EL/RE/LE/地区等关键词后缀，剥离后重试 icontains 匹配
    stripped, release_types = _strip_known_suffixes(stripped_norm)
    if stripped and stripped != stripped_norm:
        # 后缀剥离后 icontains 评分
        fallback_qs = Cigar.objects.all()
        if hint_core:
            fallback_qs = fallback_qs.filter(brand__icontains=hint_core)
        
        # 收集所有 icontains 候选（用剥离后的名字）
        candidates = []
        for cigar in fallback_qs.only('id','english_name','brand','status','name'):
            if not cigar.english_name:
                continue
            db_norm = normalize(cigar.english_name)
            if db_norm in stripped or stripped in db_norm or normalize(strip_brand(cigar.english_name)) == stripped:
                # 得分：release_type 匹配加权
                score = 5000
                if release_types and cigar.release_type:
                    # DB 款 release_type 匹配到任何识别出的 type → +2000
                    for rt in release_types:
                        if rt.lower() in (cigar.release_type or '').lower():
                            score += 2000
                            break
                    else:
                        # 识别出了后缀但 DB 款 release_type 不匹配 → -1000
                        score -= 1000
                # 长度惩罚
                ratio = max(len(stripped), len(db_norm)) / max(min(len(stripped), len(db_norm)), 1)
                if ratio > 2.5:
                    score -= int(500 * (ratio - 2.5))
                candidates.append((cigar, score))
        
        if candidates:
            candidates.sort(key=lambda x: -x[1])
            best, best_score = candidates[0]
            if best_score >= 3500:
                logger.debug(f'[suffix-strip] {name} → {best.english_name} (score={best_score})')
                return best
```

- [ ] **Step 2: 验证语法**

```bash
cd /home/jason/moscow_cigar && python3 manage.py check
```

预期: "System check identified no issues"

- [ ] **Step 3: 回归测试 — 原匹配不能退化**

```bash
cd /home/jason/moscow_cigar && python3 manage.py shell -c "
from price_tracker.matcher import match_cigar

# 这些是之前就能匹配的，改后必须仍然匹配
tests = [
    'Cohiba Siglo VI',
    'Montecristo No.2',
    'Partagás Serie D No.4',
    'Romeo y Julieta Churchills',
    'Hoyo de Monterrey Epicure No.2',
    'H. Upmann Magnum 54',
    'Bolívar Belicosos Finos',
]
for t in tests:
    c = match_cigar(t)
    status = 'PASS' if c else 'FAIL'
    print(f'{status}: {t} → {c.english_name if c else None}')
"
```

预期: 全部 PASS

- [ ] **Step 4: 验证 3 款未匹配的**

```bash
cd /home/jason/moscow_cigar && python3 manage.py shell -c "
from price_tracker.matcher import match_cigar

# 之前未匹配的3款
tests = [
    ('Montecristo 520 EL 12', True),    # 现在应匹配
    ('Partagás Linea Maestra Estuche', False),  # DB没有 → 不应匹配
    ('Rafael González 88 Asia Pacifico RE 16', True),  # 现在应匹配
]
for name, should_match in tests:
    c = match_cigar(name)
    matched = c is not None
    status = 'PASS' if matched == should_match else 'FAIL'
    detail = f'{c.brand} {c.english_name}' if c else 'None'
    print(f'{status}: {name} → {detail}')
"
```

预期:
- PASS: Montecristo 520 EL 12 → Montecristo 520
- PASS: Partagás Linea Maestra Estuche → None
- PASS: Rafael González 88 Asia Pacifico RE 16 → 88

- [ ] **Step 5: 运行 VIP Cigars 爬虫验证全量**

```bash
cd /home/jason/moscow_cigar && python3 manage.py shell -c "
from price_tracker.scraper import run_scrape_sync
run_scrape_sync('vipcigars')
"
```

预期: 匹配率 ≥ 99%, 剩余未匹配的只有 DB 没收录的

- [ ] **Step 6: Commit**

```bash
cd /home/jason/moscow_cigar
git add price_tracker/matcher.py
git commit -m "feat: add suffix-strip fallback matching for EL/RE/LE keywords"
```

---

### Task 3: 合并回 master

- [ ] **Step 1: 切回 master 并合并**

```bash
cd /home/jason/moscow_cigar
git checkout master
git merge feature/matcher-suffix-fallback
git branch -d feature/matcher-suffix-fallback
```

- [ ] **Step 2: Django check + 验收**

```bash
cd /home/jason/moscow_cigar && python3 manage.py check
```

预期: 通过
