"""只读库存事实一致性审计。"""

from collections import Counter, defaultdict
from dataclasses import dataclass
from decimal import Decimal

from .models import (
    InventoryAdjustmentAction,
    PurchaseBatch,
    PurchaseOrder,
    SalesReturn,
    SalesShipment,
    SalesOrderItem,
    StockAllocation,
    StockMovement,
)


@dataclass(frozen=True)
class InventoryAuditIssue:
    """一条可稳定引用的库存审计问题。"""

    code: str
    message: str
    batch_id: int | None = None
    order_id: int | None = None
    allocation_id: int | None = None
    movement_id: int | None = None


@dataclass(frozen=True)
class InventoryAuditResult:
    issues: tuple[InventoryAuditIssue, ...] = ()

    @property
    def ok(self):
        return not self.issues

    @property
    def healthy(self):
        return self.ok


def _issue(issues, code, message, *, batch_id=None, order_id=None,
           allocation_id=None, movement_id=None):
    issues.append(InventoryAuditIssue(
        code=code,
        message=message,
        batch_id=batch_id,
        order_id=order_id,
        allocation_id=allocation_id,
        movement_id=movement_id,
    ))


def _nonnegative(issues, batch, fields):
    for field in fields:
        value = getattr(batch, field, None)
        if value is not None and value < 0:
            _issue(
                issues,
                "BATCH_NEGATIVE_VALUE",
                f"批次 {batch.pk} 的 {field} 为负数",
                batch_id=batch.pk,
            )


