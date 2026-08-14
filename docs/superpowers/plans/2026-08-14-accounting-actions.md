# 账务动作中心统一实现计划

> **For agentic workers/Codex:** 按本计划逐个 Task 实现；所有实现与审查 worker 使用 Luna。用户明确不使用 Kanban/Kimi。

**Goal:** 在现有 Day 1、销售、库存 FIFO 和基础账务流水之上，补齐换汇、采购付款/在途/整单到货、经营费用、分红、利润报表和 React 账务动作中心，并保持资金、库存、成本和不可变流水可重建。

**Architecture:** `accounting` 继续是资金与统一流水事实来源，`cigars` 继续拥有采购、库存和销售事实。所有正式写服务先通过 Day 1 服务层门禁，再按 `_retry_sqlite_locked` → `transaction.atomic()` → writer gate → 幂等核对 → 按 id 加锁的顺序执行；账务 posting 使用现有 `_post_transaction_once()`。采购的新 canonical 语义只有 `box_size + box_quantity + unit_price_rub_per_box`：支数为 `box_size * box_quantity`，RUB 明细小计为 `box_quantity * unit_price_rub_per_box`。

**Tech Stack:** Django 5、SQLite、Decimal、Django migrations、React 19、TypeScript、TanStack Query、Vitest、Vite、Tailwind/DaisyUI、现有 `_retry_sqlite_locked`、writer gate、`_outflow_cny_cost()`、`_post_transaction_once()` 和已批准 OpenDesign 原型。

---

## 已核对的基线与不可改变的契约

- 设计依据：[内部账设计](../specs/2026-08-10-internal-accounting-module-design.md) §§4–7、10–13、15，[Day 1/工作台设计](../specs/2026-08-13-business-workspace-day1-design.md) §3，以及 [CONTEXT](../../CONTEXT.md) 的资金、库存、销售、人肉费和累计未分配利润术语。
- 真实采购模型目前是 `PurchaseOrder`、`PurchaseOrderItem.quantity`（支数）、`box_size`、`unit_price_rub`（旧每支价格）和 `unit_price_cny`（旧报价快照）；`receive_purchase_order()` 当前能从草稿直达入库，必须改为付款后到货。
- 真实账务服务已有 `_retry_sqlite_locked`、`_acquire_sqlite_writer_gate()`、`exchange_to_rub()`、`_outflow_cny_cost()`、`_post_transaction_once()`；不得复制换汇或移动平均算法。
- 真实 Day 1 服务已有 `Day1Initialization`、`save_day1_draft()`、`confirm_day1()` 和版本冲突；新增正式动作必须由服务层检查 `status=completed`，而不是仅由 React 隐藏按钮。
- 真实引导 selector 位于 `frontend/src/features/guides/guideInteractions.ts`；`guideContent.ts` 只保存章节文案。 `data-guide` 必须放在非提交控件或稳定的可聚焦 wrapper 上。
- 现有销售人肉费事实是 `SalesTransportCost`，其付款和 `SALES_TRANSPORT_COST` posting 走销售单关联路径；不得把人民币实际人肉费塞进 RUB `other` 费用。

### Canonical 采购规则（全文唯一）

每一条新采购明细必须满足：

```text
sticks = box_size * box_quantity
rub_subtotal = box_quantity * unit_price_rub_per_box
```

`box_size` 和 `box_quantity` 为正整数，`unit_price_rub_per_box` 为非负 Decimal。所有创建、编辑、付款金额、到货数量、批次包装、CNY 比例分配、API、fixture 和报表只读取这三个 canonical 字段。旧 `quantity`、`unit_price_rub`、`unit_price_cny` 仅作为迁移/旧 agent 输入兼容和只读响应字段；任何新逻辑不得使用旧每支价格计算采购总额。旧输入无法推导盒数时才写 `packaging_status=review_required` 并阻断付款；canonical 每盒价若无法无损回填旧两位每支快照，则旧价格字段置 NULL、写 `packaging_status=unrepresentable`，仍允许付款。

### 横切写入规则

- 采购草稿创建、采购草稿编辑、换汇、采购付款、整单到货、费用、分红草稿创建/编辑/确认都必须有 idempotency key；草稿编辑同时要求 `expected_version`，参数不一致返回 `409/idempotency_conflict` 或 `409/version_conflict`。
- 所有正式动作先按幂等键查询并核对完整参数（业务单、账户、金额、日期、operator、版本、warning acknowledgement），再做状态拒绝；相同参数重放返回原事实，不能因已付款/已入库先被状态错误截断。
- 所有动作使用真实 decorator `@_retry_sqlite_locked`（真实定义接收一个 operation callable 并返回包装 callable，不是 context manager）、writer gate 和函数体内 `transaction.atomic()`。锁冲突重试后仍失败返回 `503/busy`，事务内任何异常都不能留下半笔 posting、状态或库存批次。
- Day 1 未完成时，服务层拒绝全部正式账务写动作，稳定错误为 `day1_incomplete`；Day 1 自身 `save_day1_draft()`/`confirm_day1()` 使用明确的内部 bypass scope，不受该门禁阻断。
- 已入账的 `PurchasePayment`、付款后/入库后的 `PurchaseOrder`、`PurchaseOrderItem.actual_cost_cny`、`Expense` 和 `Dividend` 均不可通过实例或普通 QuerySet 改写/删除。付款成功时 payment key 与 order mirror key 必须在同一事务中同时写入，任一不一致立即回滚。受控服务必须使用明确命名的 `ledger_mutation_scope(reason, operator)` bypass，并在事务内校验动作来源；不能让普通 manager 保护合法入账流程。
- 每个 Task 的 Luna A/B 双审查若发现问题，修复后必须由另一位 Luna 针对修复 SHA 重新审查；只有该 SHA 获得 APPROVED 才能继续，问题→修复 commit SHA→复审结论写入 Task9 的 review 文档。
- 每个 Task 的固定门禁顺序都要在该 Task Step 末尾执行：spec review → fix → 不同 Luna spec re-review `APPROVED` → quality review → fix → 不同 Luna quality re-review `APPROVED` → 中文 commit。若 review 发现问题，先形成修复 commit，再由另一 Luna 审查该修复 SHA；未有两个 `APPROVED` 不得进入下一 Task。
- 用户文案、注释、文档和中文 commit 使用中文；字段、函数、API code 和枚举使用英文。每个实现 Task 的代码注释只说明本 Task 的业务规则、并发锁、旧兼容、尾差、不可变边界或前端局部状态，不写无信息量注释。

## Task 1：建立 canonical 采购字段、状态约束和迁移

本计划所有 Python/TypeScript fenced code 均是“插入现有文件的实现片段”，不是独立脚本；实现时必须补齐该文件已有 imports、基类、factory 和 decorator，以下每段只在其标注的真实文件上下文中执行。

**Objective:** 让数据库能表达盒数语义、付款/在途/到货状态和不可转换历史行，且迁移不伪造历史事实。

**Files:**

- Modify: `cigars/models.py`（`PurchaseOrder`、`PurchaseOrderItem`）
- Create: `cigars/migrations/0036_purchase_payment_state.py`
- Test: `cigars/tests/test_purchase_packaging.py`、`cigars/tests/test_purchase_migration.py`（Task 1 只负责模型/迁移；付款与到货测试归 Task 4）

### Step 1（2–5 分钟）：写 canonical RED 测试

完整 imports 为 `Decimal`、`IntegrityError`、`ValidationError`、`TestCase`、`TransactionTestCase`、`PurchaseOrder`、`PurchaseOrderItem`、`Supplier`、`Cigar`、`get_user_model`、`connection`、`MigrationExecutor`，供真实 MigrationExecutor 测试使用。

新增 `cigars/tests/test_purchase_packaging.py` 中的 `PurchasePackagingModelTest`，完整 imports 为 `Decimal`、`IntegrityError`、`ValidationError`、`TestCase`、`PurchaseOrder`、`PurchaseOrderItem`、`Supplier`、`Cigar`、`get_user_model`、`connection`、`MigrationExecutor`；`setUp()` 用真实必填 `supplier`、`rub_total`、`exchange_rate`、`cny_total`、`operator` 和 `cigar` 工厂创建行。Task 1 RED 只覆盖真实 model `full_clean()`/CheckConstraint 与 `MigrationExecutor`；不引入 `PurchasePayment`、pay/cancel、canonical service helper、`BusinessRuleError` 或未定义 fixture。

```python
class PurchasePackagingModelTest(TestCase):
    def setUp(self):
        User = get_user_model()
        self.operator = User.objects.create_user(username='purchase-model')
        self.supplier = Supplier.objects.create(name='测试供应商')
        self.cigar = Cigar.objects.create(english_name='Test Cigar', name='测试雪茄', brand='Test')
        self.order = PurchaseOrder.objects.create(supplier=self.supplier, operator=self.operator,
            rub_total='100.00', exchange_rate='12.0000', cny_total='8.33')

def test_quantity_box_check_and_model_clean_reject_mismatch(self):
    item = PurchaseOrderItem.objects.create(purchase_order=self.order, cigar=self.cigar,
        quantity=25, box_size=25, box_quantity=1, unit_price_rub='100.00', unit_price_cny='8.00',
        unit_price_rub_per_box='100.00', packaging_status='normalized')
    item.quantity = 24
    with self.assertRaises(ValidationError):
        item.full_clean()
    item.quantity = 25
    item.save(update_fields=['quantity'])
    with self.assertRaises(IntegrityError):
        PurchaseOrderItem.objects.filter(pk=item.pk).update(quantity=24)

def test_purchase_order_status_constraint_uses_paid_facts(self):
    with self.assertRaises(IntegrityError):
        PurchaseOrder.objects.filter(pk=self.order.pk).update(status='received', legacy_received=False)

class PurchaseMigrationTest(TransactionTestCase):
    def test_0036_preserves_real_received_quote_and_marks_legacy(self):
        executor = MigrationExecutor(connection)
        self.addCleanup(lambda: executor.migrate(executor.loader.graph.leaf_nodes('cigars')))
        executor.migrate([('cigars', '0035_sales_order_transport_payer')])
        old_apps = executor.loader.project_state([('cigars', '0035_sales_order_transport_payer')]).apps
        OldSupplier = old_apps.get_model('cigars', 'Supplier')
        OldUser = old_apps.get_model('cigars', 'User')
        old_supplier = OldSupplier.objects.create(name='迁移供应商')
        old_operator = OldUser.objects.create(username='migration-operator')
        OldOrder = old_apps.get_model('cigars', 'PurchaseOrder')
        row = OldOrder.objects.create(supplier_id=old_supplier.pk, operator_id=old_operator.pk,
            status='received', rub_total='100.00', exchange_rate='12.0000', cny_total='8.33')
        executor.migrate([('cigars', '0036_purchase_payment_state')])
        NewOrder = executor.loader.project_state([('cigars', '0036_purchase_payment_state')]).apps.get_model('cigars', 'PurchaseOrder')
        migrated = NewOrder.objects.get(pk=row.pk)
        self.assertTrue(migrated.legacy_received)
        self.assertEqual(migrated.exchange_rate, Decimal('12.0000'))
        self.assertEqual(migrated.cny_total, Decimal('8.33'))
        self.assertEqual(migrated.paid_cny_cost, Decimal('0.00'))
```

