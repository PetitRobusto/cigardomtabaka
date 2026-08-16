# Frontend Type Safety Baseline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 清零 50 个既有 TypeScript 错误，并让类型检查、TS/TSX Lint、Vitest 和生产构建成为 production 部署前的强制门禁。

**Architecture:** `frontend/src/types.ts` 继续作为当前 canonical 前端契约；API 边界用泛型或运行时 guard 返回具体类型，组件只消费已经建模的数据。工具链保持严格模式，源码和测试共用同一类型检查基线；Deploy 仍只在 CI 成功后触发。

**Tech Stack:** TypeScript 6、React 19、Vite 8、Vitest 3、ESLint flat config、typescript-eslint、GitHub Actions。

---

### Task 1: 修复共享 API 与领域契约

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/api.ts`
- Test: `frontend/src/api/idempotency.test.ts`

- [ ] **Step 1: 记录失败基线**

Run:

```bash
cd frontend
./node_modules/.bin/tsc --noEmit --ignoreDeprecations 6.0 --pretty false
```

Expected: FAIL；`api.ts` 出现 5 个 `TS18046`，共享类型缺少 `release_type_cn`，会计汇总账户契约错误。

- [ ] **Step 2: 为幂等写入声明响应 envelope**

在 `createSalesOrder`、`updateSalesOrder` 和 `salesAction` 调用中传入：

```ts
writeWithIdempotency<{ sales_order: SalesOrder }>(...)
```

在 `createReconciliation`、`confirmReconciliation` 调用中传入：

```ts
writeWithIdempotency<{ reconciliation: Reconciliation }>(...)
```

- [ ] **Step 3: 按真实后端响应修正 canonical 类型**

为 `CigarListItem` 和 `PriceHistoryResponse` 增加：

```ts
release_type_cn?: string;
```

新增并使用会计汇总专用行，不能伪造成完整 `FundAccount`：

```ts
export interface AccountingSummaryFundAccount {
  account_id: number;
  name: string;
  currency: string;
  original_balance: string;
  cny_book_cost: string;
}

export interface AccountingSummary {
  as_of: string;
  fund_accounts: AccountingSummaryFundAccount[];
  accounts_receivable_cny: string;
  customer_prepayments_cny: string;
  inventory_remaining_cost_cny: string;
  purchase_in_transit_cny: string;
}
```

`PaymentOrderItem` 增加后端确实返回的 `id`：

```ts
id: number;
```

- [ ] **Step 4: 运行共享 API 测试与类型检查**

Run:

```bash
cd frontend
./node_modules/.bin/vitest run src/api/idempotency.test.ts src/api/accountingActions.test.ts
./node_modules/.bin/tsc --noEmit --ignoreDeprecations 6.0 --pretty false
```

Expected: API 测试 PASS；上述共享契约错误消失，剩余错误只来自后续任务。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/types.ts frontend/src/api.ts
git commit -m "修复：校准前端共享接口类型"
```

### Task 2: 修复会计动作组件和类型安全测试夹具

**Files:**
- Modify: `frontend/src/components/accounting/AccountingActionCenter.tsx`
- Modify: `frontend/src/components/accounting/PurchaseAction.tsx`
- Modify: `frontend/src/components/accounting/AccountingActionCenter.test.tsx`
- Modify: `frontend/src/components/accounting/DividendAction.test.tsx`
- Modify: `frontend/src/components/accounting/ExchangeAction.test.tsx`
- Modify: `frontend/src/components/accounting/ExpenseAction.test.tsx`
- Modify: `frontend/src/components/accounting/PurchaseAction.test.tsx`

- [ ] **Step 1: 保留当前测试行为基线**

Run:

```bash
cd frontend
./node_modules/.bin/vitest run src/components/accounting/AccountingActionCenter.test.tsx src/components/accounting/DividendAction.test.tsx src/components/accounting/ExchangeAction.test.tsx src/components/accounting/ExpenseAction.test.tsx src/components/accounting/PurchaseAction.test.tsx
```

Expected: 现有 15 个测试 PASS，但 `tsc` 仍因 `as never` 和缺失 fixture 字段失败。

