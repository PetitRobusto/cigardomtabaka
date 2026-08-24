# Task 8 规格审查 A

审查对象：`feature/business-workspace-day1` 当前 Task 8 未提交变更（只读审查，未修改生产代码）。

审查依据：

- `docs/superpowers/plans/2026-08-14-accounting-actions.md` 的 Task 8
- `docs/superpowers/specs/2026-08-10-internal-accounting-module-design.md`
- `docs/superpowers/specs/2026-08-13-business-workspace-day1-design.md`
- `docs/CONTEXT.md`
- 当前真实 `accounting/urls.py`、`accounting/views.py`、`accounting/action_serializers.py`、动作 service

## OpenDesign evidence

- 原型文件：`.opendesign/accounting-action-center.html`（当前被 `.gitignore` 忽略，若要把原型证据随提交保存，需要显式 `git add -f .opendesign/accounting-action-center.html`）。
- 原型包含 URL `?variant=A|B|C` 三个结构明显不同的变体，并有浮动切换栏：A 为全宽双列动作卡工作台，B 为流程队列，C 为资产构成/费用分类摘要。
- 本地静态检查确认设计 token 存在且与批准 token 一致：`--cream: #FAF8F5`、`--fg: #2C2416`、`--muted: #8A7E6E`、`--border: #E8E0D6`、`--accent: #7A1F2E`、`--accent-light: #F5EFE8`、`--gold: #B87A3A`；1480px 全宽容器和 650px 移动端纵向断点存在。
- 原型脚本提供 normal、Day 1 waiting、warning 三种状态；Day 1 状态禁用动作控件，warning 状态在费用卡显示局部复核提示；假动作只更新本地 toast/feedback，不调用真实 API。
- 采用方案：生产页面吸收 A 的四卡工作台结构，并加入 C 的资产构成与费用分类摘要；没有把 throwaway 原型代码直接复制为生产逻辑。
- 手工/静态验证命令：`rg -n "variant=A|variant=B|variant=C|data-state=" .opendesign/accounting-action-center.html`、`rg -n -- "--cream: #FAF8F5|--accent: #7A1F2E|1480px|650px" .opendesign/accounting-action-center.html`、`rg -n "data-day1-disabled|warning-box|仅原型演示" .opendesign/accounting-action-center.html`。未调用 OpenDesign MCP（当前工具面没有该 MCP），以本地原型和脚本证据替代。

## 已核对并通过

- `AccountingDashboardPage` 先渲染四张 stats，再渲染 Day 1 卡或动作中心；Day 1 未完成不会渲染正式动作，且 `dashboardStatDisplay` 将 null 显示为 `—`。
- 动作列表使用独立 TanStack Query key `['accounting-actions']`，动作列表失败只显示在动作中心，不覆盖 dashboard/accounts/summary/profit/reconciliation 快照。
- 换汇请求限定 CNY/USDT → RUB；采购请求限定单次付款、在途整单到货和草稿取消；费用按 salary→CNY、rent/utilities/other→RUB；分红具备 create、update、preview、warning acknowledgement、confirm。
- 所有写 helper 通过 `writeWithIdempotency()` 发送 `Idempotency-Key`；金额字段在新增类型中以 Decimal string 表达。真实 endpoint/response 与后端路由、serializer 对齐：`/accounting/actions/`、`/accounting/exchanges/`、`/accounting/purchases/...`、`/accounting/expenses/`、`/accounting/dividends/...`。
- 四张卡有局部 loading/success/error/conflict 状态，失败路径不清空输入；采购动作按采购单隔离状态。引导 target 放在 `tabIndex={-1}` 的 section，不放 submit button；focus controller 只描述 focus/restore，不触发 click/submit。
- 定向验证通过：后端 `accounting.tests.test_action_api accounting.tests.test_error_contract` 共 17 tests OK；前端 Task 8 定向测试 10 files / 33 tests OK；`npm run lint` OK；`npm run build` OK（仅已有/非阻断 chunk size warning）。

## CHANGES_REQUIRED

### 1. [严重度：高] 采购 nullable 盒数被错误渲染为 0，违反“null 不作 0”并掩盖包装复核