Run: `.venv/bin/python manage.py test cigars.tests.test_purchase_packaging cigars.tests.test_purchase_migration -v 2`

Expected: FAIL，canonical 字段、包装状态和付款前状态尚未存在。

### Step 2（2–5 分钟）：增加可迁移字段和状态枚举

在 `PurchaseOrder` 增加 `IN_TRANSIT`，以及以下真实 Django 字段；枚举先于字段定义：

```python
class PurchaseOrder(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'draft', '草稿'
        IN_TRANSIT = 'in_transit', '在途'
        RECEIVED = 'received', '已入库'
        CANCELLED = 'cancelled', '已取消'

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    exchange_rate = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    cny_total = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    paid_cny_cost = models.DecimalField(max_digits=22, decimal_places=2, default=Decimal('0.00'), null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    payment_idempotency_key = models.CharField(max_length=128, null=True, blank=True, unique=True)
    arrival_idempotency_key = models.CharField(max_length=128, null=True, blank=True, unique=True)
    draft_idempotency_key = models.CharField(max_length=128, null=True, blank=True, unique=True)
    draft_request_fingerprint = models.CharField(max_length=64, null=True, blank=True)
    draft_operator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name='+')
    draft_business_date = models.DateField(null=True, blank=True)
    version = models.PositiveIntegerField(default=1)
    legacy_received = models.BooleanField(default=False)
```

在 `PurchaseOrderItem` 增加以下字段；canonical 数值在迁移期允许 null，服务建新行时必须非空，枚举先于字段定义：

```python
class PurchaseOrderItem(models.Model):
    class PackagingStatus(models.TextChoices):
        NORMALIZED = 'normalized', '已规范化'
        REVIEW_REQUIRED = 'review_required', '需人工复核'
        UNREPRESENTABLE = 'unrepresentable', '兼容快照不可表示'

    class LegacySnapshotStatus(models.TextChoices):
        EXPLICIT = 'explicit', '显式报价'
        DERIVED = 'derived', '可逆派生'
        UNREPRESENTABLE = 'unrepresentable', '不可表示'

    box_quantity = models.PositiveIntegerField(null=True, blank=True)
    unit_price_rub_per_box = models.DecimalField(max_digits=22, decimal_places=2, null=True, blank=True)
    packaging_status = models.CharField(max_length=20, choices=PackagingStatus.choices, default=PackagingStatus.REVIEW_REQUIRED)
    actual_cost_cny = models.DecimalField(max_digits=22, decimal_places=2, default=Decimal('0.00'))
    legacy_snapshot_status = models.CharField(max_length=24, choices=LegacySnapshotStatus.choices, default=LegacySnapshotStatus.UNREPRESENTABLE)
```

旧 `quantity` 保持原整数约束；旧 `unit_price_rub`、`unit_price_cny` 在 model/migration 中均改为 `null=True, blank=True`，以免合法 canonical 每盒价因旧两位快照不可表示而被反卡。`PurchaseOrder.exchange_rate` 也改为 `null=True, blank=True` 的 legacy quote snapshot；serializer/adapter 必须允许 JSON `null`。迁移只保留既有非空旧值，新 canonical create 不要求、不伪造、不读取 exchange/CNY/旧每支价格。新增 `legacy_snapshot_status`（`explicit`/`derived`/`unrepresentable`）记录兼容状态；canonical 新建时主 helper 只返回 canonical 字段与 NULL legacy snapshots，旧 agent adapter 才能显式传入并保留报价快照。任一旧快照无法无损表示时，两个旧价格字段都写 NULL、`packaging_status='unrepresentable'`、`legacy_snapshot_status='unrepresentable'`，不猜测且不阻止 canonical 建单/付款；`packaging_review_required` 只对应旧输入无法转换为 canonical 的人工复核。旧字段只读兼容展示，exchange rate 绝不参与付款成本或在途成本。

真实 `PurchaseOrder.exchange_rate` 与 `cny_total` 都是 nullable legacy quote snapshot，旧值原样保留，serializer/adapter 允许 JSON `null`，canonical create 不要求也不读取。真实历史 `status='received'` 必须由 migration 回填 `legacy_received=True`；允许其 `paid_cny_cost`/`paid_at` 为 NULL/0，并在状态约束中单独列出 legacy branch。新 received 必须 `legacy_received=False`、paid facts 非空；service rejects direct legacy transition and tests a real pre-migration received fixture.

`PurchaseOrder` 的 `Meta.constraints` 必须落成可执行的 `CheckConstraint`，并由服务状态矩阵共同校验：

```python
class PurchaseOrder:
    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(status='draft', paid_cny_cost=Decimal('0.00'), paid_at__isnull=True)
                    | Q(status='in_transit', legacy_received=False, paid_cny_cost__gt=0, paid_at__isnull=False)
                    | Q(status='received', legacy_received=False, paid_cny_cost__gt=0, paid_at__isnull=False)
                    | Q(status='received', legacy_received=True,
                       paid_at__isnull=True, paid_cny_cost__isnull=True)
                    | Q(status='received', legacy_received=True,
                       paid_at__isnull=True, paid_cny_cost=Decimal('0.00'))
                    | Q(status='cancelled', paid_cny_cost=Decimal('0.00'), paid_at__isnull=True,
                       payment_idempotency_key__isnull=True, arrival_idempotency_key__isnull=True)
                ), name='purchase_order_status_payment_consistent',
            ),
        ]

class PurchaseOrderItem:
    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(packaging_status='review_required', box_quantity__isnull=True, unit_price_rub_per_box__isnull=True)
                | Q(packaging_status='normalized', box_size__gt=0, box_quantity__gt=0, unit_price_rub_per_box__gte=0)
                | Q(packaging_status='unrepresentable', box_size__gt=0, box_quantity__gt=0, unit_price_rub_per_box__gte=0,
                   unit_price_rub__isnull=True, unit_price_cny__isnull=True),
                name='purchase_item_packaging_consistent',
            ),
            models.CheckConstraint(condition=Q(actual_cost_cny__gte=0), name='purchase_item_actual_cost_nonnegative'),
            models.CheckConstraint(
                condition=Q(packaging_status='review_required')
                | Q(packaging_status__in=['normalized', 'unrepresentable'], quantity=F('box_size') * F('box_quantity')),
                name='purchase_item_quantity_matches_boxes',
            ),
        ]

def clean(self):
    super().clean()
    if self.packaging_status in {
        self.PackagingStatus.NORMALIZED,
        self.PackagingStatus.UNREPRESENTABLE,
    }:
        if self.box_size is None or self.box_quantity is None or self.quantity != self.box_size * self.box_quantity:
            raise ValidationError('canonical 采购数量必须等于盒规乘盒数')
    if self.packaging_status == self.PackagingStatus.UNREPRESENTABLE:
        if self.unit_price_rub is not None or self.unit_price_cny is not None:
            raise ValidationError('不可表示的旧报价快照必须为 NULL')
```

服务矩阵固定为 `DRAFT -> IN_TRANSIT` 仅允许一次完整付款，`IN_TRANSIT -> RECEIVED` 仅允许一次整单到货；`CANCELLED` 只能由未付款 `DRAFT` 进入，必须 `paid_cny_cost=0`、`paid_at=NULL`、payment/arrival key 均为 NULL 且不存在 `PurchasePayment`，不能从已付款状态直接取消，已付款更正走后续更正动作。`IN_TRANSIT/RECEIVED` 不能取消，重复同 key 只能 replay 原事实。`review_required` 旧输入无法转换时阻断付款；`unrepresentable` 是 canonical 合法状态，仍允许付款。

添加中文注释说明旧 `quantity`/`unit_price_rub` 是历史支数/每支价快照，不能作为新采购金额来源。

### Step 3（2–5 分钟）：写无损迁移函数 RED/fixture

在 migration 中实现 `forwards(apps, schema_editor)`：先添加上述字段和 draft replay 字段，再逐行读取旧非空 `quantity`、`box_size` 和 `unit_price_rub`。有正 `box_size` 且支数可整除时写 `box_quantity = quantity // box_size`、`unit_price_rub_per_box = unit_price_rub × box_size`；旧两位每支价格或 CNY 快照无法无损表示时，两个 legacy price 字段均写 NULL、`packaging_status=unrepresentable`，但 canonical 仍可付款；只有旧输入无法转换为盒规/盒数时才保留 canonical null 并写 `review_required`。历史行的 payment/arrival/draft key、fingerprint、draft operator/date 均保持 NULL，不伪造重放事实。迁移不填 `paid_cny_cost`、`paid_at`，也不使用 `exchange_rate` 伪造付款成本。

在测试中固定 `quantity=25, box_size=25, old unit_price_rub=1000` 转为一盒每盒价 25000，并断言旧总额守恒；`quantity=26, box_size=25` 和无盒规行都必须标记 review。

### Step 4（2–5 分钟）：生成并检查迁移

Run:

```bash
.venv/bin/python manage.py makemigrations cigars
sed -n '1,260p' cigars/migrations/0036_purchase_payment_state.py
.venv/bin/python manage.py migrate --plan
```

Expected: `0036` 只添加字段、约束和 `RunPython`，依赖 `0035`；没有删除旧字段、没有伪造付款/到货流水。随后在临时迁移数据库实际执行 `migrate cigars 0036`，查询可整除、不可整除和无盒规三类历史行，验证回填/NULL/status 与约束均可运行。

### Step 5（2–5 分钟）：运行 GREEN 与直接模型约束测试

Run: `.venv/bin/python manage.py test cigars.tests.test_purchase_packaging cigars.tests.test_sales_accounting -v 2`

Expected: canonical 算式、迁移守恒、状态约束和历史 review 行全部通过。

`cigars/tests/test_purchase_migration.py` 必须建立真实旧 schema fixture：一行 `status='received'`、非空 `exchange_rate`/legacy prices，执行 `0036` forwards 后断言旧值保留、`legacy_received=True`、paid facts 为 NULL/0；另测新 received 的 `legacy_received=False` + paid facts 约束。命令为 `.venv/bin/python manage.py test cigars.tests.test_purchase_migration -v 2`。

### Step 6（2–5 分钟）：Task 1 双审查与提交

由 Luna A 对照两份 spec 和真实模型检查字段/约束，Luna B 独立检查迁移数据安全和 canonical 语义；修正后运行 `git diff --check`。

```bash
git add cigars/models.py cigars/migrations/0036_purchase_payment_state.py cigars/tests/test_purchase_packaging.py cigars/tests/test_purchase_migration.py
git commit -m "功能：建立采购盒数语义与状态迁移"
```

## Task 2：实现 ORM 不可变边界与 accounting 动作模型

**Objective:** 建立采购付款、费用、分红事实模型，并让普通 ORM 不能绕过已入账保护。

**Files:**