- [ ] **Step 2: 消除组件/领域类型同名冲突**

在 `AccountingActionCenter.tsx` 使用：

```ts
import type {
  AccountingActionsResponse,
  AccountingApiError,
  DividendAction,
  ExpenseActionPayload,
  FundAccount,
  PurchaseAction as PurchaseOrderAction,
} from '../../types';

export interface AccountingActionCenterProps {
  accounts: FundAccount[];
  summaryAccounts?: FundAccount[];
  actions?: AccountingActionsResponse;
  purchases?: PurchaseOrderAction[];
  dividends?: DividendAction[];
  businessDate: string;
  loading?: boolean;
  error?: string | AccountingApiError;
  actionsLoading?: boolean;
  actionsError?: string | AccountingApiError;
  onChanged?: () => void;
}
```

保留组件值导入 `import PurchaseAction from './PurchaseAction'`。

- [ ] **Step 3: 正确收窄采购盒数**

将 `itemTotal` 的数量判断改为：

```ts
const boxQuantity = item.box_quantity;
if (
  price === null ||
  boxQuantity === null ||
  boxQuantity === undefined ||
  !Number.isInteger(boxQuantity) ||
  boxQuantity < 0
) return '—';
return formatCents(price * BigInt(boxQuantity));
```

- [ ] **Step 4: 删除测试里的 `as never`**

所有账户 fixture 使用真实必填字段：

```ts
const cnyAccount: FundAccount = {
  id: 1,
  name: '人民币账户',
  currency: 'CNY',
  custodian_id: null,
  is_active: true,
};
```

组件 props 使用 `satisfies React.ComponentProps<typeof Component>` 校验；采购 item 补 `cigar_id`。股息 preview 使用当前 `DividendPreview` 的 `retained_earnings_cny`、`requested_cny`、结构化 `warning` 和 `warning_fingerprint`，删除旧的 `warning_code`/字符串 warning。

- [ ] **Step 5: 验证会计组**

Run:

```bash
cd frontend
./node_modules/.bin/vitest run src/components/accounting/AccountingActionCenter.test.tsx src/components/accounting/DividendAction.test.tsx src/components/accounting/ExchangeAction.test.tsx src/components/accounting/ExpenseAction.test.tsx src/components/accounting/PurchaseAction.test.tsx src/components/sales/accountingGuideTargets.test.tsx
./node_modules/.bin/tsc --noEmit --ignoreDeprecations 6.0 --pretty false
```

Expected: 6 个测试文件 PASS；会计组件和 fixture 的类型错误全部消失。

- [ ] **Step 6: 提交**

```bash
git add frontend/src/components/accounting frontend/src/components/sales/AccountingPanel.tsx
git commit -m "修复：清理会计组件类型债务"
```

### Task 3: 修复价格图表、导航和空值契约

**Files:**
- Modify: `frontend/src/components/detail/PriceChart.tsx`
- Modify: `frontend/src/components/layout/AppLayout.tsx`
- Modify: `frontend/src/components/layout/mobileNav.test.ts`
- Modify: `frontend/src/pages/Alerts.tsx`
- Modify: `frontend/src/utils/priceData.ts`

- [ ] **Step 1: 为价格数据空值补回归测试**

在现有 `priceData` 测试或新建 `frontend/src/utils/priceData.test.ts`，加入：

```ts
it('keeps a missing CNY price as null instead of inventing a zero price', () => {
  const rows = buildChartData([{ source_name: '来源', box_label: '25', currency: 'USD', box_size: 25, points: [{ date: '2026-08-16', price: 100, original_price: 100, price_cny: null, in_stock: true }] }], 'cny_per_stick');
  expect(rows[0]['来源 25 · ¥']).toBeNull();
});
```

Run: `cd frontend && ./node_modules/.bin/vitest run src/utils/priceData.test.ts`

Expected: 类型检查仍失败，因为 chart datum 当前不允许 `null`。

- [ ] **Step 2: 显式建模图表 datum**

```ts
type ChartDatum = {
  date: string;
  [key: string]: number | string | null;
};

const dateMap: Record<string, ChartDatum> = {};
```

保留缺失人民币价格为 `null`，不能改为 0。

