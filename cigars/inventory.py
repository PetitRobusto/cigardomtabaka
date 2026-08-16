"""库存事实的统一写入 Module。"""
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.utils import timezone

from accounting.services import _acquire_sqlite_writer_gate, _retry_sqlite_locked

from .audit import AgentContext
from .inventory_scope import (
    _INVENTORY_WRITE_CAPABILITY,
    inventory_mutation_scope,
)
from .models import (
    AdjustmentRecord,
    Cigar,
    PurchaseBatch,
    SalesOrder,
    SalesOrderItem,
    StockAllocation,
    StockMovement,
)


MONEY_PLACES = Decimal("0.01")


class InventoryError(ValueError):
    def __init__(self, message, *, details=None):
        super().__init__(message)
        self.details = details or {}


class InventoryInsufficientError(InventoryError):
    """动作会使可售或物理库存不足。"""


@dataclass(frozen=True)
class ShipmentResult:
    item_costs: dict[int, Decimal]
    total_cost_cny: Decimal


@dataclass(frozen=True)
class AdjustmentResult:
    batch: PurchaseBatch
    cost_cny: Decimal


def _validated_entry_costs(*, quantity, total_cost_cny, unit_cost_cny):
    """校验入库成本池与展示单价使用同一金额基础。"""
    try:
        total = Decimal(total_cost_cny)
        unit = Decimal(unit_cost_cny)
    except (TypeError, ValueError):
        raise InventoryError("入库成本无效")
    if (not isinstance(quantity, int) or isinstance(quantity, bool) or quantity <= 0
            or not total.is_finite() or not unit.is_finite()
            or total < 0 or unit < 0 or total != total.quantize(MONEY_PLACES)):
        raise InventoryError("入库数量或成本无效")
    expected_unit = (total / quantity).quantize(
        MONEY_PLACES, rounding=ROUND_HALF_UP,
    )
    if unit != expected_unit:
        raise InventoryError("成本单价与总成本不一致")
    return total, unit


def _record_movement(*, movement_type, cigar, quantity, operator, context,
                     purchase_batch=None, sales_order=None, sales_order_item=None,
                     note=""):
    return StockMovement.objects.create(
        movement_type=movement_type,
        cigar=cigar,
        purchase_batch=purchase_batch,
        sales_order=sales_order,
        sales_order_item=sales_order_item,
        quantity=quantity,
        operator=operator,
        note=note or "",
        **context.movement_fields(),
    )


def _allocation_uses_boxes(*, allocation, batch):
    item = allocation.sales_order_item
    return bool(
        item.sale_unit == SalesOrderItem.SaleUnit.BOX
        and batch.box_size == item.box_size
        and batch.box_size
        and allocation.quantity % batch.box_size == 0
    )


def _remove_remaining_cost(batch, quantity):
    """批次最后一件承接舍入尾差，确保成本池归零。"""
    if quantity > batch.physical_remaining:
        raise InventoryInsufficientError("批次物理库存不足")
    if quantity == batch.physical_remaining:
        return batch.remaining_cost_cny
    return (
        batch.remaining_cost_cny * quantity / batch.physical_remaining
    ).quantize(MONEY_PLACES, rounding=ROUND_HALF_UP)


