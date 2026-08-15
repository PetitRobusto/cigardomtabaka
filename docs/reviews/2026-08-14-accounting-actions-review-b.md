# Task 8 独立质量审查（Review B）

结论：**CHANGES_REQUIRED**

本次审查独立阅读了 Task 8 计划、未提交 diff、真实 Django 动作 API 和 React 生产代码。没有修改生产代码，也没有提交。现有定向测试与构建是绿色的，但以下问题会让账务动作以错误业务日期入账，或让操作者确认与界面当前输入不一致，因此不能批准。

## 发现的问题

### 1. P1：换汇和费用默认日期使用 UTC，而不是业务时区

- 文件：[frontend/src/components/accounting/ExchangeAction.tsx](../../frontend/src/components/accounting/ExchangeAction.tsx:24-25)、[frontend/src/components/accounting/ExpenseAction.tsx](../../frontend/src/components/accounting/ExpenseAction.tsx:25-34)、[frontend/src/components/accounting/AccountingActionCenter.tsx](../../frontend/src/components/accounting/AccountingActionCenter.tsx:38-97)
- 复现：在莫斯科时间 00:30 打开 `/accounting`，动作中心正常显示。换汇和费用卡的日期由 `new Date().toISOString().slice(0, 10)` 初始化；此时 UTC 仍是前一天，提交即可把本日动作写成前一业务日。工作台虽然已经收到 `businessDate={moscowBusinessDate()}`，却没有传给这两张卡。
- 影响：换汇/费用的账务事实、月利润和对账归属可能跨日/月，且用户没有明显提示。
- 建议：两张卡接收工作台的 Moscow business date，或统一调用已有 `moscowBusinessDate()`；不要用 UTC ISO 日期作为默认业务日期。补充跨 UTC 日界的组件测试。

### 2. P1：分红表单可在未保存编辑时预览并确认旧草稿

- 文件：[frontend/src/components/accounting/DividendAction.tsx](../../frontend/src/components/accounting/DividendAction.tsx:104-159)
- 复现：已有草稿总额为 `1000.00`；把“总额”改为 `2000.00`，不点击“保存分红编辑”，直接点击“预览”。`previewAction()` 只把 `draft.id` 传给后端，后端按数据库中的 `1000.00` 生成 preview/fingerprint；界面仍显示用户刚输入的 `2000.00`。随后确认按钮使用旧 preview 的 fingerprint 和旧 `draft.version`，实际可能确认数据库旧金额，而用户看到的是新金额。
- 同类问题：已经有 preview 后再修改总额、两位金额或账户，旧 preview 仍保留；确认不检查表单是否 dirty，也没有因输入改变而清除 preview。
- 影响：分红是资金动作，界面金额和最终入账金额可能不一致；warning fingerprint 只保护利润变化，不保护未保存表单状态。
- 建议：表单 dirty 时禁用预览/确认并提示先保存，或预览请求携带并校验当前编辑值且成功后以返回草稿覆盖输入；任何金额、账户、日期变化都应清空旧 preview 与 acknowledgement。

### 3. P1：账户列表变化后仍可能提交 stale account id

- 文件：[frontend/src/components/accounting/ExchangeAction.tsx](../../frontend/src/components/accounting/ExchangeAction.tsx:38-63)、[frontend/src/components/accounting/PurchaseAction.tsx](../../frontend/src/components/accounting/PurchaseAction.tsx:78-127)、[frontend/src/components/accounting/DividendAction.tsx](../../frontend/src/components/accounting/DividendAction.tsx:90-136)
- 复现 A（换汇）：选择一个 CNY/USDT 或 RUB 账户；在另一窗口停用该账户并刷新动作数据（或父组件传入不再包含该账户的数组）。`sourceId`/`rubId` 仍取旧输入，提交只检查是否为 truthy，不检查是否属于当前 active、正确币种账户。
- 复现 B（采购）：选择 RUB 账户后账户被停用，`input.accountId` 仍为旧 id；`pay()` 只检查非空即调用付款 API。
- 复现 C（分红）：两个下拉框允许同一个 CNY 账户，空值也会被 `Number('')` 变成 `0` 发给后端；没有前端的 active/CNY/不同账户校验。后端会拒绝 `account_same`/`account_required`，但这只能在提交后发现，且同账户选项违反该动作的业务规则。
- 影响：会把显然无效的资金账户提交到正式 API；分红的关键“两个不同人民币账户”约束没有在操作界面体现。后端防护仍在，但不能替代前端的 stale selection 防护和可操作错误提示。
- 建议：提交前按当前账户集合、active 状态和币种重新验证；账户不再可用时清空并要求重选。分红禁止 B 选择 A，并在金额/账户编辑时清空 preview/ack。

