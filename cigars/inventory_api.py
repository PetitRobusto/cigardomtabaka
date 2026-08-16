"""工作人员库存撤销与审计接口。"""

import json
from datetime import date

from django.http import JsonResponse

from accounting.guards import Day1IncompleteError
from accounting.services import LedgerError

from .inventory_audit import audit_inventory
from .models import InventoryAdjustmentAction
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
