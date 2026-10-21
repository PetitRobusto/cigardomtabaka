"""销售经营报表的共享只读口径。"""

from decimal import Decimal

from django.db.models import Sum, Count, OuterRef, Subquery, DecimalField, Value
from django.db.models.functions import Coalesce

from cigars.models import SalesOrder, SalesReceipt


def pending_collection_summary():
    """汇总所有已经确认生效、但尚未收款的销售订单。"""
    orders = SalesOrder.objects.filter(
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