### 4. P2：动作中心资产构成在账户查询完成后丢失余额

- 文件：[frontend/src/pages/AccountingDashboardPage.tsx](../../frontend/src/pages/AccountingDashboardPage.tsx:18-24,46-55)、[frontend/src/api.ts](../../frontend/src/api.ts:140-141)、[frontend/src/components/accounting/AccountingActionCenter.tsx](../../frontend/src/components/accounting/AccountingActionCenter.tsx:22-29,54-83)
- 复现：Day 1 完成后打开 `/accounting`。dashboard 响应中的 `accounts` 含 `original_balance`/`cny_book_cost`，但独立 `GET /accounting/accounts/` 只由 `serialize_account()` 返回基础字段。账户 query 完成后，`accounts.data || data.accounts` 选择了不含余额的数组（空数组也是真值），动作中心因此显示“当前接口未提供余额，不在此处推算”，而不是资产构成。
- 影响：方案 C 元素/动作中心的资产摘要在正常加载完成后反而不可用；下方 AccountingPanel 仍可用自己的 summary，因此这是展示数据源错误而非账务事实错误。
- 建议：动作中心明确使用 dashboard 快照账户余额，或让 accounts endpoint 返回 snapshot 字段；不要用空/无余额的基础账户数组覆盖已有快照。

## 已执行验证

- `frontend`: `npm test -- --run src/api/accountingActions.test.ts src/features/accounting/actionState.test.ts src/features/guides/guideFocusController.test.ts src/features/guides/guideInteractions.test.ts src/features/guides/ContextTour.test.tsx src/components/accounting`：33/33 通过。
- `frontend`: `npm run lint`：通过。
- `frontend`: `npm run build`：通过；仅有现有 bundle size warning。
- Django：`accounting.tests.test_action_api accounting.tests.test_purchase_actions accounting.tests.test_dividend_actions`：37/37 通过。

测试绿不能覆盖上述问题：现有动作卡测试全部是 `renderToStaticMarkup`，没有验证日期时区、账户集合变化、dirty preview 或真实按钮提交状态；这正是本审查要求的交互边界。

## Remediation and re-review

复审确认初审四项均已修复：

- 换汇与费用动作统一使用工作台传入的 Moscow business date，不再以 UTC ISO 日期作为默认业务日期。
- 分红草稿编辑会标记 dirty；未保存时禁止预览/确认，保存后预览绑定当前草稿版本，旧 preview 与 acknowledgement 不会继续沿用。
- 换汇、采购和分红提交前会按当前 active 账户及币种重新校验 stale id；分红两个 CNY 账户的选择项最终互斥，并保留后端重复账户校验。
- 动作中心资产摘要继续使用 dashboard snapshot 的余额字段，不会被基础账户查询结果覆盖；采购 nullable 盒数/包装待复核时显示待复核，不作 `0` 推算，并由 packaging gate 阻止错误付款/到货。

随后独立复审真实提交路径、状态转换、API payload、React hooks/closure、引导按钮和辅助函数使用情况，未发现新的 blocker。最终验证：前端定向测试 **140/140** 通过，`npm run lint` 通过，`npm run build` 通过（仅非阻断 bundle size warning）。

最终结论：**APPROVED**。


## Task 9 total quality review

结论：**CHANGES_REQUIRED**

