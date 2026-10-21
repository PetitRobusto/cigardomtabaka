"""从有效收款事实派生订单收款进度，供命令与读模型共享。"""
from decimal import Decimal


def received_amount(order):
    cache = getattr(order, '_prefetched_objects_cache', {})
    receipts = cache.get('sales_receipts')
    if receipts is None:
        receipts = order.sales_receipts.filter(reversed_at__isnull=True)
    return sum((r.amount_cny for r in receipts if r.reversed_at is None), Decimal('0.00'))


def remaining_amount(order):
    if order.fulfillment_status in ('cancelled', 'returned'):
        return Decimal('0.00')
    return max(Decimal('0.00'), order.amount_due_cny - received_amount(order))
