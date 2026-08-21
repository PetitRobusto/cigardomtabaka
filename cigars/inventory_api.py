"""工作人员库存撤销与审计接口。"""

import json
from datetime import date

from django.db import IntegrityError, transaction
from django.db.models import Count, Q, Sum
from django.http import JsonResponse

from accounting.action_serializers import serialize_purchase_order
from accounting.business_time import moscow_business_date
from accounting.guards import Day1IncompleteError
from accounting.services import LedgerError

from .inventory_audit import audit_inventory
from .models import InventoryAdjustmentAction, PurchaseOrder, Supplier
from .services import OrderServiceError, reverse_stock_adjustment


def _json(payload, status=200):
    return JsonResponse(
        payload, status=status,
        json_dumps_params={'ensure_ascii': False},
    )


def _staff(request):
    return bool(
        getattr(request.user, 'is_authenticated', False)
        and request.user.is_staff
    )


def _body(request):
    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise OrderServiceError('请求体必须是有效 JSON') from error
    if not isinstance(payload, dict):
        raise OrderServiceError('请求体必须是 JSON 对象')
    return payload


def _business_date(payload):
    try:
        return date.fromisoformat(str(payload.get('business_date')))
    except (TypeError, ValueError) as error:
        raise OrderServiceError('business_date 必须是 ISO 日期') from error


def _idempotency_key(request):
    key = str(request.headers.get('Idempotency-Key', '')).strip()
    if not key or len(key) > 128:
        raise OrderServiceError('写请求必须提供有效的 Idempotency-Key')
    return key


def _iso_query(request, name):
    value = request.GET.get(name, '').strip()
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise OrderServiceError(f'{name} 必须是 ISO 日期') from error


def inventory_suppliers(request):
    """工作人员搜索或就地新建供应商。"""
    if not _staff(request):
        return _json({'error': '仅限工作人员访问'}, 403)
    if request.method == 'GET':
        query = request.GET.get('q', '').strip()
        suppliers = Supplier.objects.filter(deleted_at__isnull=True)
        if query:
            suppliers = suppliers.filter(Q(name__icontains=query) | Q(phone__icontains=query))
        return _json({'results': [
            {'id': supplier.pk, 'name': supplier.name, 'phone': supplier.phone}
            for supplier in suppliers.order_by('name')[:30]
        ]})
    if request.method != 'POST':
        return _json({'error': '不支持的请求方法'}, 405)
    try:
        payload = _body(request)
        key = _idempotency_key(request)
        name = str(payload.get('name') or '').strip()
        phone = str(payload.get('phone') or '').strip()
        if not name or len(name) > 200:
            raise OrderServiceError('供应商名称不能为空且不能超过 200 个字符')
        if len(phone) > 50:
            raise OrderServiceError('供应商电话不能超过 50 个字符')
        existing = Supplier.objects.filter(creation_idempotency_key=key).first()
        if existing is not None:
            if existing.name != name or existing.phone != phone:
                return _json({'error': 'Idempotency-Key 已用于不同请求'}, 409)
            return _json({'supplier': {'id': existing.pk, 'name': existing.name, 'phone': existing.phone}})
        if Supplier.objects.filter(name__iexact=name).exists():
            return _json({'error': '同名供应商已存在'}, 409)
        with transaction.atomic():
            supplier = Supplier.objects.create(
                name=name, phone=phone, creation_idempotency_key=key,
            )
    except IntegrityError:
        existing = Supplier.objects.filter(creation_idempotency_key=key).first()
        if existing is None or existing.name != name or existing.phone != phone:
            return _json({'error': '供应商已存在或幂等键冲突'}, 409)
        supplier = existing
    except OrderServiceError as error:
        return _json({'error': str(error)}, 400)
    return _json({
        'supplier': {'id': supplier.pk, 'name': supplier.name, 'phone': supplier.phone},
    }, 201)