@_retry_sqlite_locked
@transaction.atomic
def open_stock(*, cigar_id, quantity, box_size, box_quantity, loose_sticks,
               total_cost_cny, unit_cost_cny, operator, context, note=""):
    """建立一个 Day 1 期初批次及其库存流水。"""
    _acquire_sqlite_writer_gate()
    if (box_size is None and (box_quantity != 0 or loose_sticks != quantity)) or (
        box_size is not None and (box_size <= 0 or box_quantity < 0 or loose_sticks < 0
                                  or quantity != box_size * box_quantity + loose_sticks)
    ):
        raise InventoryError("期初库存包装数量不一致")
    total_cost_cny, unit_cost_cny = _validated_entry_costs(
        quantity=quantity, total_cost_cny=total_cost_cny,
        unit_cost_cny=unit_cost_cny,
    )
    with inventory_mutation_scope(
        action="opening", operator=operator,
        _capability=_INVENTORY_WRITE_CAPABILITY,
    ):
        batch = PurchaseBatch.objects.create(
            purchase_order_item=None,
            source=PurchaseBatch.Source.OPENING,
            cigar_id=cigar_id,
            quantity=quantity,
            remaining=quantity,
            physical_remaining=quantity,
            box_size=box_size,
            original_box_quantity=box_quantity,
            original_stick_quantity=loose_sticks,
            physical_box_quantity=box_quantity,
            available_box_quantity=box_quantity,
            physical_stick_quantity=loose_sticks,
            available_stick_quantity=loose_sticks,
            original_cost_cny=total_cost_cny,
            remaining_cost_cny=total_cost_cny,
            positive_adjustment_quantity=0,
            positive_adjustment_cost_cny=Decimal("0.00"),
            adjustment_cost_cny=Decimal("0.00"),
            sold_cost_cny=Decimal("0.00"),
            unit_cost_cny=unit_cost_cny,
        )
        _record_movement(
            movement_type=StockMovement.MovementType.RECEIVE,
            cigar=batch.cigar,
            purchase_batch=batch,
            quantity=quantity,
            operator=operator,
            context=context,
            note=note,
        )
        return batch


@_retry_sqlite_locked
@transaction.atomic
def receive_stock(*, purchase_order_item, quantity, total_cost_cny, unit_cost_cny,
                  operator, context, note=""):
    """建立采购入库批次及其库存流水。"""
    _acquire_sqlite_writer_gate()
    if quantity != purchase_order_item.quantity:
        raise InventoryError("采购入库数量与采购明细不一致")
    total_cost_cny, unit_cost_cny = _validated_entry_costs(
        quantity=quantity, total_cost_cny=total_cost_cny,
        unit_cost_cny=unit_cost_cny,
    )
    boxes = purchase_order_item.box_quantity
    with inventory_mutation_scope(
        action="receive", operator=operator,
        _capability=_INVENTORY_WRITE_CAPABILITY,
    ):
        batch = PurchaseBatch.objects.create(
            purchase_order_item=purchase_order_item,
            source=PurchaseBatch.Source.PURCHASE,
            cigar=purchase_order_item.cigar,
            quantity=quantity,
            remaining=quantity,
            physical_remaining=quantity,
            original_cost_cny=total_cost_cny,
            remaining_cost_cny=total_cost_cny,
            sold_cost_cny=Decimal("0.00"),
            unit_cost_cny=unit_cost_cny,
            box_size=purchase_order_item.box_size,
            original_box_quantity=boxes,
            original_stick_quantity=0,
            physical_box_quantity=boxes,
            available_box_quantity=boxes,
            physical_stick_quantity=0,
            available_stick_quantity=0,
        )
        _record_movement(
            movement_type=StockMovement.MovementType.RECEIVE,
            cigar=purchase_order_item.cigar,
            purchase_batch=batch,
            quantity=quantity,
            operator=operator,
            context=context,
            note=note,
        )
        return batch


def _reserve_boxes(*, order, item, operator, context, note):
    batches = list(
        PurchaseBatch.objects.select_for_update()
        .filter(
            cigar=item.cigar,
            box_size=item.box_size,
            available_box_quantity__gt=0,
        )
        .order_by("purchased_at", "id")
    )
    available = sum(batch.available_box_quantity for batch in batches)
    if available < item.sale_quantity:
        raise InventoryInsufficientError(
            f"{item.cigar.name or item.cigar.english_name} 整盒库存不足",
            details={
                "cigar_id": item.cigar_id,
                "requested": item.sale_quantity,
                "available": available,
                "unit": "boxes",
            },
        )
    remaining = item.sale_quantity
    cost = Decimal("0.00")
    for batch in batches:
        take_boxes = min(batch.available_box_quantity, remaining)
        if not take_boxes:
            continue
        quantity = take_boxes * item.box_size
        batch.remaining -= quantity
        batch.available_box_quantity -= take_boxes
        batch.save(update_fields=["remaining", "available_box_quantity"])
        StockAllocation.objects.create(
            sales_order_item=item,
            purchase_batch=batch,
            quantity=quantity,
            status=StockAllocation.Status.RESERVED,
        )
        _record_movement(
            movement_type=StockMovement.MovementType.RESERVE,
            cigar=item.cigar,
            purchase_batch=batch,
            sales_order=order,
            sales_order_item=item,
            quantity=quantity,
            operator=operator,
            context=context,
            note=note,
        )
        cost += _remove_remaining_cost(batch, quantity)
        remaining -= take_boxes
        if not remaining:
            break
    return cost.quantize(MONEY_PLACES)


