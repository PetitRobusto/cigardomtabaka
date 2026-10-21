"""采购来源预售、自动预留与直接出库；保留历史备货兼容。"""
from collections import defaultdict
from dataclasses import replace
from datetime import date

from django.db import transaction
from django.db.models import Sum

from accounting.guards import require_day1_completed
from accounting.models import Day1Initialization, LedgerTransaction
from accounting.services import _acquire_sqlite_writer_gate, _retry_sqlite_locked
from .audit import AgentContext
from .models import InventoryAdjustmentLine, OrderEvent, PurchaseBatch, PurchaseOrder, SalesOrder, SalesOrderItem, StockAllocation
from .services import OrderServiceError, _require_operator, _record_order_event


ACTIVE_COMMITMENTS = (SalesOrder.FulfillmentStatus.CONFIRMED, SalesOrder.FulfillmentStatus.SHIPPED)


def item_key(item):
    return (item.cigar_id, item.sale_unit or 'stick', item.box_size if item.sale_unit == 'box' else None)


def purchase_capacity(order, rows=None):
    totals = defaultdict(int)
    if rows is None:
        rows = [dict(cigar_id=i.cigar_id, purchase_unit=i.purchase_unit,
                     box_size=i.box_size, sticks=i.quantity,
                     packaging_status=i.packaging_status) for i in order.items.all()]
    for row in rows:
        if row.get('packaging_status') == 'review_required':
            continue
        unit = row.get('purchase_unit') or 'box'
        size = row.get('box_size') if unit == 'box' else None
        quantity = row.get('sticks') or 0
        if quantity > 0 and (unit == 'stick' or size and quantity % size == 0):
            totals[(row['cigar_id'], unit, size)] += quantity
    return totals


def commitments(order_id, exclude_sales_order_id=None):
    qs = SalesOrderItem.objects.filter(source_purchase_order_id=order_id,
        sales_order__fulfillment_status__in=ACTIVE_COMMITMENTS)
    if exclude_sales_order_id is not None:
        qs = qs.exclude(sales_order_id=exclude_sales_order_id)
    return {(row['cigar_id'], row['sale_unit'], row['box_size']): row['total']
            for row in qs.values('cigar_id', 'sale_unit', 'box_size').annotate(total=Sum('quantity'))}


def lock_sources(items):
    ids = sorted({item.source_purchase_order_id for item in items if item.source_purchase_order_id})
    return {order.pk: order for order in PurchaseOrder.objects.select_for_update().filter(pk__in=ids).order_by('pk')}


def validate_sources(items, *, confirming=False, allow_received=False, sales_order_id=None):
    sources = lock_sources(items)
    requested = defaultdict(lambda: defaultdict(int))
    for item in items:
        if not item.source_purchase_order_id:
            continue
        if item.fulfillment_type != SalesOrderItem.FulfillmentType.PREORDER:
            raise OrderServiceError('只有预售明细可以关联来源采购单')
        source = sources.get(item.source_purchase_order_id)
        allowed = ['draft', 'in_transit'] + (['received'] if allow_received else [])
        if source is None or source.deleted_at is not None or source.status not in allowed:
            raise OrderServiceError('预售来源采购单不存在、已取消或当前不能预售')
        requested[source.pk][item_key(item)] += item.quantity
    for source_id, rows in requested.items():
        capacity = purchase_capacity(sources[source_id])
        used = commitments(source_id, exclude_sales_order_id=sales_order_id) if confirming else {}
        for key, quantity in rows.items():
            if key not in capacity:
                raise OrderServiceError('预售商品、销售单位或盒规与来源采购单不匹配')
            if quantity + used.get(key, 0) > capacity[key]:
                raise OrderServiceError('预售数量超过来源采购单剩余额度', details={
                    'purchase_order_id': source_id, 'cigar_id': key[0],
                    'requested_sticks': quantity, 'available_sticks': max(0, capacity[key] - used.get(key, 0)),
                })
    return sources


def guard_purchase_change(order, *, rows=None, cancelling=False, reversing=False):
    """调用方已经锁定来源采购；不替调用方创建财务或库存事实。"""
    used = commitments(order.pk)
    if cancelling and used:
        raise OrderServiceError('该采购单已有确认预售，请先处理关联销售订单后再取消')
    if reversing and order.preorder_sales_items.filter(
        sales_order__fulfillment_status__in=ACTIVE_COMMITMENTS,
        allocations__status__in=[StockAllocation.Status.RESERVED, StockAllocation.Status.FULFILLED],
    ).exists():
        raise OrderServiceError('关联预售已预留、备货或出库，不能撤销来源采购到货')
    if rows is not None:
        capacity = purchase_capacity(order, rows)
        if any(quantity > capacity.get(key, 0) for key, quantity in used.items()):
            raise OrderServiceError('采购修改不能删除已预售商品、改变其包装或减少至已确认预售数量以下')