def _audit_batch(issues, batch, reserved_by_batch, movements_by_batch):
    batch_id = batch.pk
    int_fields = (
        "quantity", "positive_adjustment_quantity", "remaining",
        "physical_remaining", "reversed_quantity", "original_box_quantity",
        "original_stick_quantity", "physical_box_quantity",
        "physical_stick_quantity", "available_box_quantity",
        "available_stick_quantity",
    )
    money_fields = (
        "original_cost_cny", "positive_adjustment_cost_cny",
        "adjustment_cost_cny", "remaining_cost_cny", "sold_cost_cny", "reversed_cost_cny",
        "unit_cost_cny",
    )
    _nonnegative(issues, batch, int_fields + money_fields)
    movements = movements_by_batch.get(batch_id, ())
    quantity_by_type = defaultdict(int)
    for movement in movements:
        quantity_by_type[movement.movement_type] += movement.quantity
    inventory_delta = (
        quantity_by_type[StockMovement.MovementType.RECEIVE]
        + quantity_by_type[StockMovement.MovementType.ADJUSTMENT]
        + quantity_by_type[StockMovement.MovementType.REVERSE_RECEIVE]
        + quantity_by_type[StockMovement.MovementType.REVERSE_ADJUSTMENT]
    )
    expected_physical = (
        inventory_delta
        - quantity_by_type[StockMovement.MovementType.SHIP]
        + quantity_by_type[StockMovement.MovementType.RETURN]
    )
    expected_available = (
        inventory_delta
        - quantity_by_type[StockMovement.MovementType.RESERVE]
        + quantity_by_type[StockMovement.MovementType.RELEASE_RESERVATION]
        + quantity_by_type[StockMovement.MovementType.RETURN]
    )
    if expected_physical != batch.physical_remaining:
        _issue(
            issues, "BATCH_MOVEMENT_PHYSICAL_MISMATCH",
            f"批次 {batch_id} 的库存流水与物理数量不一致",
            batch_id=batch_id,
        )
    if expected_available != batch.remaining:
        _issue(
            issues, "BATCH_MOVEMENT_AVAILABLE_MISMATCH",
            f"批次 {batch_id} 的库存流水与可售数量不一致",
            batch_id=batch_id,
        )
    receives = [
        movement for movement in movements
        if movement.movement_type == StockMovement.MovementType.RECEIVE
    ]
    expected_receive_count = 0 if batch.source == PurchaseBatch.Source.ADJUSTMENT else 1
    if (
        len(receives) != expected_receive_count
        or (receives and receives[0].quantity != batch.quantity)
    ):
        _issue(
            issues, "BATCH_RECEIVE_MOVEMENT_MISMATCH",
            f"批次 {batch_id} 的原始入库流水不一致",
            batch_id=batch_id,
        )

    if batch.reversed_at is not None:
        empty_state = (
            batch.remaining == 0
            and batch.physical_remaining == 0
            and batch.available_box_quantity == 0
            and batch.physical_box_quantity == 0
            and batch.available_stick_quantity == 0
            and batch.physical_stick_quantity == 0
            and batch.remaining_cost_cny == 0
        )
        if (
            batch.reversed_quantity != batch.quantity
            or batch.reversed_cost_cny != batch.original_cost_cny
            or not empty_state
        ):
            _issue(
                issues, "BATCH_REVERSAL_STATE_MISMATCH",
                f"批次 {batch_id} 的撤销入库状态不完整", batch_id=batch_id,
            )
        if batch.stock_allocations.exists():
            _issue(
                issues, "REVERSED_BATCH_HAS_ALLOCATION",
                f"已撤销批次 {batch_id} 仍有关联库存分配", batch_id=batch_id,
            )
        received = sum(
            movement.quantity for movement in movements
            if movement.movement_type == StockMovement.MovementType.RECEIVE
        )
        reversed_quantity = sum(
            movement.quantity for movement in movements
            if movement.movement_type == StockMovement.MovementType.REVERSE_RECEIVE
        )
        if received != batch.quantity or reversed_quantity != -batch.quantity:
            _issue(
                issues, "BATCH_REVERSAL_MOVEMENT_MISMATCH",
                f"批次 {batch_id} 的入库与撤销流水不匹配", batch_id=batch_id,
            )
    elif batch.reversed_quantity or batch.reversed_cost_cny:
        _issue(
            issues, "BATCH_REVERSAL_STATE_MISMATCH",
            f"批次 {batch_id} 的撤销数量、成本和时间不一致", batch_id=batch_id,
        )

    size = batch.box_size
    if size is not None and size <= 0:
        _issue(
            issues, "BATCH_INVALID_BOX_SIZE", f"批次 {batch_id} 的包装支数非法",
            batch_id=batch_id,
        )
    if batch.remaining > batch.physical_remaining:
        _issue(
            issues, "BATCH_REMAINING_EXCEEDS_PHYSICAL",
            f"批次 {batch_id} 的可售数量超过物理数量", batch_id=batch_id,
        )
    if batch.physical_remaining > batch.quantity + batch.positive_adjustment_quantity:
        _issue(
            issues, "BATCH_PHYSICAL_EXCEEDS_CAPACITY",
            f"批次 {batch_id} 的物理数量超过入库及正向调整容量",
            batch_id=batch_id,
        )

    if size is None:
        expected = {
            "original_box_quantity": 0,
            "physical_box_quantity": 0,
            "available_box_quantity": 0,
            "original_stick_quantity": batch.quantity,
            "physical_stick_quantity": batch.physical_remaining,
            "available_stick_quantity": batch.remaining,
        }
    elif size > 0:
        # 可用/物理形态允许拆盒，因此这里只校验聚合等式，不强制整除。
        expected = {}
        for quantity_field, box_field, stick_field in (
            ("quantity", "original_box_quantity", "original_stick_quantity"),
            ("physical_remaining", "physical_box_quantity", "physical_stick_quantity"),
            ("remaining", "available_box_quantity", "available_stick_quantity"),
        ):
            if getattr(batch, quantity_field) != (
                getattr(batch, box_field) * size + getattr(batch, stick_field)
            ):
                _issue(
                    issues, "BATCH_PACKAGING_MISMATCH",
                    f"批次 {batch_id} 的 {quantity_field} 与包装聚合不一致",
                    batch_id=batch_id,
                )
    else:
        expected = {}
    for field, value in expected.items():
        if getattr(batch, field) != value:
            _issue(
                issues, "BATCH_PACKAGING_MISMATCH",
                f"批次 {batch_id} 的 {field} 与数量聚合不一致",
                batch_id=batch_id,
            )

    if batch.available_box_quantity > batch.physical_box_quantity:
        _issue(
            issues, "BATCH_AVAILABLE_EXCEEDS_PHYSICAL",
            f"批次 {batch_id} 的可用整盒数超过物理整盒数", batch_id=batch_id,
        )
    if batch.available_stick_quantity > batch.physical_stick_quantity:
        _issue(
            issues, "BATCH_AVAILABLE_EXCEEDS_PHYSICAL",
            f"批次 {batch_id} 的可用散支数超过物理散支数", batch_id=batch_id,
        )

    left = batch.original_cost_cny + batch.positive_adjustment_cost_cny
    right = batch.remaining_cost_cny + batch.sold_cost_cny + batch.adjustment_cost_cny
    # 反向动作若已加入该字段，自动把它纳入守恒式。
    reversed_cost = getattr(batch, "reversed_cost_cny", None)
    if reversed_cost is not None:
        right += reversed_cost
        if reversed_cost < 0:
            _issue(
                issues, "BATCH_NEGATIVE_VALUE",
                f"批次 {batch_id} 的 reversed_cost_cny 为负数", batch_id=batch_id,
            )
    if left != right:
        _issue(
            issues, "BATCH_COST_NOT_CONSERVED",
            f"批次 {batch_id} 的成本池不守恒",
            batch_id=batch_id,
        )

    reserved = reserved_by_batch.get(batch_id, ())
    expected_reserved = batch.physical_remaining - batch.remaining
    actual_reserved = sum(allocation.quantity for allocation in reserved)
    if actual_reserved != expected_reserved:
        _issue(
            issues, "BATCH_RESERVED_QUANTITY_MISMATCH",
            f"批次 {batch_id} 的活动预留数量与物理/可售差额不一致",
            batch_id=batch_id,
        )

    box_reserved = 0
    stick_reserved = 0
    for allocation in reserved:
        item = allocation.sales_order_item
        if (
            item.sale_unit == SalesOrderItem.SaleUnit.BOX
            and size
            and item.box_size == size
            and allocation.quantity % size == 0
        ):
            box_reserved += allocation.quantity // size
        else:
            stick_reserved += allocation.quantity
            if item.sale_unit == SalesOrderItem.SaleUnit.BOX:
                _issue(
                    issues, "ALLOCATION_PACKAGING_MISMATCH",
                    f"活动分配 {allocation.pk} 与批次包装形态不匹配",
                    batch_id=batch_id, order_id=item.sales_order_id,
                    allocation_id=allocation.pk,
                )
    expected_box_reserved = batch.physical_box_quantity - batch.available_box_quantity
    expected_stick_reserved = batch.physical_stick_quantity - batch.available_stick_quantity
    if box_reserved != expected_box_reserved or stick_reserved != expected_stick_reserved:
        _issue(
            issues, "BATCH_RESERVED_PACKAGING_MISMATCH",
            f"批次 {batch_id} 的活动预留盒/支形态聚合不一致",
            batch_id=batch_id,
        )


