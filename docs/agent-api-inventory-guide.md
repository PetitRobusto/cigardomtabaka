# Agent API 库存操作指南

本文写给会代替真人操作订单和库存的 agent。Agent 只能调用命令式业务接口，不能直接 CRUD Django 模型或修改数据库字段。

## 当前边界

已可用：

- 搜索雪茄和查询库存。
- 创建销售单，并为现货明细 FIFO 预留库存。
- 确认付款，并把预留库存转为正式出库。
- 取消未付款销售单，并释放预留库存。
- 做库存修正。
- 查询基础业务报表。

尚未暴露为 HTTP Agent API：

- 正式创建 Purchase Order。
- 正式确认 Purchase Receiving。
- 采购入库单的供应商、币种、汇率、总额和采购事件结构化记录。

因此，经销商进货这种正式入库场景，不能长期用 `adjust_stock` 冒充采购入库。`adjust_stock` 只能作为临时补库存或盘点修正。

## 认证和责任人

接口沿用 staff 权限。Agent 请求需要满足其中一种：

- 已登录 staff session。
- 请求头带 staff 用户的 `X-Telegram-ID`。

所有写命令仍必须显式传 `operator_id`。`operator_id` 是真实业务责任人，`agent` 是执行命令的自动化工具。

```json
{
  "idempotency_key": "run_20260615_001:create_sales_order:step_03",
  "operator_id": 1,
  "agent": {
    "agent_name": "codex",
    "agent_run_id": "run_20260615_001",
    "agent_request_id": "req_abc123"
  }
}
```

## 幂等规则

所有写命令必须带 `idempotency_key`。

推荐格式：

```text
<agent_run_id>:<command_name>:<local_step_id>
```

规则：

- 同 key + 同请求体：返回第一次结果，不重复预留、扣库存或创建订单。
- 同 key + 不同请求体：返回 `409`。
- 第一次业务失败也会记录并重放，避免 agent 重试时因为外部库存变化得到不同结果。

同一个真实业务动作重试时复用同一个 key；新业务动作必须换新 key。

## 查询接口

搜索雪茄和库存批次：

```http
GET /api/agent/search/?q=cohiba&limit=20
```

查询库存汇总：

```http
GET /api/agent/stock/?q=partagas&limit=50
```

返回中的关键字段：

- `cigar_id`：后续写命令使用的雪茄 ID。
- `available_stock`：当前可售库存。
- `batches`：仍有库存的采购批次，按 FIFO 使用。

## 创建销售单

```http
POST /api/agent/orders/create/
Content-Type: application/json
```

```json
{
  "idempotency_key": "run_001:create_sales_order:step_01",
  "operator_id": 1,
  "agent": {
    "agent_name": "codex",
    "agent_run_id": "run_001",
    "agent_request_id": "req_001"
  },
  "customer_name": "张三",
  "note": "客户等付款",
  "items": [
    {
      "cigar_id": 12,
      "quantity": 5,
      "unit_price": 260,
      "fulfillment_type": "in_stock"
    },
    {
      "cigar_id": 33,
      "quantity": 10,
      "unit_price": 180,
      "fulfillment_type": "preorder"
    }
  ]
}
```

语义：

- `in_stock` 会检查可售库存，不允许负库存。
- `in_stock` 会按 FIFO 创建 `StockAllocation`，一行销售明细可跨多个批次。
- 创建后写 `reserve` 类型 `StockMovement`，订单状态为 `pending_payment`。
- `preorder` 不占用 `PurchaseBatch`，不创建 `StockAllocation`。

## 确认付款

```http
POST /api/agent/orders/confirm-payment/
Content-Type: application/json
```

```json
{
  "idempotency_key": "run_001:confirm_payment:step_02",
  "operator_id": 1,
  "agent": {
    "agent_name": "codex",
    "agent_run_id": "run_001",
    "agent_request_id": "req_002"
  },
  "sales_order_id": 1001,
  "note": "已收款"
}
```

语义：

- 已预留的 allocation 从 `reserved` 变为 `fulfilled`。
- 写 `ship` 类型 `StockMovement`。
- 销售单状态变为 `paid`。

## 取消未付款销售单

```http
POST /api/agent/orders/cancel/
Content-Type: application/json
```

