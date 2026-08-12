"""Payment 业务逻辑 — 收款单数据构建。

SalesOrder 必须由销售单工作流创建；这里的 payment privnote 只负责引用
既有销售单并渲染收款信息。
"""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from privnote.models import PaymentMethod
from accounting.models import FundAccount
from privnote.helpers import decimal_to_number, get_thumb_url, serialize_payment_method


MONEY_PLACES = Decimal('0.01')


class PaymentValidationError(ValueError):
    """收款单输入校验错误。"""


def _to_money(raw, field_name):
    try:
        value = Decimal(str(raw)).quantize(MONEY_PLACES, rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError):
        raise PaymentValidationError(f'{field_name}必须是有效金额')
    if value < 0:
        raise PaymentValidationError(f'{field_name}不能为负数')
    return value


def build_payment_data(sales_order, payment_method=None, *, remark=None, images=None,
                       extra_fees=None):
    """实时渲染收款 privnote 数据"""
    items = []
    for item in sales_order.items.select_related('cigar').all():
        cigar = item.cigar
        items.append({
            'name': cigar.name or cigar.english_name,
            'english_name': cigar.english_name,
            'vitola': cigar.vitola or '—',
            'quantity': item.quantity,
            'unit_price': decimal_to_number(item.unit_price),
            'subtotal': decimal_to_number(item.revenue.quantize(MONEY_PLACES)),
            'sale_unit': item.sale_unit,
            'sale_quantity': item.sale_quantity,
            'box_size': item.box_size,
            'thumb_url': get_thumb_url(cigar),
        })

    authoritative_total = _to_money(sales_order.amount_due_cny, '销售单应收总额')
    total = sum(
        (Decimal(str(item['subtotal'])) for item in items), Decimal('0.00')
    ).quantize(MONEY_PLACES)

    # 额外费用只来自销售单的正式应收字段或本次 privnote 快照，
    # 不再读取 payment_manual，避免手动收款信息污染销售事实。
    if extra_fees is None:
        extra_fees = []
        transport_fee = getattr(sales_order, 'customer_transport_fee_cny', Decimal('0.00'))
        if transport_fee:
            extra_fees = [{'name': '人肉费', 'amount': decimal_to_number(_to_money(transport_fee, '人肉费'))}]
    if not isinstance(extra_fees, list):
        extra_fees = []
    clean_extra_fees = []
    for fee in extra_fees:
        if not isinstance(fee, dict):
            continue
        try:
            amount = _to_money(fee.get('amount', 0), '额外费用金额')
        except PaymentValidationError:
            continue
        name = str(fee.get('name', '')).strip()
        if name and amount:
            clean_extra_fees.append({'name': name, 'amount': decimal_to_number(amount)})

    displayed_extra = sum(
        (Decimal(str(fee['amount'])) for fee in clean_extra_fees), Decimal('0.00')
    ).quantize(MONEY_PLACES)
    required_extra = (authoritative_total - total).quantize(MONEY_PLACES)
    if required_extra < 0:
        raise PaymentValidationError('销售单商品明细超过冻结应收金额，请先修正销售单')
    if displayed_extra != required_extra:
        clean_extra_fees = []
        if required_extra:
            transport_fee = _to_money(
                getattr(sales_order, 'customer_transport_fee_cny', 0), '客户人肉费'
            )
            label = '人肉费' if transport_fee == required_extra else '应收调整'
            clean_extra_fees.append({
                'name': label,
                'amount': decimal_to_number(required_extra),
            })
    extra_fees = clean_extra_fees
    extra_total = required_extra

    payment_methods = []
    if payment_method is None and getattr(sales_order, 'payment_method_id', None):
        payment_method = PaymentMethod.objects.filter(
            id=sales_order.payment_method_id,
            is_active=True,
            fund_account__is_active=True,
            fund_account__currency=FundAccount.Currency.CNY,
        ).first()
    if payment_method is not None:
        payment_methods.append(serialize_payment_method(payment_method))

    # 备注和图片属于本张 privnote 快照，不写回销售单。
    if remark is None:
        remark = getattr(sales_order, 'note', '') or ''
    if not isinstance(images, list):
        images = []

    return {
        'mode': 'payment',
        'items': items,
        'total': decimal_to_number(total),
        'extra_fees': extra_fees,
        'extra_total': decimal_to_number(extra_total),
        'grand_total': decimal_to_number(authoritative_total),
        'payment_methods': payment_methods,
        'customer_name': sales_order.customer_name or '',
        'remark': str(remark or ''),
        'images': [
            image for image in images
            if isinstance(image, dict) and str(image.get('url', '')).strip()
        ],
    }