- Modify: `accounting/models.py`
- Create: `accounting/migrations/0012_accounting_actions.py`、`accounting/migrations/0013_draft_actions.py`、`accounting/mutation_scope.py`
- Test: `accounting/tests/test_action_models.py`、`accounting/tests/test_draft_action_models.py`

### Step 1（2–5 分钟）：写 posted 旁路失败测试

在 `ActionModelMutationTest` 对每种最终事实覆盖实例 `save()`/`delete()`、QuerySet `update()`/`delete()`/`bulk_update()`/`bulk_create()`；目标包括 `PurchasePayment`、已付款/已入库 `PurchaseOrder`、`PurchaseOrderItem.actual_cost_cny`、`Expense`、已确认 `Dividend`、`PurchaseDraftAction` 和 `DividendDraftAction`；两类 action 均 append-only，普通 ORM 不可更新/删除。每条都断言 `LedgerMutationError`，并断言数据库值未变化。

```python
def test_posted_purchase_order_orm_bypass_is_rejected(self):
    order = paid_received_order()
    with self.assertRaises(LedgerMutationError):
        order.save(update_fields=['paid_cny_cost'])
    with self.assertRaises(LedgerMutationError):
        PurchaseOrder.objects.filter(pk=order.pk).update(note='bypass')
    with self.assertRaises(LedgerMutationError):
        PurchaseOrder.objects.filter(pk=order.pk).delete()
    with self.assertRaises(LedgerMutationError):
        PurchaseOrder.objects.bulk_update([order], ['paid_cny_cost'])
    with self.assertRaises(LedgerMutationError):
        PurchaseOrder.objects.bulk_create([order])
```

Run: `.venv/bin/python manage.py test accounting.tests.test_action_models accounting.tests.test_draft_action_models -v 2`

Expected: FAIL，动作模型和 QuerySet 保护尚未实现。

### Step 2（2–5 分钟）：定义模型字段和分类

扩展 `LedgerTransaction.TransactionType`：`PURCHASE_PAYMENT`、`PURCHASE_RECEIPT`、`EXPENSE`、`DIVIDEND`。扩展 `LedgerPosting.Category`：`PURCHASE_IN_TRANSIT`、`SALARY_EXPENSE`、`RENT_EXPENSE`、`UTILITIES_EXPENSE`、`OTHER_EXPENSE`、`DIVIDEND_DISTRIBUTION`、`INVENTORY_ADJUSTMENT_GAIN`、`INVENTORY_ADJUSTMENT_LOSS`、`RECONCILIATION_GAIN`、`RECONCILIATION_LOSS`。

动作模型使用以下真实 Django 字段定义（金额精度与 API Decimal 字符串一致）：

```python
class PurchasePayment(models.Model):
    class Status(models.TextChoices):
        POSTED = 'posted', '已入账'

    status = models.CharField(max_length=12, choices=Status.choices, default=Status.POSTED)
    purchase_order = models.OneToOneField('cigars.PurchaseOrder', on_delete=models.PROTECT)
    fund_account = models.ForeignKey(FundAccount, on_delete=models.PROTECT)
    rub_amount = models.DecimalField(max_digits=22, decimal_places=2)
    cny_cost = models.DecimalField(max_digits=22, decimal_places=2)
    business_date = models.DateField()
    operator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    ledger_transaction = models.OneToOneField(LedgerTransaction, on_delete=models.PROTECT)
    idempotency_key = models.CharField(max_length=128, unique=True)
    request_fingerprint = models.CharField(max_length=64)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(rub_amount__gte=0, cny_cost__gte=0), name='purchase_payment_amounts_nonnegative'),
        ]

class Expense(models.Model):
    class Status(models.TextChoices):
        POSTED = 'posted', '已入账'
    class Category(models.TextChoices):
        SALARY = 'salary', '工资'
        RENT = 'rent', '房租'
        UTILITIES = 'utilities', '水电'
        OTHER = 'other', '其他'

    status = models.CharField(max_length=12, choices=Status.choices, default=Status.POSTED)
    category = models.CharField(max_length=20, choices=Category.choices)
    fund_account = models.ForeignKey(FundAccount, on_delete=models.PROTECT)
    original_amount = models.DecimalField(max_digits=22, decimal_places=8)
    amount_cny = models.DecimalField(max_digits=22, decimal_places=2)
    business_date = models.DateField()
    operator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    ledger_transaction = models.OneToOneField(LedgerTransaction, on_delete=models.PROTECT)
    idempotency_key = models.CharField(max_length=128, unique=True)
    note = models.TextField(blank=True, default='')

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(original_amount__gte=0, amount_cny__gte=0), name='expense_amounts_nonnegative'),
        ]

class Dividend(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'draft', '草稿'
        POSTED = 'posted', '已入账'

    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT)
    total_cny = models.DecimalField(max_digits=22, decimal_places=2)
    partner_a_amount_cny = models.DecimalField(max_digits=22, decimal_places=2)
    partner_b_amount_cny = models.DecimalField(max_digits=22, decimal_places=2)
    partner_a_account = models.ForeignKey(FundAccount, on_delete=models.PROTECT, related_name='+', null=True, blank=True)
    partner_b_account = models.ForeignKey(FundAccount, on_delete=models.PROTECT, related_name='+', null=True, blank=True)
    business_date = models.DateField()
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name='+')
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name='+')
    confirmed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name='+')
    version = models.PositiveIntegerField(default=1)
    confirm_idempotency_key = models.CharField(max_length=128, unique=True, null=True, blank=True)
    confirm_request_fingerprint = models.CharField(max_length=64, null=True, blank=True)
    warning_fingerprint = models.CharField(max_length=64, null=True, blank=True)
    warning_ack = models.BooleanField(null=True, blank=True)
    warning_code = models.CharField(max_length=64, blank=True, default='')
    warning_retained_earnings_cny = models.DecimalField(max_digits=22, decimal_places=2, null=True, blank=True)
    ledger_transaction = models.OneToOneField(LedgerTransaction, on_delete=models.PROTECT, null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(total_cny__gte=0, partner_a_amount_cny__gte=0, partner_b_amount_cny__gte=0), name='dividend_amounts_nonnegative'),
        ]
```

```python
class PurchaseDraftAction(models.Model):
    class ActionType(models.TextChoices):
        CREATE = "create", "创建"
        UPDATE = "update", "编辑"
        CANCEL = "cancel", "取消"
    purchase_order = models.ForeignKey("cigars.PurchaseOrder", null=True, blank=True, on_delete=models.PROTECT)
    action_type = models.CharField(max_length=12, choices=ActionType.choices)
    idempotency_key = models.CharField(max_length=128, unique=True)
    request_fingerprint = models.CharField(max_length=64)
    result_version = models.PositiveIntegerField(null=True, blank=True)
    operator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

class DividendDraftAction(models.Model):
    class ActionType(models.TextChoices):
        CREATE = "create", "创建"
        UPDATE = "update", "编辑"
    dividend = models.ForeignKey(Dividend, null=True, blank=True, on_delete=models.PROTECT)
    action_type = models.CharField(max_length=12, choices=ActionType.choices)
    idempotency_key = models.CharField(max_length=128, unique=True)
    request_fingerprint = models.CharField(max_length=64)
    result_version = models.PositiveIntegerField(null=True, blank=True)
    operator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
```

`A+B=total` 由服务锁内校验、posted 不可变和专门 RED/GREEN 测试保证。SQLite 不可靠支持 Decimal `F('a') + F('b')` 跨字段 CheckConstraint，migration 注释记录这个 DB 限制。

`Expense` 与 `PurchasePayment` 只有 `posted` 状态，ledger 外键非空；`Dividend` 草稿账户采用唯一方案：`partner_a_account`/`partner_b_account` 为 `null=True, blank=True`，草稿允许未填，`update_dividend_draft()` 和 `confirm_dividend()` 必须校验已填、启用、CNY 且不同。只保留金额非负本表约束；posted/ledger 关系由服务和不可变测试保证，不创建跨关系或冗余非空 CheckConstraint。SQLite 版本不对 Decimal `F('a') + F('b')` 跨字段求和加 CheckConstraint；`A+B=total` 由服务锁内校验、posted 不可变和专门测试保证，迁移注释记录这个 DB 限制。

采购草稿创建 mirror 可保留在 `PurchaseOrder.draft_idempotency_key`，但唯一事实是 append-only `PurchaseDraftAction`；每次 create/update/cancel 都有独立 action key + fingerprint，fingerprint 覆盖 canonical items、business_date、operator、note 和 expected_version，不能用单一可覆盖 draft key 做 edit replay。payment 唯一事实仍是 `PurchasePayment.idempotency_key`，`PurchaseOrder.payment_idempotency_key` 只是同一 atomic 中写入的只读 mirror；arrival key 只在 PurchaseOrder 上保存到货事实。三类 key/fingerprint 互不复用，历史迁移保持所有 key/fingerprint 为 NULL。

所有金额非负，分红两栏精确求和；草稿不关联 ledger。为 `PurchasePayment`、`Expense`、`Dividend` 写 `save()`/`delete()` 终态保护，并让受控服务使用 `ledger_mutation_scope()` 调用 `models.Model.save()` 的明确 bypass。

### Step 3（2–5 分钟）：实现 QuerySet 全路径保护

为 `PurchasePaymentQuerySet`、`ExpenseQuerySet`、`DividendQuerySet`、`PurchaseOrderQuerySet` 和必要的 `PurchaseOrderItemQuerySet` 实现 `_reject_finalized()`；覆盖 `update()`、`delete()`、`bulk_update()`、`bulk_create()`，同时拒绝 `update_or_create()`/`get_or_create()` 对终态的旁路写入。 `bulk_create()` 对终态对象拒绝，草稿创建只有受控服务可调用。

保护函数检查 `ledger_mutation_scope.active`；没有 scope 必须抛错，有 scope 还要校验 `reason`、operator 和允许字段集合，禁止借 scope 修改金额、账户、业务日期或来源。`PurchaseOrder.save/delete`、`PurchaseOrderItem.save/delete` 与各自 QuerySet 保护使用同一 scope；采购付款/到货服务只在 posting 已成功的 atomic 内，用 `ledger_mutation_scope(reason='purchase_payment'|'purchase_receipt', operator=operator)` 调用受控 `models.Model.save()`，普通测试仍走拒绝路径。注释解释 manager 保护和服务 bypass 的边界，避免测试或合法入账自身被 manager 阻断。

### Step 4（2–5 分钟）：生成 accounting migration

Run:

```bash
.venv/bin/python manage.py makemigrations accounting
sed -n '1,320p' accounting/migrations/0012_accounting_actions.py
sed -n '1,320p' accounting/migrations/0013_draft_actions.py
.venv/bin/python manage.py showmigrations accounting cigars
```

Expected: `0012` 依赖 accounting 最新迁移和 `cigars 0036`，有金额/状态/唯一幂等约束，无循环依赖。

### Step 5（2–5 分钟）：验证模型和受控 bypass

测试先用普通 ORM 验证所有旁路失败，再调用一个最小 `post_test_fact()` 受控 helper 验证合法服务写入成功；测试 `bulk_update` 和 `bulk_create` 不会误杀草稿构建。