def _reserve_sticks(*, order, item, operator, context, note):
    batches = list(
        PurchaseBatch.objects.select_for_update()
        .filter(cigar=item.cigar, available_stick_quantity__gt=0)
        .order_by("purchased_at", "id")
    )
    available = sum(batch.available_stick_quantity for batch in batches)
    if available < item.quantity:
        raise InventoryInsufficientError(
            f"{item.cigar.name or item.cigar.english_name} 现货库存不足",
            details={
                "cigar_id": item.cigar_id,
                "requested": item.quantity,
                "available": available,
            },
        )
    remaining = item.quantity
    cost = Decimal("0.00")
    for batch in batches:
        take = min(batch.available_stick_quantity, remaining)
        if not take:
            continue
        batch.remaining -= take
        batch.available_stick_quantity -= take
        batch.save(update_fields=["remaining", "available_stick_quantity"])
        StockAllocation.objects.create(
            sales_order_item=item,
            purchase_batch=batch,
            quantity=take,
            status=StockAllocation.Status.RESERVED,
        )
        _record_movement(
            movement_type=StockMovement.MovementType.RESERVE,
            cigar=item.cigar,
            purchase_batch=batch,
            sales_order=order,
            sales_order_item=item,
            quantity=take,
            operator=operator,
            context=context,
            note=note,
        )
        cost += _remove_remaining_cost(batch, take)
        remaining -= take
    return cost.quantize(MONEY_PLACES)


@_retry_sqlite_locked
@transaction.atomic
def reserve_order_item(*, order, item, operator, context, note=""):
    """按包装形态和 FIFO 预留一条现货销售明细。"""
    if item.fulfillment_type != SalesOrderItem.FulfillmentType.IN_STOCK:
        raise InventoryError("预售明细不能预留现货库存")
    _acquire_sqlite_writer_gate()
    with inventory_mutation_scope(
        action="reserve", operator=operator,
        _capability=_INVENTORY_WRITE_CAPABILITY,
    ):
        if item.sale_unit == SalesOrderItem.SaleUnit.BOX:
            return _reserve_boxes(
                order=order, item=item, operator=operator,
                context=context, note=note,
            )
        return _reserve_sticks(
            order=order, item=item, operator=operator,
            context=context, note=note,
        )


@_retry_sqlite_locked
@transaction.atomic
def release_order(*, order, operator, context, note=""):
    """释放销售单全部活动预留。"""
    _acquire_sqlite_writer_gate()
    now = timezone.now()
    allocations = list(
        StockAllocation.objects.select_for_update()
        .filter(
            sales_order_item__sales_order=order,
            status=StockAllocation.Status.RESERVED,
        )
        .select_related("sales_order_item__cigar")
        .order_by("purchase_batch_id", "id")
    )
    with inventory_mutation_scope(
        action="release", operator=operator,
        _capability=_INVENTORY_WRITE_CAPABILITY,
    ):
        for allocation in allocations:
            batch = PurchaseBatch.objects.select_for_update().get(
                pk=allocation.purchase_batch_id
            )
            batch.remaining += allocation.quantity
            if _allocation_uses_boxes(allocation=allocation, batch=batch):
                batch.available_box_quantity += allocation.quantity // batch.box_size
                fields = ["remaining", "available_box_quantity"]
            else:
                batch.available_stick_quantity += allocation.quantity
                fields = ["remaining", "available_stick_quantity"]
            batch.save(update_fields=fields)
            allocation.status = StockAllocation.Status.RELEASED
            allocation.released_at = now
            allocation.save(update_fields=["status", "released_at"])
            _record_movement(
                movement_type=StockMovement.MovementType.RELEASE_RESERVATION,
                cigar=allocation.sales_order_item.cigar,
                purchase_batch=batch,
                sales_order=order,
                sales_order_item=allocation.sales_order_item,
                quantity=allocation.quantity,
                operator=operator,
                context=context,
                note=note,
            )
    return allocations


