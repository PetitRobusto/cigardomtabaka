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
| **Purchase Order** | 采购单。从供应商进货的订单；可以先作为待确认草稿存在，确认后才形成正式入库事实。 |
| **Purchase Receiving** | 采购入库。确认采购货品实际到货，并形成 Purchase Batch 的业务动作。 |
| **Purchase Batch** | 采购批次。一次采购的实际入库记录，关联到 PurchaseOrder。 |
| **Sales Order** | 销售单。卖给客户的订单。 |
| **Sales Order Item** | 销售明细。客户视角的一行商品，表示某款雪茄、数量和销售单价。 |
| **Order Event** | 订单事件。围绕销售单发生的一次操作或备注记录，保留时间、操作人和上下文。 |
| **Fulfillment Type** | 履约类型。销售明细如何履约，分为现货销售和预售。 |
| **In-stock Sale** | 现货销售。只销售 Available Stock 中已有的库存，不允许造成负库存。 |
| **Preorder** | 预售。客户购买尚未入库或尚不可分配的商品，不占用 Purchase Batch。 |
| **Stock Reservation** | 库存预留。待付款销售单占用的库存，尚未从在手库存中正式出库。 |
| **Stock Movement** | 库存流水。一次库存数量变化的事实记录，包括入库、预留、出库、释放预留和库存修正。 |
| **Stock Allocation** | 库存分配。销售明细与采购批次之间的对应关系，用于记录某个销售明细占用或消耗了哪些批次。 |
| **Stock Adjustment** | 库存修正。用于盘点、损耗、临时补录等非标准采购/销售原因造成的库存变化；不等同于正式采购入库。 |
| **Supplier** | 供应商，预先登记的供货方。正式采购入库只能引用已有 Supplier。 |
| **Dealer** | 经销商。业务口语中常指供货方；结构化进货记录里不作为独立概念，统一归口为 Supplier。 |
| **Customer** | 客户，买方。 |
| **Operator** | 操作人。创建或确认采购、销售、库存修正等业务动作的人。 |
| **Agent** | 代理执行者。代替 Operator 调用系统命令的自动化助手，不是业务责任人。 |
| **Agent Command** | Agent 可调用的命令式业务接口。只能表达业务动作，不开放模型通用 CRUD。 |
| **Idempotency Key** | 幂等键。Agent 写命令必须携带的业务动作唯一键；同一动作重试复用同一个 key。 |
| **Idempotency Record** | 幂等记录。保存 Agent 写命令第一次请求摘要和响应，用于重试重放和冲突检测。 |
| **On-hand Stock** | 在手库存。已经入库、尚未正式出库或修正扣减的库存数量。 |
| **Reserved Stock** | 预留库存。已被待付款销售单占用、不能再卖给其他客户的库存数量。 |
| **Available Stock** | 可售库存。可继续销售的库存数量，等于 On-hand Stock 减去 Reserved Stock。 |
| **Stock** | 库存。库存讨论中的总称；需要精确表达时使用 On-hand Stock、Reserved Stock 或 Available Stock。 |

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