- 文件/行号：`frontend/src/components/accounting/PurchaseAction.tsx:162`；对应类型 `frontend/src/types.ts:740-741`。
- 问题：后端 `PurchaseOrderItem.box_size`/`box_quantity` 是 nullable，`review_required` 采购行真实返回 null；组件使用 `item.box_quantity || 0` 聚合并显示“canonical 盒数：0 盒”，同时 TypeScript 类型把两个字段声明成非空 number。`itemTotal()` 会返回 `—`，说明同一行实际是未知/需复核，但摘要却伪造为零。
- 复现：让 `/api/accounting/actions/` 返回一个 `packaging_status: "review_required"`、`box_size: null`、`box_quantity: null` 的 draft，打开账务工作台；采购卡显示 `canonical 盒数：0 盒`，点击付款后后端只能返回 `packaging_review_required`。用户会把未知包装误认为零盒，并且没有前端提示复核。
- 修复要求：类型改为 nullable；聚合结果只要任一 canonical 字段未知就显示 `—/待人工复核`，不得使用 `|| 0`；付款按钮应在包装未规范化时禁用或明确展示后端复核原因，并保留输入。

### 2. [严重度：中] 换汇和费用的默认业务日期使用 UTC，而不是莫斯科业务日期

- 文件/行号：`frontend/src/components/accounting/ExchangeAction.tsx:24-25`、`frontend/src/components/accounting/ExpenseAction.tsx:25,34`；调用处 `frontend/src/components/accounting/AccountingActionCenter.tsx:94,96`。
- 问题：两个动作卡用 `new Date().toISOString().slice(0, 10)` 初始化日期。项目约定业务日期使用 Europe/Moscow；动作中心已有正确的 `businessDate`，但没有传给这两张卡。
- 复现：在 23:30 UTC（次日 02:30 Moscow）首次打开账务工作台，换汇/费用表单默认显示 UTC 当日日期，而采购/分红显示 Moscow 日期；不修改日期直接提交会把流水记到错误自然月/业务日。
- 修复要求：从动作中心传入 `moscowBusinessDate()` 计算出的 `businessDate`，或统一复用现有 business-date helper；不要用浏览器 UTC ISO 截断作为默认业务日。

### 3. [严重度：高] 分红修改输入后可直接 Preview，预览和确认针对旧草稿事实

- 文件/行号：`frontend/src/components/accounting/DividendAction.tsx:104,131-147,149-159,161-174`。
- 问题：用户修改总额、两位合伙人金额或账户后，必须先点击“保存分红编辑”才会把输入写入后端；但“预览”按钮始终可点击，`previewAction()` 只调用 `onPreview(draft.id)`，不会提交当前 input。随后页面仍显示用户刚改的 input，却把后端旧草稿的 warning/fingerprint 放入确认请求，造成“屏幕上的金额”和“实际确认的金额”不一致。
- 复现：已有草稿总额 1000；把总额改成 2000，不点“保存分红编辑”，直接点“预览”并确认 warning。preview/confirm 的后端事实仍是 1000，而输入框显示 2000；刷新后恢复 1000。该路径不会必然报错，因此不是普通网络错误可见的失败。
- 修复要求：预览前强制保存当前编辑（使用同一版本/幂等流程），或检测 dirty 状态禁用预览并提示先保存；preview 成功后确认摘要必须绑定已保存版本和金额，不能只绑定 UI input。

### 4. [严重度：中] 分红两个 CNY 账户选择器允许选择同一账户，缺少前端规则提示

- 文件/行号：`frontend/src/components/accounting/DividendAction.tsx:90,187-188`。
- 问题：A/B 两个 `<select>` 都渲染完整 CNY 账户列表，没有禁用已被另一栏选中的账户，也没有在提交前检查 `accountA !== accountB`。后端会返回 `account_same`，但用户只能在提交后得到错误，无法完成“两个合伙人分别从不同人民币账户领取”的正常表单契约。
- 复现：两个账户均存在时，A/B 都选同一个账户，点击“保存分红编辑”；请求发送重复 account id，后端返回 409/`account_same`。
- 修复要求：前端在选项层排除另一栏账户并在 update 前给出字段级错误；后端校验仍须保留。

## 结论

