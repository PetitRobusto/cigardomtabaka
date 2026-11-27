"""已确认销售单在出库前调整成交价。"""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.forms import DecimalField

from accounting.business_time import moscow_business_date
from accounting.guards import require_day1_completed
from accounting.services import _acquire_sqlite_writer_gate
from privnote.models import PaymentSubmission

from .models import SalesOrder, SalesOrderItem, StockAllocation
from .receipt_totals import received_amount
from .sales_accounting import set_receipt_status
from .services import (
    OrderServiceError, _record_order_event, _require_operator, _sales_event_metadata,
    sales_price_revision,
)


class PriceConflictError(OrderServiceError):
    """订单已有业务事实与本次改价冲突。"""


def _requested_prices(items):
    if not isinstance(items, list) or not items:
        raise OrderServiceError("请选择需要修改价格的商品")
    prices = {}
    price_field = DecimalField(min_value=0, max_digits=12, decimal_places=2)
    for row in items:
        if not isinstance(row, dict) or row.keys() != {"id", "unit_price"}:
            raise OrderServiceError("每项只能提供订单明细 ID 和新单价")
        item_id = row["id"]
        if type(item_id) is not int or item_id <= 0 or item_id in prices:
            raise OrderServiceError("订单明细 ID 无效或重复")
        try:
            prices[item_id] = price_field.clean(row["unit_price"]).quantize(Decimal("0.01"))
        except ValidationError as exc:
            raise OrderServiceError("单价须为非负人民币金额，最多两位小数，整数最多十位") from exc
    return prices


@transaction.atomic
def change_sales_prices(*, order_id, items, expected_revision, operator, context):
    operator = _require_operator(operator)
    prices = _requested_prices(items)
    if not isinstance(expected_revision, str) or not expected_revision:
        raise OrderServiceError("请提供改价前的订单版本")
    _acquire_sqlite_writer_gate()
    require_day1_completed()
    order = SalesOrder.objects.select_for_update().get(pk=order_id, deleted_at__isnull=True)
    if (order.fulfillment_status != SalesOrder.FulfillmentStatus.CONFIRMED
            or hasattr(order, "sales_shipment")
            or StockAllocation.objects.filter(sales_order_item__sales_order=order,
                status__in=[StockAllocation.Status.FULFILLED, StockAllocation.Status.RETURNED]).exists()):
        raise PriceConflictError("只有已确认且尚未出库的订单可以改价")
    if expected_revision != sales_price_revision(order):
        raise PriceConflictError("订单已更新，请刷新后重新核对价格及已收金额")

    rows = {row.pk: row for row in order.items.select_for_update().all()}
    if prices.keys() - rows.keys():
        raise OrderServiceError("商品明细不属于本订单")
    goods = sum(row.revenue for row in rows.values())
    transport_fee = order.customer_transport_fee_cny
    if goods != order.goods_amount_cny or goods + transport_fee != order.amount_due_cny:
        raise PriceConflictError("原订单金额与明细不符，请核对历史订单")
    changes = []
    changed_rows = []
    for pk, price in prices.items():
        row = rows[pk]
        if row.unit_price == price:
            continue
        changes.append({"id": pk, "old_unit_price": str(row.unit_price), "new_unit_price": str(price)})
        quantity = row.sale_quantity if row.sale_unit == SalesOrderItem.SaleUnit.BOX else row.quantity
        revenue = price * quantity
        goods += revenue - row.revenue
        row.unit_price, row.revenue = price, revenue
        changed_rows.append(row)
    if not changes:
        raise OrderServiceError("商品单价没有变化")
    due = goods + transport_fee
    if due > Decimal("9999999999.99"):
        raise OrderServiceError("订单金额超出可记录范围")
    paid = received_amount(order)
    if due < paid:
        raise PriceConflictError("改价后订单金额不能低于累计有效实收")
    if due != order.amount_due_cny and order.payment_submissions.filter(status=PaymentSubmission.Status.PENDING).exists():
        raise PriceConflictError("有待核实的付款凭证，请先核实或要求补充，再调整订单总额")
    previous_payment_status = order.payment_status
    set_receipt_status(order, paid)
    if order.payment_status != previous_payment_status or paid > order.amount_due_cny:
        raise PriceConflictError("订单收款状态与有效收款不符，请核对历史收款")

    previous_due = order.amount_due_cny
    SalesOrderItem.objects.bulk_update(changed_rows, ["unit_price", "revenue"])
    order.goods_amount_cny = order.total_revenue = goods
    order.amount_due_cny = due
    set_receipt_status(order, paid)
    order.save(update_fields=["goods_amount_cny", "total_revenue", "amount_due_cny", "payment_status", "status"])
    _record_order_event(order, operator=operator, context=context, metadata={
        **_sales_event_metadata(order, moscow_business_date()),
        "idempotency_key": context.idempotency_key, "items": changes,
        "old_amount_due_cny": str(previous_due), "new_amount_due_cny": str(due),
        "received_amount_cny": str(paid),
    })
    return order
