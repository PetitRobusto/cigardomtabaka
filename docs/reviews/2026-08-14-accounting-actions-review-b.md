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
