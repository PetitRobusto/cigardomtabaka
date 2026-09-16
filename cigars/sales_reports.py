"""销售经营报表的共享只读口径。"""

from decimal import Decimal

from django.db.models import Count, Sum

from cigars.models import SalesOrder


def pending_collection_summary():
    """汇总所有已经确认生效、但尚未收款的销售订单。"""
    totals = SalesOrder.objects.filter(
        deleted_at__isnull=True,
        fulfillment_status__in=(
            SalesOrder.FulfillmentStatus.CONFIRMED,
            SalesOrder.FulfillmentStatus.SHIPPED,
        ),
        payment_status=SalesOrder.PaymentStatus.UNPAID,
    ).aggregate(
        order_count=Count('id'),
        amount_cny=Sum('amount_due_cny'),
    )
    return {
        'order_count': totals['order_count'] or 0,
        'amount_cny': (totals['amount_cny'] or Decimal('0.00')).quantize(Decimal('0.01')),
    }
