"""JSON serializers for accounting action endpoints."""

from decimal import Decimal

from cigars.constants import BRAND_CN_MAP
from cigars.packaging import declared_box_sizes


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
    items = list(_purchase_items(order))
    current_batches = [
        batch
        for item in items
        for batch in getattr(item, '_prefetched_objects_cache', {}).get('batches', [])
        if batch.reversed_at is None
    ]
    draft_complete = bool(
        order.supplier_id
        and items
        and order.rub_total > 0
        and all(
            item.packaging_status != item.PackagingStatus.REVIEW_REQUIRED
            and item.box_size
            and item.box_quantity
            and item.unit_price_rub_per_box is not None
            for item in items
        )
    )
    return _value({
        'id': order.pk,
        'order_number': order.order_number,
        'supplier_id': order.supplier_id,
        'supplier_name': getattr(order.supplier, 'name', None),
        'supplier_phone': getattr(order.supplier, 'phone', None),
        'status': order.status,
        'version': order.version,
        'business_date': order.draft_business_date,
        'rub_total': order.rub_total,
        'paid_cny_cost': order.paid_cny_cost,
        'paid_at': order.paid_at,
        'received_at': max(
            (batch.purchased_at for batch in current_batches), default=None,
        ),
        'note': order.note,
        'created_at': order.created_at,
        'operator_id': order.operator_id,
        'draft_complete': draft_complete,
        'items': [
            {
                'id': item.pk, 'cigar_id': item.cigar_id,
                'cigar_name': getattr(item.cigar, 'name', None),
                'cigar_english_name': getattr(item.cigar, 'english_name', None),
                'brand': getattr(item.cigar, 'brand', None),
                'brand_cn': BRAND_CN_MAP.get(getattr(item.cigar, 'brand', ''), ''),
                'release_type_cn': getattr(item.cigar, 'release_type_cn', None),
                'is_regular': not bool(getattr(item.cigar, 'release_type', None)),
                'packaging_sizes': declared_box_sizes(item.cigar.packagings),
                'box_size': item.box_size, 'box_quantity': item.box_quantity,
                'quantity': item.quantity,
                'unit_price_rub_per_box': item.unit_price_rub_per_box,
                'packaging_status': item.packaging_status,
                'batches': [
                    {
                        'id': batch.pk,
                        'quantity': batch.quantity,
                        'original_cost_cny': batch.original_cost_cny,
                        'purchased_at': batch.purchased_at,
                    }
                    for batch in getattr(
                        item, '_prefetched_objects_cache', {},
                    ).get('batches', [])
                    if batch.reversed_at is None
                ],
            }
            for item in items
        ],
    })


def serialize_expense(expense):
    category_labels = dict(expense.Category.choices)
    subcategory_labels = dict(expense.Subcategory.choices)
    account = getattr(expense, 'fund_account', None)
    subcategory_label = subcategory_labels.get(expense.subcategory, expense.subcategory)
    category_label = subcategory_label.split(' · ', 1)[0] if ' · ' in subcategory_label else category_labels.get(expense.category, expense.category)
    return _value({
        'id': expense.pk, 'category': expense.category,
        'category_label': category_label,
        'subcategory': expense.subcategory,
        'subcategory_label': subcategory_label,
        'fund_account_id': expense.fund_account_id,
        'fund_account_name': getattr(account, 'name', ''),
        'currency': getattr(account, 'currency', ''),
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
