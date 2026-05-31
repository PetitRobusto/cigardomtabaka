# Matcher 模糊匹配 + 批量修复 实施计划

> **For agentic workers:** 逐 task 执行，每步 checkbox 完成。

**Goal:** 修复3个未匹配场景（Sport单复数、希腊文转写、Punch Punch Punch）+ 添加词级模糊匹配作为第6策略

**Architecture:** 
1. 扩充 `normalize()` 增加希腊字母→拉丁转写
2. 扩充 `normalize_plural()` 增加常用单复数映射
3. 修复 VIP 爬虫 Punch 数据质量问题
4. 在 `match_cigar()` 策略5后加策略6：词级 Jaccard 模糊匹配

**Tech Stack:** Python, Django ORM, regex

---

### Task 1: 添加希腊字母→拉丁转写

**Files:**
- Modify: `price_tracker/matcher.py` (normalize 和 _transliterate_greek)

- [ ] **Step 1: 扩展希腊转写表**

在 `_transliterate_greek()` 函数中（~138行），增加完整希腊字母映射：

```python
def _transliterate_greek(s: str) -> str:
    """希腊字母 → 拉丁字母转写"""
    GREEK_MAP = {
        'Α': 'A', 'α': 'a',
        'Β': 'V', 'β': 'v',
        'Γ': 'G', 'γ': 'g',
        'Δ': 'D', 'δ': 'd',
        'Ε': 'E', 'ε': 'e',
        'Ζ': 'Z', 'ζ': 'z',
        'Η': 'I', 'η': 'i',
        'Θ': 'Th', 'θ': 'th',
        'Ι': 'I', 'ι': 'i',
        'Κ': 'K', 'κ': 'k',
        'Λ': 'L', 'λ': 'l',
        'Μ': 'M', 'μ': 'm',
        'Ν': 'N', 'ν': 'n',
        'Ξ': 'X', 'ξ': 'x',
        'Ο': 'O', 'ο': 'o',
        'Π': 'P', 'π': 'p',
        'Ρ': 'R', 'ρ': 'r',
        'Σ': 'S', 'σ': 's', 'ς': 's',
        'Τ': 'T', 'τ': 't',
        'Υ': 'Y', 'υ': 'y',
        'Φ': 'F', 'φ': 'f',
        'Χ': 'Ch', 'χ': 'ch',
        'Ψ': 'Ps', 'ψ': 'ps',
        'Ω': 'O', 'ω': 'o',
    }
    result = []
    for ch in s:
        result.append(GREEK_MAP.get(ch, ch))
    return ''.join(result)
```

- [ ] **Step 2: 确保 normalize() 中调用了 _transliterate_greek()**

已存在于 normalize() 第157行，验证即可。

- [ ] **Step 3: 验证**

```bash
cd /home/jason/moscow_cigar && python3 manage.py shell -c "
from price_tracker.matcher import _transliterate_greek, match_cigar
# Greek test
print(_transliterate_greek('OMHPOΣ'))  # 应输出 'OMIROS'
print(_transliterate_greek('omhpος'))  # 应输出 'omhpos'

# 验证匹配
c = match_cigar('Sancho Panza Omiros Greece RE 22')
print(c.english_name if c else 'FAIL')
"
```

预期: `OMHPOΣ` → `OMIROS`，然后在 suffix-strip 后 `omiros` 应匹配到 DB 的 `omhpos`

- [ ] **Step 4: Commit**

---

### Task 2: 添加常用单复数映射

**Files:**
- Modify: `price_tracker/matcher.py` (normalize_plural 函数)

- [ ] **Step 1: 扩展 normalize_plural**

在 `normalize_plural()` 函数（~209行）中增加双向单复数映射：

```python
# 在 normalize_plural 函数现有的 PLURAL_RULES 之后添加：
IRREGULAR_PLURALS = {
    # 雪茄常见单复数不规则映射
    'sport': 'sports',
    'sports': 'sport',
    'edicion': 'edicion',  # 不变
}
```

实际上更简单的方法：在 normalize_plural 中，如果词以 s 结尾且去掉 s 后仍然有意义，就统一去 s。

更好的方案：在 `normalize_plural()` 中增加双向查找——对每个词，同时查原形和去s形：

```python
def normalize_plural(s: str) -> str:
    """复数归一化：双向处理，使单复数等价"""
    # ... existing logic ...
    # 新加：对每个词，同时尝试去尾s
    words = s.split()
    result = []
    for w in words:
        # 去掉尾s（如果长度>3，防止 "is"→"i"）
        if len(w) > 3 and w.endswith('s') and not w.endswith('ss'):
            w_singular = w[:-1]
            result.append(w_singular)
        elif len(w) > 3 and not w.endswith('s'):
            w_plural = w + 's'
            result.append(w_plural)
        else:
            result.append(w)
    return ' '.join(sorted(set(words + result)))
```

- [ ] **Step 2: 验证**

