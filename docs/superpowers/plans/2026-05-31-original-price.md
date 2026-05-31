# original_price 全站折扣价支持 — 实施计划

> **For agentic workers:** 直接在当前 session 执行。全部改动的文件数和代码量可控。

**Goal:** 所有活跃爬虫输出 original_price，API 返回 original_price，前端展示划线价。

**Architecture:** 爬虫 → ScrapedItem.original_price → save_items() → PriceSnapshot.original_price → Serializer/View → React 组件

**Tech Stack:** Python (httpx/Playwright/BeautifulSoup), Django DRF, React/TypeScript/Tailwind

---

### Task 1: vipcigars.py — 解析双 price div

**Files:**
- Modify: `price_tracker/scrapers/vipcigars.py:_parse_article()`

- [ ] **Step 1: 修改 _parse_article 解析 discount**

改 `_parse_article()` 的价格提取逻辑：不只取第一个 EUR 匹配，而是遍历所有带价格信息的 div，区分 `line-through`（原价）和 `text-teal-500`（售价）：

```python
# 原代码（line 170-178）替换为：
def _parse_article(self, article, brand_name: str, base_url: str) -> Optional[ScrapedItem]:
    # ... 前面 title/link/button/box_size 解析不动 ...
    
    # 提取价格（支持折扣价）
    price_eur = None
    original_price_eur = None
    text_right_div = article.select_one('.text-right')
    if text_right_div:
        price_divs = text_right_div.find_all('div', recursive=False)
        for div in price_divs:
            text = div.get_text(strip=True)
            m = re.search(r"([\d',.]+)\s*EUR", text)
            if not m:
                continue
            price_str = m.group(1).replace("'", '').replace(',', '')
            try:
                val = float(price_str)
            except ValueError:
                continue
            classes = div.get('class', [])
            if 'line-through' in classes:
                original_price_eur = val
            elif 'text-teal-500' in classes:
                price_eur = val
            elif price_eur is None:
                # 先出现的普通价格 → sale price
                price_eur = val
    
    # 如果上面没提取到价格，回退到旧逻辑
    if price_eur is None:
        article_text = article.get_text(separator=' ', strip=True)
        price_match = re.search(r"([\d',.]+)\s*EUR", article_text)
        if price_match:
            price_str = price_match.group(1).replace("'", '').replace(',', '')
            try:
                price_eur = float(price_str)
            except ValueError:
                pass
    
    # ... 后面 name/in_stock/ScrapedItem 构造不动，加上 original_price ...
    
    return ScrapedItem(
        name=full_name,
        price=price_eur,
        original_price=original_price_eur,  # 新增
        currency='EUR',
        url=url,
        box_size=box_size,
        in_stock=in_stock,
        raw_data={...}
    )
```

- [ ] **Step 2: 运行爬虫验证**

```bash
cd /home/jason/moscow_cigar && python3 -c "
import django, os; os.environ['DJANGO_SETTINGS_MODULE']='cigardomtabaka_backend.settings'; django.setup()
from price_tracker.management.commands.run_scraper import Command
result = Command().handle(source='vipcigars')
print(result)
"
```

检查输出中 original_price 是否有非 None 的值。

- [ ] **Step 3: 验证 DB 数据**

```bash
cd /home/jason/moscow_cigar && python3 -c "
import django, os; os.environ['DJANGO_SETTINGS_MODULE']='cigardomtabaka_backend.settings'; django.setup()
from price_tracker.models import PriceSnapshot
snaps = PriceSnapshot.objects.filter(source__slug='vipcigars', original_price__isnull=False).order_by('-scraped_at')[:5]
for s in snaps:
    print(f'{s.cigar.english_name}: price={s.price} original_price={s.original_price}')
"
```

- [ ] **Step 4: Commit**

```bash
git add price_tracker/scrapers/vipcigars.py
git commit -m "feat: vipcigars scraper detects original_price from line-through div"
```

---

### Task 2: lcdh_nyon.py — WooCommerce del/ins 解析

**Files:**
- Modify: `price_tracker/scrapers/lcdh_nyon.py:_scrape_brand_async()`

- [ ] **Step 1: 改 JS evaluate 脚本提取 del/ins**

修改 `_scrape_brand_async` 中的 `page.evaluate()` JS 代码，在返回的 JSON 对象里加 `originalPrice` 字段：

