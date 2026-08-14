# 账务动作中心 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在已完成 Day 1、销售出库/收款和基础账务流水的基础上，补齐人民币/USDT 换入卢布、采购付款与在途到货、经营费用、分红、月利润/累计未分配利润以及 React 账务动作中心。

**Architecture:** Accounting 继续作为统一流水事实来源；采购和库存事实仍由 `cigars` 持有。动作服务在一个 `transaction.atomic()` 中锁定业务单、资金账户和全局账务 writer gate，然后通过已有 `_post_transaction_once()` 写不可变成对分录。采购付款使用付款前卢布账户移动平均成本，整单到货只做在途到库存的分类转换；费用直接形成已入账付款事实，分红先保存可编辑草稿，人工确认时才付款并计入分派利润而非经营费用。

**Tech Stack:** Django 5/SQLite、Decimal、Django migrations、React 19、TypeScript、TanStack Query、Vitest、Vite、现有账务 writer gate 与 `writeWithIdempotency()`。

---

## 当前实现基线与设计差距

- `accounting/services.py` 已有 `exchange_to_rub()`、`transfer_same_currency()`、`record_opening_balance()`，并通过 `_post_transaction_once()`、`_outflow_cny_cost()`、SQLite writer gate、有效顺序和幂等键实现移动平均、尾差及负余额保护；本计划只补换汇 UI，不复制换汇服务。
- `LedgerTransaction` 当前只到 `SALES_REFUND`，`LedgerPosting.Category` 没有采购在途、工资、房租、水电、其他费用或分红分类；当前没有 `Expense`、`Dividend` 或采购付款事实模型。
- `PurchaseOrder.Status` 当前只有 `draft/received/cancelled`。`create_purchase_order()` 的 `exchange_rate`/`unit_price_cny` 是报价快照，`receive_purchase_order()` 可从草稿直接造批次，没有实际 RUB 付款或在途流水；`accounting_summary()` 错把所有草稿 `cny_total` 当在途。
- `AccountingDashboardPage.tsx`/`AccountingPanel.tsx` 只有统计、月报和对账；`api.ts` 没有动作 API。换汇后端存在但页面无法发起 CNY/USDT→RUB。

### 已确认约束

- 采购只允许“草稿 → 一次性 RUB 付款/在途 → 整单到货”；无分期付款、分批到货、少货确认。
- 不增加手续费字段或手续费分录；不做市场重估、未实现汇兑损益、卢布换回人民币。
- 工资只能从 CNY 账户支付；房租、水电、其他经营费用只能从 RUB 账户支付，RUB 费用按付款前移动平均成本折算 CNY。
- 分红只允许“草稿 → 人工确认/已入账”；两位实际金额和各自 CNY 出账账户可编辑，默认 50/50（半数按 0.01 元四舍五入，另一方承接尾差）；超累计未分配利润强警告但不硬拒绝；分红永不进入经营净利润。
- API 金额使用精确十进制字符串；已入账不可覆盖；所有写动作幂等、原子，禁止负余额。

### 设计矛盾/边界结论

1. 采购已有 `exchange_rate`/`unit_price_cny`，但不能作为付款成本。新增 `paid_cny_cost` 和明细 `actual_cost_cny`；旧字段保留展示兼容，不参与账务。
2. Day 1 当前规则把期初未分配利润固定为 0；报表仍读取 `OPENING_RETAINED_EARNINGS`，为未来受控迁移保留口径，不增加可编辑累计余额字段。
3. 现有用户模型没有合伙人身份映射；Dividend 首版使用固定“合伙人 A/B”两栏，不虚构权限或身份配置，操作人仍使用现有 `is_operator`。
4. migration 先建 `cigars` 采购状态/实际成本字段，再建引用 `cigars.PurchaseOrder` 的 accounting 付款模型；`accounting` 新迁移显式依赖 `cigars` 最新迁移，避免循环依赖。

## 文件职责

- Modify `accounting/models.py`：扩展交易类型/分类，增加 `PurchasePayment`、`Expense`、`Dividend` 和 posted 不可变边界。
- Create `cigars/migrations/0036_purchase_payment_state.py`：采购状态、付款成本、到货幂等字段；历史记录只回填草稿，不伪造付款。
- Create `accounting/migrations/0012_accounting_actions.py`：动作事实表、索引、唯一约束和金额约束，依赖 `cigars 0036`。
- Modify `cigars/models.py`：增加 `IN_TRANSIT`、`paid_cny_cost`、`paid_at`、`arrival_idempotency_key`、明细实际成本。
- Create `accounting/purchase_actions.py`：`pay_purchase_order()`、`receive_paid_purchase_order()`，资金/在途/库存同事务。
- Create `accounting/expense_actions.py`：`record_expense()` 和费用币种矩阵。
- Create `accounting/dividend_actions.py`：`create_dividend_draft()`、`update_dividend_draft()`、`confirm_dividend()`。
- Modify `cigars/services.py`：抽出可复用整单批次构建 helper；旧到货入口拒绝未付款草稿。
- Modify `accounting/selectors.py`：实际在途、月利润分类、商品毛利、经营净利润和派生累计未分配利润。
- Create `accounting/action_serializers.py`; modify `accounting/views.py`/`accounting/urls.py`：稳定动作 JSON 与错误 code。
- Create/modify `accounting/tests/test_purchase_actions.py`, `test_expense_actions.py`, `test_dividend_actions.py`, `test_action_api.py`；更新 `test_sales_reports_reconciliation.py` 和采购 agent/库存测试。
- Modify `frontend/src/types.ts`, `frontend/src/api.ts`; create `frontend/src/components/accounting/{AccountingActionCenter,ExchangeAction,PurchaseAction,ExpenseAction,DividendAction}.{tsx,test.tsx}`；modify `AccountingDashboardPage.tsx`/`AccountingPanel.tsx`。