@_retry_sqlite_locked
@transaction.atomic
def ship_order(*, order, operator, context, note=""):
    """把完整预留转为物理出库，并返回逐明细 FIFO 成本。"""
    _acquire_sqlite_writer_gate()
    items = list(order.items.select_for_update().select_related("cigar").order_by("id"))
    if not items:
        raise InventoryError("销售单没有明细")
    item_costs = {}
    now = timezone.now()
    with inventory_mutation_scope(
        action="ship", operator=operator,
        _capability=_INVENTORY_WRITE_CAPABILITY,
    ):
        for item in items:
            if item.fulfillment_type == SalesOrderItem.FulfillmentType.PREORDER:
                raise InventoryError("预售明细不能通过现货出库")
            allocations = list(
                StockAllocation.objects.select_for_update()
                .filter(sales_order_item=item)
                .order_by("id")
            )
            reserved = [
                allocation for allocation in allocations
                if allocation.status == StockAllocation.Status.RESERVED
            ]
            if (
                len(reserved) != len(allocations)
                or sum(allocation.quantity for allocation in reserved) != item.quantity
            ):
                raise InventoryError("销售明细库存预留不完整，不能出库")
            item_cost = Decimal("0.00")
            for allocation in reserved:
                batch = PurchaseBatch.objects.select_for_update().get(
                    pk=allocation.purchase_batch_id
                )
                quantity = allocation.quantity
                if quantity > batch.physical_remaining:
                    raise InventoryError("出库时物理库存不足")
                cost = _remove_remaining_cost(batch, quantity)
                batch.physical_remaining -= quantity
                batch.remaining_cost_cny -= cost
                batch.sold_cost_cny += cost
                if _allocation_uses_boxes(allocation=allocation, batch=batch):
                    boxes = quantity // batch.box_size
                    if boxes > batch.physical_box_quantity:
                        raise InventoryError("出库时完整盒库存不足")
                    batch.physical_box_quantity -= boxes
                    fields = [
                        "physical_remaining", "physical_box_quantity",
                        "remaining_cost_cny", "sold_cost_cny",
                    ]
                else:
                    if quantity > batch.physical_stick_quantity:
                        raise InventoryError("出库时散支库存不足")
                    batch.physical_stick_quantity -= quantity
                    fields = [
                        "physical_remaining", "physical_stick_quantity",
                        "remaining_cost_cny", "sold_cost_cny",
                    ]
                batch.save(update_fields=fields)
                allocation.status = StockAllocation.Status.FULFILLED
                allocation.fulfilled_at = now
                allocation.save(update_fields=["status", "fulfilled_at"])
                _record_movement(
                    movement_type=StockMovement.MovementType.SHIP,
                    cigar=item.cigar,
                    purchase_batch=batch,
                    sales_order=order,
                    sales_order_item=item,
                    quantity=quantity,
                    operator=operator,
                    context=context,
                    note=note,
                )
                item_cost += cost
            item_costs[item.pk] = item_cost.quantize(MONEY_PLACES)
    return ShipmentResult(
        item_costs=item_costs,
        total_cost_cny=sum(item_costs.values(), Decimal("0.00")).quantize(MONEY_PLACES),
    )


