# Agent 订单和库存写接口进度同步

> 日期：2026-06-15
> 目标：第一版 agent 可用的订单和库存写接口。
> 状态：销售单、库存预留/出库/释放、库存修正和基础报表已形成最小闭环；正式采购入库 Agent API 待设计。

## 已完成

- 新增库存事实模型：
  - `StockMovement`
  - `StockAllocation`
  - `OrderEvent`
  - `IdempotencyRecord`
  - `SalesOrderItem.fulfillment_type`
- 新增迁移：
  - `cigars/migrations/0020_agent_order_inventory_commands.py`
  - `cigars/migrations/0021_stock_movement_opening_balances.py`
- 新增服务层：
  - `create_sales_order`
  - `confirm_payment`
  - `cancel_sales_order`
  - `adjust_stock`
  - `receive_purchase_order`
  - `get_stock_summary`
- 新增 Agent API：
  - `GET /api/agent/search/`
  - `GET /api/agent/stock/`
  - `POST /api/agent/orders/create/`
  - `POST /api/agent/orders/confirm-payment/`
  - `POST /api/agent/orders/cancel/`
  - `POST /api/agent/stock/adjust/`
  - `GET /api/agent/reports/basic/`
- 改造 `privnote/services/payment.py`，避免 `operator=None`，并让付款相关库存动作经过服务层。
- 新增测试覆盖第一版核心行为。

## 当前业务语义

- `StockMovement` 是库存事实源。
- `PurchaseBatch.remaining` 保留为读模型/缓存，用于现有页面和快速查询。
- 现货销售创建时立即 FIFO 预留库存，写 `reserve` 流水。
- 确认付款时把预留转为正式出库，写 `ship` 流水。
- 取消未付款订单时释放预留库存，写 `release_reservation` 流水。
- 一条 `SalesOrderItem` 可以跨多个 `PurchaseBatch` 分配，通过 `StockAllocation` 表达。
- 预售是正式场景，但不占用批次，不创建 `StockAllocation`。
- 同一张销售单可以混合现货和预售，区分点在 `SalesOrderItem.fulfillment_type`。
- 第一版不拆 `payment_status` / `fulfillment_status`，继续沿用简单 `SalesOrder.status`。
- 订单操作上下文写入 `OrderEvent`，库存数量事实写入 `StockMovement`。

## Agent 写命令约束

- Agent 只能调用命令式业务接口，不开放通用 CRUD。
- 每个写命令必须带真实 `operator_id`。
- 每个写命令必须带 `agent.agent_name`，建议同时带 `agent_run_id` 和 `agent_request_id`。
- 每个写命令必须带 `idempotency_key`。
- 同 key + 同请求体返回第一次结果。
- 同 key + 不同请求体返回 `409`。
- 业务错误也会记录并重放，避免重试时重复扣库存或得到不一致结果。

## 已验证

已跑过：

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test cigars privnote -v 1
pytest price_tracker/tests -q
```

结果：

- Django check 通过。
- migration dry run 通过。
- `cigars` + `privnote` 测试通过：84 passed。
- `price_tracker` 测试通过：40 passed。
- 远程开发库迁移已应用到 `cigars.0021`。
- opening balance 已核对：
  - `PurchaseBatch.remaining` 汇总：535
  - opening `StockMovement` 汇总：535
  - opening movement 行数：11

## 经销商进货入库的当前结论

“从经销商进货，制作入库单”是正式采购入库场景，不应长期用 `adjust_stock` 伪装。

当前可用权衡：

- 如果只是为了让库存马上可卖，并且用户接受后续补正式采购单，可以临时使用 `POST /api/agent/stock/adjust/` 正向修正库存。
- 如果用户需要供应商、采购单号、总金额、币种、汇率和利润成本追溯，应先实现正式采购入库 Agent API。

正式方案建议设计两个命令：

- `POST /api/agent/purchase-orders/create/`
- `POST /api/agent/purchase-orders/receive/`

或者设计一个第一版一阶段命令：

- `POST /api/agent/purchase-orders/create-and-receive/`

这个选择需要先通过 `grill-with-docs` 把业务语义问清楚。

## 下一窗口建议 Prompt

```text
你在远程机器 192.168.0.97 的 jason 用户下工作，项目路径是 /home/jason/moscow_cigar。

请使用 grill-with-docs。先读：
- docs/CONTEXT.md
- docs/agent-api-inventory-guide.md
- docs/plans/2026-06-15-agent-order-inventory-progress.md
- docs/adr/0010-stock-movement-source-of-truth.md
- docs/adr/0011-agent-command-api.md
- docs/adr/0017-agent-command-idempotency.md
- cigars/models.py
- cigars/services.py
- cigars/agent_api.py

目标：严肃设计“经销商进货，制作正式入库单”的 Agent API，不要直接用库存修正冒充正式采购入库。

请一轮只问一个关键问题，持续 grill 到业务语义清楚为止。重点确认：
- Dealer 和 Supplier 是否统一建模，还是需要区分。
- 第一版是 create purchase order + receive 两步，还是 create-and-receive 一步。
- 是否需要 draft/received 状态，还是第一版只记录已入库。
- 是否需要部分到货。
- 成本字段如何记录：币种、汇率、单支成本、总额。
- 供应商不存在时是否允许 agent 自动创建。
- 幂等键粒度按整张采购单还是每个入库动作。
- 是否需要 Purchase Event，还是先用 StockMovement.note 和 PurchaseOrder.note。
- 是否需要新增 ADR。

确认设计后，再实现最小可靠闭环：
- 新增正式采购/入库 service。
- 新增 /api/agent/purchase-orders/ 命令接口。
- 所有写命令继续强制 operator、agent、idempotency_key。
- receive 必须写 receive 类型 StockMovement。
- 不要破坏 PurchaseBatch.remaining 作为读模型/缓存的规则。
- 增加测试覆盖正式入库、幂等重试、幂等冲突、供应商记录和库存流水。

注意：
- 当前远程工作区有 unrelated dirty changes，尤其 price_tracker 相关文件，不要回滚或覆盖。
- docs/ 被 .gitignore 忽略，需要提交时用 git add -f。
- 先实现最小可靠闭环，不引入复杂状态机或队列。
```

## 文档入口

- Agent 调用手册：`docs/agent-api-inventory-guide.md`
- 领域语言：`docs/CONTEXT.md`
- 库存事实源 ADR：`docs/adr/0010-stock-movement-source-of-truth.md`
- Agent 命令接口 ADR：`docs/adr/0011-agent-command-api.md`
- 幂等 ADR：`docs/adr/0017-agent-command-idempotency.md`