## Task 1: 扩展账务/采购事实模型与跨 app migrations

**Files:**

- Modify: `cigars/models.py`, `accounting/models.py`
- Create: `cigars/migrations/0036_purchase_payment_state.py`, `accounting/migrations/0012_accounting_actions.py`
- Test: `accounting/tests/test_models.py`, `cigars/tests/test_sales_accounting.py`

- [ ] **Step 1: 写失败测试**

```python
def test_purchase_order_requires_payment_before_arrival(self):
    order = make_purchase_order()
    with self.assertRaisesRegex(OrderServiceError, '必须先支付采购款'):
        receive_purchase_order(purchase_order_id=order.id, operator=self.operator)

def test_posted_expense_and_dividend_reject_ordinary_orm_update(self):
    expense = make_posted_expense()
    dividend = make_confirmed_dividend()
    with self.assertRaises(LedgerMutationError):
        Expense.objects.filter(pk=expense.pk).update(note='旁路修改')
    with self.assertRaises(LedgerMutationError):
        Dividend.objects.filter(pk=dividend.pk).update(total_cny=Decimal('1.00'))
```

- [ ] **Step 2: 运行 RED**

Run: `.venv/bin/python manage.py test accounting.tests.test_models cigars.tests.test_sales_accounting -v 2`

Expected: FAIL，缺少费用/分红模型，采购草稿仍可直达入库。

- [ ] **Step 3: 添加采购事实字段**

在 `PurchaseOrder.Status` 增加 `IN_TRANSIT='in_transit'`；增加 `paid_cny_cost`（CNY 两位小数，默认 0）、`paid_at`、唯一可空 `arrival_idempotency_key`；`PurchaseOrderItem` 增加 `actual_cost_cny`（默认 0）。`exchange_rate`/`unit_price_cny` 明确保留为报价快照。约束付款前 `paid_cny_cost=0`，到货前必须为正，历史采购不根据手填汇率伪造在途。

```python
class Status(models.TextChoices):
    DRAFT = 'draft', '草稿'
    IN_TRANSIT = 'in_transit', '在途'
    RECEIVED = 'received', '已入库'
    CANCELLED = 'cancelled', '已取消'

paid_cny_cost = models.DecimalField(max_digits=22, decimal_places=2, default=Decimal('0.00'))
paid_at = models.DateTimeField(null=True, blank=True)
arrival_idempotency_key = models.CharField(max_length=128, unique=True, null=True, blank=True)
actual_cost_cny = models.DecimalField(max_digits=22, decimal_places=2, default=Decimal('0.00'))
```

- [ ] **Step 4: 添加 accounting 动作模型和分类**

扩展交易类型：`PURCHASE_PAYMENT`、`PURCHASE_RECEIPT`、`EXPENSE`、`DIVIDEND`；扩展分类：`PURCHASE_IN_TRANSIT`、`SALARY_EXPENSE`、`RENT_EXPENSE`、`UTILITIES_EXPENSE`、`OTHER_EXPENSE`、`DIVIDEND_DISTRIBUTION`。

`PurchasePayment` 位于 accounting，`purchase_order = OneToOneField('cigars.PurchaseOrder')`，保存 RUB 账户、实际 RUB、承接 CNY 成本、业务日期、operator、ledger transaction 和唯一幂等键。`Expense` 保存分类、资金账户、原币金额、CNY 成本、业务日期、operator、ledger transaction、幂等键和备注。`Dividend` 保存 `draft|posted`、总额、A/B 金额、A/B CNY 账户、业务日期、确认人/时间、ledger transaction、确认幂等键和备注；草稿无 ledger relation。

金额均为非负；Dividend 合计由服务校验。posted 行的 `save/update/delete` 必须抛 `LedgerMutationError`，并用短注释说明这是保护“已入账不可变”的 ORM 边界。

- [ ] **Step 5: 生成并检查 migration DAG**

```bash
.venv/bin/python manage.py makemigrations cigars accounting
sed -n '1,220p' cigars/migrations/0036_purchase_payment_state.py
sed -n '1,280p' accounting/migrations/0012_accounting_actions.py
.venv/bin/python manage.py showmigrations accounting cigars
```