本轮审查从 `main...95c7fa2` 重新阅读了 Tasks 1–8 的全部后端、迁移、React、两份规格/上下文和计划，没有依赖前一轮结论。未修改生产代码；只运行了定向后端回归（62/62 通过）和 `git diff --check`。测试绿色不能覆盖以下真实业务边界：

### 1. P1：确认销售草稿会清零已经收取的客户人肉费

- 文件：[cigars/services.py](../../cigars/services.py:844-855)，入口：[cigars/sales_api.py](../../cigars/sales_api.py:250-265)
- 复现：通过创建销售草稿传入 `customer_transport_fee_cny='30.00'`（默认/显式 `transport_payer='customer'`），草稿的 `amount_due_cny` 为商品金额 + 30；调用确认接口后，`confirm_sales_order()` 无条件把 `customer_transport_fee_cny` 设为 `0.00`，并把 `amount_due_cny` 改成商品金额。之后收款、出库和收入 posting 都少记 30 元，客户实际应付金额与账务事实不一致。
- 影响：客户承担的人肉费在确认这个正常状态转换中丢失，直接造成销售收入/应收和退款金额错误；这也使本轮新增的 `transport_payer` 字段不能贯穿销售生命周期。
- 建议：确认时保留草稿中的运费与 `transport_payer`，以商品金额 + 客户运费重新计算 `amount_due_cny`；只有明确把承担方改为公司时才将客户收费置零，并补充“创建含客户运费 → 确认 → 收款/出库”回归测试。

### 2. P1：销售动作默认业务日期使用浏览器本地时区而非 Moscow business date

- 文件：[frontend/src/components/sales/SalesOrderCard.tsx](../../frontend/src/components/sales/SalesOrderCard.tsx:8,14)
- 复现：在非 Moscow 时区的浏览器（例如 UTC−5）于 Moscow 次日凌晨打开订单详情；`today()` 依据浏览器 `getTimezoneOffset()` 初始化日期。执行出库、收款、退款或人肉成本时，默认日期可能仍是前一业务日。服务器按该 payload 写入 ledger 的 `business_date`，没有把它纠正为 Moscow 日。
- 影响：销售收入、退款和运输费用可跨日/月归属，导致月利润与对账错期；这是生产销售页的默认路径，不只是孤立组件测试问题。
- 建议：复用前端已有的 Moscow business date helper，并在订单动作卡初始化/跨日时更新；增加跨 UTC 日界的销售动作测试。

### 3. P2：销售动作卡在账户列表变化后仍提交已停用的 stale account id

- 文件：[frontend/src/components/sales/SalesOrderCard.tsx](../../frontend/src/components/sales/SalesOrderCard.tsx:11,17-22,31-33)
- 复现：打开收款或人肉成本表单并选中 CNY 账户 A；另一窗口停用 A，React query 刷新 `allAccounts` 后 A 从 `accounts` 消失。组件的 effect 只在 `!accountId` 时设置默认值，不会清空/替换已有的 `accountId`；点击执行仍把旧 ID 发给 API。
- 影响：后端会拒绝停用账户，所以目前不会直接扣错账户，但操作者只能得到提交后的失败，且表单保留了一个不可见的无效选择；这违反动作中心 stale ID 防护契约并增加误重试风险。
- 建议：账户集合变化时验证当前 ID 是否仍是 active CNY，失效即切换到可用账户或清空并阻止提交；提交前再次按当前列表校验。

### 4. P2：动作卡可选默认日期的组件 API 仍回退到 UTC ISO 日期

- 文件：[frontend/src/components/accounting/ExchangeAction.tsx](../../frontend/src/components/accounting/ExchangeAction.tsx:25,38)、[frontend/src/components/accounting/ExpenseAction.tsx](../../frontend/src/components/accounting/ExpenseAction.tsx:26,33)
- 复现：直接复用任一动作卡而未传 `businessDate`（现有组件 props 允许省略），在 Moscow 00:30 打开时，`new Date().toISOString().slice(0, 10)` 仍是 UTC 前一天。当前工作台恰好传入 Moscow 日期，但这个公开组件默认仍会产生错误业务日期，且单元测试未覆盖。
- 影响：未来/其他入口若省略 prop，会把换汇或费用跨日入账；日期边界约束分散且容易回归。
- 建议：移除 UTC fallback，统一调用已有 `moscowBusinessDate()`，并增加 prop 省略时的跨时区测试。

