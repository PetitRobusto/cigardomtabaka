# CigarDomTabaka — 领域术语表

> 本文档定义项目的核心领域语言。写代码、讨论需求、写文档时统一用这些术语。
> 不含实现细节，不是 spec，只是词典。

---

## 产品

| 术语 | 定义 |
|------|------|
| **Cigar** | 一支古巴雪茄。属性包含品牌、品型、环径、长度、盒装支数。 |
| **Brand** | 雪茄品牌，共 27 个（Cohiba、Montecristo、Partagás 等）。 |
| **Vitola** | 品型，即雪茄的尺寸规格（如 Robusto、Corona、Piramides）。 |
| **Box Size** | 盒装支数。一支雪茄可能有多种包装（25 支盒、10 支盒、3 支铝管）。 |
| **Ring Gauge** | 环径，雪茄直径。 |

## 价格

| 术语 | 定义 |
|------|------|
| **Price Source** | 外部价格数据来源。一个网站 = 一个 source（如 coh_china、lcdh_nyon）。 |
| **Price Snapshot** | 某个时间点、某个 source、某支雪茄的价格记录。包含原币价和换算后的人民币价。 |
| **price_cny** | 统一换算后的人民币价格。所有 source 比较和异常检测都基于此字段。 |
| **price_ref** | 内部批发参考价，存储在 CigarPrice 模型中。用户说"X 款 Y 元"默认指此价。 |
| **PRICE_OVERRIDE_RUB** | 卢布成本价覆盖。用户明确说"成本"或"卢布"时才改此值。 |
| **Per Stick** | 单支价 = price_cny ÷ box_size。用于前端详情页展示。 |
| **Exchange Rate** | 外币 → CNY 汇率。查询优先级：DB → Fallback 表 → 默认值。 |

## 数据管线

| 术语 | 定义 |
|------|------|
| **Scrape** | 从外部网站抓取价格数据，存入本地 PriceSnapshot。只爬不推。 |
| **Push** | 将本地 PriceSnapshot 通过 HTTP API 推送到生产服务器。 |
| **Ingestion** | 标准化外部价格条目并写入 Price Snapshot 的统一管线。Scrape、Push、手工导入都应通过它执行匹配、去重、下架检测和异常重算。 |
| **Dedup** | 去重。价格未变（容差 0.01）、库存未变 → 不建新快照。 |
| **Delisting** | 下架检测。上次爬取在售、本次不在 → 创建 in_stock=False 的快照。 |
| **IQR Anomaly** | 四分位距异常检测。对同一支雪茄同一盒装的所有快照做统计，标记极端离群值。 |
| **After Scrape** | push 阶段只推爬取成功的源。通过 `.scrape_status.json` 过滤失败源。 |
| **URL Cache** | (URL, product_name) → cigar_id 的映射缓存。避免对同 URL 重复匹配。 |

## 库存

| 术语 | 定义 |
|------|------|
| **Purchase Order** | 采购单。从供应商进货的订单。 |
| **Purchase Batch** | 采购批次。一次采购的实际入库记录，关联到 PurchaseOrder。 |
| **Sales Order** | 销售单。卖给客户的订单。 |
| **Supplier** | 供应商，供货方。 |
| **Customer** | 客户，买方。 |
| **Stock** | 库存。通过 PurchaseBatch（入库）和 SalesOrder（出库）计算。 |

## Privnote

| 术语 | 定义 |
|------|------|
| **Privnote** | 一次性加密链接文档。客户通过 token 链接查看，阅后即焚。 |
| **Note Type** | 文档类型（四选一）：inventory（库存展示）、payment（收款）、message（消息）、quote（批发报价）。 |
| **Payment Method** | 预配置的收款方式（银行卡、微信、支付宝）。全局共用，含备注（remark）。 |
| **Quote** | 批发报价单。实时从 CigarPrice 构建，价格/库存变动自动反映。 |
| **Burn After Read** | 阅后即焚。查看次数达到 max_views 后自动销毁。 |

## 基础设施

| 术语 | 定义 |
|------|------|
| **CDP Browser** | Chrome DevTools Protocol 浏览器。Chrome 以 `--remote-debugging-port=9222` 常驻，多个爬虫通过 `connect_over_cdp()` 复用。 |
| **EPIPE** | Broken pipe 错误。磁盘不足（< 2G）时 Chromium 无法写临时文件，Playwright 向已崩溃的进程发命令导致。 |
| **Stealth** | playwright-stealth 插件。修改浏览器指纹绕过 Cloudflare 检测。Nyon 专用，CDP 爬虫不用。 |
| **Scrape Status** | `.scrape_status.json` 文件。记录各 source 本次爬取成功/失败，push 阶段据此过滤。 |
