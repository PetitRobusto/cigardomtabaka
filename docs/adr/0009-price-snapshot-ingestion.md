# 0009 — 统一 Price Snapshot Ingestion

**状态：** 已采纳  
**日期：** 2026-06-14  
**决策者：** 板儿面

---

## 背景

Price Snapshot 原来有三条写入路径：

- Scrape：`run_scrape_sync()` 内联匹配、URL Cache、box_size 推断、Dedup、Delisting、IQR Anomaly。
- Push：`push_bulk()` 重复实现匹配、URL Cache、Dedup、Delisting、IQR Anomaly。
- 手工导入：`import_coh_bulk()` 自己匹配并直接创建 `PriceSnapshot`。

这些路径属于同一领域动作：把外部价格条目写入 Price Snapshot。分叉实现会让 Dedup 容差、URL Cache key、下架检测和异常重算规则逐渐不一致。

## 决策

新增 `price_tracker/ingestion.py` 作为统一写入模块，公开小接口：

```python
ingest_items(source, items, mode="scrape" | "push" | "import")
```

模块内部负责：

- URL/product 匹配缓存。
- 调用既有 matcher。
- Scrape/import 的唯一历史 box_size 推断。
- 价格和库存 Dedup。
- 创建 `PriceSnapshot`。
- Delisting。
- IQR Anomaly 重算。
- 统一统计结果。

## 不引入队列或异步任务

当前写入规模较小，SQLite 是主要约束。ADR-0008 已决定 Scrape 2 worker、Push 串行；引入 Celery/队列会增加部署复杂度，但不能解决 SQLite 并发写的核心限制。

## 不重写 scraper adapter

各站 scraper 的抓取逻辑和 Cloudflare/CDP 约束独立于入库规则。此次只收敛写入路径，保留 `ScrapedItem`、`BaseScraper.match_cigar()` 和各站 scraper，避免把爬取风险和入库重构绑在一起。

## 后果

**好处：**

- Scrape / Push / 手工导入共享同一套 Price Snapshot 写入规则。
- URL Cache、Dedup、Delisting、IQR Anomaly 规则集中在一个深模块里。
- 后续迁移 management import command 时只需把外部 row 转为 `ScrapedItem`。

**代价：**

- `ingest_items()` 需要保留少量 mode 差异，例如 Push 的 `box_size=None` 语义和 delisting guard。
- 迁移期间 management import command 仍可能存在旧写入路径，需要后续单独收敛。