```javascript
// 在 products.push({...}) 之前加：
const priceEl = card.querySelector('.price');
const delEl = priceEl?.querySelector('del .woocommerce-Price-amount');
const insEl = priceEl?.querySelector('ins .woocommerce-Price-amount');
const normalEl = priceEl?.querySelector('.woocommerce-Price-amount');
let originalPrice = '';
if (delEl && insEl) {
    originalPrice = delEl.textContent.trim();
    // price 本身保持为 insEl 的值（这里用正常提取逻辑）
}

products.push({
    title: ...,
    price: delEl && insEl ? insEl?.textContent?.trim() : (normalEl?.textContent?.trim() || priceEl?.textContent?.trim()),
    originalPrice: originalPrice,
    url: ...,
    badge: ...,
    inStock: ...
});
```

- [ ] **Step 2: 改 _parse_product 传入 original_price**

在 `_parse_product` 中解析 `raw.get('originalPrice', '')`，提取数字：

```python
# 在 _parse_product 解析完 price_chf 后：
orig_price_chf = None
orig_price_str = raw.get('originalPrice', '')
if orig_price_str:
    m = re.search(r'[\d,]+\\.?\\d*', orig_price_str.replace("'", ''))
    if m:
        orig_price_chf = float(m.group().replace(',', ''))
```

ScrapedItem 构造加 `original_price=orig_price_chf`

- [ ] **Step 3: 运行爬虫验证（如果 CF 能过）**

```bash
cd /home/jason/moscow_cigar && python3 -c "
import django, os; os.environ['DJANGO_SETTINGS_MODULE']='cigardomtabaka_backend.settings'; django.setup()
from price_tracker.scraper import run_scrape_sync
result = run_scrape_sync('lcdh_nyon')
print(result)
"
```

- [ ] **Step 4: Commit**

```bash
git add price_tracker/scrapers/lcdh_nyon.py
git commit -m "feat: lcdh_nyon scraper detects original_price from WooCommerce del/ins"
```

---

### Task 3: coh_china.py + lcdh_dl.py — 预留 original_price=None

**Files:**
- Modify: `price_tracker/scrapers/coh_china.py`
- Modify: `price_tracker/scrapers/lcdh_dl.py`

- [ ] **Step 1: coh_china — 所有 ScrapedItem() 调用加 original_price=None**

两处构造 ScrapedItem：`_parse_structured` (line 162) 和 `_parse_text_lines` (line 248)，都加：
```python
original_price=None,
```

- [ ] **Step 2: lcdh_dl — ScrapedItem() 加 original_price=None**

`_parse` 方法 (line 145)，加：
```python
original_price=None,
```

- [ ] **Step 3: Commit**

```bash
git add price_tracker/scrapers/coh_china.py price_tracker/scrapers/lcdh_dl.py
git commit -m "feat: coh_china and lcdh_dl scrape with original_price=None (no discount detected)"
```

---

### Task 4: 后端 API — Serializer + View 补 original_price

**Files:**
- Modify: `price_tracker/serializers.py`
- Modify: `price_tracker/views.py`

- [ ] **Step 1: PriceSnapshotSerializer 加字段**

```python
# serializers.py, Meta.fields 加:
'original_price',
```

- [ ] **Step 2: AggregatedSourceEntry 加字段**

```python
original_price = serializers.FloatField(allow_null=True)
```

- [ ] **Step 3: list_aggregated 的 sources[] 补 original_price**

在 `views.py:298-309` 的 `entry['sources'].append({...})` 里加：
```python
'original_price': snap.original_price,
```

- [ ] **Step 4: history endpoint 的 variant.points[] 补 original_price**

在 `views.py:174-180` 的 `variants[key]['points'].append({...})` 里加：
```python
'original_price': snap.original_price,
```

- [ ] **Step 5: 验证 API 返回**

```bash
curl -s -H "Authorization: Bearer $(python3 -c "
import django,os;os.environ['DJANGO_SETTINGS_MODULE']='cigardomtabaka_backend.settings';django.setup()
from django.contrib.auth import get_user_model
User=get_user_model()
# ... skip
")" http://localhost:8000/api/prices/list_aggregated/?brand=Cohiba | python3 -m json.tool | head -80
```

或者直接用浏览器访问 `/api/prices/list_aggregated/`，检查 sources 中是否有 `original_price` 字段。