Expected: `cigars 0036` 依赖 `0035`；`accounting 0012` 依赖 `accounting 0011` 和 `cigars 0036`，无循环；旧采购字段不删除、不重算。

- [ ] **Step 6: GREEN 与中文 commit**

Run: `.venv/bin/python manage.py test accounting.tests.test_models cigars.tests.test_sales_accounting -v 2`

Expected: PASS，旧销售/库存成本守恒测试保持通过。

```bash
git add accounting/models.py accounting/migrations/0012_accounting_actions.py cigars/models.py cigars/migrations/0036_purchase_payment_state.py accounting/tests/test_models.py cigars/tests/test_sales_accounting.py
git commit -m "功能：建立采购费用分红账务事实模型"
```

## Task 2: 实现采购一次付款、在途和整单到货

**Files:**

- Create: `accounting/purchase_actions.py`
- Modify: `cigars/services.py`
- Test: `accounting/tests/test_purchase_actions.py`, `cigars/tests/test_agent_order_inventory.py`

- [ ] **Step 1: 写付款/到货 RED 测试**

```python
def test_pay_purchase_uses_rub_moving_average_and_creates_in_transit(self):
    open_rub(self.rub, original='12000.00', cny_cost='1000.00')
    order = make_purchase_order(items=[(self.cigar, 10, '120.00')])
    payment = pay_purchase_order(
        purchase_order_id=order.id, rub_account=self.rub,
        business_date=date(2026, 8, 14), operator=self.operator,
        idempotency_key='po-pay-1',
    )
    self.assertEqual(payment.cny_cost, Decimal('120.00'))
    self.assertEqual(account_snapshot(self.rub).cny_book_cost, Decimal('880.00'))
    self.assertEqual(PurchaseOrder.objects.get(pk=order.pk).status, PurchaseOrder.Status.IN_TRANSIT)

def test_receive_allocates_tail_to_last_item_and_replays(self):
    order = paid_order_with_items(rub_subtotals=['100.00', '200.00'], paid_cny_cost='100.00')
    first = receive_paid_purchase_order(
        purchase_order_id=order.id, business_date=date(2026, 8, 15),
        operator=self.operator, idempotency_key='po-arrive-1',
    )
    order.refresh_from_db()
    self.assertEqual(list(order.items.order_by('id').values_list('actual_cost_cny', flat=True)), [Decimal('33.33'), Decimal('66.67')])
    self.assertEqual(sum(batch.original_cost_cny for batch in first), Decimal('100.00'))
    replay = receive_paid_purchase_order(purchase_order_id=order.id, business_date=date(2026, 8, 15), operator=self.operator, idempotency_key='po-arrive-1')
    self.assertEqual([batch.id for batch in replay], [batch.id for batch in first])
```

- [ ] **Step 2: 运行 RED**

Run: `.venv/bin/python manage.py test accounting.tests.test_purchase_actions -v 2`

Expected: FAIL，付款/到货服务和实际成本字段不存在。

- [ ] **Step 3: 实现付款服务**

新增签名：

```python
def pay_purchase_order(*, purchase_order_id, rub_account, business_date, operator, idempotency_key, description='') -> PurchasePayment:
    ...
```

服务先取得 `_acquire_sqlite_writer_gate()`，再锁采购单和 RUB 账户；只接受 `DRAFT`，且实际 RUB 总额必须等于明细 `unit_price_rub * quantity`。调用已有 `_outflow_cny_cost()` 取得付款前移动平均，使用 `_post_transaction_once()` 写 RUB 账户负数和 `PURCHASE_IN_TRANSIT` 正 CNY；同事务创建 `PurchasePayment`、写 `paid_cny_cost`/`paid_at`/`IN_TRANSIT`。幂等 replay 必须核对采购单、账户、金额、日期和 operator。注释写明采购付款是“资金减少 + 在途增加”，不是费用或利润。

- [ ] **Step 4: 实现到货服务**

新增签名：

```python
def receive_paid_purchase_order(*, purchase_order_id, business_date, operator, idempotency_key, note='') -> list[PurchaseBatch]:
    ...
```

只接受 `IN_TRANSIT`，拒绝草稿/取消/已入库/已有批次，数量必须完整。按每明细 RUB 小计占比分配 `paid_cny_cost`，最后一条取“总额减已分配”保证尾差；复用 `cigars.services` 的包装批次构建但使用实际单支成本。一个事务内写 `PURCHASE_IN_TRANSIT -paid_cny_cost`、`INVENTORY +paid_cny_cost`、完整 `StockMovement.RECEIVE`，再标记 `RECEIVED` 和到货幂等键。不得再次扣 RUB 或使用报价汇率。现有 `receive_purchase_order()` 改为委托并拒绝未付款草稿，agent 旧接口返回结构化 400。

- [ ] **Step 5: 补原子/并发/边界测试并提交**

覆盖 CNY/USDT 误付、RUB 余额不足、同单二次付款、幂等冲突、付款/到货中途失败无残留、并发只有一方成功、尾差、不能少货伪造入库、批次成本守恒。