def _audit_allocation(issues, allocation, reserved_by_batch):
    batch = allocation.purchase_batch
    item = allocation.sales_order_item
    order_id = item.sales_order_id
    reserved_by_batch[batch.pk].append(allocation) if allocation.status == StockAllocation.Status.RESERVED else None

    if allocation.quantity <= 0:
        _issue(
            issues, "ALLOCATION_NONPOSITIVE_QUANTITY",
            f"库存分配 {allocation.pk} 数量不是正数",
            batch_id=batch.pk, order_id=order_id, allocation_id=allocation.pk,
        )
    if item.cigar_id != batch.cigar_id:
        _issue(
            issues, "ALLOCATION_CIGAR_MISMATCH",
            f"库存分配 {allocation.pk} 的明细雪茄与批次不一致",
            batch_id=batch.pk, order_id=order_id, allocation_id=allocation.pk,
        )
    if batch.reversed_at is not None:
        _issue(
            issues, "REVERSED_BATCH_HAS_ALLOCATION",
            f"库存分配 {allocation.pk} 指向已撤销批次",
            batch_id=batch.pk, order_id=order_id, allocation_id=allocation.pk,
        )
    if allocation.status not in StockAllocation.Status.values:
        _issue(
            issues, "ALLOCATION_UNKNOWN_STATUS",
            f"库存分配 {allocation.pk} 状态未知",
            batch_id=batch.pk, order_id=order_id, allocation_id=allocation.pk,
        )
        return

    if allocation.reserved_at is None:
        _issue(
            issues, "ALLOCATION_RESERVED_AT_MISSING",
            f"库存分配 {allocation.pk} 缺少预留时间",
            batch_id=batch.pk, order_id=order_id, allocation_id=allocation.pk,
        )
    if allocation.status == StockAllocation.Status.RESERVED:
        if allocation.fulfilled_at is not None or allocation.released_at is not None:
            _issue(
                issues, "ALLOCATION_TIMESTAMP_MISMATCH",
                f"活动分配 {allocation.pk} 带有终态时间",
                batch_id=batch.pk, order_id=order_id, allocation_id=allocation.pk,
            )
    elif allocation.status == StockAllocation.Status.FULFILLED:
        if allocation.fulfilled_at is None or allocation.released_at is not None:
            _issue(
                issues, "ALLOCATION_TIMESTAMP_MISMATCH",
                f"已出库分配 {allocation.pk} 的时间戳不完整",
                batch_id=batch.pk, order_id=order_id, allocation_id=allocation.pk,
            )
    elif allocation.status == StockAllocation.Status.RELEASED:
        if allocation.released_at is None or allocation.fulfilled_at is not None or getattr(allocation, "returned_at", None) is not None:
            _issue(
                issues, "ALLOCATION_TIMESTAMP_MISMATCH",
                f"已释放分配 {allocation.pk} 的时间戳不完整",
                batch_id=batch.pk, order_id=order_id, allocation_id=allocation.pk,
            )
    elif allocation.status == getattr(StockAllocation.Status, "RETURNED", "returned"):
        if allocation.fulfilled_at is None or getattr(allocation, "returned_at", None) is None or allocation.released_at is not None:
            _issue(
                issues, "ALLOCATION_TIMESTAMP_MISMATCH",
                f"已退货分配 {allocation.pk} 的时间戳不完整",
                batch_id=batch.pk, order_id=order_id, allocation_id=allocation.pk,
            )

    terminal_statuses = {
        StockAllocation.Status.FULFILLED,
        getattr(StockAllocation.Status, "RETURNED", "returned"),
    }
    if (
        allocation.status in terminal_statuses
        and (
            allocation.fulfilled_cost_cny is None
            or allocation.fulfilled_cost_cny < 0
        )
    ):
        _issue(
            issues, "ALLOCATION_COST_SNAPSHOT_MISSING",
            f"已出库分配 {allocation.pk} 缺少有效成本快照",
            batch_id=batch.pk, order_id=order_id, allocation_id=allocation.pk,
        )
    if allocation.inventory_form == SalesOrderItem.SaleUnit.BOX:
        valid_shape = (
            allocation.box_size_snapshot is not None
            and allocation.box_size_snapshot > 0
            and allocation.box_size_snapshot == batch.box_size
            and allocation.quantity % allocation.box_size_snapshot == 0
        )
    else:
        valid_shape = (
            allocation.inventory_form == SalesOrderItem.SaleUnit.STICK
            and allocation.box_size_snapshot is None
        )
    if not valid_shape:
        _issue(
            issues, "ALLOCATION_PACKAGING_SNAPSHOT_INVALID",
            f"库存分配 {allocation.pk} 的包装快照无效",
            batch_id=batch.pk, order_id=order_id, allocation_id=allocation.pk,
        )