- [ ] **Step 3: 收窄 Recharts 回调输入**

Tooltip 先检查 `typeof value === 'number'`，否则显示 `['—', '单支价格']`。Bar label 在读取数组、做坐标运算或格式化值前，必须确认 `index/x/y/width/value` 全部为 number；不满足时直接 `return null`，并删除 `null as any`。

- [ ] **Step 4: 显式声明导航项类型并修复 ES2020 测试**

```ts
import type { LucideIcon } from 'lucide-react';

interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  public?: boolean;
  external?: boolean;
}

const navItems: NavItem[] = [/* 保持现有条目 */];
```

`mobileNav.test.ts` 保存数组后使用 `items[items.length - 1]`，不升级全局 ES target。

- [ ] **Step 5: 统一 Alerts API 解包责任**

`fetchSources()` 已返回数组，因此组件使用 `setSources(s)`。为 `fetchAlerts()` 声明 `Promise<AlertItem[]>` 并在 API 层解包，组件同样直接消费数组。

- [ ] **Step 6: 验证 UI/目录组并提交**

Run:

```bash
cd frontend
./node_modules/.bin/vitest run src/utils/priceData.test.ts src/components/layout/mobileNav.test.ts
./node_modules/.bin/tsc --noEmit --ignoreDeprecations 6.0 --pretty false
```

Expected: 指定测试 PASS；PriceChart、AppLayout、Alerts、priceData 类型错误消失。

```bash
git add frontend/src/components/detail/PriceChart.tsx frontend/src/components/layout/AppLayout.tsx frontend/src/components/layout/mobileNav.test.ts frontend/src/pages/Alerts.tsx frontend/src/utils/priceData.ts frontend/src/utils/priceData.test.ts frontend/src/api.ts
git commit -m "修复：收窄图表与导航类型"
```

### Task 4: 修复 Privnote 成功响应和支付夹具

**Files:**
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/pages/PrivnotePage.tsx`
- Modify: `frontend/src/pages/privnotePayment.test.ts`
- Create: `frontend/src/api/privnote.test.ts`

- [ ] **Step 1: 写失败的 Privnote 响应边界测试**

测试有效 `{ url: '/p/token/', token: 'token' }` 能返回；成功 HTTP 若缺少字符串 url/token，则 `createPrivnote` 抛出“服务器返回格式错误”。先运行并确认缺字段用例 FAIL。

- [ ] **Step 2: 添加成功 envelope 与 guard**

```ts
interface CreatePrivnoteResponse {
  url: string;
  token: string;
}

function isCreatePrivnoteResponse(value: unknown): value is CreatePrivnoteResponse {
  if (!value || typeof value !== 'object') return false;
  const record = value as Record<string, unknown>;
  return typeof record.url === 'string' && typeof record.token === 'string';
}
```

`createPrivnote` 将 JSON 保持为 `unknown`；HTTP 成功后必须通过 guard 才返回，否则抛出明确错误。页面直接使用已经收窄的 `res.url/res.token`。

- [ ] **Step 3: 对齐支付订单测试夹具**

`PaymentOrder` fixture 只保留该接口拥有的字段，删除 `customer_id`、成本、利润、锁定、事件和收付款对象等 `SalesOrder` 字段。item 保留 `id/cigar_name/quantity/sale_unit/sale_quantity/unit_price`，删除 `cigar_id/box_size/allocations`。

- [ ] **Step 4: 验证 Privnote 组并提交**

Run:

```bash
cd frontend
./node_modules/.bin/vitest run src/api/privnote.test.ts src/pages/privnotePayment.test.ts
./node_modules/.bin/tsc --noEmit --ignoreDeprecations 6.0 --pretty false
```

Expected: 测试 PASS；Privnote 和支付夹具类型错误消失。

```bash
git add frontend/src/api.ts frontend/src/pages/PrivnotePage.tsx frontend/src/pages/privnotePayment.test.ts frontend/src/api/privnote.test.ts
git commit -m "修复：校验私密链接响应类型"
```

### Task 5: 启用严格工具链

**Files:**
- Modify: `frontend/tsconfig.json`
- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`
- Modify: `frontend/eslint.config.js`