Run: `.venv/bin/python manage.py test accounting.tests.test_purchase_actions cigars.tests.test_agent_order_inventory cigars.tests.test_sales_accounting -v 2`

Expected: PASS，旧 agent 测试明确验证草稿不能绕过付款。

```bash
git add accounting/purchase_actions.py cigars/services.py accounting/tests/test_purchase_actions.py cigars/tests/test_agent_order_inventory.py cigars/tests/test_sales_accounting.py
git commit -m "功能：实现采购付款在途与整单到货"
```

## Task 3: 实现工资、房租、水电和其他费用

**Files:**

- Create: `accounting/expense_actions.py`
- Modify: `accounting/services.py`
- Test: `accounting/tests/test_expense_actions.py`

- [ ] **Step 1: 写费用矩阵 RED 测试**

```python
def test_salary_only_accepts_cny_and_rub_expense_uses_moving_average(self):
    open_cny(self.cny, '1000.00')
    open_rub(self.rub, original='1200.00', cny_cost='100.00')
    salary = record_expense(category='salary', amount='300.00', fund_account=self.cny, business_date=date(2026, 8, 14), operator=self.operator, idempotency_key='salary-1')
    rent = record_expense(category='rent', amount='600.00', fund_account=self.rub, business_date=date(2026, 8, 14), operator=self.operator, idempotency_key='rent-1')
    self.assertEqual((salary.amount_cny, rent.amount_cny), (Decimal('300.00'), Decimal('50.00')))
    with self.assertRaisesRegex(LedgerError, '工资只能从人民币账户支付'):
        record_expense(category='salary', amount='1.00', fund_account=self.rub, business_date=date(2026, 8, 14), operator=self.operator, idempotency_key='bad-salary')
```

- [ ] **Step 2: RED**

Run: `.venv/bin/python manage.py test accounting.tests.test_expense_actions -v 2`

Expected: FAIL，费用服务与 posting 不存在。

- [ ] **Step 3: 实现 `record_expense()`**

```python
def record_expense(*, category, amount, fund_account, business_date, operator, idempotency_key, note='') -> Expense:
    ...
```

固定矩阵为 `salary -> CNY/SALARY_EXPENSE`，`rent/utilities/other -> RUB/对应分类`。严格原币精度；RUB 使用 `_outflow_cny_cost()`，CNY 原币等于 CNY 成本。posting 是资金账户负数 + 费用分类正数，业务日期决定月报月份；Expense 与 ledger 同事务，幂等参数不匹配返回冲突。注释说明 RUB 费用按付款前移动平均成本确认，不是换汇。

- [ ] **Step 4: 测试边界并提交**

覆盖四分类合法/非法币种、负/零/超精度、停用账户、余额不足、尾差归零、重复点击、posted ORM 修改、跨月业务日和原子失败无残留。

Run: `.venv/bin/python manage.py test accounting.tests.test_expense_actions accounting.tests.test_operations accounting.tests.test_external_inputs -v 2`

Expected: PASS，现有换汇/转账回归通过。

```bash
git add accounting/expense_actions.py accounting/services.py accounting/tests/test_expense_actions.py
git commit -m "功能：记录人民币与卢布经营费用"
```