def _audit_movement(issues, movement):
    batch = movement.purchase_batch
    item = movement.sales_order_item
    sales_types = {
        StockMovement.MovementType.RESERVE,
        StockMovement.MovementType.RELEASE_RESERVATION,
        StockMovement.MovementType.SHIP,
        getattr(StockMovement.MovementType, "RETURN", "return"),
    }
    is_sales = movement.movement_type in sales_types
    if batch is None:
        _issue(
            issues, "MOVEMENT_BATCH_MISSING",
            f"库存流水 {movement.pk} 缺少采购批次", movement_id=movement.pk,
        )
    elif batch.cigar_id != movement.cigar_id:
        _issue(
            issues, "MOVEMENT_CIGAR_MISMATCH",
            f"库存流水 {movement.pk} 的雪茄与批次不一致",
            batch_id=batch.pk, movement_id=movement.pk,
        )

    if (movement.sales_order_id is None) != (movement.sales_order_item_id is None):
        _issue(
            issues, "MOVEMENT_SALES_LINK_INCOMPLETE",
            f"库存流水 {movement.pk} 的销售单和明细关联不成对",
            batch_id=batch.pk if batch else None, order_id=movement.sales_order_id,
            movement_id=movement.pk,
        )
    if is_sales and (movement.sales_order_id is None or item is None):
        _issue(
            issues, "MOVEMENT_SALES_LINK_MISSING",
            f"销售库存流水 {movement.pk} 缺少销售关联",
            batch_id=batch.pk if batch else None, movement_id=movement.pk,
        )
    if not is_sales and (movement.sales_order_id is not None or movement.sales_order_item_id is not None):
        _issue(
            issues, "MOVEMENT_UNEXPECTED_SALES_LINK",
            f"非销售库存流水 {movement.pk} 带有销售关联",
            batch_id=batch.pk if batch else None, order_id=movement.sales_order_id,
            movement_id=movement.pk,
        )
    if item is not None:
        if item.sales_order_id != movement.sales_order_id or item.cigar_id != movement.cigar_id:
            _issue(
                issues, "MOVEMENT_SALES_DETAIL_MISMATCH",
                f"库存流水 {movement.pk} 的销售明细、订单或雪茄不一致",
                batch_id=batch.pk if batch else None, order_id=movement.sales_order_id,
                movement_id=movement.pk,
            )
    if movement.movement_type in {
        StockMovement.MovementType.RECEIVE,
        StockMovement.MovementType.RESERVE,
        StockMovement.MovementType.RELEASE_RESERVATION,
        StockMovement.MovementType.SHIP,
        getattr(StockMovement.MovementType, "RETURN", "return"),
        StockMovement.MovementType.SPLIT_BOX,
    } and movement.quantity <= 0:
        _issue(
            issues, "MOVEMENT_QUANTITY_INVALID",
            f"库存流水 {movement.pk} 数量必须为正数",
            batch_id=batch.pk if batch else None, order_id=movement.sales_order_id,
            movement_id=movement.pk,
        )
    if movement.movement_type == StockMovement.MovementType.ADJUSTMENT and movement.quantity == 0:
        _issue(
            issues, "MOVEMENT_QUANTITY_INVALID",
            f"库存调整流水 {movement.pk} 数量不能为零",
            batch_id=batch.pk if batch else None, movement_id=movement.pk,
        )
    if movement.movement_type == getattr(
        StockMovement.MovementType, "REVERSE_RECEIVE", "reverse_receive",
    ) and movement.quantity >= 0:
        _issue(
            issues, "MOVEMENT_QUANTITY_INVALID",
            f"撤销入库流水 {movement.pk} 数量必须为负数",
            batch_id=batch.pk if batch else None, movement_id=movement.pk,
        )
    if movement.movement_type == getattr(
        StockMovement.MovementType, "REVERSE_ADJUSTMENT", "reverse_adjustment",
    ) and movement.quantity == 0:
        _issue(
            issues, "MOVEMENT_QUANTITY_INVALID",
            f"撤销调整流水 {movement.pk} 数量不能为零",
            batch_id=batch.pk if batch else None, movement_id=movement.pk,
        )