def source_options(order):
    capacity = purchase_capacity(order)
    used = commitments(order.pk)
    names = {item.cigar_id: item.cigar.name or item.cigar.english_name
             for item in order.items.select_related('cigar').all()}
    return {
        'purchase_order_id': order.pk, 'order_number': order.order_number, 'status': order.status,
        'can_create': order.deleted_at is None and order.status in ['draft', 'in_transit'],
        'items': [dict(cigar_id=key[0], cigar_name=names[key[0]], sale_unit=key[1], box_size=key[2],
                       purchase_quantity=quantity, committed_quantity=used.get(key, 0),
                       remaining_quantity=max(0, quantity - used.get(key, 0)))
                  for key, quantity in capacity.items()],
    }


def has_reserved_inventory(item):
    allocations = list(item.allocations.all())
    return bool(allocations) and all(a.status in ['reserved', 'fulfilled'] for a in allocations) and sum(a.quantity for a in allocations) == item.quantity


def picking_confirmed(order):
    return order.events.filter(command_name='prepare_sales_preorder').exists()


def reserve_preorders_for_shipment(*, order, items, business_date, operator, context):
    """在出库事务中检查来源和日期，并兼容尚未分配的历史预售。"""
    from . import inventory
    preorders = [item for item in items if item.fulfillment_type == SalesOrderItem.FulfillmentType.PREORDER]
    if not preorders:
        return
    sources = lock_sources(preorders)
    for source in sources.values():
        if source.status != PurchaseOrder.Status.RECEIVED or source.deleted_at is not None:
            raise OrderServiceError('来源采购尚未到货，不能出库')
        arrival = LedgerTransaction.objects.filter(idempotency_key=source.arrival_idempotency_key).first()
        if arrival and business_date < arrival.business_date:
            raise OrderServiceError('出库日期不能早于来源采购到货日期')
    if order.events.filter(command_name='reserve_sales_preorder', metadata__business_date__gt=business_date.isoformat()).exists():
        raise OrderServiceError('出库日期不能早于预售预留日期')
    reserved_ids = []
    reservation_context = replace(context, command_name='reserve_sales_preorder')
    try:
        for item in preorders:
            if has_reserved_inventory(item):
                continue
            if item.allocations.exists():
                raise OrderServiceError('预售库存分配不完整，不能出库')
            inventory.reserve_preorder_item(order=order, item=item, operator=operator,
                context=reservation_context, note='历史预售在出库时补充预留')
            reserved_ids.append(item.pk)
    except inventory.InventoryError as exc:
        raise OrderServiceError(str(exc), details=exc.details) from exc
    batches = PurchaseBatch.objects.filter(stock_allocations__sales_order_item__in=preorders).distinct()
    receipt_keys = batches.exclude(purchase_order_item__isnull=True).values_list(
        'purchase_order_item__purchase_order__arrival_idempotency_key', flat=True)
    if LedgerTransaction.objects.filter(idempotency_key__in=receipt_keys, business_date__gt=business_date).exists():
        raise OrderServiceError('出库日期不能早于实际分配批次的入库日期')
    if InventoryAdjustmentLine.objects.filter(purchase_batch__in=batches, quantity_delta__gt=0,
        action__reversed_at__isnull=True, action__business_date__gt=business_date).exists():
        raise OrderServiceError('出库日期不能早于实际分配批次的库存调增日期')
    if batches.filter(source=PurchaseBatch.Source.OPENING).exists() and Day1Initialization.objects.filter(
        status='completed', business_date__gt=business_date).exists():
        raise OrderServiceError('出库日期不能早于期初库存日期')
    if reserved_ids:
        _record_order_event(order, operator=operator, context=reservation_context,
            note='历史预售在出库时补充预留', metadata={
                'business_date': business_date.isoformat(), 'idempotency_key': context.idempotency_key,
                'item_ids': reserved_ids,
            })


def reserve_arrived_items(*, order, items, business_date, operator, context, note=''):
    """调用方持有全局 writer gate；只预留已到货来源。"""
    from . import inventory
    reserved_ids = []
    reservation_date = business_date
    try:
        for item in items:
            if item.fulfillment_type != SalesOrderItem.FulfillmentType.PREORDER:
                continue
            source = item.source_purchase_order
            if source is None or source.status != PurchaseOrder.Status.RECEIVED:
                continue
            arrival = LedgerTransaction.objects.filter(idempotency_key=source.arrival_idempotency_key).first()
            if arrival:
                reservation_date = max(reservation_date, arrival.business_date)
            if has_reserved_inventory(item):
                continue
            if item.allocations.exists():
                raise OrderServiceError('预售库存分配不完整，不能自动重复预留')
            inventory.reserve_preorder_item(order=order, item=item, operator=operator, context=context, note=note)
            reserved_ids.append(item.pk)
    except inventory.InventoryError as exc:
        raise OrderServiceError(str(exc), details=exc.details) from exc
    if reserved_ids:
        _record_order_event(order, operator=operator, context=context, note=note, metadata={
            'business_date': reservation_date.isoformat(), 'idempotency_key': context.idempotency_key,
            'item_ids': reserved_ids,
        })


