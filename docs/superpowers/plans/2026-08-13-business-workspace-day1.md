# 经营工作台、订单中心与 Day 1 初始化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将销售操作和会计数据拆成独立页面，提供安全的一次性 Day 1 期初初始化，并把真实订单闭环写入站内帮助。

**Architecture:** `cigars` 继续拥有雪茄目录、销售和库存批次，`accounting` 新增共享初始化草稿、唯一完成事实与期初原子入账服务。React 使用独立 `/sales`、`/accounting` 和非常驻 `/accounting/day1` 路由；初始化状态由后端决定，前端无法绕过一次性锁。

**Tech Stack:** Django 5、SQLite、Decimal、React 19、TypeScript、TanStack Query、Vite、Vitest、Tailwind/DaisyUI、已批准的 OpenDesign/Visual Companion 原型。

---

## 文件结构

- `accounting/models.py`：Day 1 单例草稿、草稿账户、草稿库存和完成快照。
- `accounting/day1.py`：草稿校验、乐观版本控制、最终原子初始化服务。
- `accounting/day1_serializers.py`：Day 1 状态、草稿和完成摘要的稳定 JSON 读模型。
- `accounting/views.py` / `accounting/urls.py`：Day 1 与独立工作台 API。
- `accounting/tests/test_day1.py`：一次性、原子性、并发和成本守恒测试。
- `accounting/tests/test_day1_api.py`：staff 权限、草稿版本和确认 API 契约。
- `cigars/models.py`：采购批次来源和销售单人肉费承担方。
- `cigars/services.py` / `cigars/sales_api.py`：承担方校验与向后兼容。
- `cigars/tests/test_sales_transport_payer.py`：承担方业务规则和 API 测试。
- `frontend/src/pages/SalesPage.tsx`：独立订单中心。
- `frontend/src/pages/AccountingDashboardPage.tsx`：独立数据工作台。
- `frontend/src/pages/Day1SetupPage.tsx`：一次性四步向导。
- `frontend/src/components/day1/`：账户、库存、核对和完成态组件。
- `frontend/src/components/sales/SalesOrderForm.tsx`：聚焦即展开库存与承担方交互。
- `frontend/src/features/guides/guideContent.ts` / `frontend/src/pages/HelpPage.tsx`：完整流程手册。
- `frontend/src/App.tsx` / `frontend/src/components/layout/`：路由、常驻导航和旧入口兼容。

## Task 1：Day 1 数据模型与采购批次来源

**Files:**
- Modify: `accounting/models.py`
- Modify: `cigars/models.py`
- Create: `accounting/migrations/0010_day1_initialization.py`
- Create: `cigars/migrations/0034_purchase_batch_source.py`
- Create: `accounting/tests/test_day1.py`

- [ ] **Step 1: 写失败的模型测试**

```python
class Day1ModelTest(TestCase):
    def test_only_one_shared_initialization_row_can_exist(self):
        Day1Initialization.objects.create(singleton_key='company', status='draft')
        with self.assertRaises(IntegrityError):
            Day1Initialization.objects.create(singleton_key='company', status='draft')

    def test_opening_batch_does_not_require_fake_purchase_item(self):
        batch = PurchaseBatch.objects.create(
            source=PurchaseBatch.Source.OPENING,
            purchase_order_item=None,
            cigar=self.cigar,
            quantity=25,
            remaining=25,
            physical_remaining=25,
            box_size=25,
            original_box_quantity=1,
            physical_box_quantity=1,
            available_box_quantity=1,
            unit_cost_cny='100.00',
            original_cost_cny='2500.00',
            remaining_cost_cny='2500.00',
        )
        self.assertEqual(batch.source, 'opening')
```

- [ ] **Step 2: 运行 RED**

Run: `.venv/bin/python manage.py test accounting.tests.test_day1.Day1ModelTest -v 2`

Expected: FAIL，缺少 Day 1 模型、`PurchaseBatch.Source`，且采购明细仍不可为空。

- [ ] **Step 3: 添加最小模型**