Run: `.venv/bin/python manage.py check && .venv/bin/python manage.py makemigrations --check && .venv/bin/python manage.py migrate --plan && .venv/bin/python manage.py test accounting.tests.test_action_models accounting.tests.test_draft_action_models -v 2`

Expected: 旁路全部拒绝，PurchaseDraftAction/DividendDraftAction append-only 测试通过，受控 posting 可保存，终态事实字段保持不变。

### Step 6（2–5 分钟）：Task 2 双审查与提交

Luna A 审查模型/迁移约束，Luna B 审查实例和 QuerySet 全覆盖以及 bypass 安全；通过后提交。

```bash
git add accounting/models.py accounting/mutation_scope.py accounting/migrations/0012_accounting_actions.py accounting/migrations/0013_draft_actions.py accounting/tests/test_action_models.py accounting/tests/test_draft_action_models.py
git commit -m "功能：建立采购费用分红事实与不可变边界"
```

## Task 3：采购草稿、包装兼容和整单创建幂等

**Objective:** 让采购草稿创建/编辑只接受 canonical payload，旧 agent 明确转换，整单写入原子且可 replay。

**Files:** Modify: `cigars/services.py`、`cigars/agent_api.py`；Create: `accounting/purchase_actions.py`；Test: `accounting/tests/test_purchase_draft_actions.py`、`cigars/tests/test_agent_api.py`

### Step 1（2–5 分钟）：写草稿 contract RED

测试 `create_purchase_order()` 接受：

```python
items=[{'cigar_id': cigar.id, 'box_size': 25, 'box_quantity': 1,
        'unit_price_rub_per_box': '100.00'}]
```

断言 `sticks=25`、`rub_subtotal=100`、订单 RUB 总额为 100；旧 payload 只通过显式 `normalize_legacy_purchase_item()` 进入。测试缺字段、零值、review 行和旧非整除行都返回 `packaging_review_required` 并阻断付款；另测 canonical 每盒价无法无损回填旧两位每支字段时写 NULL + `unrepresentable`，仍可付款。

```python
def test_purchase_draft_is_idempotent_and_atomic(self):
    payload = canonical_payload()
    first = create_purchase_order(**payload, idempotency_key='po-draft-1')
    replay = create_purchase_order(**payload, idempotency_key='po-draft-1')
    self.assertEqual(first.pk, replay.pk)
    with self.assertRaisesRegex(PurchaseActionError, 'idempotency_conflict'):
        create_purchase_order(**{**payload, 'items': changed_items()}, idempotency_key='po-draft-1')
```

Run: `.venv/bin/python manage.py test accounting.tests.test_purchase_draft_actions -v 2`

Expected: FAIL，服务仍以旧每支字段建单。

### Step 2（2–5 分钟）：实现 canonical normalizer

在 Task3 新建的 `accounting/purchase_actions.py` 定义统一异常和 canonical value-object；`cigars/services.py` 只 import 并调用它们：

```python
class PurchaseActionError(Exception):
    def __init__(self, code: str, details: dict[str, object] | None = None):
        super().__init__(code)
        self.code = code
        self.details = details or {}

def normalize_legacy_purchase_item(*, box_size: int | None, quantity_sticks: int, unit_price_rub_per_stick: Decimal) -> dict:
    if box_size is None or box_size <= 0 or quantity_sticks <= 0 or quantity_sticks % box_size:
        raise PurchaseActionError(code='packaging_review_required', details={'quantity_sticks': quantity_sticks, 'box_size': box_size})
    return canonical_purchase_item(box_size=box_size, box_quantity=quantity_sticks // box_size,
                                   unit_price_rub_per_box=unit_price_rub_per_stick * box_size,
                                   legacy_unit_price_rub=unit_price_rub_per_stick)
def canonical_purchase_item(*, box_size: int, box_quantity: int, unit_price_rub_per_box: Decimal,
                            legacy_unit_price_rub: Decimal | None = None,
                            legacy_unit_price_cny: Decimal | None = None) -> dict:
    box_size = int(box_size)
    box_quantity = int(box_quantity)
    unit_price_rub_per_box = Decimal(str(unit_price_rub_per_box))
    legacy_unit_price_rub = None if legacy_unit_price_rub is None else Decimal(str(legacy_unit_price_rub))
    legacy_unit_price_cny = None if legacy_unit_price_cny is None else Decimal(str(legacy_unit_price_cny))
    if not unit_price_rub_per_box.is_finite() or any(value is not None and not value.is_finite()
                                                     for value in (legacy_unit_price_rub, legacy_unit_price_cny)):
        raise ValueError('采购金额必须是有限 Decimal')
    if box_size <= 0 or box_quantity <= 0 or unit_price_rub_per_box < 0:
        raise PurchaseActionError(code='invalid_packaging', details={'box_size': box_size, 'box_quantity': box_quantity})
    if legacy_unit_price_rub is not None and legacy_unit_price_rub * box_size != unit_price_rub_per_box:
        raise PurchaseActionError(code='legacy_snapshot_conflict', details={'unit_price_rub': str(legacy_unit_price_rub)})
    return {'sticks': box_size * box_quantity, 'rub_subtotal': Decimal(box_quantity) * unit_price_rub_per_box,
            'box_size': box_size, 'box_quantity': box_quantity, 'unit_price_rub_per_box': unit_price_rub_per_box,
            'unit_price_rub': legacy_unit_price_rub, 'unit_price_cny': legacy_unit_price_cny,
            'packaging_status': 'normalized' if legacy_unit_price_rub is not None else 'unrepresentable'}
```

canonical helper 返回 `sticks`、`rub_subtotal`、`packaging_status` 和旧价格兼容快照，只从盒规、盒数、每盒价计算；无法无损表示旧两位快照时返回 NULL + `unrepresentable`。legacy helper 仅在 `quantity_sticks % box_size == 0` 时返回 canonical；无盒规/不可整除抛 `BusinessRuleError(code='packaging_review_required')`，错误 details 包含 item index、旧数量、盒规，禁止静默猜测。

注释说明旧 agent 只在兼容边界转换，主流程不会再读取旧字段。

`cigars/agent_api.py:create_purchase_order_command()` 先把旧 `{exchange_rate, quantity, unit_price_rub, unit_price_cny}` payload 转成 canonical；缺少 `business_date` 时只允许兼容默认“莫斯科当前业务日”并把默认值写入 fingerprint，不能静默使用服务器时间。旧 `exchange_rate` 仅保留为报价快照，缺字段或非整除返回 `{error, code: 'packaging_review_required', details}`；同 key 的 canonical fingerprint 一致 replay，不一致返回 409 `idempotency_conflict`。新增 adapter 测试覆盖缺日期、旧字段转换、fingerprint 冲突和错误结构。

### Step 3（2–5 分钟）：加入创建幂等和 atomic

把 `create_purchase_order()` 改为或委托：

```python
@_retry_sqlite_locked
def create_purchase_order(*, supplier_id, items, business_date, operator,
                          idempotency_key, expected_version=None, note='') -> PurchaseOrder:
    with transaction.atomic():
        return _create_purchase_order_locked(supplier_id=supplier_id, items=items,
            business_date=business_date, operator=operator, idempotency_key=idempotency_key,
            expected_version=expected_version, note=note)
```

用 `_retry_sqlite_locked`、writer gate、`transaction.atomic()` 包住供应商校验、全部明细 canonical 化和订单创建；第一步按 append-only `PurchaseDraftAction(action_type='create')` 的 key/fingerprint 查询并核对，参数一致返回同一订单（即使订单已付款/取消也先 replay），冲突返回 `409/idempotency_conflict`；创建成功在同一 atomic 写 action、order creation mirror 和 result_version。订单创建任何明细失败都不留下空订单。

### Step 4（2–5 分钟）：实现草稿编辑版本控制

增加 `update_purchase_order_draft(*, purchase_order_id, items, expected_version, idempotency_key, operator, note='')`；先按 append-only `PurchaseDraftAction(action_type='update')` key/fingerprint replay/conflict，再锁订单，只有 DRAFT 可编辑，版本不符返回 `409/version_conflict`，成功后递增 version 并写 action.result_version。canonical 字段变更不得覆盖旧已付款事实；payment/arrival key 不参与草稿 replay。另增 `cancel_purchase_order(*, purchase_order_id, operator, idempotency_key, expected_version, note='')`：仅未付款 DRAFT 可取消，按 `action_type='cancel'` append-only key replay/conflict；成功后写 CANCELLED、paid_cny_cost=0、paid_at=NULL、payment_idempotency_key=NULL、arrival_idempotency_key=NULL，且不存在 PurchasePayment。

### Step 5（2–5 分钟）：GREEN、原子回滚和冲突测试

覆盖 create 及多次 update 各自 action key replay/conflict、cancel service 的 DRAFT/已付款状态矩阵、两个不同 key 并发只成功一次、第二条明细校验失败无订单/明细残留，以及 update/cancel 版本冲突和 ORM 终态约束。cancel 测试固定传入 `expected_version` 与独立 key，断言 replay 返回原订单、改 note 冲突，且取消后无付款/到货事实。

Run: `.venv/bin/python manage.py test accounting.tests.test_purchase_draft_actions cigars.tests.test_agent_order_inventory -v 2`

Expected: canonical 总额正确、重复参数返回原订单、冲突为 409、失败事务无残留；旧 agent 的非整除行得到稳定 code。

### Step 6（2–5 分钟）：Task 3 双审查与提交

Luna A 审查 canonical 公式和兼容边界，Luna B 审查幂等 fingerprint、版本锁和 atomic 回滚；通过后提交。

```bash
git add cigars/services.py cigars/agent_api.py accounting/purchase_actions.py accounting/tests/test_purchase_draft_actions.py cigars/tests/test_agent_api.py
git commit -m "功能：实现采购草稿盒数语义与幂等"
```

## Task 4：采购一次付款、在途和整单到货

**Objective:** 用付款前 RUB 移动平均建立在途成本，按 canonical RUB 小计分配 CNY 尾差，并让付款/到货重放返回原事实。

**Files:** Modify: `accounting/purchase_actions.py`、`cigars/services.py`、`cigars/sales_accounting.py`；Test: `accounting/tests/test_purchase_actions.py`、`cigars/tests/test_agent_order_inventory.py`、`cigars/tests/test_sales_accounting.py`

付款/到货测试从 `accounting.purchase_actions` import 同一 `PurchaseActionError`，不再定义第二个异常类。

`accounting/tests/test_purchase_actions.py` 的 `PurchaseActionTestBase.setUp()` 完整 import `create_completed_day1_fixture` 并保存 `self.operator/self.day/self.rub_account`；所有付款/到货测试共享 completed Day1，首个 payment replay 与首个 arrival test 都必须通过 service gate。销售 fixture 直接调用现有 `create_sales_order_draft(items, operator, customer_name, customer_transport_fee_cny)`，不使用未确认的 `agent_context` 分支。

### Step 1（2–5 分钟）：写付款 RED

测试打开 RUB 账户后创建两条 canonical 明细，调用：

