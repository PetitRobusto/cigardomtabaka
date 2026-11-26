"""销售经营报表的共享只读口径。"""

from decimal import Decimal

from django.db.models import Sum, Count, Exists, F, Q, OuterRef, Subquery, DecimalField, Value
from django.db.models.functions import Coalesce

from cigars.models import SalesOrder, SalesOrderItem, SalesReceipt, StockAllocation


def pending_collection_summary(orders=None):
    if orders is None:
        orders = SalesOrder.objects.all()
    orders = orders.filter(
        deleted_at__isnull=True,
        fulfillment_status__in=(
            SalesOrder.FulfillmentStatus.CONFIRMED,
            SalesOrder.FulfillmentStatus.SHIPPED,
        ),
        payment_status__in=(SalesOrder.PaymentStatus.UNPAID, SalesOrder.PaymentStatus.PARTIAL),
    )
    receipts = SalesReceipt.objects.filter(sales_order_id=OuterRef('pk'), reversed_at__isnull=True).order_by().values('sales_order_id').annotate(total=Sum('amount_cny')).values('total')
    money = DecimalField(max_digits=14, decimal_places=2)
    totals = orders.annotate(_received_cny=Coalesce(Subquery(receipts, output_field=money), Value(Decimal('0.00')), output_field=money)).aggregate(
        count=Count('id'), due=Sum('amount_due_cny'), received=Sum('_received_cny'),
    )
    return {'order_count': totals['count'], 'amount_cny': ((totals['due'] or Decimal('0.00')) - (totals['received'] or Decimal('0.00'))).quantize(Decimal('0.01'))}


def sales_list_stats(orders):
    """先按订单范围汇总；仅完整预留的已确认订单参与利润估算。"""
    confirmed = SalesOrder.FulfillmentStatus.CONFIRMED
    shipped = SalesOrder.FulfillmentStatus.SHIPPED
    totals = orders.aggregate(
        order_count=Count('id'),
        amount_due=Sum('amount_due_cny', filter=Q(fulfillment_status__in=(confirmed, shipped))),
        shipped_profit=Sum('contribution_profit_cny', filter=Q(fulfillment_status=shipped)),
    )
    incomplete_items = SalesOrderItem.objects.filter(sales_order_id=OuterRef('pk')).annotate(
        reserved=Sum('allocations__quantity', filter=Q(allocations__status='reserved'), default=0),
    ).exclude(reserved=F('quantity'))
    estimated = orders.filter(fulfillment_status=confirmed).filter(~Exists(incomplete_items))
    margin = estimated.aggregate(total=Sum(F('amount_due_cny') - F('actual_transport_cost_cny')))['total']
    costs = StockAllocation.objects.filter(
        status='reserved', sales_order_item__sales_order_id__in=estimated.values('pk'),
    ).aggregate(total=Sum(Coalesce('fulfilled_cost_cny', F('purchase_batch__unit_cost_cny') * F('quantity'))))['total']
    profit = (totals['shipped_profit'] or Decimal('0.00')) + (margin or 0) - (costs or 0)
    return {
        'order_count': totals['order_count'],
        'amount_due_cny': totals['amount_due'] or Decimal('0.00'),
        'contribution_profit_cny': profit.quantize(Decimal('0.01')),
    }
