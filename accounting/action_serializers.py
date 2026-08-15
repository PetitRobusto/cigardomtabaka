"""JSON serializers for accounting action endpoints."""

from decimal import Decimal


def _value(value):
    if isinstance(value, Decimal):
        return str(value)
    if hasattr(value, 'isoformat'):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_value(item) for item in value]
    return value


def _purchase_items(order):
    """复用动作列表预取结果，避免采购单数量线性增加查询。"""
    cache = getattr(order, '_prefetched_objects_cache', {})
    if 'items' in cache:
        return sorted(cache['items'], key=lambda item: item.pk)
    return order.items.select_related('cigar').order_by('id')


def serialize_purchase_order(order):
    return _value({
        'id': order.pk,
        'order_number': order.order_number,
        'supplier_id': order.supplier_id,
        'status': order.status,
        'version': order.version,
        'business_date': order.draft_business_date,
        'rub_total': order.rub_total,
        'paid_cny_cost': order.paid_cny_cost,
        'items': [
            {
                'id': item.pk, 'cigar_id': item.cigar_id,
                'cigar_name': getattr(item.cigar, 'name', None),
                'box_size': item.box_size, 'box_quantity': item.box_quantity,
                'quantity': item.quantity,
                'unit_price_rub_per_box': item.unit_price_rub_per_box,
                'packaging_status': item.packaging_status,
            }
            for item in _purchase_items(order)
        ],
    })


def serialize_expense(expense):
    return _value({
        'id': expense.pk, 'category': expense.category,
        'fund_account_id': expense.fund_account_id,
        'original_amount': expense.original_amount,
        'amount_cny': expense.amount_cny,
        'business_date': expense.business_date,
        'operator_id': expense.operator_id, 'status': expense.status,
        'idempotency_key': expense.idempotency_key, 'note': expense.note,
    })


def serialize_dividend(dividend):
    return _value({
        'id': dividend.pk, 'status': dividend.status, 'version': dividend.version,
        'total_cny': dividend.total_cny,
        'partner_a_amount_cny': dividend.partner_a_amount_cny,
        'partner_b_amount_cny': dividend.partner_b_amount_cny,
        'partner_a_account_id': dividend.partner_a_account_id,
        'partner_b_account_id': dividend.partner_b_account_id,
        'business_date': dividend.business_date,
        'warning_code': dividend.warning_code,
        'warning_ack': dividend.warning_ack,
    })


def serialize_action(action):
    """Serialize a small actionable item without exposing mutable model state."""
    return _value(action)