`Day1Initialization` 保存 `singleton_key='company'`、`status=draft|completed`、`business_date`、`version`、`updated_by`、`completed_by`、`completed_at` 和完成摘要 JSON。`Day1DraftAccount` 保存四个固定 `slot`、名称、币种、原币余额和 CNY 账面成本。`Day1DraftInventory` 保存 `cigar`、包装支数、整盒数、散支数和每支 CNY 成本，并以“初始化 + 雪茄 + 包装”唯一。

`PurchaseBatch.purchase_order_item` 改为可空，并增加：

```python
class Source(models.TextChoices):
    PURCHASE = 'purchase', '采购入库'
    OPENING = 'opening', 'Day 1 期初'

source = models.CharField(max_length=12, choices=Source.choices, default=Source.PURCHASE)
```

数据库约束保证 `purchase` 必须有采购明细、`opening` 必须没有采购明细。

- [ ] **Step 4: 生成迁移并检查内容**

Run: `.venv/bin/python manage.py makemigrations accounting cigars`

Expected: 只新增 Day 1 表、批次来源、采购明细可空和对应约束；既有批次回填为 `purchase`。

- [ ] **Step 5: 运行 GREEN**

Run: `.venv/bin/python manage.py test accounting.tests.test_day1.Day1ModelTest cigars.tests.test_sales_accounting -v 2`

Expected: PASS。

- [ ] **Step 6: 中文提交**

```bash
git add accounting cigars
git commit -m "功能：建立一次性期初初始化模型"
```

## Task 2：共享草稿与一次性原子确认服务

**Files:**
- Create: `accounting/day1.py`
- Modify: `accounting/services.py`
- Modify: `accounting/tests/test_day1.py`

- [ ] **Step 1: 写草稿版本控制的失败测试**

```python
def test_save_draft_rejects_stale_version(self):
    draft = save_day1_draft(payload=self.valid_payload, expected_version=0, operator=self.alice)
    with self.assertRaises(Day1VersionConflict):
        save_day1_draft(payload=self.valid_payload, expected_version=0, operator=self.partner)
    self.assertEqual(draft.version, 1)
```

- [ ] **Step 2: 运行 RED**

Run: `.venv/bin/python manage.py test accounting.tests.test_day1.Day1DraftServiceTest -v 2`

Expected: FAIL，服务与异常类型不存在。

- [ ] **Step 3: 实现共享草稿保存**

实现 `get_or_create_day1_draft()` 和 `save_day1_draft(payload, expected_version, operator)`。服务使用 `transaction.atomic()` 和 `select_for_update()`；完整替换四个账户槽与库存草稿行，保存成功后递增 `version`。校验四个固定币种槽、非负余额、CNY 余额等于账面成本、外币余额与成本同时为零或同时为正，以及库存数量/包装/成本规则。

- [ ] **Step 4: 写最终确认的失败测试**

```python
def test_confirm_creates_balanced_opening_facts_once(self):
    result = confirm_day1(expected_version=1, operator=self.alice, idempotency_key='day1-final')
    self.assertEqual(FundAccount.objects.count(), 4)
    self.assertEqual(PurchaseBatch.objects.filter(source='opening').count(), 2)
    self.assertEqual(result.retained_earnings_cny, Decimal('0.00'))
    self.assertEqual(result.opening_capital_cny, result.total_net_assets_cny)
    self.assertEqual(
        sum(LedgerPosting.objects.values_list('cny_amount', flat=True), Decimal('0.00')),
        Decimal('0.00'),
    )
    replay = confirm_day1(expected_version=1, operator=self.alice, idempotency_key='day1-final')
    self.assertEqual(replay.initialization_id, result.initialization_id)
```

- [ ] **Step 5: 运行确认 RED**

Run: `.venv/bin/python manage.py test accounting.tests.test_day1.Day1ConfirmationTest -v 2`

Expected: FAIL，确认服务不存在。

- [ ] **Step 6: 实现最小原子确认**