**CHANGES_REQUIRED**。当前 Task 8 的布局、门禁、真实 API 边界、Decimal 字符串、局部错误隔离和引导 focus 结构总体符合规格，且自动验证全部通过；但上述第 1、3 项会造成账务 UI 显示/确认事实不一致，必须修复并由另一位 Luna 对修复 SHA 复审后才能 APPROVED。第 2、4 项也应在同一轮修复中处理。

## Remediation and re-review

- 采购 nullable 盒数：`PurchaseAction` 与 `PurchaseActionItem` 已按 nullable canonical 字段处理；`box_quantity` 为 `null` 或 `review_required` 时显示“待复核”，不再渲染 `0 盒`，并明确提示后端 packaging gate 会阻止付款/到货。
- 莫斯科业务日期：`AccountingDashboardPage` 计算 Moscow `businessDate` 并注入 `AccountingActionCenter`；换汇、费用、采购和分红动作卡统一使用该日期，不再依赖 UTC ISO 截断作为工作台默认日期。
- 分红 dirty/版本/指纹：分红编辑变更后预览和确认均被门禁，必须先保存；保存成功会重置旧 preview、fingerprint acknowledgement 和版本基线；确认要求 preview 对应当前 draft version，并携带当前 warning fingerprint。
- 分红账户互斥：最后修复补充 `dividendAccountOptions`，A 下拉禁用 B 当前选择的账户，B 下拉禁用 A 当前选择的账户，同时保留 active/CNY/不同账户的提交前校验；新增 TDD 测试覆盖互斥选项。
- stale/inactive 账户与 dashboard 摘要：换汇、费用、采购和分红提交前均按当前 active、币种账户集合重新解析/校验；动作中心优先保留 dashboard `summaryAccounts` 的余额快照，避免基础账户查询覆盖资产摘要。

复审验证：前端全量测试 **140/140** 通过；`npm run lint` 通过；`npm run build` 通过（仅已有非阻断 chunk size warning）。逐项复核确认上述问题均已关闭，Task 8 最终结论：**APPROVED**。


## Task 9 total specification review

审查对象：`feature/business-workspace-day1` 当前 Task 9 账务动作与经营事实闭环实现；审查依据为 Task 9 计划及两份 accounting/Day 1 规格。

### CHANGES_REQUIRED

### 1. [高] 库存调整没有正式账务流水、调整损益或 Day 1 gate

- 文件：`cigars/services.py:992-1117` 的 `adjust_stock`；正向调整在 1041-1050 直接返回，负向调整在 1097-1115 仅写 `StockMovement`/`AdjustmentRecord`，两条路径均未创建 `LedgerTransaction`/`LedgerPosting`，也没有业务日期。
- 复现：调整有成本批次后，`PurchaseBatch.remaining_cost_cny` 变化，但 ledger transaction 数量和 `monthly_profit` 的 `inventory_adjustment_loss` 不变；Day 1 未完成时 `cigars/agent_api.py:460-480` 仍可调用该 service 修改批次。
- 规格依据：库存调整必须生成正式流水，盘亏进入当月调整损失、盘盈形成调整收益（内部账务规格 §11.2、§12.1）；Day 1 完成前不得产生正式经营事实。
- 修复要求：正负调整原子写入统一 ledger writer，保存业务日期、原因、操作人、来源和幂等事实，并在所有 API/service 入口执行 Day 1 gate。

### 2. [高] 在途资产按 `PurchaseOrder.paid_at` 推导业务日期

- 文件：`accounting/selectors.py:198-203`。汇总使用 `TruncDate('paid_at', tzinfo=ZoneInfo('Europe/Moscow'))`，而真实付款事实的显式日期是 `accounting.PurchasePayment.business_date`（`accounting/models.py:597-610`）。
- 复现：付款 `business_date=2026-08-10`、服务器创建/付款时间为 2026-08-15 时，`accounting_summary(as_of=2026-08-10)` 排除在途金额，查询 8 月 15 日才出现。
- 规格依据：余额和月报必须按真实业务日期自然月汇总，不依赖服务器创建时间（内部账务规格 §4.3）。
- 修复要求：通过已入账 `PurchasePayment.business_date` 过滤在途，并补跨日回归测试。