def _audit_movement_pairs(issues, movements, allocations):
    movement_totals = defaultdict(lambda: defaultdict(int))
    for movement in movements:
        if movement.sales_order_item_id is None or movement.purchase_batch_id is None:
            continue
        movement_totals[
            (movement.purchase_batch_id, movement.sales_order_item_id)
        ][movement.movement_type] += movement.quantity
    allocation_totals = defaultdict(lambda: defaultdict(int))
    for allocation in allocations:
        allocation_totals[(allocation.purchase_batch_id, allocation.sales_order_item_id)][allocation.status] += allocation.quantity

    lifecycle_totals = {
        StockMovement.MovementType.RESERVE: lambda values: sum(values.values()),
        StockMovement.MovementType.RELEASE_RESERVATION: lambda values: values.get("released", 0),
        StockMovement.MovementType.SHIP: lambda values: (
            values.get("fulfilled", 0) + values.get("returned", 0)
        ),
        getattr(StockMovement.MovementType, "RETURN", "return"): lambda values: values.get("returned", 0),
    }
    for key, totals in movement_totals.items():
        batch_id, item_id = key
        allocation_values = allocation_totals.get(key, {})
        for movement_type, expected_quantity in lifecycle_totals.items():
            movement_quantity = totals.get(movement_type, 0)
            allocation_quantity = expected_quantity(allocation_values)
            if movement_quantity != allocation_quantity:
                order_id = next(
                    (a.sales_order_item.sales_order_id for a in allocations
                     if (a.purchase_batch_id, a.sales_order_item_id) == key),
                    None,
                )
                _issue(
                    issues, "MOVEMENT_ALLOCATION_MISMATCH",
                    f"批次 {batch_id} 明细 {item_id} 的 {movement_type} 流水与分配不一致",
                    batch_id=batch_id, order_id=order_id,
                )


def _audit_ledger_reversals(issues):
    """核对原交易与冲正交易的关联和逐笔相反分录。"""
    from accounting.models import LedgerTransaction

    originals = LedgerTransaction.objects.filter(
        reversed_by__isnull=False,
    ).select_related('reversed_by').prefetch_related(
        'postings', 'reversed_by__postings',
    )
    for original in originals:
        reversal = original.reversed_by
        metadata_valid = (
            original.status == LedgerTransaction.Status.POSTED
            and reversal.status == LedgerTransaction.Status.POSTED
            and reversal.transaction_type == original.transaction_type
            and reversal.source_type == 'ledger_reversal'
            and reversal.source_id == str(original.pk)
            and reversal.business_date >= original.business_date
        )
        if not metadata_valid:
            _issue(
                issues, 'LEDGER_REVERSAL_LINK_MISMATCH',
                f'账务交易 {original.pk} 的冲正关联不完整',
            )
        original_rows = Counter(
            (
                posting.account_id, posting.category, posting.currency,
                -posting.amount, -posting.cny_amount,
            )
            for posting in original.postings.all()
        )
        reversal_rows = Counter(
            (
                posting.account_id, posting.category, posting.currency,
                posting.amount, posting.cny_amount,
            )
            for posting in reversal.postings.all()
        )
        if original_rows != reversal_rows:
            _issue(
                issues, 'LEDGER_REVERSAL_POSTINGS_MISMATCH',
                f'账务交易 {original.pk} 的冲正分录不完全相反',
            )

    linked_reversal_ids = set(originals.values_list('reversed_by_id', flat=True))
    orphan_ids = LedgerTransaction.objects.filter(
        source_type='ledger_reversal',
    ).exclude(pk__in=linked_reversal_ids).values_list('pk', flat=True)
    for reversal_id in orphan_ids:
        _issue(
            issues, 'LEDGER_REVERSAL_ORPHAN',
            f'冲正交易 {reversal_id} 没有对应原交易',
        )


def _posting_counter(transaction_obj, categories=None):
    postings = transaction_obj.postings.all()
    if categories is not None:
        postings = postings.filter(category__in=categories)
    return Counter(
        (
            row.account_id, row.category, row.currency,
            row.amount, row.cny_amount,
        )
        for row in postings
    )