```bash
cd /home/jason/moscow_cigar && python3 manage.py shell -c "
from price_tracker.matcher import match_cigar, normalize_plural

# Test plural normalization
print(normalize_plural('Sport Largos'))  # 应包含 'sports largos' 或类似
print(normalize_plural('Sports Largos'))

# Verify match
c = match_cigar('Romeo y Julieta Sport Largos')
print(c.english_name if c else 'FAIL')
"
```

预期: "Sport Largos" 匹配到 "Sports Largos"

- [ ] **Step 3: Commit**

---

### Task 3: 添加词级模糊匹配（策略6）

**Files:**
- Modify: `price_tracker/matcher.py` (match_cigar 函数，策略5之后)

- [ ] **Step 1: 添加 _token_fuzzy_match() 函数**

在 match_cigar() 上方添加：

```python
def _token_fuzzy_match(stripped: str, qs, brand_filter, hint: str = '') -> Optional:
    """
    词级模糊匹配：当 icontains 全失败时的兜底策略。
    
    用 Jaccard 相似度（词级），要求 ≥50% 重叠 + 品牌通过。
    额外奖励：前缀包含（sport⊂sports）
    """
    STOP = {'de', 'del', 'la', 'el', 'los', 'las', 'the', 'of', 'no', 'serie', 'box',
            'slb', 'cabinet', 'pack', 'tin', 'tubos', 'tube'}
    scraper_words = [w for w in stripped.split() if w not in STOP and len(w) > 1]
    if not scraper_words:
        return None
    scraper_set = set(scraper_words)
    
    best = None
    best_score = 0.0
    for cigar in qs.only('id','english_name','brand','status','name'):
        if not cigar.english_name or not brand_filter(cigar):
            continue
        # 归一化并去品牌
        db_norm = normalize(cigar.english_name)
        db_base = normalize(strip_brand(cigar.english_name))
        # 选较短的名字做匹配（去掉品牌名更干净）
        db_name_for_match = db_base if len(db_base) < len(db_norm) else db_norm
        db_words = [w for w in db_name_for_match.split() if w not in STOP and len(w) > 1]
        if not db_words:
            continue
        db_set = set(db_words)
        
        # Jaccard
        intersection = scraper_set & db_set
        union = scraper_set | db_set
        jaccard = len(intersection) / len(union) if union else 0
        
        # 前缀奖励：scraper词是DB词的前缀或反之
        prefix_bonus = 0
        for sw in scraper_set - intersection:
            for dw in db_set - intersection:
                if (len(sw) >= 3 and len(dw) >= 3 and 
                    (sw.startswith(dw) or dw.startswith(sw))):
                    prefix_bonus += 0.25
        
        score = jaccard + prefix_bonus
        if score > best_score and score >= 0.5:
            best_score = score
            best = cigar
    
    if best and best_score >= 0.5:
        logger.debug(f'[token-fuzzy] {stripped} → {best.english_name} (jaccard={best_score:.2f})')
    return best
```

- [ ] **Step 2: 在 match_cigar() 末段添加策略6**

在策略5（后缀剥离回退）之后、`logger.warning('[no-match]')` 之前：

```python
    # 策略 6：词级模糊匹配（Jaccard）
    match = _token_fuzzy_match(stripped_norm, qs, _brand_match, brand_hint or '')
    if match:
        return match
```

- [ ] **Step 3: 回归测试 + 验证**

```bash
cd /home/jason/moscow_cigar && python3 manage.py shell -c "
from price_tracker.matcher import match_cigar

# 原匹配不能退化
tests = [
    ('Cohiba Siglo VI', 'Siglo VI'),
    ('Montecristo No.2', 'No.2'),
    ('Partagás Serie D No.4', 'Serie D No.4'),
    ('Montecristo 520 EL 12', '520'),  # suffix-strip
    ('H. Upmann Magnum 54', 'Magnum 54'),
]
for name, expected in tests:
    c = match_cigar(name)
    ok = c and expected.lower() in (c.english_name or '').lower()
    print(f'{\"PASS\" if ok else \"FAIL\"}: {name} -> {c.english_name if c else None}')
print()

# 新场景验证
print('=== 新匹配 ===')
c = match_cigar('Romeo y Julieta Sport Largos')
print(f'Sport Largos: {c.english_name if c else None}')

c = match_cigar('Sancho Panza Omiros Greece RE 22')
print(f'Omiros: {c.english_name if c else None}')
"
```

- [ ] **Step 4: 全量 VIP Cigars 跑一遍**

```bash
cd /home/jason/moscow_cigar && python3 manage.py shell -c "
from price_tracker.scraper import run_scrape_sync
run_scrape_sync('vipcigars')
"
```

预期: 匹配率 99%+，只剩 DB 无收录的

- [ ] **Step 5: Commit**

---

### Task 4: 合并回 master

- [ ] **Step 1: 切回 master 合并**

```bash
cd /home/jason/moscow_cigar
git checkout master
git merge feature/matcher-fuzzy-fixes
git branch -d feature/matcher-fuzzy-fixes
```

- [ ] **Step 2: Django check**

```bash
cd /home/jason/moscow_cigar && python3 manage.py check
```