def reserve_purchase_preorders(*, purchase_order, business_date, operator, context):
    orders = SalesOrder.objects.select_for_update().filter(
        fulfillment_status=SalesOrder.FulfillmentStatus.CONFIRMED,
        items__source_purchase_order=purchase_order,
    ).distinct().order_by('id')
    for order in orders:
        items = list(order.items.select_for_update().filter(source_purchase_order=purchase_order).select_related('source_purchase_order', 'cigar'))
        reservation_context = replace(context, command_name='reserve_sales_preorder',
            idempotency_key=f'{context.idempotency_key}:preorder:{order.pk}')
        reserve_arrived_items(order=order, items=items, business_date=business_date,
            operator=operator, context=reservation_context, note=f'{purchase_order.order_number} 到货自动预留')


def inventory_preorder_quantities():
    """实际活动预留的预售拆分；不把尚未到货承诺算成在库预留。"""
    rows = list(StockAllocation.objects.filter(status=StockAllocation.Status.RESERVED,
        sales_order_item__fulfillment_type=SalesOrderItem.FulfillmentType.PREORDER,
        sales_order_item__sales_order__fulfillment_status=SalesOrder.FulfillmentStatus.CONFIRMED,
    ).values('sales_order_item__cigar_id', 'sales_order_item__sales_order_id').annotate(quantity=Sum('quantity')))
    picked = set(OrderEvent.objects.filter(command_name='prepare_sales_preorder',
        sales_order_id__in=[row['sales_order_item__sales_order_id'] for row in rows]).values_list('sales_order_id', flat=True))
    totals = defaultdict(lambda: {'preorder_waiting_quantity': 0, 'preorder_prepared_quantity': 0})
    for row in rows:
        field = 'preorder_prepared_quantity' if row['sales_order_item__sales_order_id'] in picked else 'preorder_waiting_quantity'
        totals[row['sales_order_item__cigar_id']][field] += row['quantity']
    return totals


@_retry_sqlite_locked
@transaction.atomic
def prepare_sales_preorder(*, order_id, business_date, operator, idempotency_key, note='', agent_context=None):
    from . import inventory
    _acquire_sqlite_writer_gate()
    operator = _require_operator(operator)
    if isinstance(order_id, str) and len(order_id) <= 19 and order_id.isascii() and order_id.isdigit():
        order_id = int(order_id)
    if type(order_id) is not int or not 0 < order_id <= 9223372036854775807:
        raise OrderServiceError('销售订单编号必须是正整数')
    if type(business_date) is not date or not isinstance(idempotency_key, str) or not idempotency_key.strip():
        raise OrderServiceError('备货必须提供业务日期和幂等键')
    order = SalesOrder.objects.select_for_update().get(pk=order_id)
    previous = order.events.filter(command_name='prepare_sales_preorder', metadata__idempotency_key=idempotency_key).first()
    if previous:
        if previous.operator_id != operator.pk or previous.metadata.get('business_date') != business_date.isoformat() or previous.note != note:
            raise OrderServiceError('备货幂等键已用于不同请求')
        return order
    require_day1_completed()
    if order.fulfillment_status != SalesOrder.FulfillmentStatus.CONFIRMED:
        raise OrderServiceError('只有已确认、尚未出库的销售单可以备货')
    items = list(order.items.select_for_update().filter(fulfillment_type=SalesOrderItem.FulfillmentType.PREORDER).prefetch_related('allocations').order_by('id'))
    if not items:
        raise OrderServiceError('该销售单没有预售明细')
    if picking_confirmed(order):
        raise OrderServiceError('预售商品已经完成备货，请勿重复操作')
    if order.events.filter(command_name='reserve_sales_preorder', metadata__business_date__gt=business_date.isoformat()).exists():
        raise OrderServiceError('备货日期不能早于预售预留日期')
    sources = lock_sources(items)
    for source in sources.values():
        if source.status != PurchaseOrder.Status.RECEIVED or source.deleted_at is not None:
            raise OrderServiceError('来源采购尚未到货，不能备货')
        arrival = LedgerTransaction.objects.filter(idempotency_key=source.arrival_idempotency_key).first()
        if arrival and business_date < arrival.business_date:
            raise OrderServiceError('备货日期不能早于来源采购到货日期')
    context = replace(agent_context or AgentContext(), command_name='prepare_sales_preorder', idempotency_key=idempotency_key)
    try:
        for item in items:
            if has_reserved_inventory(item):
                continue
            if item.allocations.exists():
                raise OrderServiceError('预售库存分配不完整，请先核实，不能重复备货')
            inventory.reserve_preorder_item(order=order, item=item, operator=operator, context=context, note=note)
    except inventory.InventoryError as exc:
        raise OrderServiceError(str(exc), details=exc.details) from exc
    _record_order_event(order, operator=operator, context=context, note=note, metadata={
        'business_date': business_date.isoformat(), 'idempotency_key': idempotency_key,
        'item_ids': [item.pk for item in items],
    })
    return order