def _audit_purchase_receipts(issues):
    """按采购单、入库键和冲正流水核对采购到货。"""
    from accounting.models import FundAccount, LedgerPosting, LedgerTransaction

    orders = list(PurchaseOrder.objects.prefetch_related('items'))
    batches = PurchaseBatch.objects.filter(
        source=PurchaseBatch.Source.PURCHASE,
    ).select_related(
        'purchase_order_item__purchase_order',
    ).prefetch_related('stock_movements')
    receipt_groups = defaultdict(list)
    batches_by_order = defaultdict(list)
    for batch in batches:
        order = batch.purchase_order_item.purchase_order
        batches_by_order[order.pk].append(batch)
        # 旧历史采购没有可追溯的付款/到货交易，只在批次本身的通用审计中检查。
        if order.legacy_received:
            continue
        # 草稿测试夹具没有正式到货事实；正式已到货或已撤销批次必须审计。
        if order.status != PurchaseOrder.Status.RECEIVED and batch.reversed_at is None:
            continue
        receives = [
            movement for movement in batch.stock_movements.all()
            if movement.movement_type == StockMovement.MovementType.RECEIVE
        ]
        if len(receives) != 1 or not receives[0].idempotency_key:
            _issue(
                issues, 'PURCHASE_RECEIPT_LEDGER_MISMATCH',
                f'采购批次 {batch.pk} 缺少可追溯的原到货交易',
                batch_id=batch.pk,
            )
            continue
        receipt_groups[(order.pk, receives[0].idempotency_key)].append(batch)

    # 采购单级检查不能只从批次反推，否则“已到货但少批次”会静默通过。
    for order in orders:
        if order.legacy_received:
            continue
        order_items = list(order.items.all())
        order_batches = batches_by_order.get(order.pk, [])
        active = [batch for batch in order_batches if batch.reversed_at is None]
        if order.status == PurchaseOrder.Status.RECEIVED:
            current = [
                batch for batch in active
                if any(
                    movement.movement_type == StockMovement.MovementType.RECEIVE
                    and movement.idempotency_key == order.arrival_idempotency_key
                    for movement in batch.stock_movements.all()
                )
            ]
            current_by_item = defaultdict(list)
            for batch in current:
                current_by_item[batch.purchase_order_item_id].append(batch)
            complete = (
                bool(order.arrival_idempotency_key)
                and bool(order_items)
                and len(current) == len(order_items)
                and all(len(current_by_item[item.pk]) == 1 for item in order_items)
                and len(active) == len(current)
            )
            if not complete:
                _issue(
                    issues, 'PURCHASE_RECEIPT_LEDGER_MISMATCH',
                    f'采购单 {order.pk} 已到货但批次与明细不完整',
                    order_id=order.pk,
                )
            expected_cost = sum(
                (item.actual_cost_cny for item in order_items), Decimal('0.00'),
            )
            batch_cost = sum(
                (batch.original_cost_cny for batch in current), Decimal('0.00'),
            )
            if (
                expected_cost != (order.paid_cny_cost or Decimal('0.00'))
                or batch_cost != expected_cost
            ):
                _issue(
                    issues, 'PURCHASE_RECEIPT_LEDGER_MISMATCH',
                    f'采购单 {order.pk} 的到货成本合计不一致',
                    order_id=order.pk,
                )
        elif order.status == PurchaseOrder.Status.IN_TRANSIT and active:
            _issue(
                issues, 'PURCHASE_RECEIPT_LEDGER_MISMATCH',
                f'采购单 {order.pk} 仍在途但存在未撤销到货批次',
                order_id=order.pk,
            )

    def reversal_valid(original):
        """已撤销到货必须有一笔逐项相反的账务交易。"""
        reversal = original.reversed_by
        if reversal is None:
            return False
        metadata_valid = (
            reversal.status == LedgerTransaction.Status.POSTED
            and reversal.transaction_type == LedgerTransaction.TransactionType.PURCHASE_RECEIPT
            and reversal.source_type == 'ledger_reversal'
            and reversal.source_id == str(original.pk)
            and reversal.business_date >= original.business_date
        )
        return metadata_valid and _posting_counter(reversal) == Counter(
            (
                posting.account_id, posting.category, posting.currency,
                -posting.amount, -posting.cny_amount,
            )
            for posting in original.postings.all()
        )

    for (order_id, receipt_key), grouped_batches in receipt_groups.items():
        order = grouped_batches[0].purchase_order_item.purchase_order
        active = [batch for batch in grouped_batches if batch.reversed_at is None]
        cost = sum(
            (batch.original_cost_cny for batch in grouped_batches),
            Decimal('0.00'),
        )
        transaction_obj = LedgerTransaction.objects.filter(
            idempotency_key=receipt_key,
        ).first()
        expected = Counter({
            (
                None, LedgerPosting.Category.PURCHASE_IN_TRANSIT,
                FundAccount.Currency.CNY, -cost, -cost,
            ): 1,
            (
                None, LedgerPosting.Category.INVENTORY,
                FundAccount.Currency.CNY, cost, cost,
            ): 1,
        })
        valid = (
            transaction_obj is not None
            and transaction_obj.status in (
                LedgerTransaction.Status.POSTED,
                LedgerTransaction.Status.REVERSED,
            )
            and transaction_obj.transaction_type == LedgerTransaction.TransactionType.PURCHASE_RECEIPT
            and transaction_obj.source_type == 'purchase_order'
            and transaction_obj.source_id == str(order_id)
            and (not active or order.arrival_idempotency_key == receipt_key)
            and _posting_counter(transaction_obj) == expected
        )
        if valid and active:
            valid = (
                transaction_obj.status == LedgerTransaction.Status.POSTED
                and transaction_obj.reversed_by_id is None
            )
        elif valid and not active:
            valid = (
                transaction_obj.status == LedgerTransaction.Status.POSTED
                and reversal_valid(transaction_obj)
            )
        if not valid:
            _issue(
                issues, 'PURCHASE_RECEIPT_LEDGER_MISMATCH',
                f'采购单 {order_id} 的到货账务交易与批次成本不一致',
            )


