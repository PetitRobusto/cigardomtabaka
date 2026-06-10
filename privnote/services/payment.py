"""Payment 业务逻辑 — 收款单数据构建、SalesOrder 创建"""
from django.shortcuts import get_object_or_404

from cigars.models import Cigar, PurchaseBatch, SalesOrder, SalesOrderItem
from privnote.models import PaymentMethod
from privnote.helpers import get_thumb_url, serialize_payment_method


def build_payment_data(sales_order):
    """实时渲染收款 privnote 数据"""
    items = []
    for item in sales_order.items.select_related('cigar').all():
        cigar = item.cigar
        items.append({
            'name': cigar.name or cigar.english_name,
            'english_name': cigar.english_name,
            'vitola': cigar.vitola or '—',
            'quantity': item.quantity,
            'unit_price': item.unit_price,
            'subtotal': round(item.quantity * item.unit_price, 2),
            'thumb_url': get_thumb_url(cigar),
        })

    total = round(sum(it['subtotal'] for it in items), 2)

    # 额外费用
    extra_fees = sales_order.payment_manual.get('extra_fees', []) if sales_order.payment_manual else []
    extra_total = round(sum(float(f.get('amount', 0)) for f in extra_fees), 2)

    payment_methods = []
    if sales_order.payment_method_id:
        try:
            pm = PaymentMethod.objects.get(id=sales_order.payment_method_id, is_active=True)
            payment_methods.append(serialize_payment_method(pm))
        except PaymentMethod.DoesNotExist:
            pass

    if sales_order.payment_manual:
        manual = sales_order.payment_manual
        if manual.get('bank_name') or manual.get('card_number') or manual.get('card_holder'):
            payment_methods.append({
                'method_type': 'bank_card',
                'label': '手动填写',
                'bank_name': manual.get('bank_name', ''),
                'card_number': manual.get('card_number', ''),
                'card_holder': manual.get('card_holder', ''),
                'qr_url': manual.get('qr_url'),
            })

    # 备注图片
    images = sales_order.payment_manual.get('images', []) if sales_order.payment_manual else []

    return {
        'mode': 'payment',
        'items': items,
        'total': total,
        'extra_fees': extra_fees,
        'extra_total': extra_total,
        'grand_total': round(total + extra_total, 2),
        'payment_methods': payment_methods,
        'customer_name': sales_order.customer_name or '',
        'remark': sales_order.payment_manual.get('remark', '') if sales_order.payment_manual else '',
        'images': images,
    }


def create_sales_order_from_items(items_raw, customer_name, payment_method_id,
                                   payment_manual, extra_fees, remark, images):
    """
    从商品列表创建 SalesOrder + SalesOrderItem。
    返回创建好的 SalesOrder 实例。
    """
    order = SalesOrder.objects.create(
        customer_name=customer_name or '',
        operator=None,
        status='draft',
        payment_method_id=int(payment_method_id) if payment_method_id else None,
        payment_manual=dict(payment_manual, extra_fees=extra_fees, remark=remark, images=images),
    )

    total_revenue = 0
    total_cost = 0
    for it in items_raw:
        cigar_id = it.get('cigar_id')
        quantity = int(it.get('quantity', 1))
        unit_price = float(it.get('unit_price', 0))

        cigar = get_object_or_404(Cigar, id=cigar_id)

        # 如果关联库存，自动填成本
        unit_cost = 0
        purchase_batch_id = it.get('batch_id')
        if purchase_batch_id:
            batch = PurchaseBatch.objects.filter(id=purchase_batch_id).first()
            if batch:
                unit_cost = batch.unit_cost_cny or 0

        revenue = round(quantity * unit_price, 2)
        cost = round(quantity * unit_cost, 2)
        total_revenue += revenue
        total_cost += cost

        SalesOrderItem.objects.create(
            sales_order=order,
            cigar=cigar,
            quantity=quantity,
            unit_price=unit_price,
            unit_cost=unit_cost,
            revenue=revenue,
            cost=cost,
            profit=round(revenue - cost, 2),
        )

    order.total_revenue = round(total_revenue, 2)
    order.total_cost = round(total_cost, 2)
    order.total_profit = round(total_revenue - total_cost, 2)
    order.save(update_fields=['total_revenue', 'total_cost', 'total_profit'])

    return order
