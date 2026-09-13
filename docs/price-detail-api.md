# 价格详情页展示契约

路由：`/prices/cigar/:id`。沿用 `.opendesign/price-detail-redesign/index.html`，不修改或重新生成设计 artifact。详情页的桌面双栏 Hero、商品图、五格信息条、聚合条、密集报价行与移动卡片使用项目 font-display / font-body / font-mono 和既有颜色。

## API

`GET /api/prices/snapshots/history/?cigar_id=:id&days=30|90|180|365|all`

- `all` 无起始日期限制，响应 `history_days=null`；正整数 days 表示滚动天数，非法值返回 400。
- 当前报价按 `(source_id, box_size, url)` 分组，取 `scraped_at DESC, id DESC` 的最新快照；不因时间范围而消失，不回填旧的有效价格。
- `points` 仅包含所选范围内的实际快照。没有每日插值或状态延续。
- `record_count` 是该报价全部历史记录数；`history_record_count` 是当前窗口内记录数。
- 当前报价和 points 均返回快照身份 `snapshot_id`、库存、下架、币种和 anomaly。原币字段 `price/current_price` 使用采集系统的实际售价，可能为折后售价；与 CNY 折算和去重所用价格一致。稀疏的 `box_price` 字段不作为替代价。
- 正式增加 `product_name`：从 raw_data 中取第一个非空字符串 `title_original → product_name → title → product`。这是来源款式名称，不是目录中文名。没有来源名则返回空字符串，不伪造。旧 `scraped_name` 保留为同值兼容别名；普通 snapshot serializer 共用该逻辑。
- `source_currency/source_exchange_rate` 是来源的当前参考配置，不是历史快照换算汇率。缺失时返回空值，页面明确说明。历史实际换算汇率、时间、采用的汇率记录 ID 尚未存储。

## 状态与统计

状态优先级为：明确下架 → 明确售罄 → 无有效价格/盒规或缺少库存状态 → 在售。售罄但缺少价格的报价仍显示售罄，同时附带缺价说明。

在售资格要求 `in_stock === true`、未下架、CNY 价格有限且大于零、盒规为正整数。后端标记排除统计的异常独立展示，并从均价、极值和图表中剔除。

首页 Card、详情聚合条和当前报价条形图共用前端资格与单支价计算函数。单支价保留两位小数；当前均价按来源 × 盒规 × 商品链接报价等权计算，计数标为有效报价而非唯一网站。Dashboard 卡片另统计拥有有效在售价的唯一网站数，保留原有卡片布局。

## 图表

- 当前在售单支价条形图从低到高排序，虚线是有效报价均价。
- 历史按 UTC 周一分周。每条报价取周内最后快照，先对同来源的报价平均，再对来源等权平均，降低抓取频次和同站多盒规的权重偏差。
- 在售只有一条主均线。售罄、下架各为低透明度虚线，可整体隐藏；缺价记录保留计数但不生成价格点。缺测周保持 null、断线。
- 历史取当时状态，不把当前售罄状态套用到全部历史。
- CNY 使用已存的 price_cny；原币按每条历史快照的 currency 分币种展示，绝不合并 USD/CHF 等币种。当前原币条形图仍遵守在售 CNY 资格，并额外要求有效原币价格。
- 没有时间加权或每日市场均价。采集系统按价格/状态变化去重，缺少记录不表示当天停卖。

## 异常契约与核验

```ts
anomaly?: {
  code: 'spike' | 'parse_error' | 'outlier' | 'invalid_box';
  label: string;
  reason: string;
  exclude_from_aggregate: boolean;
} | null;
```

当前后端已有 `is_anomalous`，源于同款同盒规的 IQR 检测。本次只将它映射为 `outlier`，不创建新的自动判断、不重算历史标记、不增加迁移。原因明确说明后端未保存当时阈值或偏离幅度，不能虚构“上涨 180%”。

异常报价显示独立 pill、原因、来源链接、抓取时间与快照 ID，用户先打开来源核验，再将记录 ID 交管理员处理。管理员已有只读入口 `manage.py review_anomalies`；修改标记或重匹配仍须依原有授权流程。页面没有新增直接写库或一键清除异常功能。

后续如新增 spike/parse_error/invalid_box，应在 ingestion 端保存原因、基线快照、阈值、检测时间及核验信息，并覆盖检测与撤销标记的成功/错误路径。当前前端只兼容契约，不能自行推断这些类型。

## 已知限制

- 空 URL 的同来源同盒规报价缺少稳定商品身份，会合并；不能仅依靠名称猜测不同商品。需要采集端提供稳定商品键后再扩展身份。
- 当前来源参考汇率可能与保存的 CNY 折算值不同；不能用于历史成本或会计入账。
- 历史均线来自实际抓取样本，来源构成变化可能改变均值，不代表同一固定市场篮子的涨跌。
- 全部历史返回一个商品的全部 points，没有分页；数据显著增长后需后端聚合或分页。
- 旧 `latest()` 端点的分组方式不在本次详情与 Dashboard 调用链内，保留既有实现。
