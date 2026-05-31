# Design: 全站 original_price 折扣价支持

## 目标

所有活跃爬虫统一适配 `original_price`（划线原价），后端 API 补字段，前端展示划线价。

## 架构

```
ScrapedItem.original_price (爬虫写)
    ↓
save_items() → PriceSnapshot.original_price (DB)
    ↓
Serializer/View (API 返回)
    ↓
React 组件 (前端展示)
```

## 爬虫端改造

| 爬虫 | 现状 | 改动 |
|------|------|------|
| vipcigars.py | 只取单一价格 | 解析双 price div：`line-through`→original, `text-teal-500`→sale |
| coh_china.py | 只取单一价格 | 预留 original_price=None（COH暂无折扣） |
| lcdh_nyon.py | WooCommerce `.price` 文本 | 改 JS evaluate 脚本提取 `<del>` + `<ins>` |
| lcdh_dl.py | Odoo 单一价格 | 预留 original_price=None |
| lcdh_brussels.py | ✅ 已完成 | 不动 |

### vipcigars 解析逻辑

```
for article in soup.find_all('article'):
    price_divs = article.select('.text-right > div')
    
    for div in price_divs:
        text = div.get_text().replace("'", '').replace(',', '')
        m = re.search(r'([\d.]+)\s*EUR', text)
        if not m: continue
        
        if 'line-through' in div.get('class', []):
            original_price = float(m.group(1))
        elif 'text-teal-500' in div.get('class', []):
            sale_price = float(m.group(1))
    
    # 无折扣 → price=sale_price, original_price=None
    # 有折扣 → price=sale_price, original_price=original_price
```

### lcdh_nyon 解析逻辑

```
改 JS evaluate: 不只取 .price 的 text，而是取 innerHTML 解析：

const priceEl = card.querySelector('.price');
const delEl = priceEl?.querySelector('del .woocommerce-Price-amount');
const insEl = priceEl?.querySelector('ins .woocommerce-Price-amount');
const normalEl = priceEl?.querySelector('.woocommerce-Price-amount');

return {
    price_text: delEl ? insEl?.textContent : normalEl?.textContent,
    original_price_text: delEl?.textContent || ''
};
```

## 后端 API 改造

### PriceSnapshotSerializer
加 `'original_price'` 到 fields

### AggregatedSourceEntry
加 `original_price = serializers.FloatField(allow_null=True)`

### list_aggregated 的 sources[]
每个 source entry 加 `original_price = snap.original_price`

### history 的 variant.points[]
每个 point 加 `original_price`

## 前端改造

### types.ts
- `CigarListItem.sources[]`: 加 `original_price: number | null`
- `Variant.points[]` (HistoryPoint): 加 `original_price: number | null`
- `AggregatedSourceEntry`: 加 `original_price: number | null`

### PriceCard.tsx
- 在 source 信息中检测 original_price
- 有 original_price → 显示 `~~¥原价~~ ¥现价`

### VariantCard.tsx
- 在价格行检测 original_price
- 有 original_price → 显示 `原价 CHF 944 → 售价 CHF 802.40`

## 测试验证

1. 逐个运行爬虫：`run_scrape_sync('vipcigars')` 等
2. 检查 DB 中 PriceSnapshot.original_price 有无值
3. API 返回验证：`/api/prices/list_aggregated/`
4. 前端视觉验证：VIP Cigars 有折扣的产品显示划线价