实现 `confirm_day1(...)`：先取得 SQLite writer gate 和初始化行锁；拒绝非期初正式流水、已有资金账户、已有非 opening 批次或已完成初始化；创建四个账户、账户期初分录、库存 opening 批次、库存资产/期初投入资本平衡分录，期初未分配利润固定为零。全部动作在一个事务中；完成摘要冻结到账户与库存总额，不再依赖可编辑草稿。

- [ ] **Step 7: 添加回滚、并发与非法前提测试**

覆盖中途创建批次失败后零账户/零分录/零批次、两个线程并发只成功一次、不同幂等键重复确认不重复创建、已有日常流水或正式库存时拒绝、完成后不能保存草稿。

- [ ] **Step 8: 运行 GREEN**

Run: `.venv/bin/python manage.py test accounting.tests.test_day1 accounting.tests.test_ledger cigars.tests.test_sales_accounting -v 2`

Expected: PASS。

- [ ] **Step 9: 中文提交并审查后端切片**

```bash
git add accounting cigars
git commit -m "功能：原子确认公司期初资产"
```

## Task 3：Day 1 与工作台 API

**Files:**
- Create: `accounting/day1_serializers.py`
- Create: `accounting/tests/test_day1_api.py`
- Modify: `accounting/views.py`
- Modify: `accounting/urls.py`
- Modify: `accounting/selectors.py`
- Modify: `accounting/tests/test_api.py`

- [ ] **Step 1: 写失败的 API 契约测试**

```python
def test_day1_status_draft_save_and_confirm_contract(self):
    self.client.force_login(self.staff)
    self.assertEqual(self.client.get('/api/accounting/day1/').json()['status'], 'not_started')
    saved = self.client.put(
        '/api/accounting/day1/draft/', data=json.dumps(self.payload),
        content_type='application/json', HTTP_IF_MATCH='0',
    )
    self.assertEqual(saved.status_code, 200)
    self.assertEqual(saved.json()['version'], 1)
    confirmed = self.client.post(
        '/api/accounting/day1/confirm/', data=json.dumps({'version': 1}),
        content_type='application/json', HTTP_IDEMPOTENCY_KEY='confirm-day1',
    )
    self.assertEqual(confirmed.status_code, 200)
    self.assertEqual(confirmed.json()['status'], 'completed')
```

- [ ] **Step 2: 运行 RED**

Run: `.venv/bin/python manage.py test accounting.tests.test_day1_api -v 2`

Expected: FAIL，三个端点均为 404。

- [ ] **Step 3: 实现 API 和序列化**

新增：

- `GET /api/accounting/day1/`
- `PUT /api/accounting/day1/draft/`，以 `If-Match` 版本防覆盖。
- `POST /api/accounting/day1/confirm/`，强制 `Idempotency-Key`。
- `GET /api/accounting/dashboard/`，返回初始化状态、四个顶部统计、账户快照、月利润和对账提醒。

金额全部输出字符串。非 staff 返回 403；版本冲突返回 409；字段校验返回 400 和结构化 `details`；完成后读接口返回冻结摘要。

- [ ] **Step 4: 补工作台失败隔离测试**

测试未初始化时财务统计为 `null` 且带 `requires_day1=true`，不能伪装为 0；已初始化后返回 CNY 合计、库存成本、待收金额和月利润。

- [ ] **Step 5: 运行 GREEN**

Run: `.venv/bin/python manage.py test accounting.tests.test_day1_api accounting.tests.test_api -v 2`

Expected: PASS。

- [ ] **Step 6: 中文提交**

```bash
git add accounting
git commit -m "功能：提供期初初始化与数据工作台接口"
```

## Task 4：销售人肉费承担方与库存联想契约

**Files:**
- Modify: `cigars/models.py`
- Create: `cigars/migrations/0035_sales_order_transport_payer.py`
- Modify: `cigars/services.py`
- Modify: `cigars/sales_api.py`
- Create: `cigars/tests/test_sales_transport_payer.py`
- Modify: `privnote/views.py`

- [ ] **Step 1: 写承担方失败测试**