@_retry_sqlite_locked
@transaction.atomic
def split_box(*, batch_id, operator, context, note=""):
    """把一个完全可用的完整盒转换为同批次散支。"""
    _acquire_sqlite_writer_gate()
    try:
        batch = PurchaseBatch.objects.select_for_update().get(pk=batch_id)
    except PurchaseBatch.DoesNotExist as exc:
        raise InventoryError("批次不存在") from exc
    if not batch.box_size:
        raise InventoryError("散支批次不能拆盒")
    if batch.physical_box_quantity < 1:
        raise InventoryError("批次没有完整物理盒可拆")
    if batch.available_box_quantity < 1:
        raise InventoryError("批次没有可用完整盒可拆")
    with inventory_mutation_scope(
        action="split_box", operator=operator,
        _capability=_INVENTORY_WRITE_CAPABILITY,
    ):
        batch.physical_box_quantity -= 1
        batch.available_box_quantity -= 1
        batch.physical_stick_quantity += batch.box_size
        batch.available_stick_quantity += batch.box_size
        batch.save(update_fields=[
            "physical_box_quantity", "available_box_quantity",
            "physical_stick_quantity", "available_stick_quantity",
        ])
        _record_movement(
            movement_type=StockMovement.MovementType.SPLIT_BOX,
            cigar=batch.cigar,
            purchase_batch=batch,
            quantity=batch.box_size,
            operator=operator,
            context=context,
            note=note,
        )
    return batch


def _adjustment_batches(*, cigar, batch_id=None):
    queryset = PurchaseBatch.objects.select_for_update().filter(
        cigar=cigar, remaining__gt=0
    )
    if batch_id:
        queryset = queryset.filter(pk=batch_id)
    batches = list(queryset.order_by("purchased_at", "id"))
    if batch_id and not batches:
        raise InventoryError("批次不存在或无可用库存")
    return batches


def _adjustment_batch(*, cigar, batch_id, unit_cost_cny):
    if batch_id:
        try:
            return PurchaseBatch.objects.select_for_update().get(
                pk=batch_id, cigar=cigar
            )
        except PurchaseBatch.DoesNotExist as exc:
            raise InventoryError("批次不存在或不匹配") from exc
    if unit_cost_cny is None:
        raise InventoryError("正向库存修正需要 unit_cost_cny")
    if unit_cost_cny <= 0:
        raise InventoryError("正向库存修正成本单价必须大于零")
    return PurchaseBatch.objects.create(
        purchase_order_item=None,
        source=PurchaseBatch.Source.ADJUSTMENT,
        cigar=cigar,
        original_cost_cny=Decimal("0.00"),
        positive_adjustment_quantity=0,
        positive_adjustment_cost_cny=Decimal("0.00"),
        adjustment_cost_cny=Decimal("0.00"),
        quantity=0,
        remaining=0,
        physical_remaining=0,
        remaining_cost_cny=Decimal("0.00"),
        sold_cost_cny=Decimal("0.00"),
        unit_cost_cny=unit_cost_cny,
    )