- [ ] **Step 6: Commit**

```bash
git add price_tracker/serializers.py price_tracker/views.py
git commit -m "feat: API returns original_price in serializers + aggregated/history endpoints"
```

---

### Task 5: 前端 — types.ts + PriceCard + VariantCard

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/components/dashboard/PriceCard.tsx`
- Modify: `frontend/src/components/detail/VariantCard.tsx`

- [ ] **Step 1: types.ts 加字段**

`CigarListItem.sources[]` 对象里加：
```typescript
original_price: number | null;
```

`HistoryPoint` 加：
```typescript
original_price: number | null;
```

`AggregatedSourceEntry` 加：
```typescript
original_price: number | null;
```

- [ ] **Step 2: PriceCard 加划线原价**

在 `PriceCard.tsx` 的均价行下方（大约 line 121），加一个来源原价提示：

```tsx
{/* 有来源是折扣价时显示 */}
{cigar.sources.some(s => s.original_price) && (
  <div className="text-[0.65rem] text-muted/60 mt-1">
    <span className="line-through">
      {/* 取第一个有 original_price 的来源 */}
      {(() => {
        const s = cigar.sources.find(s => s.original_price);
        if (!s) return null;
        const cny = s.original_price * (s.price_cny && s.price ? s.price_cny / s.price : 7.8);
        return `原价 ¥${Math.round(cny).toLocaleString()}`;
      })()}
    </span>
  </div>
)}
```

简化版：只显示划线价文字：

```tsx
{cigar.sources.some(s => s.original_price) && (
  <div className="mt-1 flex items-center gap-1.5 text-[0.65rem] text-muted/50">
    <span className="line-through">原价</span>
    <span className="px-1.5 py-0.5 rounded bg-amber-50 text-amber-700 font-medium text-[0.6rem]">
      特价
    </span>
  </div>
)}
```

- [ ] **Step 3: VariantCard 加划线原价**

在 `VariantCard.tsx` 的原货币价格行（line 103-109），改为显示原价+现价：

```tsx
{/* Original currency price row — 支持折扣价 */}
<div className="text-xs text-muted flex items-center gap-2">
  {variant.original_price != null ? (
    <>
      <span className="line-through text-muted/50">
        {formatPrice(variant.original_price, variant.currency)}
      </span>
      <span className="text-amber-600 font-semibold">
        {formatPrice(latest.price, variant.currency)}
      </span>
    </>
  ) : (
    <span className="font-mono font-semibold text-muted">
      {formatPrice(latest.price, variant.currency)}
    </span>
  )}
</div>
```

- [ ] **Step 4: 构建前端 + 重启**

```bash
cd /home/jason/moscow_cigar/frontend && npm run build
# 复制构建产物
cd .. && python3 manage.py collectstatic --noinput
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types.ts frontend/src/components/dashboard/PriceCard.tsx frontend/src/components/detail/VariantCard.tsx
git commit -m "feat: frontend displays original_price strikethrough on PriceCard and VariantCard"
```

---

### Task 6: 集成验证

- [ ] **Step 1: 全站验证 — 逐个跑爬虫**

```bash
cd /home/jason/moscow_cigar
python3 manage.py run_scraper --source=vipcigars
python3 manage.py run_scraper --source=lcdh_nyon
python3 manage.py run_scraper --source=coh_china
python3 manage.py run_scraper --source=lcdh_dl
python3 manage.py run_scraper --source=lcdh_brussels
```

- [ ] **Step 2: 验证 DB 数据完整性**

```bash
python3 -c "
import django,os;os.environ['DJANGO_SETTINGS_MODULE']='cigardomtabaka_backend.settings';django.setup()
from price_tracker.models import PriceSnapshot
from django.db.models import Count, Q
# 每个来源的 original_price 覆盖率
for src in ['vipcigars','lcdh_nyon','lcdh_dl','coh_china','lcdh_brussels']:
    total = PriceSnapshot.objects.filter(source__slug=src).count()
    with_op = PriceSnapshot.objects.filter(source__slug=src, original_price__isnull=False).count()
    print(f'{src}: {with_op}/{total} have original_price')
"
```

- [ ] **Step 3: Django check**

```bash
python3 manage.py check
```

- [ ] **Step 4: Final commit**

```bash
git add -A && git commit -m "chore: full-site original_price integration verified"
```
