"""Command-style API for agents.

The API intentionally exposes business commands instead of model CRUD.
"""
import hashlib
import json
from decimal import Decimal

from django.db import transaction
from django.db.models import Count, Q, Sum
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from privnote.decorators import staff_required
from privnote.helpers import decimal_to_number

from .models import (
    Cigar,
    IdempotencyRecord,
    OrderEvent,
    PurchaseBatch,
    SalesOrder,
    SalesOrderItem,
    StockMovement,
    User,
)
from .search import CigarSearchEngine
from .services import (
    AgentContext,
    InsufficientStockError,
    OrderServiceError,
    adjust_stock,
    cancel_sales_order,
    confirm_payment,
    create_sales_order,
    get_stock_summary,
    serialize_sales_order,
)


def _json_response(payload, status=200):
    return JsonResponse(payload, status=status, json_dumps_params={'ensure_ascii': False})


def _load_json(request):
    try:
        return json.loads(request.body.decode('utf-8') or '{}')
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise OrderServiceError('请求体必须是 JSON')


def _canonical_body(body):
    return json.dumps(body, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def _request_hash(body):
    return hashlib.sha256(_canonical_body(body).encode('utf-8')).hexdigest()


def _resolve_operator(request, body):
    raw_operator_id = body.get('operator_id')
    if raw_operator_id:
        try:
            return User.objects.get(id=int(raw_operator_id))
        except (TypeError, ValueError, User.DoesNotExist):
            raise OrderServiceError('operator_id 不存在')
    if request.user.is_authenticated and request.user.is_staff:
        return request.user
    tg_id = request.headers.get('X-Telegram-ID', '').strip()
    if tg_id:
        try:
            return User.objects.get(telegram_id=tg_id, is_staff=True)
        except User.DoesNotExist:
            pass
    raise OrderServiceError('必须提供真实 operator_id')


def _agent_context(body, command_name):
    agent = body.get('agent') or {}
    idempotency_key = str(body.get('idempotency_key') or '').strip()
    context = AgentContext.from_mapping(
        agent,
        command_name=command_name,
        idempotency_key=idempotency_key,
    )
    if not context.agent_name:
        raise OrderServiceError('必须提供 agent.agent_name')
    if not context.idempotency_key:
        raise OrderServiceError('写命令必须提供 idempotency_key')
    return context


def _idempotent_command(request, command_name, handler):
    try:
        body = _load_json(request)
        operator = _resolve_operator(request, body)
        context = _agent_context(body, command_name)
    except OrderServiceError as exc:
        return _json_response({'error': str(exc), 'details': exc.details}, status=400)

    body_hash = _request_hash(body)
    with transaction.atomic():
        record = IdempotencyRecord.objects.select_for_update().filter(key=context.idempotency_key).first()
        if record:
            if record.command_name != command_name or record.request_hash != body_hash:
                return _json_response({
                    'error': 'idempotency_key 已用于不同请求',
                    'idempotency_key': context.idempotency_key,
                }, status=409)
            return _json_response(record.response_body, status=record.status_code)

        try:
            response_body = handler(body, operator, context)
            status_code = 200
        except InsufficientStockError as exc:
            response_body = {'error': str(exc), 'details': exc.details}
            status_code = 400
        except OrderServiceError as exc:
            response_body = {'error': str(exc), 'details': exc.details}
            status_code = 400
        except SalesOrder.DoesNotExist:
            response_body = {'error': '销售单不存在'}
            status_code = 404

        IdempotencyRecord.objects.create(
            key=context.idempotency_key,
            command_name=command_name,
            request_hash=body_hash,
            request_body=body,
            response_body=response_body,
            status_code=status_code,
            operator=operator,
            agent_name=context.agent_name,
            agent_run_id=context.agent_run_id,
            agent_request_id=context.agent_request_id,
        )
    return _json_response(response_body, status=status_code)


def _parse_limit(request, default=30, maximum=100):
    try:
        limit = int(request.GET.get('limit', default))
    except (TypeError, ValueError):
        limit = default
    return max(1, min(limit, maximum))


def _stock_for_cigar(cigar):
    batches = []
    total = 0
    for batch in PurchaseBatch.objects.filter(cigar=cigar, remaining__gt=0).order_by('purchased_at', 'id'):
        batches.append({
            'batch_id': batch.id,
            'remaining': batch.remaining,
            'unit_cost_cny': decimal_to_number(batch.unit_cost_cny),
            'purchased_at': batch.purchased_at.isoformat(),
        })
        total += batch.remaining
    return {'available_stock': total, 'batches': batches}


@staff_required
def search_inventory(request):
    """GET /api/agent/search/?q=..."""
    query = request.GET.get('q', '').strip()
    limit = _parse_limit(request)
    cigars_qs = Cigar.objects.all()
    results = CigarSearchEngine.search(cigars=cigars_qs, query=query, stock_only=False, limit=limit)
    payload = []
    for cigar in results:
        stock = _stock_for_cigar(cigar)
        payload.append({
            'cigar_id': cigar.id,
            'brand': cigar.brand,
            'name': cigar.name or cigar.english_name,
            'english_name': cigar.english_name,
            'vitola': cigar.vitola or '',
            **stock,
        })
    return _json_response({'results': payload})


@staff_required
def stock_query(request):
    """GET /api/agent/stock/?q=..."""
    return _json_response({'results': get_stock_summary(query=request.GET.get('q', '').strip(), limit=_parse_limit(request))})


@csrf_exempt
@staff_required
def create_sales_order_command(request):
    if request.method != 'POST':
        return _json_response({'error': 'Method not allowed'}, status=405)

    def handler(body, operator, context):
        order = create_sales_order(
            items=body.get('items'),
            operator=operator,
            customer_id=body.get('customer_id'),
            customer_name=str(body.get('customer_name') or '').strip(),
            payment_method_id=body.get('payment_method_id'),
            payment_manual=body.get('payment_manual') or {},
            note=str(body.get('note') or '').strip(),
            agent_context=context,
        )
        return {'sales_order': serialize_sales_order(order)}

    return _idempotent_command(request, 'create_sales_order', handler)


@csrf_exempt
@staff_required
def confirm_payment_command(request):
    if request.method != 'POST':
        return _json_response({'error': 'Method not allowed'}, status=405)

    def handler(body, operator, context):
        order = confirm_payment(
            sales_order_id=body.get('sales_order_id'),
            operator=operator,
            note=str(body.get('note') or '').strip(),
            agent_context=context,
        )
        return {'sales_order': serialize_sales_order(order)}

    return _idempotent_command(request, 'confirm_payment', handler)


@csrf_exempt
@staff_required
def cancel_sales_order_command(request):
    if request.method != 'POST':
        return _json_response({'error': 'Method not allowed'}, status=405)

    def handler(body, operator, context):
        order = cancel_sales_order(
            sales_order_id=body.get('sales_order_id'),
            operator=operator,
            note=str(body.get('note') or '').strip(),
            agent_context=context,
        )
        return {'sales_order': serialize_sales_order(order)}

    return _idempotent_command(request, 'cancel_sales_order', handler)


@csrf_exempt
@staff_required
def adjust_stock_command(request):
    if request.method != 'POST':
        return _json_response({'error': 'Method not allowed'}, status=405)

    def handler(body, operator, context):
        batch = adjust_stock(
            cigar_id=body.get('cigar_id'),
            quantity_delta=body.get('quantity_delta'),
            operator=operator,
            reason=str(body.get('reason') or body.get('note') or '').strip(),
            batch_id=body.get('batch_id'),
            unit_cost_cny=body.get('unit_cost_cny'),
            agent_context=context,
        )
        return {
            'batch': {
                'id': batch.id if batch else None,
                'cigar_id': batch.cigar_id if batch else body.get('cigar_id'),
                'remaining': batch.remaining if batch else None,
            }
        }

    return _idempotent_command(request, 'adjust_stock', handler)


@staff_required
def business_report(request):
    """GET /api/agent/reports/basic/"""
    paid_items = SalesOrderItem.objects.filter(sales_order__status='paid')
    pending_items = SalesOrderItem.objects.filter(sales_order__status='pending_payment')
    stock_value = PurchaseBatch.objects.filter(remaining__gt=0).aggregate(
        qty=Sum('remaining'),
    )
    movement_counts = StockMovement.objects.values('movement_type').annotate(count=Count('id'))
    return _json_response({
        'orders': {
            'pending_payment': SalesOrder.objects.filter(status='pending_payment').count(),
            'paid': SalesOrder.objects.filter(status='paid').count(),
            'cancelled': SalesOrder.objects.filter(status='cancelled').count(),
        },
        'sales': {
            'paid_revenue': decimal_to_number(paid_items.aggregate(total=Sum('revenue'))['total'] or Decimal('0.00')),
            'paid_profit': decimal_to_number(paid_items.aggregate(total=Sum('profit'))['total'] or Decimal('0.00')),
            'pending_revenue': decimal_to_number(pending_items.aggregate(total=Sum('revenue'))['total'] or Decimal('0.00')),
            'preorder_items': SalesOrderItem.objects.filter(fulfillment_type='preorder').count(),
        },
        'stock': {
            'available_quantity': stock_value['qty'] or 0,
        },
        'stock_movements': {row['movement_type']: row['count'] for row in movement_counts},
        'recent_order_events': [
            {
                'sales_order_id': event.sales_order_id,
                'command_name': event.command_name,
                'operator_id': event.operator_id,
                'agent_name': event.agent_name,
                'note': event.note,
                'created_at': event.created_at.isoformat(),
            }
            for event in OrderEvent.objects.select_related('operator').order_by('-created_at')[:20]
        ],
    })