@_retry_sqlite_locked
@transaction.atomic
def adjust_stock(*, cigar, quantity_delta, inventory_form, operator, context,
                 reason, batch_id=None, unit_cost_cny=None,
                 adjustment_type=AdjustmentRecord.AdjustType.LOSS):
    """执行一次库存调整；负向调整按 FIFO 扣减。"""
    _acquire_sqlite_writer_gate()
    if quantity_delta == 0:
        raise InventoryError("库存修正数量不能为 0")
    if inventory_form not in {"stick", "box"}:
        raise InventoryError("库存修正形态必须是 stick 或 box")
    if inventory_form == "box" and not batch_id:
        raise InventoryError("box 修正必须指定批次")
    with inventory_mutation_scope(
        action="adjust", operator=operator,
        _capability=_INVENTORY_WRITE_CAPABILITY,
    ):
        if quantity_delta > 0:
            batch = _adjustment_batch(
                cigar=cigar, batch_id=batch_id, unit_cost_cny=unit_cost_cny
            )
            if inventory_form == "box":
                if not batch.box_size:
                    raise InventoryError("散支批次不能按 box 修正")
                if quantity_delta % batch.box_size:
                    raise InventoryError("box 修正数量必须是包装支数的整数倍")
                shape_quantity = quantity_delta // batch.box_size
                available_field = "available_box_quantity"
                physical_field = "physical_box_quantity"
            else:
                shape_quantity = quantity_delta
                available_field = "available_stick_quantity"
                physical_field = "physical_stick_quantity"
            added_cost = (batch.unit_cost_cny * quantity_delta).quantize(MONEY_PLACES)
            batch.positive_adjustment_quantity += quantity_delta
            batch.positive_adjustment_cost_cny += added_cost
            batch.remaining += quantity_delta
            batch.physical_remaining += quantity_delta
            batch.remaining_cost_cny += added_cost
            setattr(batch, available_field, getattr(batch, available_field) + shape_quantity)
            setattr(batch, physical_field, getattr(batch, physical_field) + shape_quantity)
            batch.save(update_fields=[
                "positive_adjustment_quantity", "positive_adjustment_cost_cny",
                "remaining", "physical_remaining", available_field, physical_field,
                "remaining_cost_cny",
            ])
            _record_movement(
                movement_type=StockMovement.MovementType.ADJUSTMENT,
                cigar=cigar,
                purchase_batch=batch,
                quantity=quantity_delta,
                operator=operator,
                context=context,
                note=reason,
            )
            return AdjustmentResult(batch=batch, cost_cny=added_cost)

        quantity_to_remove = abs(quantity_delta)
        batches = _adjustment_batches(cigar=cigar, batch_id=batch_id)
        if inventory_form == "box":
            batch = batches[0]
            if not batch.box_size:
                raise InventoryError("散支批次不能按 box 修正")
            if quantity_to_remove % batch.box_size:
                raise InventoryError("box 修正数量必须是包装支数的整数倍")
            available = batch.available_box_quantity * batch.box_size
        else:
            available = sum(batch.available_stick_quantity for batch in batches)
        if available < quantity_to_remove:
            raise InventoryInsufficientError(
                f"{cigar.name or cigar.english_name} 可修正库存不足",
                details={
                    "cigar_id": cigar.pk,
                    "requested": quantity_to_remove,
                    "available": available,
                },
            )
        remaining = quantity_to_remove
        total_cost = Decimal("0.00")
        last_batch = None
        for batch in batches:
            if remaining <= 0:
                break
            if inventory_form == "box":
                take = min(
                    batch.available_box_quantity,
                    remaining // batch.box_size,
                ) * batch.box_size
            else:
                take = min(batch.available_stick_quantity, remaining)
            if not take:
                continue
            cost = _remove_remaining_cost(batch, take)
            batch.adjustment_cost_cny += cost
            batch.remaining -= take
            batch.physical_remaining -= take
            batch.remaining_cost_cny -= cost
            if inventory_form == "box":
                batch.available_box_quantity -= take // batch.box_size
                batch.physical_box_quantity -= take // batch.box_size
                shape_fields = ["available_box_quantity", "physical_box_quantity"]
            else:
                batch.available_stick_quantity -= take
                batch.physical_stick_quantity -= take
                shape_fields = ["available_stick_quantity", "physical_stick_quantity"]
            batch.save(update_fields=[
                "remaining", "physical_remaining", *shape_fields,
                "remaining_cost_cny", "adjustment_cost_cny",
            ])
            _record_movement(
                movement_type=StockMovement.MovementType.ADJUSTMENT,
                cigar=cigar,
                purchase_batch=batch,
                quantity=-take,
                operator=operator,
                context=context,
                note=reason,
            )
            AdjustmentRecord.objects.create(
                cigar=cigar,
                batch=batch,
                type=adjustment_type,
                quantity=take,
                unit_cost_cny=batch.unit_cost_cny,
                cost_cny=cost,
                operator=operator,
                reason=reason,
            )
            total_cost += cost
            remaining -= take
            last_batch = batch
        return AdjustmentResult(
            batch=last_batch,
            cost_cny=total_cost.quantize(MONEY_PLACES),
        )
