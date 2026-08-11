"""Order and inventory write services.

All stock-changing paths should go through this module so PurchaseBatch.remaining
stays a read model backed by StockMovement facts.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from .models import (
    AdjustmentRecord,
    Cigar,
    Customer,
    OrderEvent,
    PurchaseBatch,
    PurchaseOrder,
    PurchaseOrderItem,
    SalesOrder,
    SalesOrderItem,
    StockAllocation,
    StockMovement,
    Supplier,
    User,
)


MONEY_PLACES = Decimal('0.01')
EXCHANGE_RATE_PLACES = Decimal('0.0001')


class OrderServiceError(ValueError):
    """Base validation error for order/inventory commands."""

    def __init__(self, message, *, details=None):
        super().__init__(message)
        self.details = details or {}


class InsufficientStockError(OrderServiceError):
    """Raised when an in-stock sale or adjustment would make stock negative."""


@dataclass(frozen=True)
class AgentContext:
    agent_name: str = ''
    agent_run_id: str = ''
    agent_request_id: str = ''
    command_name: str = ''
    idempotency_key: str = ''

    @classmethod
    def from_mapping(cls, raw=None, *, command_name='', idempotency_key=''):
        raw = raw or {}
        return cls(
            agent_name=str(raw.get('agent_name') or raw.get('name') or '').strip(),
            agent_run_id=str(raw.get('agent_run_id') or raw.get('run_id') or '').strip(),
            agent_request_id=str(raw.get('agent_request_id') or raw.get('request_id') or '').strip(),
            command_name=command_name or str(raw.get('command_name') or '').strip(),
            idempotency_key=idempotency_key or str(raw.get('idempotency_key') or '').strip(),
        )


def _to_money(raw, field_name):
    try:
        value = Decimal(str(raw)).quantize(MONEY_PLACES, rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError):
        raise OrderServiceError(f'{field_name}必须是有效金额')
    if value < 0:
        raise OrderServiceError(f'{field_name}不能为负数')
    return value


def _to_signed_money(raw, field_name):
    try:
        return Decimal(str(raw)).quantize(MONEY_PLACES, rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError):
        raise OrderServiceError(f'{field_name}必须是有效金额')


def _to_exchange_rate(raw, field_name):
    try:
        value = Decimal(str(raw)).quantize(EXCHANGE_RATE_PLACES, rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError):
        raise OrderServiceError(f'{field_name}必须是有效汇率')
    if value <= 0:
        raise OrderServiceError(f'{field_name}必须大于 0')
    return value


def _to_positive_int(raw, field_name):
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise OrderServiceError(f'{field_name}必须是正整数')
    if value <= 0:
        raise OrderServiceError(f'{field_name}必须是正整数')
    return value


def _to_int(raw, field_name):
    try:
        return int(raw)
    except (TypeError, ValueError):
        raise OrderServiceError(f'{field_name}必须是整数')


def _require_operator(operator):
    if not isinstance(operator, User) or not operator.pk or not operator.is_operator:
        raise OrderServiceError('必须提供真实操作人 operator')
    return operator


def _movement_meta(context: AgentContext):
    return {
        'agent_name': context.agent_name,
        'agent_run_id': context.agent_run_id,
        'agent_request_id': context.agent_request_id,
        'command_name': context.command_name,
        'idempotency_key': context.idempotency_key,
    }


def _record_movement(*, movement_type, cigar, quantity, operator, context,
                     purchase_batch=None, sales_order=None, sales_order_item=None, note=''):
    return StockMovement.objects.create(
        movement_type=movement_type,
        cigar=cigar,
        purchase_batch=purchase_batch,
        sales_order=sales_order,
        sales_order_item=sales_order_item,
        quantity=quantity,
        operator=operator,
        note=note or '',
        **_movement_meta(context),
    )


def _record_order_event(order, *, operator, context, note='', metadata=None):
    return OrderEvent.objects.create(
        sales_order=order,
        operator=operator,
        agent_name=context.agent_name,
        agent_run_id=context.agent_run_id,
        agent_request_id=context.agent_request_id,
        command_name=context.command_name,
        note=note or '',
        metadata=metadata or {},
    )


def serialize_sales_order(order):
    items = []
    for item in order.items.select_related('cigar').prefetch_related('allocations__purchase_batch').all():
        allocations = [
            {
                'batch_id': alloc.purchase_batch_id,
                'quantity': alloc.quantity,
                'status': alloc.status,
            }
            for alloc in item.allocations.all()
        ]
        items.append({
            'id': item.id,
            'cigar_id': item.cigar_id,
            'cigar_name': item.cigar.name or item.cigar.english_name,
            'quantity': item.quantity,
            'unit_price': _decimal_to_json(item.unit_price),
            'unit_cost': _decimal_to_json(item.unit_cost),
            'revenue': _decimal_to_json(item.revenue),
            'cost': _decimal_to_json(item.cost),
            'profit': _decimal_to_json(item.profit),
            'fulfillment_type': item.fulfillment_type,
            'allocations': allocations,
        })
    return {
        'id': order.id,
        'order_number': order.order_number,
        'status': order.status,
        'customer_id': order.customer_id,
        'customer_name': order.customer_name,
        'total_revenue': _decimal_to_json(order.total_revenue),
        'total_cost': _decimal_to_json(order.total_cost),
        'total_profit': _decimal_to_json(order.total_profit),
        'note': order.note,
        'items': items,
    }


def _decimal_to_json(value):
    if value is None:
        return None
    if value == value.to_integral_value():
        return int(value)
    return float(value)


def serialize_purchase_order(order):
    items = []
    for item in order.items.select_related('cigar').prefetch_related('batches').all():
        batches = [
            {
                'batch_id': batch.id,
                'quantity': batch.quantity,
                'remaining': batch.remaining,
                'unit_cost_cny': _decimal_to_json(batch.unit_cost_cny),
                'purchased_at': batch.purchased_at.isoformat(),
            }
            for batch in item.batches.all()
        ]
        items.append({
            'id': item.id,
            'cigar_id': item.cigar_id,
            'cigar_name': item.cigar.name or item.cigar.english_name,
            'quantity': item.quantity,
            'box_size': item.box_size,
            'unit_price_rub': _decimal_to_json(item.unit_price_rub),
            'unit_price_cny': _decimal_to_json(item.unit_price_cny),
            'batches': batches,
        })
    return {
        'id': order.id,
        'order_number': order.order_number,
        'status': order.status,
        'supplier_id': order.supplier_id,
        'supplier_name': order.supplier.name,
        'rub_total': _decimal_to_json(order.rub_total),
        'exchange_rate': _decimal_to_json(order.exchange_rate),
        'cny_total': _decimal_to_json(order.cny_total),
        'operator_id': order.operator_id,
        'note': order.note,
        'items': items,
    }


def _get_customer(raw_customer_id):
    if not raw_customer_id:
        return None
    customer_id = _to_positive_int(raw_customer_id, '客户ID')
    try:
        return Customer.objects.get(id=customer_id)
    except Customer.DoesNotExist:
        raise OrderServiceError('客户不存在')


@transaction.atomic
def create_purchase_order(*, supplier_id, items, exchange_rate, operator, note='',
                          agent_context=None):
    """Create an immutable purchase order draft. It does not receive stock."""
    operator = _require_operator(operator)
    context = agent_context or AgentContext(command_name='create_purchase_order')
    if not isinstance(items, list) or not items:
        raise OrderServiceError('至少需要一个采购明细')

    supplier_pk = _to_positive_int(supplier_id, '供应商ID')
    try:
        supplier = Supplier.objects.get(id=supplier_pk, deleted_at__isnull=True)
    except Supplier.DoesNotExist:
        raise OrderServiceError('供应商不存在')

    rate = _to_exchange_rate(exchange_rate, '汇率')
    purchase_order = PurchaseOrder.objects.create(
        supplier=supplier,
        rub_total=Decimal('0.00'),
        exchange_rate=rate,
        cny_total=Decimal('0.00'),
        operator=operator,
        note=note or '',
        status=PurchaseOrder.Status.DRAFT,
    )

    rub_total = Decimal('0.00')
    cny_total = Decimal('0.00')
    for idx, raw_item in enumerate(items, start=1):
        if not isinstance(raw_item, dict):
            raise OrderServiceError(f'第{idx}个采购明细格式错误')
        cigar_id = _to_positive_int(raw_item.get('cigar_id'), f'第{idx}个采购明细雪茄ID')
        quantity = _to_positive_int(raw_item.get('quantity'), f'第{idx}个采购明细数量')
        unit_price_rub = _to_money(raw_item.get('unit_price_rub'), f'第{idx}个采购明细卢布单价')
        raw_box_size = raw_item.get('box_size')
        box_size = None if raw_box_size in (None, '') else _to_positive_int(raw_box_size, f'第{idx}个采购明细盒装支数')

        try:
            cigar = Cigar.objects.get(id=cigar_id)
        except Cigar.DoesNotExist:
            raise OrderServiceError(f'第{idx}个采购明细雪茄不存在')

        unit_price_cny = (unit_price_rub * rate).quantize(MONEY_PLACES, rounding=ROUND_HALF_UP)
        PurchaseOrderItem.objects.create(
            purchase_order=purchase_order,
            cigar=cigar,
            quantity=quantity,
            box_size=box_size,
            unit_price_rub=unit_price_rub,
            unit_price_cny=unit_price_cny,
        )
        rub_total += (unit_price_rub * quantity)
        cny_total += (unit_price_cny * quantity)

    purchase_order.rub_total = rub_total.quantize(MONEY_PLACES)
    purchase_order.cny_total = cny_total.quantize(MONEY_PLACES)
    purchase_order.save(update_fields=['rub_total', 'cny_total'])
    return purchase_order


@transaction.atomic
def create_sales_order(*, items, operator, customer=None, customer_id=None,
                       customer_name='', payment_method_id=None,
                       payment_manual=None, note='', agent_context=None):
    """Create a pending sales order and reserve in-stock items FIFO."""
    operator = _require_operator(operator)
    context = agent_context or AgentContext(command_name='create_sales_order')
    if not isinstance(items, list) or not items:
        raise OrderServiceError('至少需要一个商品')

    customer_obj = customer or _get_customer(customer_id)
    if customer_obj and not customer_name:
        customer_name = customer_obj.name
    selected_payment_method_id = None
    if payment_method_id:
        selected_payment_method_id = _to_positive_int(payment_method_id, '收款方式ID')

    order = SalesOrder.objects.create(
        customer=customer_obj,
        customer_name=customer_name or '',
        operator=operator,
        status='pending_payment',
        note=note or '',
        payment_method_id=selected_payment_method_id,
        payment_manual=payment_manual or {},
    )

    total_revenue = Decimal('0.00')
    total_cost = Decimal('0.00')

    for idx, raw_item in enumerate(items, start=1):
        if not isinstance(raw_item, dict):
            raise OrderServiceError(f'第{idx}个商品格式错误')
        cigar_id = _to_positive_int(raw_item.get('cigar_id'), f'第{idx}个商品ID')
        quantity = _to_positive_int(raw_item.get('quantity', 1), f'第{idx}个商品数量')
        unit_price = _to_money(raw_item.get('unit_price', 0), f'第{idx}个商品单价')
        fulfillment_type = str(raw_item.get('fulfillment_type') or SalesOrderItem.FulfillmentType.IN_STOCK)
        if fulfillment_type not in SalesOrderItem.FulfillmentType.values:
            raise OrderServiceError(f'第{idx}个商品履约类型错误')
        sale_unit = str(raw_item.get('sale_unit') or SalesOrderItem.SaleUnit.STICK)
        if sale_unit not in SalesOrderItem.SaleUnit.values:
            raise OrderServiceError(f'第{idx}个商品销售单位错误')
        if sale_unit == SalesOrderItem.SaleUnit.BOX:
            sale_quantity = _to_positive_int(raw_item.get('sale_quantity'), f'第{idx}个商品销售盒数')
            box_size = _to_positive_int(raw_item.get('box_size'), f'第{idx}个商品包装支数')
            if quantity != sale_quantity * box_size:
                raise OrderServiceError(f'第{idx}个商品盒装数量与包装快照不一致')
        else:
            sale_quantity = quantity
            box_size = None

        try:
            cigar = Cigar.objects.get(id=cigar_id)
        except Cigar.DoesNotExist:
            raise OrderServiceError(f'第{idx}个商品不存在')

        revenue = (unit_price * quantity).quantize(MONEY_PLACES)
        item = SalesOrderItem.objects.create(
            sales_order=order,
            cigar=cigar,
            quantity=quantity,
            unit_price=unit_price,
            unit_cost=Decimal('0.00'),
            revenue=revenue,
            cost=Decimal('0.00'),
            profit=revenue,
            fulfillment_type=fulfillment_type,
            sale_unit=sale_unit,
            sale_quantity=sale_quantity,
            box_size=box_size,
        )

        item_cost = Decimal('0.00')
        if fulfillment_type == SalesOrderItem.FulfillmentType.IN_STOCK:
            item_cost = _reserve_stock_fifo(
                order=order,
                item=item,
                cigar=cigar,
                quantity=quantity,
                operator=operator,
                context=context,
                note=note,
            )

        unit_cost = (item_cost / quantity).quantize(MONEY_PLACES, rounding=ROUND_HALF_UP)
        item.unit_cost = unit_cost
        item.cost = item_cost.quantize(MONEY_PLACES)
        item.profit = (revenue - item.cost).quantize(MONEY_PLACES)
        item.save(update_fields=['unit_cost', 'cost', 'profit'])

        total_revenue += revenue
        total_cost += item.cost

    order.total_revenue = total_revenue.quantize(MONEY_PLACES)
    order.total_cost = total_cost.quantize(MONEY_PLACES)
    order.total_profit = (total_revenue - total_cost).quantize(MONEY_PLACES)
    order.save(update_fields=['total_revenue', 'total_cost', 'total_profit'])

    _record_order_event(
        order,
        operator=operator,
        context=context,
        note=note,
        metadata={'status': order.status},
    )
    return order


def _reserve_stock_fifo(*, order, item, cigar, quantity, operator, context, note=''):
    batches = list(
        PurchaseBatch.objects.select_for_update()
        .filter(cigar=cigar, remaining__gt=0)
        .order_by('purchased_at', 'id')
    )
    available = sum(batch.remaining for batch in batches)
    if available < quantity:
        raise InsufficientStockError(
            f'{cigar.name or cigar.english_name} 现货库存不足',
            details={
                'cigar_id': cigar.id,
                'requested': quantity,
                'available': available,
            },
        )

    remaining_to_allocate = quantity
    item_cost = Decimal('0.00')
    for batch in batches:
        if remaining_to_allocate <= 0:
            break
        take = min(batch.remaining, remaining_to_allocate)
        batch.remaining -= take
        batch.save(update_fields=['remaining'])
        StockAllocation.objects.create(
            sales_order_item=item,
            purchase_batch=batch,
            quantity=take,
            status=StockAllocation.Status.RESERVED,
        )
        _record_movement(
            movement_type=StockMovement.MovementType.RESERVE,
            cigar=cigar,
            purchase_batch=batch,
            sales_order=order,
            sales_order_item=item,
            quantity=take,
            operator=operator,
            context=context,
            note=note,
        )
        item_cost += (batch.unit_cost_cny * take)
        remaining_to_allocate -= take
    return item_cost.quantize(MONEY_PLACES)


def _remove_remaining_cost(batch, quantity):
    """Return exact removed cost, assigning rounding residue to the last unit."""
    if quantity > batch.physical_remaining:
        raise InsufficientStockError('批次物理库存不足')
    if quantity == batch.physical_remaining:
        return batch.remaining_cost_cny
    return (batch.remaining_cost_cny * quantity / batch.physical_remaining).quantize(MONEY_PLACES)

@transaction.atomic
def confirm_payment(*, sales_order_id, operator, agent_context=None, note=''):
    operator = _require_operator(operator)
    context = agent_context or AgentContext(command_name='confirm_payment')
    order = SalesOrder.objects.select_for_update().get(id=_to_positive_int(sales_order_id, '销售单ID'))
    if order.status == 'paid':
        return order
    if order.status == 'cancelled':
        raise OrderServiceError('已取消订单不能确认付款')
    if order.status not in ('pending_payment', 'draft'):
        raise OrderServiceError(f'当前状态不能确认付款: {order.status}')

    now = timezone.now()
    allocations = (
        StockAllocation.objects.select_for_update()
        .filter(sales_order_item__sales_order=order, status=StockAllocation.Status.RESERVED)
        .select_related('purchase_batch', 'sales_order_item__cigar')
        .order_by('purchase_batch_id', 'id')
    )
    for alloc in allocations:
        batch = PurchaseBatch.objects.select_for_update().get(id=alloc.purchase_batch_id)
        cost = _remove_remaining_cost(batch, alloc.quantity)
        batch.physical_remaining -= alloc.quantity
        batch.remaining_cost_cny -= cost
        batch.sold_cost_cny += cost
        batch.save(update_fields=[
            'physical_remaining', 'remaining_cost_cny', 'sold_cost_cny',
        ])
        alloc.status = StockAllocation.Status.FULFILLED
        alloc.fulfilled_at = now
        alloc.save(update_fields=['status', 'fulfilled_at'])
        _record_movement(
            movement_type=StockMovement.MovementType.SHIP,
            cigar=alloc.sales_order_item.cigar,
            purchase_batch=alloc.purchase_batch,
            sales_order=order,
            sales_order_item=alloc.sales_order_item,
            quantity=alloc.quantity,
            operator=operator,
            context=context,
            note=note,
        )

    order.status = 'paid'
    if note:
        order.note = note
    order.save(update_fields=['status', 'note'] if note else ['status'])
    _record_order_event(order, operator=operator, context=context, note=note, metadata={'status': order.status})
    return order


@transaction.atomic
def cancel_sales_order(*, sales_order_id, operator, agent_context=None, note=''):
    operator = _require_operator(operator)
    context = agent_context or AgentContext(command_name='cancel_sales_order')
    order = SalesOrder.objects.select_for_update().get(id=_to_positive_int(sales_order_id, '销售单ID'))
    if order.status == 'cancelled':
        return order
    if order.status == 'paid':
        raise OrderServiceError('已付款订单不能用第一版取消命令自动回滚库存')

    now = timezone.now()
    allocations = (
        StockAllocation.objects.select_for_update()
        .filter(sales_order_item__sales_order=order, status=StockAllocation.Status.RESERVED)
        .select_related('purchase_batch', 'sales_order_item__cigar')
    )
    for alloc in allocations:
        batch = PurchaseBatch.objects.select_for_update().get(id=alloc.purchase_batch_id)
        batch.remaining += alloc.quantity
        batch.save(update_fields=['remaining'])
        alloc.status = StockAllocation.Status.RELEASED
        alloc.released_at = now
        alloc.save(update_fields=['status', 'released_at'])
        _record_movement(
            movement_type=StockMovement.MovementType.RELEASE_RESERVATION,
            cigar=alloc.sales_order_item.cigar,
            purchase_batch=batch,
            sales_order=order,
            sales_order_item=alloc.sales_order_item,
            quantity=alloc.quantity,
            operator=operator,
            context=context,
            note=note,
        )

    order.status = 'cancelled'
    if note:
        order.note = note
    order.save(update_fields=['status', 'note'] if note else ['status'])
    _record_order_event(order, operator=operator, context=context, note=note, metadata={'status': order.status})
    return order


@transaction.atomic
def adjust_stock(*, cigar_id, quantity_delta, operator, reason='', batch_id=None,
                 unit_cost_cny=None, adjustment_type=AdjustmentRecord.AdjustType.LOSS,
                 agent_context=None):
    """Adjust available stock. Negative adjustments never allow stock below zero."""
    operator = _require_operator(operator)
    context = agent_context or AgentContext(command_name='adjust_stock')
    delta = _to_int(quantity_delta, '库存修正数量')
    if delta == 0:
        raise OrderServiceError('库存修正数量不能为 0')
    try:
        cigar = Cigar.objects.get(id=_to_positive_int(cigar_id, '雪茄ID'))
    except Cigar.DoesNotExist:
        raise OrderServiceError('雪茄不存在')

    if delta > 0:
        batch = _get_or_create_adjustment_batch(
            cigar=cigar,
            quantity=delta,
            operator=operator,
            batch_id=batch_id,
            unit_cost_cny=unit_cost_cny,
        )
        batch.quantity += delta
        batch.remaining += delta
        batch.physical_remaining += delta
        batch.remaining_cost_cny += (batch.unit_cost_cny * delta).quantize(MONEY_PLACES)
        batch.save(update_fields=['quantity', 'remaining', 'physical_remaining', 'remaining_cost_cny'])
        _record_movement(
            movement_type=StockMovement.MovementType.ADJUSTMENT,
            cigar=cigar,
            purchase_batch=batch,
            quantity=delta,
            operator=operator,
            context=context,
            note=reason,
        )
        return batch

    quantity_to_remove = abs(delta)
    batches = _adjustment_batches(cigar=cigar, batch_id=batch_id)
    available = sum(batch.remaining for batch in batches)
    if available < quantity_to_remove:
        raise InsufficientStockError(
            f'{cigar.name or cigar.english_name} 可修正库存不足',
            details={'cigar_id': cigar.id, 'requested': quantity_to_remove, 'available': available},
        )

    remaining_to_remove = quantity_to_remove
    last_batch = None
    for batch in batches:
        if remaining_to_remove <= 0:
            break
        take = min(batch.remaining, remaining_to_remove)
        cost = _remove_remaining_cost(batch, take)
        batch.quantity -= take
        batch.remaining -= take
        batch.physical_remaining -= take
        batch.remaining_cost_cny -= cost
        batch.save(update_fields=['quantity', 'remaining', 'physical_remaining', 'remaining_cost_cny'])
        last_batch = batch
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
            operator=operator,
            reason=reason,
        )
        remaining_to_remove -= take
    return last_batch


def _adjustment_batches(*, cigar, batch_id=None):
    qs = PurchaseBatch.objects.select_for_update().filter(cigar=cigar, remaining__gt=0)
    if batch_id:
        qs = qs.filter(id=_to_positive_int(batch_id, '批次ID'))
    batches = list(qs.order_by('purchased_at', 'id'))
    if batch_id and not batches:
        raise OrderServiceError('批次不存在或无可用库存')
    return batches


def _get_or_create_adjustment_batch(*, cigar, quantity, operator, batch_id=None, unit_cost_cny=None):
    if batch_id:
        try:
            return PurchaseBatch.objects.select_for_update().get(
                id=_to_positive_int(batch_id, '批次ID'),
                cigar=cigar,
            )
        except PurchaseBatch.DoesNotExist:
            raise OrderServiceError('批次不存在或不匹配')
    if unit_cost_cny is None:
        raise OrderServiceError('正向库存修正需要 unit_cost_cny')
    unit_cost = _to_signed_money(unit_cost_cny, '成本单价')
    if unit_cost < 0:
        raise OrderServiceError('成本单价不能为负数')
    supplier, _ = Supplier.objects.get_or_create(name='库存修正')
    purchase_order = PurchaseOrder.objects.create(
        supplier=supplier,
        rub_total=Decimal('0.00'),
        exchange_rate=Decimal('1.0000'),
        cny_total=(unit_cost * quantity).quantize(MONEY_PLACES),
        operator=operator,
        status=PurchaseOrder.Status.RECEIVED,
        note='库存修正自动建批次',
    )
    purchase_item = PurchaseOrderItem.objects.create(
        purchase_order=purchase_order,
        cigar=cigar,
        quantity=0,
        box_size=None,
        unit_price_rub=Decimal('0.00'),
        unit_price_cny=unit_cost,
    )
    return PurchaseBatch.objects.create(
        purchase_order_item=purchase_item,
        cigar=cigar,
        quantity=0,
        remaining=0,
        physical_remaining=0,
        remaining_cost_cny=Decimal('0.00'),
        sold_cost_cny=Decimal('0.00'),
        unit_cost_cny=unit_cost,
    )


@transaction.atomic
def receive_purchase_order(*, purchase_order_id, operator, agent_context=None, note=''):
    """Create missing batches for purchase order items and record receive movements."""
    operator = _require_operator(operator)
    context = agent_context or AgentContext(command_name='receive_purchase_order')
    try:
        purchase_order = PurchaseOrder.objects.select_for_update().get(
            id=_to_positive_int(purchase_order_id, '进货单ID')
        )
    except PurchaseOrder.DoesNotExist:
        raise OrderServiceError('进货单不存在')

    if purchase_order.status == PurchaseOrder.Status.RECEIVED:
        raise OrderServiceError('进货单已入库')
    if purchase_order.status == PurchaseOrder.Status.CANCELLED:
        raise OrderServiceError('已取消进货单不能入库')
    if purchase_order.status != PurchaseOrder.Status.DRAFT:
        raise OrderServiceError(f'当前状态不能入库: {purchase_order.status}')

    items = list(purchase_order.items.select_related('cigar').order_by('id'))
    if not items:
        raise OrderServiceError('进货单没有明细')
    if PurchaseBatch.objects.filter(purchase_order_item__purchase_order=purchase_order).exists():
        raise OrderServiceError('进货单已存在入库批次')

    batches = []
    for item in items:
        batch = PurchaseBatch.objects.create(
            purchase_order_item=item,
            cigar=item.cigar,
            quantity=item.quantity,
            remaining=item.quantity,
            physical_remaining=item.quantity,
            remaining_cost_cny=(item.quantity * item.unit_price_cny).quantize(MONEY_PLACES),
            sold_cost_cny=Decimal('0.00'),
            unit_cost_cny=item.unit_price_cny,
        )
        _record_movement(
            movement_type=StockMovement.MovementType.RECEIVE,
            cigar=item.cigar,
            purchase_batch=batch,
            quantity=item.quantity,
            operator=operator,
            context=context,
            note=note,
        )
        batches.append(batch)
    purchase_order.status = PurchaseOrder.Status.RECEIVED
    purchase_order.save(update_fields=['status'])
    return batches


def get_stock_summary(*, query='', limit=50):
    qs = Cigar.objects.all().order_by('brand', 'english_name')
    if query:
        qs = qs.filter(
            Q(brand__icontains=query)
            | Q(english_name__icontains=query)
            | Q(name__icontains=query)
        )
    results = []
    for cigar in qs[:limit]:
        total = PurchaseBatch.objects.filter(cigar=cigar, remaining__gt=0).aggregate(
            total=Sum('remaining')
        )['total'] or 0
        results.append({
            'cigar_id': cigar.id,
            'brand': cigar.brand,
            'name': cigar.name or cigar.english_name,
            'english_name': cigar.english_name,
            'available_stock': total,
        })
    return results