## Task 4: 分红草稿与人工确认
**Files:** Test `accounting/tests/test_dividend_actions.py`; implement `create_dividend_draft`, `update_dividend_draft`, and `confirm_dividend`.
- [ ] **Step 2: RED 命令**：`.venv/bin/python manage.py test accounting.tests.test_dividend_actions -v 2`；预期缺少服务而失败。
- [ ] **Step 3: 实现服务**：新增 `create_dividend_draft`、`update_dividend_draft`、`confirm_dividend`。创建按半数四舍五入、另一方承接尾差；编辑只允许 draft，两个账户必须不同/启用/CNY，A+B 精确等于总额。确认锁 Dividend、两账户和 writer gate，posting 为两笔账户负数加 `DIVIDEND_DISTRIBUTION` 正数；超留存利润只 warning，余额不足/幂等冲突原子回滚。草稿不触达资金，posted 不可编辑，分红不进经营费用。
- [ ] **Step 4: GREEN/commit**：覆盖币种、余额、精度、重复确认、超留存警告和并发；运行 `.venv/bin/python manage.py test accounting.tests.test_dividend_actions accounting.tests.test_ledger -v 2`，预期 PASS；提交 `git add accounting/dividend_actions.py accounting/tests/test_dividend_actions.py && git commit -m "功能：支持分红草稿与人工确认"`。
## Task 5: 报表口径与动作 API
**Files:** Modify `accounting/selectors.py`, `accounting/views.py`, `accounting/urls.py`; create `accounting/action_serializers.py`, `accounting/tests/test_action_api.py`; update report/API tests.
- [ ] **Step 1 RED**：断言草稿采购不进入 `purchase_in_transit_cny`，而 `IN_TRANSIT.paid_cny_cost=120.00` 进入；工资100、销售利润500、分红50时月净利润400、累计未分配利润350；salary 用 RUB 返回 HTTP 400/code `currency_rule`。运行 `.venv/bin/python manage.py test accounting.tests.test_sales_reports_reconciliation accounting.tests.test_action_api -v 2`，预期 FAIL。
- [ ] **Step 2 实现选择器**：月报按业务日期/POSTED 返回各费用、商品毛利、经营净利润和 `retained_earnings_cny`；经营净利润=商品毛利+客户人肉费收入-实际人肉成本-工资-房租-水电-其他；累计未分配利润=-期初留存分类累计额+累计净利润-已确认分红。采购、换汇、转账、应收/预收、投入、分红不进净利润；摘要只聚合已付款在途。
- [ ] **Step 3 实现 API**：新增 `GET /api/accounting/actions/`、采购创建/pay/receive、`POST /api/accounting/expenses/`、分红 GET/POST/PATCH/confirm；复用 `cigars.services.create_purchase_order()`，写接口 staff-only 且必须 `Idempotency-Key`，错误统一 `{error,code,details}`（`currency_rule`/`insufficient_balance`/`invalid_state`/`idempotency_conflict`/`validation_error`/`busy`），Decimal 全为字符串。
- [ ] **Step 4 GREEN/commit**：运行 `.venv/bin/python manage.py test accounting.tests.test_action_api accounting.tests.test_api accounting.tests.test_sales_reports_reconciliation cigars.tests.test_agent_order_inventory -v 2`，预期 PASS；提交 `git add accounting/selectors.py accounting/action_serializers.py accounting/views.py accounting/urls.py accounting/tests/test_action_api.py accounting/tests/test_api.py accounting/tests/test_sales_reports_reconciliation.py && git commit -m "功能：提供账务动作与利润报表接口"`。
## Task 6: React 账务动作中心与局部错误状态
**Files:** Modify `frontend/src/types.ts`, `frontend/src/api.ts`, `frontend/src/pages/AccountingDashboardPage.tsx`, `frontend/src/components/sales/AccountingPanel.tsx`; create `frontend/src/components/accounting/AccountingActionCenter.tsx`, `ExchangeAction.tsx`, `PurchaseAction.tsx`, `ExpenseAction.tsx`, `DividendAction.tsx` and tests.
- [ ] **Step 1 RED**：组件测试选择 USDT、输入 `1.00000000`/`1200.00` 断言 `exchangeToRub` 收到实际金额；模拟 `currency_rule` 时错误只出现在费用卡，其他区域保留错误。运行 `cd frontend && npm test -- --run src/components/accounting`，预期 FAIL。
- [ ] **Step 2 实现契约**：types Decimal 全用 string；api 增加 `fetchAccountingActions`、`exchangeToRub`、采购创建/付款/到货、`recordExpense`、分红列表/创建/编辑/确认，所有写请求使用 `writeWithIdempotency()`。
- [ ] **Step 3 实现组件**：换汇源仅 CNY/USDT、目标固定 RUB，只提交实际数量；采购只提供草稿付款/在途整单到货，无手续费/分期/分批控件；费用按分类筛账户；分红展示 A/B 和超留存 warning。每卡独立 idle/loading/success/error/conflict，保留输入，失败不清空其他数据或把 null 显示为 0。
- [ ] **Step 4 GREEN/commit**：Day1 未完成只显示初始化待办；完成后沿用 OpenDesign 接入工作台。运行 `cd frontend && npm test -- --run src/components/accounting src/pages/AccountingDashboardPage.test.tsx && npm run lint && npm run build`，预期 PASS；提交 `git add frontend/src/types.ts frontend/src/api.ts frontend/src/components/accounting frontend/src/pages/AccountingDashboardPage.tsx frontend/src/components/sales/AccountingPanel.tsx && git commit -m "前端：接入账务动作中心与错误状态"`。
## Task 7: 全量验证与交付审查
- [ ] **Step 1 migration/check**：运行 `.venv/bin/python manage.py makemigrations --check`、`.venv/bin/python manage.py check`、`.venv/bin/python manage.py showmigrations accounting cigars`；预期无未生成迁移/系统错误/循环依赖，cigars 0036 先于 accounting 0012。
- [ ] **Step 2 后端回归**：运行 `.venv/bin/python manage.py test accounting cigars.tests.test_sales_accounting cigars.tests.test_sales_order_workflow cigars.tests.test_agent_order_inventory -v 2`；预期换汇移动平均/尾差、采购在途、库存 FIFO、销售、对账、Day1 全部 PASS。
- [ ] **Step 3 前端回归**：运行 `cd frontend && npm test -- --run && npm run lint && npm run build`；预期 Vitest、lint、production build 全部通过。
- [ ] **Step 4 验收**：逐项确认实际换汇金额、一次采购付款/整单到货、费用币种、分红草稿与非利润确认、留存利润派生、幂等/负余额/尾差/不可变/原子回滚，以及无分期/分批/手续费/市场重估；独立代码审查资金、成本、库存和分红不变量。
## 验收与注释要求
- 新代码必须有简短中文注释，说明原子付款/到货、RUB 移动平均及最后尾差、幂等/posted 不可变、旧报价字段只读兼容、局部错误不伪装零值；注释不能替代测试。前端沿用 OpenDesign；用户文案/文档/commit 中文，标识符/API/枚举英文。未有上述验证证据不得宣称完成；本计划不 push/merge，实际实现另开分支。