## 验证

- `.venv/bin/python manage.py test accounting.tests.test_purchase_actions accounting.tests.test_purchase_draft_actions accounting.tests.test_dividend_actions cigars.tests.test_sales_refund_transport cigars.tests.test_sales_transport_payer -v 1`：62/62 通过。
- `git diff --check main...95c7fa2`：通过。

上述问题均未被现有定向测试覆盖；其中第 1、2 项会改变正式销售金额或账务日期，因此本轮不能批准。

## Task 9 remediation re-review

结论：**CHANGES_REQUIRED**

本轮独立复核了当前全部未提交后端、前端、迁移与测试变更。客户人肉费保留、Moscow 默认业务日期、销售 stale CNY 账户、换汇/费用 UTC fallback、在途付款业务日期，以及通用/opening ledger replay 完整参数核对均已修复；库存调整借贷符号和月利润 gain/loss 方向也一致。未发现为接受旧错误而删除或削弱断言，但仍有以下阻塞项：

### 1. P1：库存调整同 key 并发仍可能重复改变库存，且 replay 不返回原调整批次

- 文件：[cigars/services.py](../../cigars/services.py:1027-1076)、[cigars/services.py](../../cigars/services.py:1088-1195)。
- `adjust_stock()` 在取得 ledger writer gate 之前先查询幂等交易，随后才锁/修改 `PurchaseBatch`；`StockMovement.idempotency_key` 只有普通索引，没有唯一约束。两个相同 key 的请求都在首笔 ledger 提交前 miss 时，第二个请求可在批次锁释放后再次扣减/增加库存；若单位成本未变，末尾 `_post_transaction_once()` 会把既有相同 posting 当作合法 replay，于是只保留一笔 ledger、却提交两次库存变化。该服务也没有按计划套 `_retry_sqlite_locked`，SQLite 竞争会退化为不稳定锁错误。
- 顺序 replay 也不绑定原结果：`batch_id` 为空时直接返回该雪茄当前 `order_by('-id').first()`。首次盘盈后若又产生更晚批次，重放首个 key 会返回后一个批次，响应事实与第一次不同。
- 修复要求：在任何库存读取/修改前取得统一 writer gate 并按 key 锁定持久化的库存调整事实；匹配重放返回原关联批次/调整结果，参数不同稳定 `idempotency_conflict`；补同 key 并发及“后续批次存在后 replay”测试。

### 2. P1：新加的 Day 1 gate 在 legacy agent HTTP 入口变成 500

- 文件：[cigars/agent_api.py](../../cigars/agent_api.py:137-220)、[cigars/agent_api.py](../../cigars/agent_api.py:410-495)，服务 gate 位于 `cigars/services.py:768,947,1034`。
- `_idempotent_command()` 不捕获 `Day1IncompleteError` 或 `LedgerError`，因此本轮为 legacy 销售创建/取消、库存调整加入的 service gate 会逃出视图。
- 真实入口复现（临时测试库）：Day 1 未完成时 POST `/api/agent/orders/create/`，带合法 staff、agent 和幂等键，实际响应 **500**，契约要求 **409** 且 `code=day1_incomplete`。库存调整的 ledger 幂等冲突也存在同类 500 路径。
- 修复要求：统一映射 `Day1IncompleteError`/`LedgerError` 为稳定 `{error, code, details}`，`day1_incomplete` 与 `idempotency_conflict` 返回 409，并增加三个新 gate 入口的 HTTP 契约测试。

### 3. P2：正式库存调整仍允许空原因

- 文件：[cigars/services.py](../../cigars/services.py:1027-1035)、[cigars/agent_api.py](../../cigars/agent_api.py:477-486)。
- service 的 `reason=''` 是合法默认值，agent 入口也把缺失原因规范成空串；空原因随后进入 ledger description、StockMovement note 和 AdjustmentRecord.reason，违反内部账规格 §11.2 与原 review-a 的修复要求。
- 修复要求：库存变动前拒绝空白原因，并补 service/API 测试，确认失败无库存、成本池、movement、adjustment record 或 ledger 残留。