```json
{
  "idempotency_key": "run_001:cancel_sales_order:step_03",
  "operator_id": 1,
  "agent": {
    "agent_name": "codex",
    "agent_run_id": "run_001",
    "agent_request_id": "req_003"
  },
  "sales_order_id": 1001,
  "note": "客户取消"
}
```

语义：

- 只支持第一版自动取消未付款订单。
- 已预留库存释放回批次。
- 写 `release_reservation` 类型 `StockMovement`。
- 已付款订单不要用这个接口自动回滚，需要人工确认退货、退款和重新入库方案。

## 库存修正

```http
POST /api/agent/stock/adjust/
Content-Type: application/json
```

增加库存示例：

```json
{
  "idempotency_key": "run_001:adjust_stock:step_01",
  "operator_id": 1,
  "agent": {
    "agent_name": "codex",
    "agent_run_id": "run_001",
    "agent_request_id": "req_004"
  },
  "cigar_id": 12,
  "quantity_delta": 25,
  "unit_cost_cny": 180,
  "reason": "盘点补录：Cohiba Robustos 25 支，成本 180 CNY/支"
}
```

减少库存示例：

```json
{
  "idempotency_key": "run_001:adjust_stock:step_02",
  "operator_id": 1,
  "agent": {
    "agent_name": "codex",
    "agent_run_id": "run_001",
    "agent_request_id": "req_005"
  },
  "cigar_id": 12,
  "quantity_delta": -2,
  "batch_id": 7,
  "reason": "盘点损耗 2 支"
}
```

语义：

- 正向修正如果不传 `batch_id`，系统会创建“库存修正”供应商和采购批次。
- 负向修正不允许把可用库存扣成负数。
- `reason` 必须写清楚原因、数量、成本依据和上下文。
- 这不是正式采购入库流程。

## 基础报表

```http
GET /api/agent/reports/basic/
```

返回订单数量、已付款销售额、预售明细数量、可用库存数量、库存流水计数和最近订单事件。

## 经销商进货：怎么权衡

用户说“我从经销商进了一批货，帮我做入库单”时，先判断用户要的是正式入库单，还是临时让库存可售。

正式入库单需要长期追踪：

- 经销商或供应商是谁。
- 每一行货品、数量、盒规、成本。
- 总金额、币种、汇率。
- 后续利润能追溯到这次进货。
- 有采购单号或入库单号。

当前第一版 Agent API 还没有正式 `create_purchase_order` / `receive_purchase_order` HTTP 接口。遇到正式入库需求时，应先明确告诉用户：当前可以临时补库存，但正式入库单需要先补采购入库命令接口。

可对用户这样说：

```text
当前 Agent API 还没有正式采购入库单接口。
我可以先用库存修正把这批货补进可售库存，并在 reason 里标记“经销商入库临时补录，待补正式采购单”；
但这样不会结构化记录供应商、采购总额、币种、汇率和采购单号。
如果你要正式入库单，我们应该先实现 purchase order / receiving 的 Agent API。
你要先临时补库存，还是先做正式采购入库接口？
```

如果用户明确说“先能卖就行”，才使用 `adjust_stock`。每款雪茄单独调用一次，`reason` 必须包含经销商、到货日期、数量、成本和“临时补录，待补正式采购单”。

示例：

```json
{
  "idempotency_key": "run_20260615_001:adjust_stock:dealer_lot_01_line_01",
  "operator_id": 1,
  "agent": {
    "agent_name": "codex",
    "agent_run_id": "run_20260615_001",
    "agent_request_id": "dealer_lot_01_line_01"
  },
  "cigar_id": 12,
  "quantity_delta": 25,
  "unit_cost_cny": 180,
  "reason": "临时入库补录：经销商 Ivan，2026-06-15 到货 Cohiba Robustos 25 支，成本 180 CNY/支；待补正式采购单"
}
```

正式方案后续应补两个命令：

- `POST /api/agent/purchase-orders/create/`
- `POST /api/agent/purchase-orders/receive/`

设计这两个命令前，需要先确认 Supplier/Dealer 术语、是否一阶段创建并入库、是否支持部分到货、成本币种和汇率、幂等粒度以及是否新增 Purchase Event。