## 修订补充：采购包装语义与不可变 QuerySet

下面的补充详细步骤是对上方压缩摘要的替代执行清单；实现者按本节逐项执行。

### Task 1 补充：采购包装转换和 QuerySet 保护

- [ ] **Step 7（2–5 分钟）：先固定包装事实测试**

```python
def test_legacy_purchase_row_converts_without_changing_rub_total(self):
    order = legacy_order(quantity=25, box_size=25, unit_price_rub='1000.00')
    normalize_purchase_item(order.items.get())
    item = order.items.get()
    self.assertEqual((item.box_quantity, item.unit_price_rub_per_box), (1, Decimal('25000.00')))
    self.assertEqual(item.quantity * item.unit_price_rub, Decimal('25000.00'))

def test_non_divisible_legacy_row_is_blocked_until_manual_packaging_review(self):
    item = legacy_item(quantity=26, box_size=25, unit_price_rub='1000.00')
    with self.assertRaisesRegex(OrderServiceError, '包装数量无法无损转换'):
        normalize_purchase_item(item)
```

- [ ] **Step 8（2–5 分钟）：实现安全 canonical 字段**

在 PurchaseOrderItem 新增 `box_quantity`、`unit_price_rub_per_box`，两者可空以容纳历史未转换行；新建/新保存的采购单必须有 `box_size > 0`、`box_quantity > 0`，并令 `quantity = box_size * box_quantity`。保留旧 `quantity` 和 `unit_price_rub` 作为 legacy 只读兼容列。新增 `normalize_purchase_item(item)`：若 canonical 已有值只校验；若旧行的 `quantity % box_size == 0`，写 `box_quantity=quantity//box_size`、`unit_price_rub_per_box=unit_price_rub*box_size`；若 box_size 为空或有余数，保留原值并返回 `packaging_review_required`，付款接口拒绝。

注释说明旧服务当前把 quantity 当支数、unit_price_rub 当每支价；转换只把每支价乘盒规，不改 rub_total，防止历史订单成本漂移。

- [ ] **Step 9（2–5 分钟）：迁移和新输入转换**

`cigars/migrations/0036_purchase_payment_state.py` 先添加 canonical nullable 字段，再用 RunPython 逐行转换可整除旧数据；不可整除/无盒规行保持 null 并写入状态标志，不静默猜盒数。新 API payload 只接受 `{box_size, box_quantity, unit_price_rub_per_box}`，计算 `sticks = box_size * box_quantity`、`rub_subtotal = box_quantity * unit_price_rub_per_box`；兼容旧 agent payload 时先调用 normalize，非整除行返回明确 409，旧字段继续返回以供查询。

- [ ] **Step 10（2–5 分钟）：测试 RUB/CNY 守恒**

```python
def test_purchase_totals_use_boxes_and_last_cny_line_tail(self):
    order = create_purchase_order(items=[
        {'cigar_id': self.a.id, 'box_size': 25, 'box_quantity': 1, 'unit_price_rub_per_box': '100.00'},
        {'cigar_id': self.b.id, 'box_size': 10, 'box_quantity': 2, 'unit_price_rub_per_box': '100.00'},
    ], exchange_rate='1.0000', supplier_id=self.supplier.id, operator=self.operator)
    self.assertEqual(order.rub_total, Decimal('300.00'))
    costs = allocate_paid_cny(order, Decimal('100.00'))
    self.assertEqual(costs, [Decimal('33.33'), Decimal('66.67')])
    self.assertEqual(sum(costs), Decimal('100.00'))
```

Run: `.venv/bin/python manage.py test cigars.tests.test_purchase_packaging accounting.tests.test_purchase_actions -v 2`.
Expected: legacy整除行无损转换，非整除行阻断，盒数×每盒价精确等于 RUB 总额，CNY 最后一行承接尾差。

- [ ] **Step 11（2–5 分钟）：落实 QuerySet/Manager posted 保护**

在 `accounting/models.py` 写实际保护类，而非只依赖实例 save/delete：

```python
class ExpenseQuerySet(models.QuerySet):
    def _reject_posted(self):
        if self.filter(ledger_transaction__status__in=('posted', 'reversed')).exists():
            raise LedgerMutationError('已入账费用不可修改或删除')
    def update(self, **kwargs):
        self._reject_posted(); return super().update(**kwargs)
    def delete(self):
        self._reject_posted(); return super().delete()
    def bulk_update(self, objs, fields, **kwargs):
        self._reject_posted(); return super().bulk_update(objs, fields, **kwargs)
    def bulk_create(self, objs, **kwargs):
        raise LedgerMutationError('费用必须通过受控服务创建')

class DividendQuerySet(models.QuerySet):
    def _reject_posted(self):
        if self.filter(status='posted').exists():
            raise LedgerMutationError('已确认分红不可修改或删除')
    def update(self, **kwargs):
        self._reject_posted(); return super().update(**kwargs)
    def delete(self):
        self._reject_posted(); return super().delete()
    def bulk_update(self, objs, fields, **kwargs):
        self._reject_posted(); return super().bulk_update(objs, fields, **kwargs)
    def bulk_create(self, objs, **kwargs):
        raise LedgerMutationError('分红必须通过草稿/确认服务创建')
```

