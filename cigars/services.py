"""订单与库存写服务。

库存变动统一由本模块处理；PurchaseBatch.remaining 是库存流水支撑的读模型。
"""
from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import hashlib
import json

from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone
from uuid import uuid4
from accounting.business_time import moscow_business_date

from accounting.mutation_scope import ledger_mutation_scope
from accounting.guards import require_day1_completed
from accounting.models import LedgerPosting, LedgerTransaction
from accounting.services import (
    LedgerError, PostingInput, _acquire_sqlite_writer_gate, _post_transaction_once,
    _retry_sqlite_locked, reverse_ledger_transaction,
)

from .audit import AgentContext
from . import inventory as inventory_module
from .models import (
    AdjustmentRecord,
    Cigar,
    Customer,
    InventoryAdjustmentAction,
    InventoryAdjustmentLine,
    OrderEvent,
    PurchaseBatch,
    SalesShipment,
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

    def __init__(self, message, *, details=None, code=None):
        super().__init__(message)
        self.details = details or {}
        self.code = code


class InsufficientStockError(OrderServiceError):
    """Raised when an in-stock sale or adjustment would make stock negative."""




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


def _sales_event_metadata(order, business_date=None):
    # 双状态和业务日期共同构成销售命令的审计快照。
    if business_date is not None and type(business_date) is not date:
        raise OrderServiceError('业务日期必须是 date')
    metadata = {
        'fulfillment_status': order.fulfillment_status,
        'payment_status': order.payment_status,
    }
    if business_date is not None:
        metadata['business_date'] = business_date.isoformat()
    return metadata


def serialize_sales_order(order):
    items = []
    if hasattr(order, '_prefetched_objects_cache') and 'items' in order._prefetched_objects_cache:
        order_items = order._prefetched_objects_cache['items']
    else:
        order_items = order.items.select_related('cigar').prefetch_related('allocations__purchase_batch').all()
    for item in order_items:
        if hasattr(item, '_prefetched_objects_cache') and 'allocations' in item._prefetched_objects_cache:
            item_allocations = item._prefetched_objects_cache['allocations']
        else:
            item_allocations = item.allocations.all()
        allocations = [
            {
                'id': alloc.id,
                'batch_id': alloc.purchase_batch_id,
                'quantity': alloc.quantity,
                'status': alloc.status,
                'unit_cost_cny': _decimal_to_json(alloc.purchase_batch.unit_cost_cny),
                'cost_cny': _decimal_to_json(
                    alloc.fulfilled_cost_cny
                    if alloc.fulfilled_cost_cny is not None
                    else alloc.purchase_batch.unit_cost_cny * alloc.quantity
                ),
            }
            for alloc in item_allocations
        ]
        items.append({
            'id': item.id,
            'cigar_id': item.cigar_id,
            'cigar_name': item.cigar.name or item.cigar.english_name,
            'quantity': item.quantity,
            'sale_unit': item.sale_unit,
            'sale_quantity': item.sale_quantity,
            'box_size': item.box_size,
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
        'display_status': order.display_status,
        'fulfillment_status': order.fulfillment_status,
        'payment_status': order.payment_status,
        'customer_id': order.customer_id,
        'customer_name': order.customer_name,
        'customer': ({
            'id': order.customer_id,
            'name': order.customer.name,
            'phone': order.customer.phone,
            'deleted_at': order.customer.deleted_at.isoformat() if order.customer.deleted_at else None,
        } if getattr(order, 'customer', None) is not None else None),
        'goods_amount_cny': _decimal_to_json(order.goods_amount_cny),
        'customer_transport_fee_cny': _decimal_to_json(order.customer_transport_fee_cny),
        'transport_payer': order.transport_payer,
        'amount_due_cny': _decimal_to_json(order.amount_due_cny),
        'total_revenue': _decimal_to_json(order.total_revenue),
        'total_cost': _decimal_to_json(order.total_cost),
        'total_profit': _decimal_to_json(order.total_profit),
        'fifo_cost': _decimal_to_json(order.fifo_cost_cny),
        'contribution_profit': _decimal_to_json(order.contribution_profit_cny),
        'actual_transport_cost_cny': _decimal_to_json(order.actual_transport_cost_cny),
        'locked': order.locked,
        'created_at': order.created_at.isoformat() if order.created_at else None,
        'confirmed_at': order.confirmed_at.isoformat() if order.confirmed_at else None,
        'cancelled_at': order.cancelled_at.isoformat() if order.cancelled_at else None,
        'note': order.note,
        'items': items,
        'sales_shipment': ({
            'id': order.sales_shipment.id,
            'business_date': order.sales_shipment.business_date.isoformat(),
            'fifo_cost_cny': _decimal_to_json(order.sales_shipment.fifo_cost_cny),
        } if hasattr(order, 'sales_shipment') else None),
        'sales_receipt': ({
            'id': order.sales_receipt.id,
            'amount_cny': _decimal_to_json(order.sales_receipt.amount_cny),
            'business_date': order.sales_receipt.business_date.isoformat(),
            'fund_account_id': order.sales_receipt.fund_account_id,
        } if hasattr(order, 'sales_receipt') else None),
        'sales_refund': ({
            'id': order.sales_refund.id,
            'amount_cny': _decimal_to_json(order.sales_refund.amount_cny),
            'business_date': order.sales_refund.business_date.isoformat(),
            'fund_account_id': order.sales_refund.fund_account_id,
        } if hasattr(order, 'sales_refund') else None),
        'sales_return': ({
            'id': order.sales_return.id,
            'amount_cny': _decimal_to_json(order.sales_return.amount_cny),
            'fifo_cost_cny': _decimal_to_json(order.sales_return.fifo_cost_cny),
            'business_date': order.sales_return.business_date.isoformat(),
            'reason': order.sales_return.reason,
        } if hasattr(order, 'sales_return') else None),
        'sales_transport_cost': ({
            'id': order.sales_transport_cost.id,
            'actual_cost_cny': _decimal_to_json(order.sales_transport_cost.actual_cost_cny),
            'business_date': order.sales_transport_cost.business_date.isoformat(),
            'fund_account_id': order.sales_transport_cost.fund_account_id,
        } if hasattr(order, 'sales_transport_cost') else None),
        'available_actions': _sales_order_available_actions(order),
    }


def _sales_order_available_actions(order):
    actions = []
    if order.fulfillment_status == SalesOrder.FulfillmentStatus.DRAFT:
        actions.extend(['confirm', 'cancel'])
    if order.fulfillment_status == SalesOrder.FulfillmentStatus.CONFIRMED:
        actions.extend(['ship', 'cancel'])
        if order.payment_status == SalesOrder.PaymentStatus.UNPAID:
            actions.append('receive')
    if order.fulfillment_status == SalesOrder.FulfillmentStatus.SHIPPED:
        actions.append('return')
        if order.payment_status == SalesOrder.PaymentStatus.UNPAID:
            actions.append('receive')
        if not hasattr(order, 'sales_transport_cost'):
            actions.append('transport_cost')
    if order.fulfillment_status == SalesOrder.FulfillmentStatus.CANCELLED and order.payment_status == SalesOrder.PaymentStatus.REFUND_PENDING:
        actions.append('refund')
    if order.fulfillment_status == SalesOrder.FulfillmentStatus.RETURNED:
        if order.payment_status == SalesOrder.PaymentStatus.REFUND_PENDING:
            actions.append('refund')
        if not hasattr(order, 'sales_transport_cost'):
            actions.append('transport_cost')
    return actions

def _decimal_to_json(value):
    if value is None:
        return None
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
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
            'sticks': item.quantity,
            'box_size': item.box_size,
            'box_quantity': item.box_quantity,
            'unit_price_rub_per_box': _decimal_to_json(item.unit_price_rub_per_box),
            'rub_subtotal': _decimal_to_json(
                (Decimal(item.box_quantity) * item.unit_price_rub_per_box)
                if item.box_quantity is not None and item.unit_price_rub_per_box is not None else None
            ),
            'packaging_status': item.packaging_status,
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
        'version': order.version,
        'business_date': order.draft_business_date.isoformat() if order.draft_business_date else None,
        'items': items,
    }


def _get_customer(raw_customer_id):
    if not raw_customer_id:
        return None
    customer_id = _to_positive_int(raw_customer_id, '客户ID')
    try:
        return Customer.objects.get(id=customer_id, deleted_at__isnull=True)
    except Customer.DoesNotExist:
        raise OrderServiceError('客户不存在')


def _transport_payer(raw_payer, customer_fee):
    """Validate explicit payers and infer omitted values for legacy clients."""
    if raw_payer in (None, ""):
        # 旧客户端没有承担方字段，按原有收费数据无损推断。
        return (
            SalesOrder.TransportPayer.CUSTOMER
            if customer_fee > 0 else SalesOrder.TransportPayer.COMPANY
        )
    payer = str(raw_payer).strip()
    if payer not in SalesOrder.TransportPayer.values:
        raise OrderServiceError("人肉费承担方无效")
    if payer == SalesOrder.TransportPayer.COMPANY and customer_fee != 0:
        raise OrderServiceError("公司承担人肉费时客户收费必须为零")
    return payer


@transaction.atomic
def create_sales_order_draft(*, items, operator, customer=None, customer_id=None,
                             customer_name="", payment_method_id=None,
                             payment_manual=None, customer_transport_fee_cny=0,
                             transport_payer=None, note="", agent_context=None, business_date=None):
    """创建可编辑的销售草稿，不预留库存。"""
    operator = _require_operator(operator)
    context = agent_context or AgentContext(command_name="create_sales_order_draft")
    if not isinstance(items, list) or not items:
        raise OrderServiceError("至少需要一个商品")

    customer_obj = customer or _get_customer(customer_id)
    if customer_obj and not customer_name:
        customer_name = customer_obj.name
    transport_fee = _to_money(customer_transport_fee_cny, "客户人肉费")
    selected_transport_payer = _transport_payer(transport_payer, transport_fee)
    selected_payment_method_id = (
        _to_positive_int(payment_method_id, "收款方式ID")
        if payment_method_id not in (None, "") else None
    )
    order = SalesOrder.objects.create(
        customer=customer_obj,
        customer_name=customer_name or "",
        operator=operator,
        fulfillment_status=SalesOrder.FulfillmentStatus.DRAFT,
        payment_status=SalesOrder.PaymentStatus.UNPAID,
        status="draft",
        locked=False,
        note=note or "",
        payment_method_id=selected_payment_method_id,
        payment_manual=payment_manual or {},
    )

    goods_amount = Decimal("0.00")
    for idx, raw_item in enumerate(items, start=1):
        if not isinstance(raw_item, dict):
            raise OrderServiceError(f"第{idx}个商品格式错误")
        try:
            cigar = Cigar.objects.get(id=_to_positive_int(raw_item.get("cigar_id"), f"第{idx}个商品ID"))
        except Cigar.DoesNotExist:
            raise OrderServiceError(f"第{idx}个商品不存在")
        fulfillment_type = str(raw_item.get("fulfillment_type") or SalesOrderItem.FulfillmentType.IN_STOCK)
        if fulfillment_type not in SalesOrderItem.FulfillmentType.values:
            raise OrderServiceError(f"第{idx}个商品履约类型错误")
        sale_unit = str(raw_item.get("sale_unit") or SalesOrderItem.SaleUnit.STICK)
        if sale_unit not in SalesOrderItem.SaleUnit.values:
            raise OrderServiceError(f"第{idx}个商品销售单位错误")
        sale_unit_price = _to_money(raw_item.get("unit_price"), f"第{idx}个商品单价")
        if sale_unit == SalesOrderItem.SaleUnit.BOX:
            sale_quantity = _to_positive_int(raw_item.get("sale_quantity"), f"第{idx}个商品销售盒数")
            box_size = _to_positive_int(raw_item.get("box_size"), f"第{idx}个商品包装支数")
            quantity = sale_quantity * box_size
            if raw_item.get("quantity") not in (None, "") and _to_positive_int(raw_item.get("quantity"), f"第{idx}个商品数量") != quantity:
                raise OrderServiceError(f"第{idx}个商品盒装数量与包装快照不一致")
        else:
            quantity = _to_positive_int(raw_item.get("quantity"), f"第{idx}个商品数量")
            sale_quantity = quantity
            box_size = None
        revenue = (sale_unit_price * sale_quantity).quantize(MONEY_PLACES)
        SalesOrderItem.objects.create(
            sales_order=order, cigar=cigar, quantity=quantity,
            unit_price=sale_unit_price,
            unit_cost=Decimal("0.00"), revenue=revenue, cost=Decimal("0.00"), profit=Decimal("0.00"),
            fulfillment_type=fulfillment_type, sale_unit=sale_unit,
            sale_quantity=sale_quantity, box_size=box_size,
        )
        goods_amount += revenue

    goods_amount = goods_amount.quantize(MONEY_PLACES)
    order.goods_amount_cny = goods_amount
    order.customer_transport_fee_cny = transport_fee
    order.transport_payer = selected_transport_payer
    order.amount_due_cny = (goods_amount + transport_fee).quantize(MONEY_PLACES)
    order.total_revenue = goods_amount
    order.total_cost = Decimal("0.00")
    order.total_profit = Decimal("0.00")
    order.fifo_cost_cny = Decimal("0.00")
    order.contribution_profit_cny = Decimal("0.00")
    order.save(update_fields=[
        "goods_amount_cny", "customer_transport_fee_cny", "transport_payer",
        "amount_due_cny",
        "total_revenue", "total_cost", "total_profit", "fifo_cost_cny",
        "contribution_profit_cny",
    ])
    _record_order_event(
        order, operator=operator, context=context, note=note,
        metadata=_sales_event_metadata(order, business_date),
    )
    return order


@transaction.atomic
def update_sales_order_draft(*, sales_order_id, items, operator, customer=None, customer_id=None,
                             customer_name="", payment_method_id=None, payment_manual=None,
                             customer_transport_fee_cny=0, transport_payer=None,
                             note="", agent_context=None, business_date=None):
    """整体替换未锁定、未收款草稿的业务快照。"""
    operator = _require_operator(operator)
    context = agent_context or AgentContext(command_name="update_sales_order_draft")
    order = SalesOrder.objects.select_for_update().get(id=_to_positive_int(sales_order_id, "销售单ID"))
    if (order.fulfillment_status != SalesOrder.FulfillmentStatus.DRAFT or
            order.payment_status != SalesOrder.PaymentStatus.UNPAID or order.locked):
        raise OrderServiceError("当前订单不能编辑草稿")
    if StockAllocation.objects.filter(sales_order_item__sales_order=order).exists():
        raise OrderServiceError("存在库存分配的订单不能编辑草稿")
    if not isinstance(items, list) or not items:
        raise OrderServiceError("至少需要一个商品")
    transport_fee = _to_money(customer_transport_fee_cny, "客户人肉费")
    selected_transport_payer = _transport_payer(transport_payer, transport_fee)

    snapshots = []
    for idx, raw_item in enumerate(items, start=1):
        if not isinstance(raw_item, dict):
            raise OrderServiceError(f"第{idx}个商品格式错误")
        try:
            cigar = Cigar.objects.get(id=_to_positive_int(raw_item.get("cigar_id"), f"第{idx}个商品ID"))
        except Cigar.DoesNotExist:
            raise OrderServiceError(f"第{idx}个商品不存在")
        fulfillment_type = str(raw_item.get("fulfillment_type") or SalesOrderItem.FulfillmentType.IN_STOCK)
        if fulfillment_type not in SalesOrderItem.FulfillmentType.values:
            raise OrderServiceError(f"第{idx}个商品履约类型错误")
        sale_unit = str(raw_item.get("sale_unit") or SalesOrderItem.SaleUnit.STICK)
        if sale_unit not in SalesOrderItem.SaleUnit.values:
            raise OrderServiceError(f"第{idx}个商品销售单位错误")
        sale_unit_price = _to_money(raw_item.get("unit_price"), f"第{idx}个商品单价")
        if sale_unit == SalesOrderItem.SaleUnit.BOX:
            sale_quantity = _to_positive_int(raw_item.get("sale_quantity"), f"第{idx}个商品销售盒数")
            box_size = _to_positive_int(raw_item.get("box_size"), f"第{idx}个商品包装支数")
            quantity = sale_quantity * box_size
            if raw_item.get("quantity") not in (None, "") and _to_positive_int(raw_item.get("quantity"), f"第{idx}个商品数量") != quantity:
                raise OrderServiceError(f"第{idx}个商品盒装数量与包装快照不一致")
        else:
            quantity = _to_positive_int(raw_item.get("quantity"), f"第{idx}个商品数量")
            sale_quantity, box_size = quantity, None
        revenue = (sale_unit_price * sale_quantity).quantize(MONEY_PLACES)
        snapshots.append((cigar, quantity, sale_unit, sale_quantity, box_size, sale_unit_price, revenue, fulfillment_type))

    customer_obj = customer or _get_customer(customer_id)
    if customer_obj and not customer_name:
        customer_name = customer_obj.name
    order.items.all().delete()
    goods_amount = Decimal("0.00")
    for cigar, quantity, sale_unit, sale_quantity, box_size, sale_unit_price, revenue, fulfillment_type in snapshots:
        SalesOrderItem.objects.create(
            sales_order=order, cigar=cigar, quantity=quantity,
            unit_price=sale_unit_price,
            unit_cost=Decimal("0.00"), revenue=revenue, cost=Decimal("0.00"), profit=Decimal("0.00"),
            fulfillment_type=fulfillment_type, sale_unit=sale_unit, sale_quantity=sale_quantity, box_size=box_size,
        )
        goods_amount += revenue
    order.customer, order.customer_name = customer_obj, customer_name or ""
    order.payment_method_id = _to_positive_int(payment_method_id, "收款方式ID") if payment_method_id not in (None, "") else None
    order.payment_manual, order.note = payment_manual or {}, note or ""
    order.goods_amount_cny = goods_amount.quantize(MONEY_PLACES)
    order.customer_transport_fee_cny = transport_fee
    order.transport_payer = selected_transport_payer
    order.amount_due_cny = (order.goods_amount_cny + order.customer_transport_fee_cny).quantize(MONEY_PLACES)
    order.total_revenue, order.total_cost = order.goods_amount_cny, Decimal("0.00")
    order.total_profit, order.fifo_cost_cny, order.contribution_profit_cny = Decimal("0.00"), Decimal("0.00"), Decimal("0.00")
    order.save()
    _record_order_event(order, operator=operator, context=context, note=note, metadata=_sales_event_metadata(order, business_date))
    return order




def _reserve_box_stock_fifo(*, order, item, operator, context, note=''):
    try:
        return inventory_module.reserve_order_item(
            order=order, item=item, operator=operator, context=context, note=note,
        )
    except inventory_module.InventoryInsufficientError as error:
        raise InsufficientStockError(str(error), details=error.details) from error
    except inventory_module.InventoryError as error:
        raise OrderServiceError(str(error), details=error.details) from error


@_retry_sqlite_locked
@transaction.atomic
def confirm_sales_order(*, sales_order_id, operator, agent_context=None, note="",
                        business_date=None):
    """确认未收款草稿，并预留其中的现货库存。"""
    operator = _require_operator(operator)
    context = agent_context or AgentContext(command_name="confirm_sales_order")
    require_day1_completed()
    _acquire_sqlite_writer_gate()
    order = SalesOrder.objects.select_for_update().get(id=_to_positive_int(sales_order_id, "销售单ID"))
    if (order.fulfillment_status != SalesOrder.FulfillmentStatus.DRAFT or
            order.payment_status != SalesOrder.PaymentStatus.UNPAID):
        raise OrderServiceError("当前订单不能确认")
    total_cost = Decimal("0.00")
    for item in order.items.select_for_update().select_related("cigar").order_by("id"):
        if item.fulfillment_type == SalesOrderItem.FulfillmentType.PREORDER:
            item_cost = Decimal("0.00")
        elif item.sale_unit == SalesOrderItem.SaleUnit.BOX:
            item_cost = _reserve_box_stock_fifo(order=order, item=item, operator=operator, context=context, note=note)
        else:
            item_cost = _reserve_stock_fifo(
                order=order, item=item, cigar=item.cigar, quantity=item.quantity,
                operator=operator, context=context, note=note,
            )
        item.cost = Decimal("0.00")
        item.unit_cost = Decimal("0.00")
        item.profit = Decimal("0.00")
        item.save(update_fields=["cost", "unit_cost", "profit"])
    now = timezone.now()
    order.total_cost = Decimal("0.00")
    order.total_profit = Decimal("0.00")
    order.fulfillment_status = SalesOrder.FulfillmentStatus.CONFIRMED
    order.status = "pending_payment"
    order.confirmed_at = now
    order.locked, order.locked_by, order.locked_at = True, operator, now
    if note:
        order.note = note
    order.save()
    _record_order_event(order, operator=operator, context=context, note=note, metadata=_sales_event_metadata(order, business_date))
    return order


@_retry_sqlite_locked
@transaction.atomic
def cancel_confirmed_sales_order(*, sales_order_id, operator, agent_context=None, note="",
                                 business_date=None):
    """取消草稿或未出库的已确认订单；已确认订单同时释放预留。"""
    operator = _require_operator(operator)
    context = agent_context or AgentContext(command_name="cancel_confirmed_sales_order")
    _acquire_sqlite_writer_gate()
    order = SalesOrder.objects.select_for_update().get(id=_to_positive_int(sales_order_id, "销售单ID"))
    if order.fulfillment_status == SalesOrder.FulfillmentStatus.DRAFT:
        if order.payment_status != SalesOrder.PaymentStatus.UNPAID or order.locked:
            raise OrderServiceError("当前订单不能取消")
        if StockAllocation.objects.filter(sales_order_item__sales_order=order).exists():
            raise OrderServiceError("存在库存分配的草稿不能取消")
        now = timezone.now()
        order.fulfillment_status = SalesOrder.FulfillmentStatus.CANCELLED
        order.status, order.cancelled_at = "cancelled", now
        order.locked, order.locked_by, order.locked_at = True, operator, now
        if note:
            order.note = note
        order.save()
        _record_order_event(order, operator=operator, context=context, note=note, metadata=_sales_event_metadata(order, business_date))
        return order
    require_day1_completed()
    if order.fulfillment_status != SalesOrder.FulfillmentStatus.CONFIRMED:
        raise OrderServiceError("当前订单不能取消")
    if order.payment_status not in (SalesOrder.PaymentStatus.UNPAID, SalesOrder.PaymentStatus.PAID):
        raise OrderServiceError("当前付款状态不能取消")
    if StockAllocation.objects.filter(
        sales_order_item__sales_order=order,
        status=StockAllocation.Status.FULFILLED,
    ).exists():
        raise OrderServiceError("已出库订单不能取消")
    if SalesShipment.objects.filter(sales_order=order).exists():
        raise OrderServiceError("已出库订单不能取消")
    now = timezone.now()
    try:
        inventory_module.release_order(
            order=order, operator=operator, context=context, note=note,
        )
    except inventory_module.InventoryError as error:
        raise OrderServiceError(str(error), details=error.details) from error
    order.fulfillment_status = SalesOrder.FulfillmentStatus.CANCELLED
    order.payment_status = (SalesOrder.PaymentStatus.REFUND_PENDING if order.payment_status == SalesOrder.PaymentStatus.PAID else SalesOrder.PaymentStatus.UNPAID)
    order.status, order.cancelled_at = "cancelled", now
    if note:
        order.note = note
    order.save()
    _record_order_event(order, operator=operator, context=context, note=note, metadata=_sales_event_metadata(order, business_date))
    return order


@_retry_sqlite_locked
@transaction.atomic
def split_purchase_batch_box(*, batch_id, operator, agent_context=None, note=''):
    """把一个可用完整盒拆成同批次散支。"""
    operator = _require_operator(operator)
    context = agent_context or AgentContext(command_name='split_purchase_batch_box')
    require_day1_completed()
    _acquire_sqlite_writer_gate()
    try:
        return inventory_module.split_box(
            batch_id=_to_positive_int(batch_id, '批次ID'),
            operator=operator,
            context=context,
            note=note,
        )
    except inventory_module.InventoryError as error:
        raise OrderServiceError(str(error), details=error.details) from error


def create_purchase_order(*, supplier_id, items, business_date=None, operator,
                          idempotency_key=None, expected_version=None, note='',
                          exchange_rate=None, agent_context=None):
    from accounting.purchase_actions import (
        PurchaseActionError, create_purchase_order as create_draft,
        normalize_legacy_purchase_item,
    )
    if not idempotency_key:
        # 仅兼容旧内部调用；canonical/API 仍必须显式提供 key/date。
        idempotency_key = (
            getattr(agent_context, 'idempotency_key', None)
            or f'legacy-purchase-{uuid4().hex}'
        )
        if business_date is None:
            business_date = moscow_business_date()
    elif business_date is None:
        raise PurchaseActionError('invalid_business_date', {'business_date': '必须显式提供'})
    normalized_items = []
    legacy_input = False
    for index, raw in enumerate(items or []):
        if not isinstance(raw, dict):
            raise PurchaseActionError('invalid_items', {'item_index': index})
        if 'box_quantity' in raw or 'unit_price_rub_per_box' in raw:
            normalized_items.append(raw)
        else:
            legacy_input = True
            legacy_cny = raw.get('unit_price_cny')
            if legacy_cny in (None, '') and exchange_rate not in (None, ''):
                try:
                    legacy_cny = Decimal(str(raw.get('unit_price_rub'))) * Decimal(str(exchange_rate))
                except (InvalidOperation, TypeError, ValueError):
                    raise PurchaseActionError('invalid_exchange_rate')
            normalized_items.append(
                normalize_legacy_purchase_item(
                    box_size=raw.get('box_size'),
                    quantity_sticks=raw.get('quantity'),
                    unit_price_rub_per_stick=raw.get('unit_price_rub'),
                    unit_price_cny_per_stick=legacy_cny,
                ) | {'cigar_id': raw.get('cigar_id')}
            )
    try:
        order = create_draft(
            supplier_id=supplier_id, items=normalized_items, business_date=business_date,
            operator=operator, idempotency_key=idempotency_key,
            expected_version=expected_version, note=note, exchange_rate=exchange_rate,
        )
    except PurchaseActionError as error:
        if legacy_input:
            if error.code == 'supplier_not_found':
                raise OrderServiceError('供应商不存在', details=error.details)
            if error.code == 'cigar_not_found':
                index = error.details.get('item_index', 0) + 1
                raise OrderServiceError(f'第{index}个采购明细雪茄不存在', details=error.details)
            raise OrderServiceError(error.code, details=error.details)
        raise
    return order


@_retry_sqlite_locked
@transaction.atomic
def create_sales_order(*, items, operator, customer=None, customer_id=None,
                       customer_name='', payment_method_id=None, payment_manual=None,
                       customer_transport_fee_cny=0, transport_payer=None, note='', agent_context=None):
    """Create a pending sales order and reserve in-stock items FIFO."""
    operator = _require_operator(operator)
    context = agent_context or AgentContext(command_name='create_sales_order')
    require_day1_completed()
    _acquire_sqlite_writer_gate()
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
    transport_fee = _to_money(customer_transport_fee_cny, '客户人肉费')
    selected_transport_payer = _transport_payer(transport_payer, transport_fee)

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

        revenue = (unit_price * sale_quantity).quantize(MONEY_PLACES)
        item = SalesOrderItem.objects.create(
            sales_order=order,
            cigar=cigar,
            quantity=quantity,
            unit_price=unit_price,
            unit_cost=Decimal('0.00'),
            revenue=revenue,
            cost=Decimal('0.00'),
            profit=Decimal('0.00'),
            fulfillment_type=fulfillment_type,
            sale_unit=sale_unit,
            sale_quantity=sale_quantity,
            box_size=box_size,
        )

        if fulfillment_type == SalesOrderItem.FulfillmentType.IN_STOCK:
            if sale_unit == SalesOrderItem.SaleUnit.BOX:
                _reserve_box_stock_fifo(
                    order=order, item=item, operator=operator, context=context, note=note,
                )
            else:
                _reserve_stock_fifo(
                    order=order, item=item, cigar=cigar, quantity=quantity,
                    operator=operator, context=context, note=note,
                )

        item.unit_cost = Decimal('0.00')
        item.cost = Decimal('0.00')
        item.profit = Decimal('0.00')
        item.save(update_fields=['unit_cost', 'cost', 'profit'])

        total_revenue += revenue
        total_cost += item.cost

    order.total_revenue = total_revenue.quantize(MONEY_PLACES)
    order.fulfillment_status = SalesOrder.FulfillmentStatus.CONFIRMED
    order.payment_status = SalesOrder.PaymentStatus.UNPAID
    order.locked = True
    order.locked_by = operator
    order.confirmed_at = timezone.now()
    order.total_cost = total_cost.quantize(MONEY_PLACES)
    order.total_profit = Decimal('0.00')
    order.goods_amount_cny = order.total_revenue
    order.customer_transport_fee_cny = transport_fee
    order.transport_payer = selected_transport_payer
    order.amount_due_cny = (order.total_revenue + transport_fee).quantize(MONEY_PLACES)
    order.save(update_fields=['total_revenue', 'total_cost', 'total_profit', 'goods_amount_cny', 'customer_transport_fee_cny', 'transport_payer', 'amount_due_cny', 'fulfillment_status', 'payment_status', 'locked', 'locked_by', 'confirmed_at'])

    _record_order_event(
        order,
        operator=operator,
        context=context,
        note=note,
        metadata={'status': order.status},
    )
    return order


def _reserve_stock_fifo(*, order, item, cigar, quantity, operator, context, note=''):
    # 保留旧内部签名，库存事实统一由库存 Module 写入。
    try:
        return inventory_module.reserve_order_item(
            order=order, item=item, operator=operator, context=context, note=note,
        )
    except inventory_module.InventoryInsufficientError as error:
        raise InsufficientStockError(str(error), details=error.details) from error
    except inventory_module.InventoryError as error:
        raise OrderServiceError(str(error), details=error.details) from error

@transaction.atomic
def confirm_payment(*, sales_order_id, operator, agent_context=None, note=''):
    """Disabled legacy shortcut; receipt and shipment are independent facts."""
    _require_operator(operator)
    SalesOrder.objects.get(id=_to_positive_int(sales_order_id, '销售单ID'))
    raise OrderServiceError('confirm_payment 已停用；请使用独立的收款与出库服务')


@_retry_sqlite_locked
@transaction.atomic
def cancel_sales_order(*, sales_order_id, operator, agent_context=None, note=''):
    operator = _require_operator(operator)
    context = agent_context or AgentContext(command_name='cancel_sales_order')
    require_day1_completed()
    _acquire_sqlite_writer_gate()
    order = SalesOrder.objects.select_for_update().get(id=_to_positive_int(sales_order_id, '销售单ID'))
    if order.status == 'cancelled':
        return order
    if order.status == 'paid':
        raise OrderServiceError('已付款订单不能用第一版取消命令自动回滚库存')
    if order.fulfillment_status != SalesOrder.FulfillmentStatus.CONFIRMED:
        raise OrderServiceError('当前订单不能取消')
    if order.payment_status != SalesOrder.PaymentStatus.UNPAID:
        raise OrderServiceError('当前付款状态不能取消')
    if StockAllocation.objects.filter(
        sales_order_item__sales_order=order,
        status=StockAllocation.Status.FULFILLED,
    ).exists():
        raise OrderServiceError('已出库订单不能取消')
    if SalesShipment.objects.filter(sales_order=order).exists():
        raise OrderServiceError('已出库订单不能取消')

    try:
        inventory_module.release_order(
            order=order, operator=operator, context=context, note=note,
        )
    except inventory_module.InventoryError as error:
        raise OrderServiceError(str(error), details=error.details) from error

    order.status = 'cancelled'
    order.fulfillment_status = SalesOrder.FulfillmentStatus.CANCELLED
    if note:
        order.note = note
    order.save(update_fields=['status', 'fulfillment_status', 'note'] if note else ['status', 'fulfillment_status'])
    _record_order_event(order, operator=operator, context=context, note=note, metadata={'status': order.status})
    return order


def _post_stock_adjustment(*, cost_cny, gain, business_date, operator, context, reason, source_id):
    """库存调整统一写资产与当期调整损益，和库存事实处于同一事务。"""
    if not context.idempotency_key:
        raise OrderServiceError('库存调整必须提供幂等键')
    amount = Decimal(cost_cny).quantize(MONEY_PLACES)
    category = (LedgerPosting.Category.INVENTORY_ADJUSTMENT_GAIN
                if gain else LedgerPosting.Category.INVENTORY_ADJUSTMENT_LOSS)
    postings = [
        PostingInput(category=LedgerPosting.Category.INVENTORY, currency='CNY',
                     amount=amount if gain else -amount,
                     cny_amount=amount if gain else -amount),
        PostingInput(category=category, currency='CNY', amount=-amount if gain else amount,
                     cny_amount=-amount if gain else amount),
    ]
    return _post_transaction_once(
        transaction_type=LedgerTransaction.TransactionType.INVENTORY_ADJUSTMENT,
        business_date=business_date, postings=postings, operator=operator,
        idempotency_key=context.idempotency_key, description=reason,
        source_type='stock_adjustment', source_id=source_id,
    )


@_retry_sqlite_locked
@transaction.atomic
def adjust_stock(*, cigar_id, quantity_delta, operator, reason='', batch_id=None,
                 unit_cost_cny=None, adjustment_type=AdjustmentRecord.AdjustType.LOSS, inventory_form='stick',
                 business_date=None, agent_context=None):
    """调整可用库存；负向调整不得形成负库存。"""
    operator = _require_operator(operator)
    context = agent_context or AgentContext(command_name='adjust_stock')
    reason = str(reason or '').strip()
    if not reason:
        raise OrderServiceError('库存调整原因不能为空')
    require_day1_completed()
    business_date = business_date or moscow_business_date()
    delta = _to_int(quantity_delta, '库存修正数量')
    cigar_id_for_source = _to_positive_int(cigar_id, '雪茄ID')
    batch_id_for_source = (
        None if batch_id in (None, '') else _to_positive_int(batch_id, '批次ID')
    )
    # 幂等指纹使用排序 JSON 和两位小数规范化，避免请求格式差异产生不同来源。
    if unit_cost_cny is None:
        fingerprint_cost = None
    else:
        try:
            normalized_cost = Decimal(str(unit_cost_cny)).quantize(
                MONEY_PLACES, rounding=ROUND_HALF_UP,
            )
            fingerprint_cost = normalized_cost.to_eng_string()
        except (InvalidOperation, TypeError, ValueError):
            fingerprint_cost = str(unit_cost_cny)
    fingerprint_payload = {
        'cigar_id': cigar_id_for_source,
        'batch_id': batch_id_for_source,
        'delta': delta,
        'inventory_form': str(inventory_form),
        'adjustment_type': str(adjustment_type),
        'unit_cost_cny': fingerprint_cost,
    }
    request_fingerprint = hashlib.sha256(json.dumps(
        fingerprint_payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
    ).encode('utf-8')).hexdigest()
    # 先升级统一 writer gate，再查询幂等事实，避免并发请求同时通过空检查。
    _acquire_sqlite_writer_gate()
    if context.idempotency_key:
        existing = LedgerTransaction.objects.filter(
            idempotency_key=context.idempotency_key,
            transaction_type=LedgerTransaction.TransactionType.INVENTORY_ADJUSTMENT,
        ).first()
        if existing is not None:
            source_prefix = f'stock_adjustment:{request_fingerprint}:'
            if (existing.business_date != business_date or existing.operator_id != operator.pk
                    or existing.description != reason or existing.source_type != 'stock_adjustment'
                    or not existing.source_id.startswith(source_prefix)):
                raise LedgerError('idempotency_conflict', code='idempotency_conflict')
            result_batch_raw = existing.source_id[len(source_prefix):]
            if not result_batch_raw.isdigit() or int(result_batch_raw) <= 0:
                raise LedgerError('idempotency_conflict', code='idempotency_conflict')
            result_batch = PurchaseBatch.objects.filter(pk=int(result_batch_raw)).first()
            if (result_batch is None or result_batch.cigar_id != cigar_id_for_source
                    or (batch_id_for_source is not None and result_batch.pk != batch_id_for_source)):
                raise LedgerError('idempotency_conflict', code='idempotency_conflict')
            return result_batch
    if delta == 0:
        raise OrderServiceError('库存修正数量不能为 0')
    if inventory_form not in ('stick', 'box'):
        raise OrderServiceError('库存修正形态必须是 stick 或 box')
    if inventory_form == 'box' and not batch_id:
        raise OrderServiceError('box 修正必须指定批次')
    try:
        cigar = Cigar.objects.get(id=_to_positive_int(cigar_id, '雪茄ID'))
    except Cigar.DoesNotExist:
        raise OrderServiceError('雪茄不存在')

    normalized_unit_cost = (
        None if unit_cost_cny is None
        else _to_signed_money(unit_cost_cny, '成本单价')
    )
    try:
        result = inventory_module.adjust_stock(
            cigar=cigar,
            quantity_delta=delta,
            inventory_form=inventory_form,
            operator=operator,
            context=context,
            reason=reason,
            batch_id=batch_id_for_source,
            unit_cost_cny=normalized_unit_cost,
            adjustment_type=adjustment_type,
        )
    except inventory_module.InventoryInsufficientError as error:
        raise InsufficientStockError(str(error), details=error.details) from error
    except inventory_module.InventoryError as error:
        raise OrderServiceError(str(error), details=error.details) from error
    source_id = f'stock_adjustment:{request_fingerprint}:{result.batch.pk}'
    ledger = _post_stock_adjustment(
        cost_cny=result.cost_cny,
        gain=delta > 0,
        business_date=business_date,
        operator=operator,
        context=context,
        reason=reason,
        source_id=source_id,
    )
    with ledger_mutation_scope(
        reason='inventory_adjustment_fact',
        model='cigars.InventoryAdjustmentAction', operator=operator,
    ):
        action = InventoryAdjustmentAction.objects.create(
            cigar=cigar,
            quantity_delta=delta,
            inventory_form=inventory_form,
            ledger_transaction=ledger,
            business_date=business_date,
            operator=operator,
            reason=reason,
            idempotency_key=context.idempotency_key,
        )
    # 每条明细单独经过模型门禁，避免 bulk_create 绕过事实校验。
    with ledger_mutation_scope(
        reason='inventory_adjustment_fact',
        model='cigars.InventoryAdjustmentLine', operator=operator,
    ):
        for line in result.lines:
            InventoryAdjustmentLine.objects.create(
                action=action,
                purchase_batch=line.batch,
                stock_movement=line.movement,
                quantity_delta=line.quantity_delta,
                box_delta=line.box_delta,
                stick_delta=line.stick_delta,
                cost_delta_cny=line.cost_delta_cny,
                batch_state_after=line.batch_state_after,
            )
    return result.batch


@_retry_sqlite_locked
@transaction.atomic
def reverse_stock_adjustment(*, adjustment_id, business_date, operator,
                             idempotency_key, reason):
    """整次撤销一笔有结构化逐批事实的库存调整。"""
    operator = _require_operator(operator)
    _acquire_sqlite_writer_gate()
    reason = str(reason or '').strip()
    if not reason:
        raise OrderServiceError('撤销原因不能为空')
    require_day1_completed()
    action = InventoryAdjustmentAction.objects.select_for_update().filter(
        pk=_to_positive_int(adjustment_id, '库存调整ID'),
    ).first()
    if action is None:
        raise OrderServiceError('库存调整不存在')
    context = AgentContext(
        command_name='reverse_stock_adjustment', idempotency_key=idempotency_key,
    )
    if action.reversal_transaction_id is not None:
        reverse_ledger_transaction(
            original_transaction=action.ledger_transaction,
            business_date=business_date, operator=operator,
            idempotency_key=idempotency_key, reason=reason,
        )
        return action
    try:
        inventory_module.reverse_adjustment(
            action=action, operator=operator, context=context, note=reason,
        )
    except inventory_module.InventoryError as error:
        raise OrderServiceError(str(error), details=error.details) from error
    reversal = reverse_ledger_transaction(
        original_transaction=action.ledger_transaction,
        business_date=business_date, operator=operator,
        idempotency_key=idempotency_key, reason=reason,
    )
    action.reversal_transaction = reversal
    action.reversed_at = timezone.now()
    action.reversal_operator = operator
    action.reversal_reason = reason
    with ledger_mutation_scope(
        reason='inventory_adjustment_reversal',
        model='cigars.InventoryAdjustmentAction', operator=operator,
    ):
        action.save(update_fields=[
            'reversal_transaction', 'reversed_at',
            'reversal_operator', 'reversal_reason',
        ])
    return action


def receive_purchase_order(*, purchase_order_id, operator, agent_context=None, note='',
                           business_date=None, idempotency_key=None):
    """旧入口委托 Task 4 到货动作，保留 Agent 调用兼容性。"""
    from accounting.purchase_actions import (
        PurchaseActionError, receive_paid_purchase_order,
    )
    context = agent_context or AgentContext(command_name='receive_purchase_order')
    key = idempotency_key or context.idempotency_key
    if not key:
        key = f'legacy-purchase-receipt-{uuid4().hex}'
    if context.idempotency_key != key:
        # 旧入口的库存移动与正式到货事实必须使用同一个审计键。
        context = replace(context, idempotency_key=key)
    if business_date is None:
        order = PurchaseOrder.objects.filter(pk=_to_positive_int(purchase_order_id, '进货单ID')).first()
        business_date = (order.draft_business_date if order and order.draft_business_date
                         else moscow_business_date())
    try:
        return receive_paid_purchase_order(
            purchase_order_id=purchase_order_id, business_date=business_date,
            operator=operator, idempotency_key=key, note=note,
            agent_context=context,
        )
    except PurchaseActionError as error:
        raise OrderServiceError(
            error.code, code=error.code, details=error.details,
        ) from error

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


def update_purchase_order_draft(*, purchase_order_id, items, expected_version,
                               idempotency_key, operator, note=''):
    from accounting.purchase_actions import update_purchase_order_draft as update_draft
    return update_draft(
        purchase_order_id=purchase_order_id, items=items,
        expected_version=expected_version, idempotency_key=idempotency_key,
        operator=operator, note=note,
    )


def cancel_purchase_order(*, purchase_order_id, operator, idempotency_key,
                          expected_version, note=''):
    from accounting.purchase_actions import cancel_purchase_order as cancel_draft
    return cancel_draft(
        purchase_order_id=purchase_order_id, operator=operator,
        idempotency_key=idempotency_key, expected_version=expected_version,
        note=note,
    )