- [ ] **Step 1: 消除 TS6 配置弃用**

确认 `rg -n "@/" frontend/src` 无结果后，删除未使用的 `baseUrl` 和 `paths`，不添加 `ignoreDeprecations`。

- [ ] **Step 2: 添加脚本与 ESLint TypeScript 支持**

Run: `cd frontend && npm install --save-dev typescript-eslint`

脚本调整为：

```json
{
  "build": "npm run typecheck && vite build",
  "lint": "eslint . --max-warnings 0",
  "test": "vitest",
  "test:run": "vitest run",
  "typecheck": "tsc -p tsconfig.json --noEmit"
}
```

ESLint flat config保留 JS 规则，并新增 `**/*.{ts,tsx}` 的 `typescript-eslint` recommended、React Hooks、React Refresh 和 browser globals。测试文件同时允许 Node globals。

- [ ] **Step 3: 清零启用规则后暴露的真实 Lint 错误**

Run: `cd frontend && npm run lint`

Expected: 第一次可能 FAIL；逐项修复源码，不关闭规则、不批量 ignore，直到零 warning/零 error。

- [ ] **Step 4: 完整前端验证并提交**

Run:

```bash
cd frontend
npm run typecheck
npm run lint
npm run test:run
npm run build
```

Expected: 四条命令全部退出 0；Vitest 当前基线至少 32 files / 144 tests，新增测试后数量只增不减。

```bash
git add frontend/tsconfig.json frontend/package.json frontend/package-lock.json frontend/eslint.config.js frontend/src
git commit -m "构建：启用前端类型与测试门禁"
```

### Task 6: 接入 CI 并验证 production 部署链

**Files:**
- Modify: `.github/workflows/ci.yml`
- Modify: `deploy/README.md`

- [ ] **Step 1: 扩充前端 CI 步骤**

将单一 `Install & Build` 拆为：

```yaml
- name: Install frontend dependencies
  working-directory: frontend
  run: npm ci

- name: Lint frontend
  working-directory: frontend
  run: npm run lint

- name: Test frontend
  working-directory: frontend
  run: npm run test:run

- name: Build frontend with typecheck
  working-directory: frontend
  run: npm run build
```

- [ ] **Step 2: 修正 CI 后端覆盖**

后端测试至少加入 `accounting`，并停止用 `|| true` 掩盖部署检查。若 `check --deploy` 的 warning 是预期环境差异，拆成明确的非 deploy `manage.py check`，而不是吞掉退出码。

- [ ] **Step 3: 更新部署说明**

明确 `push main → CI 全绿 → Deploy production`，production 目标为现有服务器；说明任何 typecheck/lint/test/build 失败都会阻止部署。

- [ ] **Step 4: 最终验证与提交**

Run:

```bash
cd frontend
npm run typecheck
npm run lint
npm run test:run
npm run build
cd ..
DJANGO_DEBUG=True DJANGO_SECRET_KEY=ci-test-key .venv/bin/python manage.py check
DJANGO_DEBUG=True DJANGO_SECRET_KEY=ci-test-key .venv/bin/python manage.py test cigars privnote accounting --verbosity=1
git diff --check
```

Expected: 所有命令退出 0。

```bash
git add .github/workflows/ci.yml deploy/README.md
git commit -m "构建：完善生产部署前质量门禁"
```

### Task 7: 多轮审查与分支收尾

**Files:**
- Review: all changes since `8bc5bc4`

- [ ] **Step 1: 规格审查**

逐项核对设计目标：50 个错误清零、无 `any`/规则禁用、TS/TSX 确实被 Lint、CI 运行前端测试、Deploy 仍只在 CI 成功后触发。

- [ ] **Step 2: 代码质量审查**

独立审查 API 契约、空值处理、测试夹具真实性和 GitHub Actions 失败传播；修复所有 Critical/Important 问题并复审。

- [ ] **Step 3: 最终全量验证**

重复 Task 6 Step 4 的全部命令，并记录测试数量与退出码。

- [ ] **Step 4: 按 finishing-a-development-branch 流程合并**

本地合并回 `main`，合并后再次运行完整验证；不 push，等待用户明确指令。