```python
payment = pay_purchase_order(
    purchase_order_id=order.id, rub_account_id=rub_account_id, business_date=business_date,
    operator=operator, idempotency_key=idempotency_key
)
```

断言 RUB 总额是各 `box_quantity * unit_price_rub_per_box` 之和，付款承接 `_outflow_cny_cost()` 的付款前 CNY 成本，订单变为 `IN_TRANSIT`，产生一笔 `PURCHASE_PAYMENT` 和 `PURCHASE_IN_TRANSIT` posting。

```python
def test_payment_replay_precedes_state_rejection(self):
    order = canonical_draft()
    first = pay_purchase_order(purchase_order_id=order.id, rub_account_id=self.rub.id,
                               business_date=self.day, operator=self.operator,
                               idempotency_key='pay-1')
    replay = pay_purchase_order(purchase_order_id=order.id, rub_account_id=self.rub.id,
                                business_date=self.day, operator=self.operator,
                                idempotency_key='pay-1')
    self.assertEqual(first.id, replay.id)
```

Run: `.venv/bin/python manage.py test accounting.tests.test_purchase_actions.PurchasePaymentTest -v 2`

Expected: FAIL，付款服务不存在。

### Step 2（2–5 分钟）：实现幂等优先和锁顺序

`pay_purchase_order()` 定义上方加 `@_retry_sqlite_locked`，函数体内使用 `transaction.atomic()`；先 writer gate，再按 key 查 `PurchasePayment`/ledger 并核对采购单、RUB 账户、canonical RUB 总额、日期和 operator，匹配则返回原 payment，即使订单已 IN_TRANSIT。只有没有 replay 时才锁订单和账户（按 id 排序）并检查 Day 1、状态、review packaging、RUB 币种和余额。

注释说明幂等检查必须先于状态拒绝，锁顺序固定以避免 SQLite/数据库死锁；所有新代码禁止用旧每支价格计算金额。

### Step 3（2–5 分钟）：实现 posting 和状态更新

使用 `_post_transaction_once()` 写 RUB 资金减少和 `PURCHASE_IN_TRANSIT` CNY 增加；在同一事务创建 `PurchasePayment`，用 `ledger_mutation_scope(reason='purchase_payment')` 写入付款时间、CNY 成本和 `IN_TRANSIT`。CNY 成本必须等于 posting，余额不足返回 `insufficient_balance`，参数冲突返回 `idempotency_conflict`。

### Step 4（2–5 分钟）：写到货 RED 和 canonical fixture

固定两条明细 `box_size=25, box_quantity=1, per_box=100` 与 `box_size=10, box_quantity=2, per_box=100`，RUB 小计为 100 和 200，付款 CNY 为 100；另测 normalized 与 unrepresentable 均可到货，review_required 返回 packaging_review_required；断言实际成本为 33.33 和 66.67，且 `sum(actual_cost_cny)=100`。断言每个批次支数分别为 25 和 20，包装来自 canonical 字段；然后对第一批次执行拆盒，断言拆盒前后 `remaining_cost_cny`、整单成本池和批次总成本相同，再按既有 FIFO 销售分配算法卖出全部支数，最后销售单位取剩余成本池尾差并使每批 `remaining_cost_cny=0`。

```python
from django.db.models import Sum
from cigars.models import PurchaseBatch

def test_receive_accepts_normalized_and_unrepresentable_but_rejects_review(self):
    for status in ('normalized', 'unrepresentable'):
        order = paid_canonical_order(packaging_status=status)
        batches = receive_paid_purchase_order(purchase_order_id=order.id, business_date=self.day, operator=self.operator, idempotency_key=f'arrive-{status}')
        self.assertTrue(batches)
    review = paid_legacy_review_order()
    with self.assertRaisesRegex(PurchaseActionError, 'packaging_review_required'):
        receive_paid_purchase_order(purchase_order_id=review.id, business_date=self.day, operator=self.operator, idempotency_key='arrive-review')

def test_receive_allocates_cost_pool_tail_and_replays(self):
    order = paid_canonical_order(rub_subtotals=['100.00', '200.00'], paid_cny_cost='100.00')
    batches = receive_paid_purchase_order(purchase_order_id=order.id, business_date=self.day,
                                          operator=self.operator, idempotency_key='arrive-1')
    self.assertEqual(list(order.items.order_by('id').values_list('actual_cost_cny', flat=True)),
                     [Decimal('33.33'), Decimal('66.67')])
    self.assertEqual(sum(b.original_cost_cny for b in batches), Decimal('100.00'))
    self.assertEqual(sum(b.remaining_cost_cny for b in batches), Decimal('100.00'))
    self.assertEqual(receive_paid_purchase_order(purchase_order_id=order.id, business_date=self.day,
                     operator=self.operator, idempotency_key='arrive-1'), batches)
    before_split = sum(b.remaining_cost_cny for b in batches)
    split_purchase_batch_box(batch_id=batches[0].id, operator=self.operator)
    self.assertEqual(sum(batches[0].__class__.objects.filter(pk__in=[b.id for b in batches]).values_list('remaining_cost_cny', flat=True)), before_split)
    from cigars.services import create_sales_order_draft, confirm_sales_order
    from cigars.sales_accounting import ship_sales_order
    for cigar_id in {batch.cigar_id for batch in batches}:
        quantity = sum(batch.remaining for batch in batches if batch.cigar_id == cigar_id)
        sales_order = create_sales_order_draft(
            items=[{'cigar_id': cigar_id, 'sale_unit': 'stick', 'quantity': quantity, 'unit_price': '1.00'}],
            operator=self.operator, customer_name='测试客户',
            customer_transport_fee_cny='0.00',
        )
        confirm_sales_order(
            sales_order_id=sales_order.id, operator=self.operator,
        )
        ship_sales_order(order_id=sales_order.id, business_date=self.day,
                         operator=self.operator, idempotency_key=f'ship-fifo-{cigar_id}', note='出库')
    self.assertEqual(PurchaseBatch.objects.filter(pk__in=[b.id for b in batches]).aggregate(total=Sum('remaining_cost_cny'))['total'], Decimal('0.00'))
```

Run: `.venv/bin/python manage.py test accounting.tests.test_purchase_actions.PurchaseReceiptTest -v 2`

Expected: FAIL，整单到货仍读取旧字段且没有在途转库存。

### Step 5（2–5 分钟）：实现到货幂等优先和尾差

实现：

```python
@_retry_sqlite_locked
def receive_paid_purchase_order(
    *, purchase_order_id, business_date, operator, idempotency_key, note=''
) -> list[PurchaseBatch]:
    with transaction.atomic():
        return _receive_paid_purchase_order_locked(purchase_order_id=purchase_order_id,
            business_date=business_date, operator=operator, idempotency_key=idempotency_key, note=note)
```

先按 key 查询 `arrival_idempotency_key`/`PURCHASE_RECEIPT` 并核对订单、日期、operator，匹配则返回原批次；没有 replay 才锁订单和明细，要求 `IN_TRANSIT`、所有行 `packaging_status in {'normalized', 'unrepresentable'}`、无既有批次；完全从 canonical `box_size`、`box_quantity`、`unit_price_rub_per_box` 构建批次，`review_required` 稳定返回 `packaging_review_required` 并阻断到货。按每行 `rub_subtotal / rub_total` 分配 paid CNY，Decimal 量化到 0.01，最后一行取总额减已分配；不可少货、不重复扣 RUB、不读取报价汇率。

同一 atomic 内写 `PURCHASE_IN_TRANSIT` 减少和 `INVENTORY` 增加、建立完整 `PurchaseBatch`/`StockMovement.RECEIVE`、填 `actual_cost_cny`、标记 `RECEIVED` 和 arrival key。每个批次必须把该行 CNY 成本精确写入 `PurchaseBatch.original_cost_cny` 和 `remaining_cost_cny`；`unit_cost_cny` 只能作为展示/销售分配参考，FIFO 每次从剩余成本池计算，卖出最后一个单位后 `remaining_cost_cny` 必须精确为 0。补一个完整 FIFO 两批次、最后销售单位尾差归零和批次成本守恒测试，并断言 `original_cost_cny = remaining_cost_cny + sold_cost_cny + adjustment_cost_cny`。中文注释说明最后一行承接尾差和到货不再次付款。

### Step 6（2–5 分钟）：改造旧到货入口和边界测试

`cigars.services.receive_purchase_order()` 委托新服务；草稿返回 `invalid_state`，review 行返回 `packaging_review_required`，已付款/已入库相同 key 返回原事实，其他 key 冲突返回 409。测试 CNY/USDT 误付、负余额、重复付款、付款/到货中途异常无 posting/批次残留、锁冲突重试、并发单写入。

Run: `.venv/bin/python manage.py test accounting.tests.test_purchase_actions cigars.tests.test_agent_order_inventory cigars.tests.test_sales_accounting -v 2`

Expected: 付款前移动平均、canonical RUB/CNY 守恒、库存 FIFO 包装和幂等 replay 全部通过。

### Step 7（2–5 分钟）：Task 4 双审查与提交

Luna A 审查资金/在途/库存不变量，Luna B 独立审查幂等优先顺序、锁重试、尾差和旧入口兼容；通过后提交。

```bash
git add accounting/purchase_actions.py cigars/services.py cigars/sales_accounting.py accounting/tests/test_purchase_actions.py cigars/tests/test_agent_order_inventory.py cigars/tests/test_sales_accounting.py
git commit -m "功能：实现采购付款在途与整单到货"
```

## Task 5：工资、RUB 经营费用和销售人肉费路径

**Objective:** 固定费用币种矩阵，沿用销售单记录人民币实际人肉费，并让费用动作幂等、原子和可重放。

**Files:** Modify: `accounting/services.py`；Create: `accounting/expense_actions.py`；Test: `accounting/tests/test_expense_actions.py`、`accounting/tests/test_operations.py`

### Step 1（2–5 分钟）：写费用和人肉费 RED

`record_expense(*, category, amount, fund_account_id, business_date, operator, idempotency_key, note='')` 测试 salary 只能 CNY，rent/utilities/other 只能 RUB；RUB 使用 `_outflow_cny_cost()`，负/零/超精度/停用/余额不足返回稳定 code。销售人肉费入口及其 gate 由 Task4/Task7 测试，本 Task 不重复 ownership。

Run: `.venv/bin/python manage.py test accounting.tests.test_expense_actions accounting.tests.test_operations -v 2`

Expected: FAIL，费用动作和新增币种规则尚未实现。

### Step 2（2–5 分钟）：实现费用服务和门禁

`record_expense()` 定义上方加 `@_retry_sqlite_locked`，函数体使用 `transaction.atomic()`、writer gate；先按 Expense 幂等键核对完整 category/amount/account/date/operator，再锁账户并调用 `require_day1_completed()`。salary posting 为 CNY 资金减少 + `SALARY_EXPENSE`，其他三类为 RUB 资金减少 + 对应费用分类，RUB CNY 成本来自付款前移动平均。注释说明此动作不是换汇，且不挪用销售人肉费路径。

### Step 3（2–5 分钟）：覆盖原子失败和锁重试