### 3. [中高] 通用 ledger/opening replay 不核对完整参数

- 文件：`accounting/services.py:317-337` 的 `_post_transaction_once`、591-603 的 `_record_opening_balance`。相同 key 被发现后在解析 postings、账户、金额、权益分类和 operator 前直接返回旧交易。
- 复现：第一次用账户 A/金额 100 创建 opening；第二次复用 key 改账户 B/金额 1，service 仍返回第一次事实，不报 `idempotency_conflict`；通用 posting 也可同样静默 replay。
- 规格依据：所有写操作按幂等键不得重复记账，参数不同必须冲突而不能静默解释为旧动作（内部账务规格 §11.4、Task 9 幂等契约）。
- 修复要求：规范化并比较 transaction type、business date、operator、description/source 和完整 posting；不一致统一抛稳定 `idempotency_conflict`，opening 另核对账户、权益分类及两种金额。

### 4. [中高] 销售确认/取消、legacy 销售及库存入口缺少 Day 1 gate

- 文件：`cigars/services.py:570-607`、610-640、753-800、992-999；HTTP 入口 `cigars/sales_api.py:250-283`、`cigars/agent_api.py:402-419,460-480` 直接转发。
- 问题：`confirm_sales_order` 会预留库存，legacy `create_sales_order` 会立即创建 pending order 并预留库存，取消会释放正式预留，库存 API 会修改批次，但这些 service 没有调用 `require_day1_completed()`。
- 复现：没有 `Day1Initialization(status=completed)` 时，创建/确认销售单仍产生 `StockAllocation`/`StockMovement`，`adjust_stock_command` 仍改变 `PurchaseBatch`。
- 规格依据：Day 1 规格 §5.1、§6 要求完成前不产生正式经营事实；销售确认流程才允许预留库存。
- 修复要求：正式订单履约、预留/释放库存、批次修改的 service 边界统一 gate；允许保存的草稿必须不预留库存、不写正式库存移动。

### 结论

**CHANGES_REQUIRED**。Task 9 不能标记 APPROVED；上述四项必须修复并由另一位审查代理复核。


## Task 9 remediation re-review

本轮只复核 review-a 与 review-b 的 Task 9 八项发现及对应测试，不修改生产代码、不提交。

- 库存调整：`adjust_stock()` 现先执行 Day 1 gate，接收显式业务日期，并在同一 `transaction.atomic` 内更新批次、库存移动/调整记录和 `INVENTORY_ADJUSTMENT` 双分录。正向写库存资产与调整收益，负向按实际移出成本合计写库存资产与调整损失；任一步失败会整体回滚。请求参数经数值/JSON 规范化后生成固定 64 位摘要，重放核对业务日期、操作人、说明、来源和完整参数；同 key 同参数无副作用返回，不同成本/类型等返回 `idempotency_conflict`。
- 在途业务日期：`accounting_summary()` 已通过 posted `PurchasePayment.business_date <= as_of` 选择在途采购，不再从服务器 `paid_at` 推导。跨日测试直接创建真实付款事实并覆盖该口径。
- 通用/opening replay：`_post_transaction_once()` 在返回旧事实前比较类型、posted 状态、业务日期、operator、规范化 description/source 及完整 posting multiset；opening 同样重建并比较账户、原币金额、CNY 成本和权益分类。相同请求在操作员失去 staff 或账户停用后仍可稳定重放，参数变化稳定返回 `idempotency_conflict`。
- Day 1 service gate：销售确认、确认后取消、legacy 即时销售、legacy 取消、拆盒及库存调整均在 service 边界调用 `require_day1_completed()`；销售草稿仍可创建但不会预留库存，符合“完成前只允许草稿”的边界。
- 客户人肉费：销售草稿确认不再覆盖 `customer_transport_fee_cny`/`transport_payer`/`amount_due_cny`；legacy agent 创建入口也接收并保存承担方与费用。回归覆盖 20 元商品 + 30 元客户人肉费确认后应收 50 元。
- Moscow 日期与 stale 账户：销售动作、换汇和费用的默认日期统一使用 `moscowBusinessDate()`；省略 accounting 卡片日期 prop 的路径也不再回退 UTC。销售账户刷新后只保留 active CNY，提交前再次核对当前账户集合；Task 8 已复核的换汇/采购/分红 stale 账户保护保持不变。
- 测试完整性：原测试未被删除；既有销售/库存测试仅补 Day 1 completed fixture 以适配新增正式动作门禁。opening 旧的宽松 replay 期望改为“同参数返回原事实、不同参数冲突”，属于强化契约。新增库存正负损益、原子重放、规范化摘要、参数冲突、付款业务日期、正式动作门禁、客户人肉费及前端跨时区/stale 账户覆盖。

