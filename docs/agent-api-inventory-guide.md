# Agent API 业务操作指南

本文用于约束代替真人操作系统的 Agent。Agent 只能调用业务命令，不能直接修改 Django 模型、库存余额或账户余额。

## 当前能力

销售：

- 创建和修改销售草稿。
- 确认订单并预留库存。
- 取消未出库订单并释放预留。
- 独立执行出库、收款、退款和实际人肉成本入账。
- 按客户、单号、履约状态和收款状态查询销售单。
- 查询基于实际出库、收退款和贡献利润的基础报表。

采购与库存：

- 查询供应商。
- 创建、修改和取消采购草稿。
- 整单确认入库。
- 查询库存与批次。
- 执行有原因记录的库存修正。

## 认证与审计字段

接口要求 staff 权限。调用方使用已登录的 staff session，或提供 staff 用户的 X-Telegram-ID 请求头。

每个销售写命令必须提供：

- operator_id：实际承担业务责任的人。
- agent.agent_name：执行命令的 Agent。
- idempotency_key：本次业务动作的唯一键。
- business_date：ISO 日期，例如 2026-08-16。

示例公共字段：

    {
      "idempotency_key": "run_001:create_sales_order_draft:step_01",
      "operator_id": 1,
      "business_date": "2026-08-16",
      "agent": {
        "agent_name": "codex",
        "agent_run_id": "run_001",
        "agent_request_id": "req_001"
      }
    }

相同 key 和相同请求体返回首次结果，不重复创建订单、预留、出库或记账。相同 key 对应不同请求体返回 409。业务失败同样会被记录并稳定重放。

## 销售单查询

列表：

    GET /api/agent/orders/?q=张三&fulfillment_status=confirmed&payment_status=unpaid

详情：

    GET /api/agent/orders/1001/

q 支持客户名、数字 ID 和 SO-000001 格式的订单号。返回结果包含双状态、明细、批次分配、出库、收款、退款、人肉成本和当前可执行动作。

## 创建销售草稿

    POST /api/agent/orders/create/

    {
      "idempotency_key": "run_001:create_sales_order_draft:step_01",
      "operator_id": 1,
      "business_date": "2026-08-16",
      "agent": {
        "agent_name": "codex",
        "agent_run_id": "run_001",
        "agent_request_id": "req_001"
      },
      "customer_name": "张三",
      "transport_payer": "customer",
      "customer_transport_fee_cny": "50.00",
      "items": [
        {
          "cigar_id": 12,
          "sale_unit": "box",
          "sale_quantity": 1,
          "box_size": 25,
          "unit_price": "6500.00",
          "fulfillment_type": "in_stock"
        }
      ],
      "note": "待客户确认"
    }

创建只生成可编辑草稿，不检查或预留库存。公司承担人肉费时 transport_payer 使用 company，且 customer_transport_fee_cny 必须为 0。

## 修改销售草稿

    POST /api/agent/orders/update/

请求体与创建接口相同，并增加 sales_order_id。更新采用整单快照替换，只允许修改未锁定、未收款的草稿。商品、客户、价格或人肉费任一变化时，都应提交完整的新快照。

## 确认并预留库存

    POST /api/agent/orders/confirm/

    {
      "idempotency_key": "run_001:confirm_sales_order:step_02",
      "operator_id": 1,
      "business_date": "2026-08-16",
      "agent": {
        "agent_name": "codex",
        "agent_run_id": "run_001",
        "agent_request_id": "req_002"
      },
      "sales_order_id": 1001,
      "note": "客户确认"
    }

确认后订单进入 confirmed，现货按 FIFO 预留并写 reserve 流水。预售明细不占用现货。库存不足时整笔确认失败，草稿保持可编辑。

## 取消订单

    POST /api/agent/orders/cancel/

只允许取消已确认但尚未出库的订单。系统释放全部预留并写 release_reservation 流水。若订单已经预收，取消后收款状态变为 refund_pending，必须再执行退款命令。

## 出库

    POST /api/agent/orders/ship/

    {
      "idempotency_key": "run_001:ship_sales_order:step_03",
      "operator_id": 1,
      "business_date": "2026-08-16",
      "agent": {
        "agent_name": "codex",
        "agent_run_id": "run_001",
        "agent_request_id": "req_003"
      },
      "sales_order_id": 1001,
      "note": "已交付客户"
    }

出库将预留转为 fulfilled，减少物理库存，确认 FIFO 销售成本并写账。出库与收款互相独立，可以先出库后收款，也可以先收款后出库。

## 收款

    POST /api/agent/orders/receive/

    {
      "idempotency_key": "run_001:receive_sales_order_payment:step_04",
      "operator_id": 1,
      "business_date": "2026-08-16",
      "agent": {
        "agent_name": "codex",
        "agent_run_id": "run_001",
        "agent_request_id": "req_004"
      },
      "sales_order_id": 1001,
      "amount_cny": "6550.00",
      "fund_account_id": 3
    }

每张销售单只允许一次人民币整单收款。金额必须等于 amount_due_cny，账户必须是启用的人民币账户。

旧接口 /api/agent/orders/confirm-payment/ 已删除，不得继续调用。

