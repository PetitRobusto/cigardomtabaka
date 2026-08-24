# 价格存储规范 — 存原始标价货币，禁止中转换算

## 原则

**所有价格以网站实际标价货币（USD/EUR/CHF/CNY）存储，禁止在爬取和存储环节做任何货币换算。**

换算全部在前端/展示层完成。

## 禁止

- ❌ Nyon：网站上 EUR 价，爬虫换算成 CHF 再存
- ❌ 任何去重逻辑比较 `price_cny`（CNY 受汇率影响）
- ❌ 用 `ExchangeRate.get_rate()` 在爬取环节做乘除

## 许可

- ✅ 网站标什么货币就存什么货币
- ✅ 去重只看 `item.price`（原始货币），不看 `price_cny`
- ✅ CNY 换算在 `convert_to_cny()` → `PriceSnapshot.price_cny` 字段（仅用于前端展示）
- ✅ 同次 scrape 内存去重：`(cigar_id, box_size, price)` 只入库一次

## 涉及的爬虫

| 爬虫 | 网站货币 | 之前 | 修正后 |
|---|---|---|---|
| coh_china | USD | ✅ 直存 | ✅ |
| coh（已停） | USD | ✅ 直存 | — |
| cigarone | USD | ✅ 直存 | ✅ |
| ihavanas | — | — | — |
| egm | — | — | — |
| lcdh_brussels | EUR | ✅ 直存 | ✅ |
| lcdh_dl | CHF | ✅ 直存 | ✅ |
| lcdh_nyon | **EUR** | ❌ EUR→CHF 换算 | ✅ 直存 EUR |
| hyhpuro | CNY | ✅ 直存 | ✅ |
| vipcigars | EUR | ✅ 直存 | ✅ |

## 去重规则（`ingestion.py` `_should_create_snapshot`）

```
同一 source + cigar + box_size + url：
  价格 (原始货币) 没变 → 不创建
  价格 (原始货币) 变了 → 创建新 snapshot
  库存状态变了 → 创建新 snapshot
```

`price_cny` 不参与去重判断。

## 生效日期

2026-06-19 — 修复 Nyon EUR→CHF 问题。