def _audit_sales_shipments(issues):
    """核对销售出库来源和 FIFO 库存成本分录。"""
    from accounting.models import FundAccount, LedgerPosting, LedgerTransaction

    shipments = SalesShipment.objects.select_related(
        'sales_order', 'ledger_transaction',
    ).prefetch_related('ledger_transaction__postings')
    categories = {
        LedgerPosting.Category.COST_OF_GOODS_SOLD,
        LedgerPosting.Category.INVENTORY,
    }
    for shipment in shipments:
        transaction_obj = shipment.ledger_transaction
        cost = shipment.fifo_cost_cny
        expected = Counter({
            (
                None, LedgerPosting.Category.COST_OF_GOODS_SOLD,
                FundAccount.Currency.CNY, cost, cost,
            ): 1,
            (
                None, LedgerPosting.Category.INVENTORY,
                FundAccount.Currency.CNY, -cost, -cost,
            ): 1,
        })
        valid = (
            transaction_obj.status == LedgerTransaction.Status.POSTED
            and transaction_obj.transaction_type == LedgerTransaction.TransactionType.SALES_SHIPMENT
            and transaction_obj.source_type == 'sales_order'
            and transaction_obj.source_id == str(shipment.sales_order_id)
            and _posting_counter(transaction_obj, categories) == expected
        )
        if not valid:
            _issue(
                issues, 'SALES_SHIPMENT_LEDGER_MISMATCH',
                f'销售单 {shipment.sales_order_id} 的出库账务交易与 FIFO 成本不一致',
                order_id=shipment.sales_order_id,
            )


def _audit_adjustment_actions(issues):
    """核对结构化调整、逐批事实与反向流水。"""
    actions = InventoryAdjustmentAction.objects.select_related(
        'ledger_transaction', 'reversal_transaction',
    ).prefetch_related('lines__stock_movement')
    for action in actions:
        lines = list(action.lines.all())
        if not lines or sum(line.quantity_delta for line in lines) != action.quantity_delta:
            _issue(
                issues, 'ADJUSTMENT_LINES_MISMATCH',
                f'库存调整 {action.pk} 的逐批数量与动作总量不一致',
            )
        for line in lines:
            movement = line.stock_movement
            if (
                movement.movement_type != StockMovement.MovementType.ADJUSTMENT
                or movement.purchase_batch_id != line.purchase_batch_id
                or movement.quantity != line.quantity_delta
            ):
                _issue(
                    issues, 'ADJUSTMENT_MOVEMENT_MISMATCH',
                    f'库存调整 {action.pk} 的原调整流水不一致',
                    batch_id=line.purchase_batch_id,
                    movement_id=movement.pk,
                )
        from accounting.models import FundAccount, LedgerPosting, LedgerTransaction
        cost_delta = sum((line.cost_delta_cny for line in lines), Decimal('0.00'))
        offset_category = (
            LedgerPosting.Category.INVENTORY_ADJUSTMENT_GAIN
            if cost_delta > 0
            else LedgerPosting.Category.INVENTORY_ADJUSTMENT_LOSS
        )
        expected_postings = Counter({
            (
                None, LedgerPosting.Category.INVENTORY,
                FundAccount.Currency.CNY, cost_delta, cost_delta,
            ): 1,
            (
                None, offset_category, FundAccount.Currency.CNY,
                -cost_delta, -cost_delta,
            ): 1,
        })
        original = action.ledger_transaction
        source_parts = original.source_id.split(':')
        source_matches_action = (
            len(source_parts) == 3
            and source_parts[0] == 'stock_adjustment'
            and len(source_parts[1]) == 64
            and all(character in '0123456789abcdef' for character in source_parts[1])
            and source_parts[2].isdigit()
            and int(source_parts[2]) in {line.purchase_batch_id for line in lines}
        )
        ledger_valid = (
            bool(lines)
            and original.status == LedgerTransaction.Status.POSTED
            and original.transaction_type == LedgerTransaction.TransactionType.INVENTORY_ADJUSTMENT
            and original.source_type == 'stock_adjustment'
            and original.idempotency_key == action.idempotency_key
            and source_matches_action
            and _posting_counter(original) == expected_postings
        )
        if not ledger_valid:
            _issue(
                issues, 'ADJUSTMENT_LEDGER_MISMATCH',
                f'库存调整 {action.pk} 的原账务交易与成本变化不一致',
            )
        if action.reversal_transaction_id is None:
            if action.reversed_at is not None or action.reversal_operator_id is not None or action.reversal_reason:
                _issue(
                    issues, 'ADJUSTMENT_REVERSAL_STATE_MISMATCH',
                    f'库存调整 {action.pk} 的撤销状态不完整',
                )
            continue
        reversal = action.reversal_transaction
        if (
            action.reversed_at is None
            or action.reversal_operator_id is None
            or not action.reversal_reason
            or action.ledger_transaction.reversed_by_id != reversal.pk
        ):
            _issue(
                issues, 'ADJUSTMENT_REVERSAL_STATE_MISMATCH',
                f'库存调整 {action.pk} 的撤销关联不完整',
            )
        reverse_movements = StockMovement.objects.filter(
            movement_type=StockMovement.MovementType.REVERSE_ADJUSTMENT,
            idempotency_key=reversal.idempotency_key,
        )
        reverse_totals = defaultdict(int)
        for movement in reverse_movements:
            reverse_totals[movement.purchase_batch_id] += movement.quantity
        expected_totals = defaultdict(int)
        for line in lines:
            expected_totals[line.purchase_batch_id] -= line.quantity_delta
        if dict(reverse_totals) != dict(expected_totals):
            _issue(
                issues, 'ADJUSTMENT_REVERSE_MOVEMENT_MISMATCH',
                f'库存调整 {action.pk} 的撤销流水与逐批事实不一致',
            )