```python
def test_company_paid_transport_forces_customer_charge_to_zero(self):
    with self.assertRaisesMessage(OrderServiceError, '公司承担人肉费时客户收费必须为零'):
        create_sales_order_draft(
            items=self.items,
            operator=self.staff,
            transport_payer='company',
            customer_transport_fee_cny='300.00',
        )

def test_customer_paid_transport_is_in_amount_due(self):
    order = create_sales_order_draft(
        items=self.items,
        operator=self.staff,
        transport_payer='customer',
        customer_transport_fee_cny='300.00',
    )
    self.assertEqual(order.amount_due_cny, order.goods_amount_cny + Decimal('300.00'))
```

- [ ] **Step 2: 运行 RED**

Run: `.venv/bin/python manage.py test cigars.tests.test_sales_transport_payer -v 2`

Expected: FAIL，缺少 `transport_payer` 参数和字段。

- [ ] **Step 3: 实现字段、迁移与兼容规则**

添加 `customer|company` choices。数据迁移把既有非零客户人肉费设为 `customer`，零金额设为 `company`。创建/更新草稿显式校验；旧请求未发送承担方时按同一规则推断。订单确认后该字段与金额继续冻结。

- [ ] **Step 4: 固化库存联想 API 契约**

扩展现有 stock-only 搜索，使空 `q` 合法并返回最多 20 个有可售库存结果；每项返回 `box_options`（包装、可售盒数）和 `available_sticks`。写 API 测试证明无库存商品不出现，查询文本仍能过滤，提交订单时仍由后端重新锁定校验库存。

- [ ] **Step 5: 运行 GREEN**

Run: `.venv/bin/python manage.py test cigars.tests.test_sales_transport_payer privnote.tests -v 2`

Expected: PASS。

- [ ] **Step 6: 中文提交并二次后端审查**

```bash
git add cigars privnote
git commit -m "功能：区分客户与公司承担人肉费"
```

## Task 5：React 路由、工作台和订单中心

**Execution constraint:** 由 `gpt-5.6-luna` 前端子代理实现；不得使用 Kanban、Kimi 或 Terra。开始前读取已批准的 `.opendesign/accounting-sales-profit.html` 与本轮 Visual Companion 原型作为视觉基线。

**Files:**
- Create: `frontend/src/pages/SalesPage.tsx`
- Create: `frontend/src/pages/AccountingDashboardPage.tsx`
- Create: `frontend/src/pages/businessRoutes.test.ts`
- Modify: `frontend/src/pages/SalesAccountingPage.tsx`
- Modify: `frontend/src/components/sales/SalesOrderForm.tsx`
- Modify: `frontend/src/components/sales/AccountingPanel.tsx`
- Modify: `frontend/src/components/sales/salesState.ts`
- Modify: `frontend/src/components/sales/salesState.test.ts`
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/layout/AppLayout.tsx`
- Modify: `frontend/src/components/layout/mobileNav.ts`
- Modify: `frontend/src/components/layout/mobileNav.test.ts`

- [ ] **Step 1: 写路由和导航 RED**

```ts
expect(resolveLegacyBusinessRoute('/sales', '#accounting')).toBe('/accounting')
expect(mobileNavItems(true).map(item => item.label)).toEqual(['品牌', '库存', '订单', '账务', '更多'])
expect(desktopBusinessNav(true).some(item => item.label === '管理')).toBe(false)
expect(desktopBusinessNav(true).some(item => item.label === 'Day 1')).toBe(false)
```

- [ ] **Step 2: 运行 RED**

Run: `cd frontend && npm test -- --run src/pages/businessRoutes.test.ts src/components/layout/mobileNav.test.ts`

Expected: FAIL，页面/纯路由函数不存在，导航仍含管理且销售/账务未独立。

- [ ] **Step 3: 拆分路由并移除管理入口**

`/sales` 渲染订单中心，`/accounting` 渲染数据工作台，`/sales#accounting` 使用兼容组件重定向。桌面和手机导航只提供“订单”和“账务”，不提供 Admin 或 Day 1。统计卡必须位于两个业务页面标题后、表单与明细之前。

- [ ] **Step 4: 写订单表单 RED**

测试纯状态函数：聚焦空输入产生 `{ q: '', stock_only: true }` 请求；公司承担把客户收费归零并禁用金额输入；客户承担把收费加入应收总额；搜索选择结果默认整盒。