def inventory_purchases(request, purchase_id=None):
    """库存工作台采购目录；采购事实写入仍走账务受控动作接口。"""
    if not _staff(request):
        return _json({'error': '仅限工作人员访问'}, 403)
    if request.method != 'GET':
        return _json({'error': '不支持的请求方法'}, 405)
    purchases = PurchaseOrder.objects.select_related(
        'supplier', 'operator',
    ).prefetch_related('items__cigar', 'items__batches').filter(deleted_at__isnull=True)
    if purchase_id is not None:
        purchase = purchases.filter(pk=purchase_id).first()
        if purchase is None:
            return _json({'error': '采购单不存在'}, 404)
        return _json({'purchase_order': serialize_purchase_order(purchase)})
    try:
        date_from = _iso_query(request, 'date_from')
        date_to = _iso_query(request, 'date_to')
        if date_from and date_to and date_from > date_to:
            raise OrderServiceError('date_from 不能晚于 date_to')
        limit = int(request.GET.get('limit', '100'))
        if not 1 <= limit <= 100:
            raise ValueError
    except (OrderServiceError, TypeError, ValueError) as error:
        return _json({'error': str(error) if str(error) else 'limit 必须是 1 到 100'}, 400)

    all_stats = PurchaseOrder.objects.filter(deleted_at__isnull=True).aggregate(
        total=Count('id'),
        draft=Count('id', filter=Q(status=PurchaseOrder.Status.DRAFT)),
        in_transit=Count('id', filter=Q(status=PurchaseOrder.Status.IN_TRANSIT)),
        received=Count('id', filter=Q(status=PurchaseOrder.Status.RECEIVED)),
        cancelled=Count('id', filter=Q(status=PurchaseOrder.Status.CANCELLED)),
        in_transit_rub=Sum('rub_total', filter=Q(status=PurchaseOrder.Status.IN_TRANSIT)),
    )
    month_start = moscow_business_date().replace(day=1)
    monthly_received = PurchaseOrder.objects.filter(
        deleted_at__isnull=True,
    ).aggregate(
        received_sticks=Sum(
            'items__batches__quantity',
            filter=Q(
                items__batches__purchased_at__date__gte=month_start,
                items__batches__reversed_at__isnull=True,
            ),
        ),
    )
    # 付款额必须在不连接采购明细/批次的独立查询中汇总，否则一单多行
    # 商品会把整单金额重复累计。
    monthly_paid = PurchaseOrder.objects.filter(
        deleted_at__isnull=True,
        paid_at__date__gte=month_start,
    ).aggregate(paid_rub=Sum('rub_total'))
    status = request.GET.get('status', '').strip()
    if status:
        if status not in PurchaseOrder.Status.values:
            return _json({'error': '采购状态无效'}, 400)
        purchases = purchases.filter(status=status)
    if date_from:
        purchases = purchases.filter(draft_business_date__gte=date_from)
    if date_to:
        purchases = purchases.filter(draft_business_date__lte=date_to)
    query = request.GET.get('q', '').strip()
    if query:
        search = (
            Q(supplier__name__icontains=query)
            | Q(note__icontains=query)
            | Q(items__cigar__name__icontains=query)
            | Q(items__cigar__english_name__icontains=query)
            | Q(items__cigar__brand__icontains=query)
        )
        if query.upper().startswith('PO-') and query[3:].isdigit():
            search |= Q(pk=int(query[3:]))
        elif query.isdigit():
            search |= Q(pk=int(query))
        purchases = purchases.filter(search).distinct()
    return _json({
        'stats': {
            **all_stats,
            'in_transit_rub': all_stats['in_transit_rub'] or 0,
            'month_received_sticks': monthly_received['received_sticks'] or 0,
            'month_paid_rub': monthly_paid['paid_rub'] or 0,
        },
        'results': [serialize_purchase_order(order) for order in purchases[:limit]],
    })


def inventory_adjustment_reverse(request, adjustment_id):
    if not _staff(request):
        return _json({'error': '仅限工作人员访问'}, 403)
    if request.method != 'POST':
        return _json({'error': '不支持的请求方法'}, 405)
    key = str(request.headers.get('Idempotency-Key', '')).strip()
    if not key:
        return _json({'error': '写请求必须提供 Idempotency-Key'}, 400)
    try:
        payload = _body(request)
        action = reverse_stock_adjustment(
            adjustment_id=adjustment_id,
            business_date=_business_date(payload),
            operator=request.user,
            idempotency_key=key,
            reason=str(payload.get('reason') or '').strip(),
        )
    except Day1IncompleteError as error:
        return _json({'error': str(error), 'code': error.code, 'details': error.details}, 409)
    except (OrderServiceError, LedgerError) as error:
        return _json({
            'error': str(error),
            'code': getattr(error, 'code', None) or 'input_error',
            'details': getattr(error, 'details', {}),
        }, 409)
    return _json({
        'adjustment': {
            'id': action.pk,
            'reversal_transaction_id': action.reversal_transaction_id,
            'reversed_at': action.reversed_at.isoformat() if action.reversed_at else None,
        },
    })


def inventory_audit(request):
    if not _staff(request):
        return _json({'error': '仅限工作人员访问'}, 403)
    if request.method != 'GET':
        return _json({'error': '不支持的请求方法'}, 405)
    result = audit_inventory()
    recent_adjustments = InventoryAdjustmentAction.objects.select_related(
        'cigar',
    ).order_by('-created_at')[:50]
    return _json({
        'ok': result.ok,
        'issue_count': len(result.issues),
        'issues': [issue.__dict__ for issue in result.issues],
        'recent_adjustments': [
            {
                'id': action.pk,
                'cigar_id': action.cigar_id,
                'cigar_name': action.cigar.name or action.cigar.english_name,
                'quantity_delta': action.quantity_delta,
                'inventory_form': action.inventory_form,
                'business_date': action.business_date.isoformat(),
                'reason': action.reason,
                'reversed_at': action.reversed_at.isoformat() if action.reversed_at else None,
                'can_reverse': action.reversal_transaction_id is None,
            }
            for action in recent_adjustments
        ],
    })