将 `objects = ExpenseQuerySet.as_manager()`/`DividendQuerySet.as_manager()` 接到模型，并测试 `filter(pk).update()`、`delete()`、`bulk_update()`、`bulk_create()` 四条旁路均抛错；这是验收必需项。

### Task 4 详细执行：分红

- [ ] **Step 1（2–5 分钟）：写 RED 测试**

```python
def test_dividend_draft_split_and_confirmation(self):
    draft = create_dividend_draft(total_cny='101.01', business_date=self.day, operator=self.alice)
    self.assertEqual((draft.partner_a_amount_cny, draft.partner_b_amount_cny), (Decimal('50.51'), Decimal('50.50')))
    update_dividend_draft(dividend_id=draft.id, total_cny='101.01', partner_a_amount_cny='30.00', partner_b_amount_cny='71.01', partner_a_account=self.cny_a, partner_b_account=self.cny_b, operator=self.alice)
    result = confirm_dividend(dividend_id=draft.id, operator=self.alice, idempotency_key='div-1')
    self.assertEqual(sum(p.cny_amount for p in result.ledger_transaction.postings.all()), Decimal('0.00'))
    self.assertFalse(monthly_profit(month=self.day.replace(day=1))['dividend_cny'])
```

- [ ] **Step 2（2–5 分钟）：运行 RED**

Run: `.venv/bin/python manage.py test accounting.tests.test_dividend_actions.DividedActionTest.test_dividend_draft_split_and_confirmation -v 2`.
Expected: FAIL，Dividend service/model 尚未实现。

- [ ] **Step 3（2–5 分钟）：写最小服务签名和状态机**

```python
def create_dividend_draft(*, total_cny, business_date, operator, note='') -> Dividend: ...
def update_dividend_draft(*, dividend_id, total_cny, partner_a_amount_cny, partner_b_amount_cny, partner_a_account, partner_b_account, operator, note='') -> Dividend: ...
def confirm_dividend(*, dividend_id, operator, idempotency_key) -> Dividend: ...
```

实现每一步都包 `transaction.atomic()`；confirm 先 writer gate 再按 id 排序锁两账户和 Dividend，posting 使用 `_post_transaction_once()`，超留存利润只产生 warning。注释只解释并发锁顺序、草稿不触达资金和尾差规则。

- [ ] **Step 4（2–5 分钟）：补 API 错误测试并 GREEN**

测试合计不等、同账户、非 CNY、余额不足、重复 key 参数冲突分别得到 400/409；重复相同 key 返回同一 ledger id。运行 `.venv/bin/python manage.py test accounting.tests.test_dividend_actions accounting.tests.test_action_api -v 2`，Expected: PASS。

- [ ] **Step 5（2–5 分钟）：提交**

```bash
git add accounting/models.py accounting/dividend_actions.py accounting/tests/test_dividend_actions.py accounting/tests/test_action_api.py
git commit -m "功能：完成分红草稿确认与不可变保护"
```

### Task 5 详细执行：报表与动作 API

- [ ] **Step 1（2–5 分钟）：写选择器 RED**

```python
def test_profit_and_retained_earnings_exclude_dividend_and_purchase(self):
    post_sale_profit('500.00', self.day); post_salary('100.00', self.day); confirm_dividend_fixture('50.00', self.day)
    report = monthly_profit(month=self.day.replace(day=1))
    self.assertEqual(report['net_profit_cny'], Decimal('400.00'))
    self.assertEqual(report['retained_earnings_cny'], Decimal('350.00'))
```

- [ ] **Step 2（2–5 分钟）：实现并跑 GREEN**

在 `selectors.py` 增加 `_sum_category` 映射和 `retained_earnings(as_of)`；符号固定为收入负、费用正，月利润只在 selector 中转为展示正负。`accounting_summary` 改为聚合 `PurchaseOrder.objects.filter(status=IN_TRANSIT).paid_cny_cost`。运行 `.venv/bin/python manage.py test accounting.tests.test_sales_reports_reconciliation -v 2`，Expected: PASS。

- [ ] **Step 3（2–5 分钟）：写 API contract RED**

```python
def test_actions_endpoint_returns_pending_purchase_and_dividend(self):
    self.client.force_login(self.operator)
    data = self.client.get('/api/accounting/actions/').json()
    self.assertIn('purchase_drafts', data); self.assertIn('dividend_drafts', data)
```

Run: `.venv/bin/python manage.py test accounting.tests.test_action_api.ActionApiTest -v 2`。
Expected: FAIL with 404 until urls/view are wired.

- [ ] **Step 4（2–5 分钟）：实现 API 和错误映射**