验证证据：后端修复/ledger/销售定向 **63/63** 通过；在途汇总、利润、迁移与 agent 库存模块 **66/66** 通过；前端日期/stale 账户定向 **10/10** 通过；`git diff --check` 通过；`manage.py makemigrations --check --dry-run` 输出 `No changes detected`。临时 HTTP 契约测试暴露 500（失败断言 `500 != 409`）。

最终结论：**CHANGES_REQUIRED**。以上三项修复并补齐回归前，Task 9 不能 APPROVED。

## Task 9 final re-review

结论：**APPROVED**

本轮在上一轮三个 blocker 修复后重新阅读当前完整未提交 diff，并复核生产路径、迁移和测试变更；未修改生产代码或测试，未提交。

### 上一轮三个 blocker 关闭证据

- 库存调整 exactly-once：`adjust_stock()` 现在由 `_retry_sqlite_locked` 包裹，并在任何幂等查询、批次锁定或库存修改前取得统一 ledger writer gate；同 key 并发会串行观察同一事实。相同参数 replay 返回同一批次，参数不同抛稳定 `idempotency_conflict`；定向并发测试同时断言批次只扣一次、仅一条 `StockMovement`、仅一笔 ledger。
- 原批次 replay：ledger `source_id` 持久化规范化请求指纹和实际返回批次 ID；未指定 `batch_id` 且跨多个 FIFO 批次时，后续 replay 从该来源事实解析原结果批次，不再按当前最新主键猜测。回归测试刻意让 FIFO 顺序与主键顺序相反，首次结果与 replay 主键一致。
- Legacy agent 错误契约：`_idempotent_command()` 在 canonical 与 legacy 两条分支均映射 `Day1IncompleteError`/`LedgerError`；`day1_incomplete`、`idempotency_conflict` 返回 409 JSON。Day 1 失败响应写入 `IdempotencyRecord`，同 body 重放保持相同 409 body/status，不会在 Day 1 状态变化后意外执行旧请求。
- 空原因无业务残留：service 在 Day 1 gate、writer gate、批次查询和任何库存/成本写入之前规范化并拒绝空白 reason。测试验证批次数量不变且无 ledger/`StockMovement`；按控制流也不会创建 `AdjustmentRecord` 或改变成本池。API 返回可重放的 400 业务错误，只有预期的幂等错误记录，不产生经营事实。

### 原 Task 9 八项 blocker 回归状态

- 库存调整已生成平衡的正式 ledger，盘盈/盘亏符号与月利润 gain/loss 公式一致；在途汇总使用 `PurchasePayment.business_date`；generic/opening replay 核对类型、日期、operator、metadata 与完整 posting，并发唯一键冲突也复核参数。
- 销售确认/取消、legacy 销售及库存服务维持 Day 1 gate；客户承担的人肉费在草稿确认及 legacy 创建中保留，`amount_due_cny` 为商品金额加客户费用。
- 销售动作、换汇和费用 fallback 均使用 Moscow business date；销售账户刷新与提交前均重新验证 active CNY，旧 stale ID 不会发送。
- 旧测试没有被删除或改成接受错误行为：在途 fixture 改为经真实付款服务生成 `PurchasePayment`，原 opening 错误 replay 预期改为“相同参数成功、不同参数冲突”，其余删除行均由更强断言或 Day 1 合法 fixture 替代。

### 验证

- 已有全量证据：后端 **448/448**，前端 **144/144**，lint/build 通过。
- 本轮独立定向后端：Task 9 修复、agent API、库存并发与 ledger operations 共 **52/52** 通过。
- 本轮独立定向前端：Moscow 日期与 stale 账户共 **10/10** 通过。
- `git diff --check` 通过；`manage.py makemigrations --check --dry-run` 输出 `No changes detected`。

最终结论：**APPROVED**。上一轮三个 blocker 与此前八项 blocker 均已关闭，未发现新的合并阻塞项。