验证：项目已提供后端全量 **442/442**、前端全量 **144/144**、lint/build 通过证据。本轮另跑后端定向 `accounting.tests.test_task9_backend_fixes accounting.tests.test_operations cigars.tests.test_sales_order_workflow` 共 **41/41** 通过；前端定向 3 files / **10/10** 通过；`git diff --check` 通过。

最终结论：**APPROVED**。review-a 与 review-b 的 Task 9 八项问题均已关闭，未发现残余规格 blocker。


## Task 9 final re-review

本轮基于当前最终 diff 重新审查，不沿用上一轮 APPROVED；范围限定为第三轮库存调整并发/重放、Agent API 错误契约，以及对前八项修复的回归影响。未修改生产代码或测试，未提交。

- exactly-once：`adjust_stock` 的 `_retry_sqlite_locked` 包住完整 `transaction.atomic`，每次尝试先调用统一 `_acquire_sqlite_writer_gate()`。SQLite 下 writer gate 对 `LedgerSequence` 执行不递增序号的等值写，空检查、批次锁定/修改、库存移动和 ledger posting 因而处于同一个串行化写事务；锁冲突重试的是整个事务，不会只重放半段副作用。并发同 key 只产生一个 ledger 和一个 `StockMovement`；不同 body 同 key 恰好一方成功、另一方稳定 `idempotency_conflict`。
- ledger 并发边界：统一 writer gate 现在包括 sequence 首次创建后的每次写尝试；`_post_transaction_once` 的唯一键竞态兜底也执行完整交易/posting 参数比对，不会把不同并发请求静默当作成功，且等值 gate 不消耗 `effective_sequence`。
- result batch 绑定：库存调整 `source_id` 固化为 `stock_adjustment:<规范化请求 SHA-256>:<实际返回批次 id>`，长度在 128 字段范围内。重放解析不可变 source，核对摘要、业务日期、operator、reason、来源、雪茄及显式 batch，返回原 result batch；不再根据“最新主键”猜测。跨两个 FIFO 批次且不传 batch_id 的回归证明重放返回首次实际最后处理的批次。
- 输入与原子性：reason 先 trim 并在 writer gate/批次读取前拒绝空值；空原因不会产生批次变化、移动或 ledger。业务日期、成本和库存形态仍进入原有规范化/ledger 校验；账务失败继续由外层原子事务整体回滚。
- Agent API：canonical/non-canonical 及事务外兜底路径均显式捕获 `Day1IncompleteError` 和 `LedgerError`，输出含 `error/code/details` 的 JSON；`day1_incomplete`、`idempotency_conflict` 为 409，其余 ledger 错误为 400。失败响应连同状态码写入 `IdempotencyRecord`，相同请求重放相同 JSON/HTTP 状态；空原因返回 400 JSON 且无库存副作用。
- 回归检查：PurchasePayment 显式业务日期、通用/opening 完整 replay、销售/拆盒/库存 Day1 gate、客户人肉费、Moscow 默认日期和 stale 账户修复均仍保留。第三轮只强化 writer gate、库存 replay 结果和 API 错误映射，没有删除或放宽前述保护。

验证：最终全量证据为后端 **448/448**、前端 **144/144**、lint/build 通过。本轮另跑 `accounting.tests.test_task9_backend_fixes`、`StockAdjustmentConcurrencyTest`、`AgentCommandApiTest`，共 **22/22** 通过。

最终结论：**APPROVED**。第三轮 exactly-once、原结果批次绑定、空原因和 Agent API 错误重放均满足规格，前八项修复未被破坏，未发现残余 blocker。