## 退款

    POST /api/agent/orders/refund/

退款只用于已取消且处于 refund_pending 的预收订单。系统按原收款金额和原人民币账户执行整笔退款。

## 记录实际人肉成本

    POST /api/agent/orders/transport-cost/

    {
      "idempotency_key": "run_001:record_sales_transport_cost:step_05",
      "operator_id": 1,
      "business_date": "2026-08-16",
      "agent": {
        "agent_name": "codex",
        "agent_run_id": "run_001",
        "agent_request_id": "req_005"
      },
      "sales_order_id": 1001,
      "actual_cost_cny": "120.00",
      "fund_account_id": 3,
      "note": "莫斯科配送"
    }

实际人肉成本只在出库后记录一次，从指定人民币账户支付，并扣减订单贡献利润。客户承担的人肉收费与公司实际支付的人肉成本是两个独立事实。

## 基础报表

    GET /api/agent/reports/basic/

报表返回：

- fulfillment 与 payment 两组订单状态数量。
- 已出库应收总额、FIFO 成本和贡献利润。
- 收款、退款和净收款金额。
- 可售库存数量与库存流水计数。
- 最近 Agent 命令和订单事件。

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

## 经销商进货：怎么权衡

用户说“我从经销商进了一批货，帮我做入库单”时，先判断用户要的是正式入库单，还是临时让库存可售。

正式入库单需要长期追踪：

- 经销商或供应商是谁。
- 每一行货品、数量、盒规、成本。
- 总金额、币种、汇率。
- 后续利润能追溯到这次进货。
- 有采购单号或入库单号。

正式采购先维护草稿，再整单确认入库：

0. `GET /api/agent/suppliers/?q=habanos`
   - 查询已有 `Supplier` 的 ID。
   - 返回 `supplier_id` 和 `name`。

1. `POST /api/agent/purchase-orders/create/`
   - 创建 `PurchaseOrder` 草稿和 `PurchaseOrderItem`。
   - 不创建 `PurchaseBatch`，不写 `StockMovement`，不增加可售库存。
   - `Supplier` 必须已存在，通过 `supplier_id` 引用；第一版不自动创建供应商。
   - 金额以行级 `unit_price_rub` 和整单 `exchange_rate` 为输入，CNY 单价和总额由系统计算。

2. POST /api/agent/purchase-orders/update/ 或 /cancel/
   - 草稿可按 expected_version 整单更新，也可在入库前取消。
   - 更新和取消使用独立的 idempotency_key。

3. POST /api/agent/purchase-orders/receive/
   - agent 二次确认后调用。
   - 只允许整单一次性确认入库。
   - 创建 `PurchaseBatch`，写 `receive` 类型 `StockMovement`，并把采购单状态变为 `received`。

草稿可在入库前整单修改；每次更新必须提交 expected_version 和完整 items。若不再采购，应调用取消命令，不要遗留无效草稿。

### 创建采购单草稿

先查询供应商：

```http
GET /api/agent/suppliers/?q=habanos
```

示例返回：

```json
{
  "results": [
    {
      "supplier_id": 1,
      "name": "Habanos"
    }
  ]
}
```

```http
POST /api/agent/purchase-orders/create/
Content-Type: application/json
```

```json
{
  "idempotency_key": "run_001:create_purchase_order:dealer_lot_01",
  "operator_id": 1,
  "agent": {
    "agent_name": "codex",
    "agent_run_id": "run_001",
    "agent_request_id": "req_po_create_001"
  },
  "supplier_id": 1,
  "exchange_rate": "0.0800",
  "note": "Habanos 到货，待二次确认",
  "items": [
    {
      "cigar_id": 12,
      "quantity": 25,
      "box_size": 25,
      "unit_price_rub": "1000.00"
    },
    {
      "cigar_id": 33,
      "quantity": 10,
      "box_size": 10,
      "unit_price_rub": "1200.00"
    }
  ]
}
```

返回 `purchase_order.status = draft`。此时库存没有增加。

### 确认采购入库

```http
POST /api/agent/purchase-orders/receive/
Content-Type: application/json
```

```json
{
  "idempotency_key": "run_001:receive_purchase_order:dealer_lot_01",
  "operator_id": 1,
  "agent": {
    "agent_name": "codex",
    "agent_run_id": "run_001",
    "agent_request_id": "req_po_receive_001"
  },
  "purchase_order_id": 1001,
  "note": "已二次确认，正式入库"
}
```

幂等规则是整单级：

- 同 key + 同请求体：返回首次结果，不重复创建批次或流水。
- 同 key + 不同请求体：返回 `409`。
- `create_purchase_order` 和 `receive_purchase_order` 应分别使用不同的 `idempotency_key`。

如果用户明确说“先能卖就行”，且接受不是正式入库单，才使用 `adjust_stock`。每款雪茄单独调用一次，`reason` 必须包含经销商、到货日期、数量、成本和“临时补录，非正式采购入库”。

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
  "reason": "临时入库补录：经销商 Habanos，2026-06-15 到货 Cohiba Robustos 25 支，成本 180 CNY/支；非正式采购入库"
}
```