def _audit_sales_returns(issues):
    """核对退货事实、订单状态、成本快照与销售出库冲正。"""
    returns = SalesReturn.objects.select_related(
        'sales_order', 'sales_shipment__ledger_transaction', 'ledger_transaction',
    ).prefetch_related(
        'sales_order__items__allocations',
    )
    return_order_ids = set()
    for sales_return in returns:
        order = sales_return.sales_order
        return_order_ids.add(order.pk)
        allocations = [
            allocation
            for item in order.items.all()
            for allocation in item.allocations.all()
        ]
        returned_cost = sum(
            (allocation.fulfilled_cost_cny or 0) for allocation in allocations
        )
        valid = (
            order.fulfillment_status == order.FulfillmentStatus.RETURNED
            and sales_return.sales_shipment.sales_order_id == order.pk
            and allocations
            and all(
                allocation.status == StockAllocation.Status.RETURNED
                for allocation in allocations
            )
            and returned_cost == sales_return.fifo_cost_cny
            and sales_return.amount_cny == order.amount_due_cny
            and sales_return.sales_shipment.ledger_transaction.reversed_by_id
            == sales_return.ledger_transaction_id
            and sales_return.sales_shipment.ledger_transaction.source_type == 'sales_order'
            and sales_return.sales_shipment.ledger_transaction.source_id == str(order.pk)
        )
        if not valid:
            _issue(
                issues, 'SALES_RETURN_FACT_MISMATCH',
                f'销售单 {order.pk} 的退货事实不完整', order_id=order.pk,
            )

    from .models import SalesOrder

    missing_ids = SalesOrder.objects.filter(
        fulfillment_status=SalesOrder.FulfillmentStatus.RETURNED,
    ).exclude(pk__in=return_order_ids).values_list('pk', flat=True)
    for order_id in missing_ids:
        _issue(
            issues, 'SALES_RETURN_FACT_MISSING',
            f'已退货销售单 {order_id} 缺少退货事实', order_id=order_id,
        )


def audit_inventory():
    """读取全部库存事实并返回问题；本函数不执行任何写入。"""
    issues = []
    batches = list(PurchaseBatch.objects.all().order_by("pk"))
    allocations = list(
        StockAllocation.objects.select_related("purchase_batch", "sales_order_item").all()
    )
    movements = list(
        StockMovement.objects.select_related(
            "purchase_batch", "sales_order_item", "sales_order",
        ).all()
    )
    movements_by_batch = defaultdict(list)
    for movement in movements:
        if movement.purchase_batch_id is not None:
            movements_by_batch[movement.purchase_batch_id].append(movement)

    reserved_by_batch = defaultdict(list)
    for allocation in allocations:
        _audit_allocation(issues, allocation, reserved_by_batch)
    for batch in batches:
        _audit_batch(issues, batch, reserved_by_batch, movements_by_batch)
    for movement in movements:
        _audit_movement(issues, movement)
    _audit_movement_pairs(issues, movements, allocations)
    _audit_purchase_receipts(issues)
    _audit_sales_shipments(issues)
    _audit_ledger_reversals(issues)
    _audit_adjustment_actions(issues)
    _audit_sales_returns(issues)
    return InventoryAuditResult(issues=tuple(issues))


__all__ = ["InventoryAuditIssue", "InventoryAuditResult", "audit_inventory"]