注入 `_retry_sqlite_locked` 的第一次锁冲突，断言第二次成功且只一笔 Expense/ledger；注入 posting 后账户保存失败，断言 Expense、posting 和账户原币事实全部回滚。测试重复参数 replay 与冲突、跨月业务日期、Day 1 未完成 `day1_incomplete`。

Run: `.venv/bin/python manage.py test accounting.tests.test_expense_actions cigars.tests.test_sales_accounting accounting.tests.test_operations -v 2`

Expected: 币种矩阵、销售人肉费隔离、幂等和无残留全部通过。

### Step 4（2–5 分钟）：Task 5 双审查与提交

Luna A 对照费用币种和销售人肉费 spec，Luna B 检查移动平均、事务回滚和错误 code；通过后提交。

```bash
git add accounting/expense_actions.py accounting/services.py accounting/tests/test_expense_actions.py accounting/tests/test_operations.py
git commit -m "功能：实现费用币种矩阵与销售人肉费路径"
```

## Task 6：分红草稿、预览、确认和跨月利润边界

**Objective:** 用统一 Dividend 契约支持可编辑草稿、超留存预览 warning 和一次性确认付款，不把分红计入经营净利润。

**Files:** Create: `accounting/dividend_actions.py`、`accounting/dividend_types.py`、`accounting/errors.py`；Test: `accounting/tests/test_dividend_actions.py`

### Step 1（2–5 分钟）：写统一字段/服务 RED

`DividendDraftAction` 仅允许 `CREATE`/`UPDATE`；首版不支持取消或删除分红草稿，未知 `CANCEL` action_type 必须拒绝并有测试。API 不注册 dividend cancel/delete route；不想分红时继续编辑为 0（若金额约束禁止 0 则保留草稿）。posted Dividend 更不可删除。

固定唯一服务签名：

```python
from dataclasses import dataclass
from decimal import Decimal

@dataclass(frozen=True)
class DividendPreview:
    retained_earnings_cny: Decimal
    requested_cny: Decimal
    warning: dict[str, object] | None
    warning_fingerprint: str

    def to_dict(self) -> dict[str, object]:
        return {'retained_earnings_cny': str(self.retained_earnings_cny),
                'requested_cny': str(self.requested_cny), 'warning': self.warning,
                'warning_fingerprint': self.warning_fingerprint}

class DividendActionError(Exception):
    def __init__(self, code: str, details: dict[str, object] | None = None):
        super().__init__(code)
        self.code = code
        self.details = details or {}

def create_dividend_draft(*, total_cny, business_date, operator,
                           idempotency_key, note='') -> Dividend:
    return _create_dividend_draft_locked(total_cny=total_cny, business_date=business_date,
        operator=operator, idempotency_key=idempotency_key, note=note)
def update_dividend_draft(*, dividend_id, total_cny, partner_a_amount_cny,
                          partner_b_amount_cny, partner_a_account_id,
                          partner_b_account_id, expected_version,
                          idempotency_key, operator, note='') -> Dividend:
    return _update_dividend_draft_locked(dividend_id=dividend_id, total_cny=total_cny,
        partner_a_amount_cny=partner_a_amount_cny, partner_b_amount_cny=partner_b_amount_cny,
        partner_a_account_id=partner_a_account_id, partner_b_account_id=partner_b_account_id,
        expected_version=expected_version, idempotency_key=idempotency_key, operator=operator, note=note)
def preview_dividend(*, dividend_id, operator) -> DividendPreview:
    return _preview_dividend_locked(dividend_id=dividend_id, operator=operator)
def confirm_dividend(*, dividend_id, operator, idempotency_key, expected_version,
                     warning_fingerprint: str, warning_ack: bool) -> Dividend:
    return _confirm_dividend_locked(dividend_id=dividend_id, operator=operator,
        idempotency_key=idempotency_key, expected_version=expected_version,
        warning_fingerprint=warning_fingerprint, warning_ack=warning_ack)
```

测试默认 101.01 分为 A=50.51/B=50.50；编辑后两栏精确相等、账户不同且均为 CNY；草稿无资金/ledger 变化。新增 create/update 各自 append-only action key/fingerprint replay、同 key 改实际 payload 的 `idempotency_conflict`；confirm 相同 key/fingerprint replay、同 key 冲突，以及旧 warning fingerprint 在锁内重算后的 `warning_stale`。

```python
def test_dividend_draft_split_and_current_warning(self):
    draft = create_dividend_draft(total_cny='101.01', business_date=self.day,
                                   operator=self.operator, idempotency_key='div-draft-1')
    self.assertEqual((draft.partner_a_amount_cny, draft.partner_b_amount_cny),
                     (Decimal('50.51'), Decimal('50.50')))
    preview = preview_dividend(dividend_id=draft.id, operator=self.operator)
    self.assertIn('warning_fingerprint', preview.to_dict())
    self.assertIn('warning', preview.to_dict())
    with self.assertRaises(ValidationError):
        DividendDraftAction(action_type='cancel', idempotency_key='div-cancel', request_fingerprint='x', operator=self.operator).full_clean()

def test_dividend_replay_conflict_and_stale_warning(self):
    first = create_dividend_draft(total_cny='50.00', business_date=self.day,
                                  operator=self.operator, idempotency_key='div-replay-1')
    replay = create_dividend_draft(total_cny='50.00', business_date=self.day,
                                   operator=self.operator, idempotency_key='div-replay-1')
    self.assertEqual(first.pk, replay.pk)
    with self.assertRaisesRegex(DividendActionError, 'idempotency_conflict'):
        create_dividend_draft(total_cny='51.00', business_date=self.day,
                              operator=self.operator, idempotency_key='div-replay-1')
    preview = preview_dividend(dividend_id=first.id, operator=self.operator)
    warning = preview.to_dict()
    seed_profit_facts(sales=Decimal('500.00'))
    with self.assertRaisesRegex(DividendActionError, 'warning_stale'):
        confirm_dividend(dividend_id=first.id, operator=self.operator,
                         idempotency_key='div-confirm-1', expected_version=first.version,
                         warning_fingerprint=warning['warning_fingerprint'], warning_ack=True)
```

Run: `.venv/bin/python manage.py test accounting.tests.test_dividend_actions -v 2`

Expected: FAIL，Dividend 服务和 preview 契约尚未存在。

### Step 2（2–5 分钟）：实现草稿幂等和版本

创建/编辑/confirm 定义上方分别加 `@_retry_sqlite_locked`，函数体使用 `transaction.atomic()`、writer gate。先按 append-only `DividendDraftAction(action_type=create|update)` 的独立 key + fingerprint 查询并核对 total、A/B amounts、A/B accounts、business_date、operator、note 和 expected_version；一致 replay，冲突 `idempotency_conflict`。confirm 先按 confirm key + confirm fingerprint 做同参数 replay/conflict，再锁 Dividend，要求 draft 和 expected version，递增 version；posted 不能改。created_by/updated_by 在每次草稿写入时保存，confirm 成功写入 confirmed_by（确认 operator），注释解释草稿不触达资金，版本锁保护双人同时编辑。

### Step 3（2–5 分钟）：实现 preview warning 契约

`preview_dividend()` 返回派生 `retained_earnings_cny`、`total_cny`、`warning: {code, retained_earnings_cny, requested_cny, fingerprint}`；若持久化 `warning_retained_earnings_cny`，仅作为不可编辑的 preview snapshot，不参与报表或真实账户余额，写入 `warning_fingerprint` 并将 `warning_ack=False`；`confirm_dividend()` 唯一签名和 payload 必须带 `warning_fingerprint` 与 `warning_ack`，确认成功持久化 ack/fingerprint。累计未分配利润按期初未分配利润 + 截止业务日累计经营净利润 − 已确认分红派生；Day 1 固定期初未分配利润仍为 0。超出只产生 `retained_earnings_exceeded` warning，不在 preview 扣款。

### Step 4（2–5 分钟）：实现 confirm posting

确认先按 confirm key 核对 Dividend、金额、两账户、版本、warning acknowledgement，再锁 Dividend、两个账户（id 排序）和 writer gate；进入锁内后必须按 `business_date` 重新计算当前 retained earnings 和 warning fingerprint。若 preview 已过期，旧 fingerprint 的 `warning_ack` 返回 `409/warning_stale` 和最新 warning，不得确认旧 warning；并发利润/分红变化测试必须覆盖这一点。账户不足或 warning 未确认原子失败；成功时用 `_post_transaction_once()` 写两个 CNY 账户减少和 `DIVIDEND_DISTRIBUTION` 正分类 posting，受控 bypass 更新 Dividend posted/确认信息。分红不进入经营净利润。

### Step 5（2–5 分钟）：补跨月、期初、并发和回滚测试

测试：期初 retained=0、上月利润不被本月 dividend 影响；preview 返回 fingerprint，锁内利润变化后旧 fingerprint 确认返回 `{code:'warning_stale', details:{warning, fingerprint}}`；跨月确认按 dividend business_date 扣累计分配而不改历史月净利润；超留存 preview/confirm warning 字段稳定；重复 confirm 返回原 ledger；两个账户余额不足、账户相同/非 CNY、锁冲突重试和 posting 中途失败均无残留。

Run: `.venv/bin/python manage.py test accounting.tests.test_dividend_actions -v 2`

Expected: 分红字段/返回契约一致，确认可重放且不进入经营净利润。

### Step 6（2–5 分钟）：Task 6 双审查与提交

Luna A 审查 warning/confirm 来源和利润边界，Luna B 审查版本幂等、锁顺序、posted bypass 和跨月测试；通过后提交。

```bash
git add accounting/dividend_actions.py accounting/dividend_types.py accounting/errors.py accounting/tests/test_dividend_actions.py
git commit -m "功能：实现分红草稿预览与确认"
```

## Task 7：利润选择器、动作 API、Day 1 服务门禁和错误契约

**Objective:** 统一利润公式与 JSON 错误响应，并让所有后端正式动作在 Day 1 未完成时稳定阻断。

**Files:** Modify: `accounting/selectors.py`、`accounting/views.py`、`accounting/urls.py`、`cigars/sales_api.py`；Create: `accounting/action_serializers.py`、`accounting/guards.py`；Test: `accounting/tests/test_sales_reports_reconciliation.py`、`accounting/tests/test_action_api.py`、`accounting/tests/test_api.py`、`cigars/tests/test_sales_refund_transport.py`、`cigars/tests/test_sales_order_api.py`

### Step 1（2–5 分钟）：写 selector RED

Task7 同时 Modify `cigars/sales_accounting.py`，并由本 Task 的 `git add` 纳入其 gate 修改。

新增测试 fixture：销售收入 500、销售成本 0、工资 100、销售单实际人肉成本 20、库存调整收益 7、库存调整损失 3、资金对账收益 2、资金对账损失 1、确认分红 50。