- [ ] **Step 5: 实现订单 autocomplete 与承担方交互**

输入框 `onFocus` 立即加载 stock-only 结果，250ms 防抖只用于后续输入；结果展示包装可售盒数和散支数。表单发送 `transport_payer`，底部拆分商品金额、客户人肉费与应收。API 或某一区域失败时显示局部错误，不渲染假零值。

- [ ] **Step 6: 实现独立数据工作台**

工作台使用 `/api/accounting/dashboard/`。未初始化显示唯一 Day 1 待办卡；草稿显示继续入口；完成后不渲染任何 Day 1 常用入口。账户、利润、库存与对账保留现有真实动作，订单创建/查询完全移除。

- [ ] **Step 7: 运行 GREEN**

Run: `cd frontend && npm test -- --run src/pages/businessRoutes.test.ts src/components/layout/mobileNav.test.ts src/components/sales/salesState.test.ts`

Expected: PASS。

- [ ] **Step 8: 中文提交并执行前端审查**

```bash
git add frontend
git commit -m "前端：拆分订单中心与数据工作台"
```

## Task 6：React 一次性 Day 1 向导

**Execution constraint:** 由新的 `gpt-5.6-luna` 前端子代理实现，先测试纯状态和 payload 构建，再写组件。

**Files:**
- Create: `frontend/src/pages/Day1SetupPage.tsx`
- Create: `frontend/src/components/day1/Day1AccountsStep.tsx`
- Create: `frontend/src/components/day1/Day1InventoryStep.tsx`
- Create: `frontend/src/components/day1/Day1ReviewStep.tsx`
- Create: `frontend/src/features/day1/day1State.ts`
- Create: `frontend/src/features/day1/day1State.test.ts`
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: 写向导状态 RED**

```ts
expect(nextDay1Step(1)).toBe(2)
expect(day1InventoryTotal({ boxes: 4, box_size: 25, loose_sticks: 3 })).toBe(103)
expect(day1RouteMode({ status: 'completed' })).toBe('readonly-summary')
expect(day1RouteMode({ status: 'draft' })).toBe('editable-wizard')
```

- [ ] **Step 2: 运行 RED**

Run: `cd frontend && npm test -- --run src/features/day1/day1State.test.ts`

Expected: FAIL，模块不存在。

- [ ] **Step 3: 实现纯状态与 API 客户端**

定义 `Day1Status`、账户槽、库存行、版本和完成摘要类型。保存发送 `If-Match`；确认使用幂等写工具。版本冲突返回明确“另一位经营者已更新，请刷新”。

- [ ] **Step 4: 实现四步页面**

步骤为范围、四账户、期初库存、核对。库存只能搜索现有目录；每行实时显示总支数和 CNY 成本。确认页必须二次确认并说明不可重跑。保存失败保留 React 本地表单。已完成状态只显示冻结摘要与“返回账务工作台”，不显示提交按钮。

- [ ] **Step 5: 验证入口边界**

测试 `/accounting/day1` 需要 staff；未完成可编辑；完成后只读；主导航、手机导航和普通功能列表均找不到 Day 1。

- [ ] **Step 6: 运行 GREEN**

Run: `cd frontend && npm test -- --run src/features/day1/day1State.test.ts src/pages/businessRoutes.test.ts`

Expected: PASS。

- [ ] **Step 7: 中文提交并执行前端审查**

```bash
git add frontend
git commit -m "前端：提供一次性 Day 1 初始化向导"
```

## Task 7：完整帮助流程与引导路由

**Execution constraint:** 由新的 `gpt-5.6-luna` 前端子代理实现。

**Files:**
- Modify: `frontend/src/features/guides/guideContent.ts`
- Modify: `frontend/src/features/guides/guideState.test.ts`
- Modify: `frontend/src/features/guides/guideInteractions.ts`
- Modify: `frontend/src/features/guides/guideInteractions.test.ts`
- Modify: `frontend/src/features/guides/manualTour.ts`
- Modify: `frontend/src/features/guides/manualTour.test.ts`
- Modify: `frontend/src/pages/HelpPage.tsx`