新增 `/actions/`、采购 pay/receive、expense、dividend CRUD/confirm views；每个 view 调用已定义 service，错误转换为 `{error, code, details}`，Decimal `str()`；所有写入检查 staff 和 `Idempotency-Key`。加入注释说明 API 不从流水自行拼财务数字。

- [ ] **Step 5（2–5 分钟）：验证并提交**

Run: `.venv/bin/python manage.py test accounting.tests.test_action_api accounting.tests.test_api accounting.tests.test_sales_reports_reconciliation -v 2`。
Expected: PASS；提交 `git add accounting/selectors.py accounting/action_serializers.py accounting/views.py accounting/urls.py accounting/tests/test_action_api.py && git commit -m '功能：完成动作列表与留存利润接口'`。

### Task 6 详细执行：React 与帮助链接

- [ ] **Step 1（2–5 分钟）：写 API helper RED**

```ts
it('sends exchange amounts as strings and uses idempotency helper', async () => {
  await exchangeToRub({source_account_id: 2, rub_account_id: 3, source_amount: '1.00000000', rub_amount: '1200.00', business_date: '2026-08-14'})
  expect(writeWithIdempotency).toHaveBeenCalled()
})
```

Run: `cd frontend && npm test -- --run src/api/accountingActions.test.ts`。Expected: FAIL because helper is absent.

- [ ] **Step 2（2–5 分钟）：实现 API/types**

在 `types.ts` 定义所有 Decimal 为 string；在 `api.ts` 实现 `fetchAccountingActions`、`exchangeToRub`、`payPurchaseOrder`、`receivePurchaseOrder`、`recordExpense`、`create/update/confirmDividend`，所有写函数调用现有 `writeWithIdempotency`。运行同一测试，Expected: PASS。

- [ ] **Step 3（2–5 分钟）：写动作卡 RED**

```tsx
it('keeps a currency error in the expense card', async () => {
  mockExpenseRequest.rejects({response:{data:{error:'工资只能从人民币账户支付', code:'currency_rule'}}})
  render(<AccountingActionCenter />)
  await user.click(screen.getByRole('button', {name:'记录费用'}))
  expect(await screen.findByText('工资只能从人民币账户支付')).toBeVisible()
})
```

- [ ] **Step 4（2–5 分钟）：实现动作卡并连接真实控件**

`ExchangeAction` 只列 CNY/USDT→固定 RUB；`PurchaseAction` 只让 DRAFT 付款、IN_TRANSIT 到货；`ExpenseAction` 根据分类过滤账户；`DividendAction` 保存草稿后确认。每卡保留输入/局部 error/loading，注释说明错误隔离与幂等，不做视觉重设计。运行 `cd frontend && npm test -- --run src/components/accounting`，Expected: PASS。

- [ ] **Step 5（2–5 分钟）：更新并测试帮助链接**

在 `frontend/src/features/guides/guideContent.ts` 将换汇、采购、费用章节的 target 指向动作卡真实 `data-guide` 控件；在 `guideInteractions.test.ts` 增加三项断言，确认点击帮助链接能定位并聚焦真实控件，不能触发提交。运行 `cd frontend && npm test -- --run src/features/guides`，Expected: PASS。

### Task 7 详细执行：验证与当前功能分支收尾

- [ ] **Step 1（2–5 分钟）：migration/check**

```bash
.venv/bin/python manage.py makemigrations --check
.venv/bin/python manage.py check
.venv/bin/python manage.py showmigrations accounting cigars
```

Expected: 无未生成迁移、无 system check 错误、cigars 0036 在 accounting 0012 之前且无循环依赖。

- [ ] **Step 2（2–5 分钟）：后端回归**

Run: `.venv/bin/python manage.py test accounting cigars.tests.test_sales_accounting cigars.tests.test_sales_order_workflow cigars.tests.test_agent_order_inventory -v 2`。
Expected: 全部 PASS，覆盖移动平均、尾差、采购在途、库存 FIFO、销售、对账、Day1。

- [ ] **Step 3（2–5 分钟）：前端回归**

Run: `cd frontend && npm test -- --run && npm run lint && npm run build`。
Expected: Vitest PASS、lint 0 error、production build exit 0。

- [ ] **Step 4（2–5 分钟）：spec coverage/self-review**

逐项对照批准设计 §§4–7、10、12–13、15 与 workspace/day1 §3：换汇真实金额、采购盒规/每盒价/整单守恒、费用币种、分红非利润、留存利润派生、幂等/负余额/posted QuerySet 不可变、局部错误和帮助链接。搜索常见未完成占位词时排除本条自检说明本身，Expected: 无真正的占位项；再检查每个函数名和类型与前文一致。

- [ ] **Step 5（2–5 分钟）：继续当前功能分支收尾**

只 stage 计划文件，确认 `git diff --cached --name-only` 只有该文件；提交中文 commit。实现完成后的分支流程是：在当前 `feature/business-workspace-day1` 本地完成验证后合并 main、删除该功能分支；不 push、不另开分支。