```python
def test_profit_formula_keeps_adjustment_and_reconciliation_gain_loss(self):
    seed_profit_facts(sales=Decimal('500.00'), salary=Decimal('100.00'), transport=Decimal('20.00'),
                      inventory_gain=Decimal('7.00'), inventory_loss=Decimal('3.00'),
                      reconciliation_gain=Decimal('2.00'), reconciliation_loss=Decimal('1.00'))
    self.assertEqual(monthly_profit(month=date(2026, 8, 1))['net_profit_cny'], Decimal('385.00'))
    before = monthly_profit(month=date(2026, 8, 1))
    confirm_dividend_fixture(total_cny=Decimal('50.00'), business_date=self.day)
    after = monthly_profit(month=date(2026, 8, 1))
    self.assertEqual(before['net_profit_cny'], after['net_profit_cny'])
    self.assertEqual(after['retained_earnings_cny'], before['retained_earnings_cny'] - Decimal('50.00'))
```

断言经营净利润为 `500 - 100 - 20 + 7 - 3 + 2 - 1 = 385`；采购付款、换汇、转账、预收、投入和分红不进入经营净利润。另测 `IN_TRANSIT.paid_cny_cost` 才进入在途摘要，DRAFT 不进入。

Run: `.venv/bin/python manage.py test accounting.tests.test_sales_reports_reconciliation -v 2`

Expected: FAIL，选择器还没有全部分类和实际人肉费路径。

### Step 2（2–5 分钟）：实现利润与 retained selectors

在 `accounting/selectors.py` 增加 `_sum_category()`、`monthly_profit(*, month)`（调用统一使用 `monthly_profit(month='2026-08')`）、`retained_earnings(as_of='2026-08-31')` 和 `accounting_summary()`。`GET /api/accounting/actions/` 单独查询 pending actions，不能复用或覆盖现有 dashboard query。展示公式明确为：销售收入 + 客户人肉费收入 − FIFO 销售成本 − `TRANSPORT_EXPENSE` − 工资/房租/水电/其他 + 库存调整收益 − 库存调整损失 + 资金对账收益 − 资金对账损失。实际人民币人肉费只从 `SalesTransportCost`/`SALES_TRANSPORT_COST` 关联事实读取。换汇、采购在途、库存转移、分红和资金本金不进入净利润。

注释说明资产转移不等于损益，库存和对账 gain/loss 是批准规格中的显式经营结果。

日期契约固定为 `monthly_profit(month=date(2026, 8, 1))` 与 `retained_earnings(as_of=date(2026, 8, 31))`；API 输入字符串 `2026-08` 在 serializer 中解析为上述 date，selector 不接收未解析字符串。

### Step 3（2–5 分钟）：实现 Day 1 service guard

在 `accounting/guards.py` 定义 `require_day1_completed(*, allow_day1=False)` 和 `Day1IncompleteError(code='day1_incomplete')`；未完成时拒绝 exchange、purchase draft/pay/receive/cancel、expense、dividend draft/edit/confirm，以及 `cigars/sales_accounting.py` 的 `ship_sales_order()`、`receive_sales_order_payment()`、`refund_sales_order_payment()`、`record_sales_transport_cost()`。`cigars/sales_api.py` 只负责映射错误，不能成为门禁唯一位置。把 guard 放入每个服务入口，Day 1 `save_day1_draft()`/`confirm_day1()` 通过明确 `allow_day1=True` 的内部 scope。新增直接服务测试，不经过 HTTP：逐个调用出库、收款、退款、人肉费并断言 `day1_incomplete`；确认 Day 1 自身写入仍可用。

### Step 4（2–5 分钟）：统一现有 exchange API 错误

在 `accounting/views.py` 增加统一 `error_response(error)`，将现有 `exchange_to_rub()` 的 `LedgerError` 映射为 `{error, code, details}`，并覆盖 `day1_incomplete`、`insufficient_balance`、`currency_rule`、`packaging_review_required`、`idempotency_conflict`、`warning_stale`、`busy`；canonical `unrepresentable` 不是错误。保留 Decimal 为字符串，不能返回零值伪装 Day 1 未完成。为换汇 API 增加契约测试。

### Step 5（2–5 分钟）：接入动作 API

新增并注册：`GET /api/accounting/actions/`、`POST /api/accounting/purchases/`、`POST /api/accounting/purchases/<id>/pay/`、`POST /api/accounting/purchases/<id>/receive/`、`POST /api/accounting/purchases/<id>/cancel/`、`POST /api/accounting/expenses/`、`GET/POST /api/accounting/dividends/`、`PATCH /api/accounting/purchases/<id>/`、`PATCH /api/accounting/dividends/<id>/`、`POST /api/accounting/dividends/<id>/preview/`、`POST /api/accounting/dividends/<id>/confirm/`。collection 仅 GET/POST，两个 detail PATCH body 必须含 `expected_version` 和 `Idempotency-Key`；If-Match 可作为等价 header，但若同时提供必须与 expected_version 相同，否则 409 `version_conflict`。所有写 view 检查 operator/staff、Idempotency-Key、expected_version（适用时），调用对应服务，不在 view 自行改模型；cancel endpoint 调用 `cancel_purchase_order(idempotency_key, expected_version, note)`，并覆盖 replay/conflict/day1/state tests。

统一错误 details 至少含 field/code context；采购 create/update/cancel 与分红 create/update 各自发送独立 Idempotency-Key，对应 append-only action replay/conflict；旧输入无法转换的采购 review 行返回 `409` + `packaging_review_required`，canonical `unrepresentable` 行照常付款；已付款/已入库 replay 返回原事实 JSON。

### Step 6（2–5 分钟）：API RED/GREEN 和事务测试

新增 `ActionApiTest`：工资 RUB 返回 400 `currency_rule`，Day 1 未完成所有正式写接口返回 409 `day1_incomplete`，换汇同 key replay 返回同 ledger，采购参数冲突返回 409，分红 preview warning 字段和 confirm ack 契约一致。注入锁冲突和中途异常，检查 API code 与数据库无残留。

Run: `.venv/bin/python manage.py test accounting.tests.test_action_api accounting.tests.test_api accounting.tests.test_sales_reports_reconciliation -v 2`

Expected: API 错误结构统一，选择器公式和服务层门禁通过。

### Step 7（2–5 分钟）：Task 7 双审查与提交

Luna A 对照两份 spec、CONTEXT 和真实 service/API 检查公式及门禁；Luna B 独立检查所有 endpoint、错误 code、Decimal 序列化和回滚测试；通过后提交。

```bash
git add accounting/selectors.py accounting/guards.py accounting/views.py accounting/urls.py accounting/action_serializers.py cigars/sales_api.py accounting/tests/test_action_api.py accounting/tests/test_api.py accounting/tests/test_sales_reports_reconciliation.py cigars/tests/test_sales_refund_transport.py cigars/tests/test_sales_order_api.py
git add cigars/sales_accounting.py
git commit -m "功能：提供利润选择器与账务动作接口"
```

## Task 8：React 动作中心、OpenDesign 原型和真实帮助 selector

**Objective:** 让每张动作卡提交实际金额、保留局部错误和输入，并通过已批准 OpenDesign 原型连接真实控件与帮助引导。

**Files:**

- Modify: `frontend/src/types.ts`, `frontend/src/api.ts`, `frontend/src/pages/AccountingDashboardPage.tsx`, `frontend/src/components/sales/AccountingPanel.tsx`
- Create: `.opendesign/accounting-action-center.html`、`frontend/src/components/accounting/AccountingActionCenter.tsx`、`frontend/src/components/accounting/ExchangeAction.tsx`、`frontend/src/components/accounting/PurchaseAction.tsx`、`frontend/src/components/accounting/ExpenseAction.tsx`、`frontend/src/components/accounting/DividendAction.tsx`
- Create: `frontend/src/features/accounting/actionState.ts`、`frontend/src/features/guides/guideFocusController.ts`
- Modify: `frontend/src/features/guides/guideInteractions.ts`、`frontend/src/features/guides/ContextTour.tsx`；`guideContent.ts` 无文案变化，不修改、不列为 Task 文件。
- Test: `frontend/src/api/accountingActions.test.ts`、`frontend/src/features/accounting/actionState.test.ts`、`frontend/src/features/guides/guideFocusController.test.ts`、`frontend/src/components/accounting/AccountingActionCenter.test.tsx`、`frontend/src/components/accounting/ExchangeAction.test.tsx`、`frontend/src/components/accounting/PurchaseAction.test.tsx`、`frontend/src/components/accounting/ExpenseAction.test.tsx`、`frontend/src/components/accounting/DividendAction.test.tsx`、`frontend/src/features/guides/guideInteractions.test.ts`、`frontend/src/features/guides/ContextTour.test.tsx`

OpenDesign 项目使用批准的 `CigarDomTabaka (570372ce-21b8-4752-a21a-bd254f061568)`；先在 `.opendesign/accounting-action-center.html` 验证现有奶油色/勃艮第红/金色 token 和动作卡布局，再把已验证结构接入 React，不在本 Task 直接进行未经原型验证的视觉重设计。

### Step 1（2–5 分钟）：写 API/type RED

测试所有 Decimal 类型为 string；

```tsx
import { expect, it } from 'vitest';
import { initialActionState, reduceActionState } from '../features/accounting/actionState';

it('keeps local input and isolates action error', () => {
  const state = reduceActionState(initialActionState(), { type: 'error', code: 'busy', message: '动作区暂时不可用' });
  expect(state.error?.code).toBe('busy');
  expect(state.input).toEqual(initialActionState().input);
});
```
`exchangeToRub({source_account_id, rub_account_id, source_amount:'1.00000000', rub_amount:'1200.00', business_date})` 必须使用现有 `writeWithIdempotency()` 并发送 `Idempotency-Key`。同样测试 purchase pay/receive/cancel、expense、dividend create/update/preview/confirm helpers；采购草稿操作区提供明确取消按钮，其他卡不新增取消入口。

Run: `cd frontend && npm test -- --run src/api/accountingActions.test.ts`

Expected: FAIL，helpers 和统一错误解析尚未存在。

### Step 2（2–5 分钟）：实现 types/API 和局部错误解析

在 `frontend/src/types.ts` 定义 canonical purchase 字段和统一 `{error, code, details}`；在 `api.ts` 实现动作 helpers。`fetchAccountingActions()` 使用独立 query key，不复用 dashboard query；动作请求失败只更新动作区 error state，账户/统计/利润 query 保持原数据，null 继续显示 loading/unknown 而不是 0。所有写请求调用 `writeWithIdempotency()`，不把 null 转成 0。注释说明 idempotency header 和 Decimal 字符串是资金动作边界。

### Step 3（2–5 分钟）：写动作卡 RED

组件测试只渲染已注入 props 的 presentational markup，并测试 `actionState`/纯 helper contract：Decimal 保持 string、局部 error 不覆盖 sibling state、purchase card 不输出分期/分批 controls、dividend props 输出 warning/ack 要求；不声称真实选择、模拟交互或 QueryClient 行为。

Run: `cd frontend && npm test -- --run src/components/accounting`

Expected: FAIL，动作卡尚未连接。

### Step 4（2–5 分钟）：实现动作卡并接入工作台