- [ ] **Step 1: 写完整流程 RED**

```ts
expect(getManualChapter('first-order')?.sections.map(section => section.title)).toEqual([
  '创建销售草稿', '添加现货', '设置人肉费', '确认并预留', '出库与收款',
])
expect(getManualChapter('accounting')?.route).toBe('/accounting')
expect(manualTourDecision(getManualChapter('day1')!, { day1Status: 'completed' }).kind)
  .toBe('readonly')
```

- [ ] **Step 2: 运行 RED**

Run: `cd frontend && npm test -- --run src/features/guides/guideState.test.ts src/features/guides/guideInteractions.test.ts src/features/guides/manualTour.test.ts`

Expected: FAIL，章节和新路由尚不存在。

- [ ] **Step 3: 实现流程型帮助**

增加 Day 1、换汇采购、完整销售单、对账月利润章节。完整订单章节逐步链接真实 `/sales` 控件；引导只聚焦和解释，不调用写 API。所有旧 `/sales#accounting` 内容更新到 `/accounting`。初始化完成时 Day 1 章节仍可读，但按钮只打开只读摘要。

- [ ] **Step 4: 运行 GREEN**

Run: `cd frontend && npm test -- --run src/features/guides/guideState.test.ts src/features/guides/guideInteractions.test.ts src/features/guides/manualTour.test.ts`

Expected: PASS。

- [ ] **Step 5: 中文提交并执行前端审查**

```bash
git add frontend
git commit -m "前端：补全业务流程使用手册"
```

## Task 8：全链验证、审查与本地合并

**Files:**
- Modify only if a failing verification has a TDD regression test first.

- [ ] **Step 1: 运行迁移与 Django 静态检查**

Run: `.venv/bin/python manage.py makemigrations --check --dry-run`

Run: `.venv/bin/python manage.py migrate --plan`

Run: `.venv/bin/python manage.py check`

Expected: 无遗漏迁移，迁移计划只包含本功能迁移，check 无错误。

- [ ] **Step 2: 运行分层后端套件**

Run: `.venv/bin/python manage.py test accounting.tests.test_day1 accounting.tests.test_day1_api cigars.tests.test_sales_transport_payer -v 2`

Run: `.venv/bin/python manage.py test accounting.tests cigars.tests -v 1`

Expected: 全部 PASS；若全套耗时较长，先用第一条快速反馈，再运行完整套件。

- [ ] **Step 3: 运行完整前端验证**

Run: `cd frontend && npm test -- --run`

Run: `cd frontend && npm run lint`

Run: `cd frontend && npm run build`

Expected: 全部 exit 0，无新增 warning/error。

- [ ] **Step 4: 使用开发数据库做安全演练**

确认 `DJANGO_DEBUG=True` 指向 `cigars_dev.db`，在开发库完整执行：创建共享草稿、另一用户更新、确认、刷新工作台、尝试二次确认、创建客户/公司承担人肉费的两张草稿。不得在 `cigars.db` 执行初始化演练。

- [ ] **Step 5: 浏览器桌面与手机检查**

检查 `/accounting`、`/sales`、`/accounting/day1`、`/help`：统计在顶部、无管理入口、无 Day 1 常驻入口、聚焦即有库存、承担方金额正确、完成后 Day 1 只读、帮助可走完整订单流程。

- [ ] **Step 6: 至少两轮独立审查**

第一轮分别审查后端不变量和前端交互；修复后重新运行相关测试。第二轮由新的审查代理复核修复、迁移安全、权限、幂等、移动布局与帮助安全边界。所有发现必须逐条关闭或书面说明不改理由。

- [ ] **Step 7: verification-before-completion**

读取并执行 `superpowers:verification-before-completion`，保存最新命令输出作为完成证据；不得引用早期测试结果声称完成。

- [ ] **Step 8: finishing-a-development-branch**

读取并执行 `superpowers:finishing-a-development-branch`。合并回 `main`，删除功能分支，最终停留在 `main`。不 push。
