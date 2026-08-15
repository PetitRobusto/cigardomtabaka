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