`ExchangeAction` 仅 CNY/USDT → 固定 RUB，提交实际数量；`PurchaseAction` 仅 DRAFT 付款、IN_TRANSIT 整单到货并展示 canonical 盒数；`ExpenseAction` 按分类过滤账户；`DividendAction` 创建/编辑/preview/confirm。每卡独立 `idle/loading/success/error/conflict` 状态，失败保留输入，局部错误不覆盖其他卡。注释只说明错误隔离与不可将 null 显示成零值。

### Step 5（2–5 分钟）：实现 OpenDesign prototype 验证记录

在 `.opendesign/accounting-action-center.html` 保留动作卡、Day 1 waiting 状态和 warning 状态的可操作预览；实现者在提交前将截图/手工验证结果固定写入 `docs/reviews/2026-08-14-accounting-actions-review-a.md` 的 `## OpenDesign evidence` 小节，不把 prototype 产物当生产 API。

### Step 6（2–5 分钟）：修正 guide selector 和非提交控件

在 `frontend/src/features/guides/guideInteractions.ts` 把会计步骤 target 指向真实 `data-guide` selector，例如 `accounting-actions-exchange`、`accounting-actions-purchase`、`accounting-actions-expense`；这些属性放在可聚焦的 `<section tabIndex={-1}>` 或帮助按钮上，不能放在 submit button。引导点击只 `focus()`/滚动，不触发提交。

### Step 7（2–5 分钟）：写 guide 定位/聚焦测试并 GREEN

`AccountingDashboardPage.tsx` 调用纯 `actionState.ts` controller；动作状态测试只输入/输出 plain objects。`ContextTour.tsx` 调用纯 `guideFocusController.ts` 的 `resolveTarget(selector) -> {selector, restoreId}` 与 `restoreTarget(restoreId)` contract；其测试不声称执行 DOM effect/focus，只断言 controller 的 selector、restore id 和“不提交” action。组件页面只用 `renderToStaticMarkup` 测 SSR markup，完全不引入 DOM/testing-library 依赖，也不直接测试 QueryClient/provider。

Run: `cd frontend && npm test -- --run src/features/accounting/actionState.test.ts src/features/guides/guideFocusController.test.ts src/features/guides/guideInteractions.test.ts src/features/guides/ContextTour.test.tsx src/components/accounting && npm run lint`

Expected: API、动作卡、guide selector 和 lint 全部通过。

### Step 8（2–5 分钟）：Task 8 双审查与提交

Luna A 审查 OpenDesign 与 React 交互边界，Luna B 独立审查实际金额、局部错误、guide focus 和非提交控件；通过后提交。

```bash
git add .opendesign/accounting-action-center.html frontend/src/types.ts frontend/src/api.ts frontend/src/pages/AccountingDashboardPage.tsx frontend/src/components/sales/AccountingPanel.tsx frontend/src/components/accounting/AccountingActionCenter.tsx frontend/src/components/accounting/AccountingActionCenter.test.tsx frontend/src/components/accounting/ExchangeAction.tsx frontend/src/components/accounting/ExchangeAction.test.tsx frontend/src/components/accounting/PurchaseAction.tsx frontend/src/components/accounting/PurchaseAction.test.tsx frontend/src/components/accounting/ExpenseAction.tsx frontend/src/components/accounting/ExpenseAction.test.tsx frontend/src/components/accounting/DividendAction.tsx frontend/src/components/accounting/DividendAction.test.tsx frontend/src/features/accounting/actionState.ts frontend/src/features/accounting/actionState.test.ts frontend/src/api/accountingActions.test.ts frontend/src/features/guides/guideInteractions.ts frontend/src/features/guides/guideInteractions.test.ts frontend/src/features/guides/guideFocusController.ts frontend/src/features/guides/guideFocusController.test.ts frontend/src/features/guides/ContextTour.tsx frontend/src/features/guides/ContextTour.test.tsx
git commit -m "前端：接入账务动作中心与真实帮助引导"
```

## Task 9：第二轮规格审查、回归验证和分支收尾

**Objective:** 用两轮独立 Luna 总审查和完整命令确认规格覆盖、路径一致、测试存在，并按指定分支策略结束。

**Files:** 只读审查全部 Task 文件；Create: `docs/reviews/2026-08-14-accounting-actions-review-a.md`、`docs/reviews/2026-08-14-accounting-actions-review-b.md`、`accounting/tests/test_accounting_plan_paths.py`；不新增生产代码。

### Step 1（2–5 分钟）：完成第二轮独立 Luna 总审查

Luna A 不看第一轮结论，逐项对照两份 spec、`CONTEXT.md`、真实 `models.py/services.py/guideInteractions.ts`，检查 canonical 公式、迁移约束、状态机、利润 gain/loss、Day 1 gate、分红字段和 API contract。Luna B 独立做相同审查，输出差异清单；任何差异先修复再继续。每个差异都记录问题→修复 SHA→由另一位 Luna 复审该 SHA 并写 `APPROVED`，否则阻断 Task9 合并。

### Step 2（2–5 分钟）：执行 migration/type/path self-review

先以 `AccountingPlanReferencePathTest.test_required_reference_paths_exist` 作为 RED 检查真实既有路径；该类定义在 `accounting/tests/test_accounting_plan_paths.py`，review 产物路径在本 Task 创建后再转 GREEN，未关闭问题会阻断合并：

```python
from pathlib import Path
from django.test import TestCase

REQUIRED_EXISTING_PATHS = (
    'CONTEXT.md',
    'docs/superpowers/specs/2026-08-10-internal-accounting-module-design.md',
    'docs/superpowers/specs/2026-08-13-business-workspace-day1-design.md',
    'accounting/models.py', 'accounting/services.py', 'accounting/day1.py',
    'cigars/models.py', 'cigars/services.py', 'cigars/agent_api.py',
    'cigars/sales_accounting.py', 'cigars/sales_api.py',
    'frontend/src/api.ts', 'frontend/src/features/guides/guideInteractions.ts',
    'frontend/src/features/guides/ContextTour.tsx',
)

EXPECTED_REVIEW_PATHS = (
    'docs/reviews/2026-08-14-accounting-actions-review-a.md',
    'docs/reviews/2026-08-14-accounting-actions-review-b.md',
)

class AccountingPlanReferencePathTest(TestCase):
    def test_required_reference_paths_exist(self):
        for path in REQUIRED_EXISTING_PATHS:
            self.assertTrue(Path(path).is_file(), path)

    def test_review_artifacts_exist(self):
        for path in EXPECTED_REVIEW_PATHS:
            self.assertTrue(Path(path).is_file(), path)
```

Run: `.venv/bin/python manage.py test accounting.tests.test_accounting_plan_paths.AccountingPlanReferencePathTest -v 2`

Run:

```bash
.venv/bin/python manage.py makemigrations --check
.venv/bin/python manage.py check
.venv/bin/python manage.py showmigrations accounting cigars
rg -n -e 'unit_price_rub\s*\*\s*quantity|quantity\s*\*\s*unit_price_rub|unit_price_rub.*quantity' docs/superpowers/plans/2026-08-14-accounting-actions.md
.venv/bin/python -c "from pathlib import Path; p=Path('docs/superpowers/plans/2026-08-14-accounting-actions.md'); t=p.read_text(); bad=('T'+'BD','TO'+'DO','Similar'+' to','适'+'当处理','待'+'定','Divided'+'Action'); found=[x for x in bad if x in t]; raise SystemExit('placeholder: '+','.join(found)) if found else print('placeholder scan: clean')"
```

Expected: migration/check 无错误；第一条只允许命中本计划说明“禁止旧公式”的审查文本，不能出现任何实现步骤；第二条无输出。再用 `rg --files` 确认计划列出的测试路径和 `guideInteractions.ts` 存在，逐项核对函数/字段名。

### Step 3（2–5 分钟）：执行后端全量验证

Run: `.venv/bin/python manage.py test accounting accounting.tests.test_accounting_plan_paths cigars.tests.test_purchase_packaging cigars.tests.test_purchase_migration cigars.tests.test_sales_accounting cigars.tests.test_sales_refund_transport cigars.tests.test_sales_order_api cigars.tests.test_sales_order_workflow cigars.tests.test_agent_order_inventory accounting.tests.test_operations accounting.tests.test_api -v 2`

Expected: Day 1、换汇移动平均、锁重试、canonical 采购、库存 FIFO、销售人肉费、费用、分红、利润和 API 全部通过，失败时不得声称完成。

### Step 4（2–5 分钟）：执行前端验证

Run:

```bash
cd frontend
npm test -- --run
npm run lint
npm run build
```

Expected: Vitest 0 failures、lint 0 errors、production build exit 0。

### Step 5（2–5 分钟）：审查 staged 范围和用户改动

在当前 `feature/business-workspace-day1` 分支运行 `git status --short`、`git diff --check`、`git diff --cached --name-only`；每个实现 Task 只 stage 自己列出的实际文件，不能纳入 Day1 用户改动、`.db`、`media/`、`.env` 或 `staticfiles/`。每个 Task commit 后运行 `git show --name-only --format=fuller HEAD` 并核对只包含该 Task Files。若发现未提交用户改动，不 stash，先暂停并由主代理处理。

### Step 6（2–5 分钟）：本地合并和分支收尾

仓库发布分支是 `main`；实现期间继续使用现有 `feature/business-workspace-day1`，不另开分支。先运行 `git branch --show-current` 并断言输出为 `feature/business-workspace-day1`；所有 Task commit 和最终验证完成后执行：

```bash
git checkout main
git merge --no-ff feature/business-workspace-day1
git diff --check
git branch -d feature/business-workspace-day1
test -f docs/reviews/2026-08-14-accounting-actions-review-a.md
test -f docs/reviews/2026-08-14-accounting-actions-review-b.md
git status --short
```

合并后再次运行后端/前端验证，确认主代理需要的提交；只允许本地合并和删除，不 push。

### Step 7（2–5 分钟）：保存两轮独立总审查产物

两轮总审查必须写入 `docs/reviews/2026-08-14-accounting-actions-review-a.md` 和 `docs/reviews/2026-08-14-accounting-actions-review-b.md`，每份包含审查基线 SHA、发现的问题、修复 commit SHA、复审结论和未关闭项；任一未关闭项阻止合并。每个 Task 的 spec review→fix→不同 Luna rereview `APPROVED`→quality review→fix→不同 Luna rereview `APPROVED` 均须在该 review log 记录；Task9 只允许在所有阻断项关闭后继续。Luna A/B 不得只在聊天中口头报告。

Task9 Step 7 必须显式执行：`git add docs/reviews/2026-08-14-accounting-actions-review-a.md docs/reviews/2026-08-14-accounting-actions-review-b.md accounting/tests/test_accounting_plan_paths.py`，`git commit -m "审查：记录账务动作双轮复审证据"`，随后对该 commit 运行 `git show --name-only --format=fuller HEAD` 和 `git status --short`；OpenDesign 手工/截图验证记录固定写入 review A 的 `## OpenDesign evidence` 小节并随该 commit stage。

### Step 8（2–5 分钟）：最终证据回报

回报所有中文 commit SHA、两份 review 文件路径、两轮 Luna 结论、迁移/check、后端、前端和 placeholder/type/path scan 的实际命令输出摘要；只有全部证据满足才可声明完成。
