"""Payment 业务逻辑 — 收款单数据构建、SalesOrder 创建"""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from cigars.models import PurchaseBatch, SalesOrderItem
from cigars.services import (
    AgentContext,
    InsufficientStockError,
    OrderServiceError,
    create_sales_order,
)
from privnote.models import PaymentMethod
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


def _to_positive_int(raw, field_name):
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise PaymentValidationError(f'{field_name}必须是正整数')
    if value <= 0:
        raise PaymentValidationError(f'{field_name}必须是正整数')
    return value


def _normalize_extra_fees(extra_fees):
    if not extra_fees:
        return []
    if not isinstance(extra_fees, list):
        raise PaymentValidationError('额外费用格式错误')

    normalized = []
    for idx, fee in enumerate(extra_fees, start=1):
        if not isinstance(fee, dict):
            raise PaymentValidationError(f'第{idx}项额外费用格式错误')
        name = str(fee.get('name', '')).strip()
        amount = _to_money(fee.get('amount', 0), f'第{idx}项额外费用金额')
        if not name and amount == 0:
            continue
        if not name:
            raise PaymentValidationError(f'第{idx}项额外费用名称不能为空')
        normalized.append({'name': name, 'amount': decimal_to_number(amount)})
    return normalized


def _normalize_manual_payment(payment_manual):
    if not payment_manual:
        return {}
    if not isinstance(payment_manual, dict):
        raise PaymentValidationError('手动收款信息格式错误')
    allowed_keys = ('bank_name', 'card_number', 'card_holder', 'qr_url')
    return {
        key: str(payment_manual.get(key, '')).strip()
        for key in allowed_keys
        if payment_manual.get(key)
    }


def _normalize_images(images):
    if not images:
        return []
    if not isinstance(images, list):
        raise PaymentValidationError('图片数据格式错误')
    normalized = []
    for image in images:
        if not isinstance(image, dict):
            continue
        url = str(image.get('url', '')).strip()
        name = str(image.get('name', '')).strip()
        if url:
            normalized.append({'url': url, 'name': name})
    return normalized


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
            'unit_price': decimal_to_number(item.unit_price),
            'subtotal': decimal_to_number((item.quantity * item.unit_price).quantize(MONEY_PLACES)),
            'thumb_url': get_thumb_url(cigar),
        })

    total = sum(Decimal(str(it['subtotal'])) for it in items).quantize(MONEY_PLACES)

    # 额外费用
    extra_fees = sales_order.payment_manual.get('extra_fees', []) if sales_order.payment_manual else []
    extra_total = sum(
        (_to_money(f.get('amount', 0), '额外费用金额') for f in extra_fees),
        Decimal('0.00'),
    ).quantize(MONEY_PLACES)

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
        'total': decimal_to_number(total),
        'extra_fees': extra_fees,
        'extra_total': decimal_to_number(extra_total),
        'grand_total': decimal_to_number((total + extra_total).quantize(MONEY_PLACES)),
        'payment_methods': payment_methods,
        'customer_name': sales_order.customer_name or '',
        'remark': sales_order.payment_manual.get('remark', '') if sales_order.payment_manual else '',
        'images': images,
    }


def create_sales_order_from_items(items_raw, customer_name, payment_method_id,
                                   payment_manual, extra_fees, remark, images,
                                   operator=None, customer=None):
    """
    从商品列表创建 SalesOrder + SalesOrderItem。
    返回创建好的 SalesOrder 实例。
    """
    if not isinstance(items_raw, list):
        raise PaymentValidationError('商品数据格式错误')
    normalized_manual = _normalize_manual_payment(payment_manual)
    normalized_extra_fees = _normalize_extra_fees(extra_fees)
    normalized_images = _normalize_images(images)

    selected_payment_method_id = None
    if payment_method_id:
        selected_payment_method_id = _to_positive_int(payment_method_id, '收款方式ID')
        if not PaymentMethod.objects.filter(id=selected_payment_method_id, is_active=True).exists():
            raise PaymentValidationError('收款方式不存在或未启用')

    normalized_items = []
    for idx, it in enumerate(items_raw, start=1):
        if not isinstance(it, dict):
            raise PaymentValidationError(f'第{idx}个商品格式错误')
        cigar_id = _to_positive_int(it.get('cigar_id'), f'第{idx}个商品ID')
        purchase_batch_id = it.get('batch_id')
        if purchase_batch_id:
            batch_id = _to_positive_int(purchase_batch_id, f'第{idx}个商品批次ID')
            if not PurchaseBatch.objects.filter(id=batch_id, cigar_id=cigar_id).exists():
                raise PaymentValidationError(f'第{idx}个商品批次不存在或不匹配')
        normalized_items.append({
            'cigar_id': cigar_id,
            'quantity': _to_positive_int(it.get('quantity', 1), f'第{idx}个商品数量'),
            'unit_price': _to_money(it.get('unit_price', 0), f'第{idx}个商品单价'),
            'fulfillment_type': it.get('fulfillment_type') or SalesOrderItem.FulfillmentType.IN_STOCK,
        })

    try:
        return create_sales_order(
            items=normalized_items,
            operator=operator,
            customer=customer,
            customer_name=customer_name or '',
            payment_method_id=selected_payment_method_id,
            payment_manual=dict(
                normalized_manual,
                extra_fees=normalized_extra_fees,
                remark=remark,
                images=normalized_images,
            ),
            note=remark,
            agent_context=AgentContext(command_name='privnote_create_payment'),
        )
    except InsufficientStockError as exc:
        raise PaymentValidationError(str(exc))
    except OrderServiceError as exc:
        raise PaymentValidationError(str(exc))
