"""面向 Agent 的业务命令接口。

接口只暴露业务动作，不允许 Agent 直接修改模型。
"""
import hashlib
import json
import re
from datetime import date
from decimal import Decimal, InvalidOperation

from django.db import transaction
from accounting.business_time import moscow_business_date
from accounting.guards import Day1IncompleteError
from accounting.models import FundAccount
from accounting.services import LedgerError
from accounting.services import _acquire_sqlite_writer_gate, _retry_sqlite_locked
from accounting.purchase_actions import (
    PurchaseActionError,
    canonical_purchase_item,
    normalize_legacy_purchase_item,
    reverse_received_purchase_order,
)
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
    SalesReceipt,
    SalesRefund,
    SalesReturn,
    SalesShipment,
    StockMovement,
    Supplier,
    User,
)
from .search import CigarSearchEngine
from .inventory_audit import audit_inventory
from .services import (
    AgentContext,
    InsufficientStockError,
    OrderServiceError,
    adjust_stock,
    cancel_confirmed_sales_order,
    confirm_sales_order,
    create_purchase_order,
    create_sales_order_draft,
    get_stock_summary,
    receive_purchase_order,
    reverse_stock_adjustment,
    serialize_purchase_order,
    serialize_sales_order,
    update_sales_order_draft,
)
from .sales_accounting import (
    receive_sales_order_payment, record_sales_transport_cost,
    refund_sales_order_payment, return_sales_order, ship_sales_order,
)


def _json_response(payload, status=200):
    return JsonResponse(payload, status=status, json_dumps_params={'ensure_ascii': False})


def _load_json(request):
    try:
        body = json.loads(request.body.decode('utf-8') or '{}')
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise OrderServiceError('请求体必须是 JSON')
    if not isinstance(body, dict):
        raise OrderServiceError('请求体必须是 JSON 对象')
    return body


def _canonical_body(body):
    return json.dumps(body, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def _request_hash(body):
    return hashlib.sha256(_canonical_body(body).encode('utf-8')).hexdigest()


def _resolve_operator(request, body):
    # 认证只决定调用权限；operator_id 单独记录业务责任人。
    raw_operator_id = body.get('operator_id')
    if raw_operator_id in (None, ''):
        raise OrderServiceError('必须提供真实 operator_id')
    if type(raw_operator_id) is int:
        operator_id = raw_operator_id
    elif (
        isinstance(raw_operator_id, str)
        and raw_operator_id.strip().isdigit()
    ):
        operator_id = int(raw_operator_id.strip())
    else:
        raise OrderServiceError('operator_id 必须是正整数')
    if operator_id <= 0:
        raise OrderServiceError('operator_id 必须是正整数')
    try:
        return User.objects.get(id=operator_id)
    except User.DoesNotExist:
        raise OrderServiceError('operator_id 不存在')


def _purchase_error_status(code):
    if code in {'supplier_not_found', 'purchase_order_not_found'}:
        return 404
    if code in {
        'invalid_state', 'idempotency_conflict', 'packaging_review_required',
        'version_conflict', 'day1_incomplete', 'receipt_already_used',
    }:
        return 409
    return 400


def _purchase_error_body(exc):
    return {
        'error': '供应商不存在' if exc.code == 'supplier_not_found' else exc.code,
        'code': exc.code,
        'details': exc.details,
    }


def _ledger_error_result(exc):
    code = exc.code or 'ledger_error'
    return {
        'error': exc.code or str(exc),
        'code': code,
        'details': exc.details,
    }, 409 if code in {'day1_incomplete', 'idempotency_conflict'} else 400


def _day1_error_result(exc):
    return {
        'error': exc.code,
        'code': exc.code,
        'details': exc.details,
    }, 409


def _order_service_error_result(exc):
    """兼容服务携带采购 code 时，沿用 canonical HTTP 错误协议。"""
    if exc.code:
        return _purchase_error_body(exc), _purchase_error_status(exc.code)
    return {'error': str(exc), 'code': 'order_service_error', 'details': exc.details}, 400


def _business_date_from_body(body):
    raw = body.get('business_date')
    if not raw:
        return moscow_business_date()
    try:
        return date.fromisoformat(str(raw))
    except (TypeError, ValueError):
        raise OrderServiceError('business_date 必须是 ISO 日期')


def _agent_context(body, command_name):
    agent = body.get('agent') or {}
    if not isinstance(agent, dict):
        raise OrderServiceError('agent 必须是 JSON 对象')
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


@_retry_sqlite_locked
def _idempotent_command(request, command_name, handler, *, canonical_action=False):
    try:
        body = _load_json(request)
        operator = _resolve_operator(request, body)
        context = _agent_context(body, command_name)
    except OrderServiceError as exc:
        response_body, status_code = _order_service_error_result(exc)
        return _json_response(response_body, status=status_code)

    if canonical_action:
        body_hash = _request_hash(body)
        try:
            with transaction.atomic():
                _acquire_sqlite_writer_gate()
                # 先占用幂等键，再执行业务动作；并发请求只能有一个创建者。
                record, created = (
                    IdempotencyRecord.objects.select_for_update().get_or_create(
                        key=context.idempotency_key,
                        defaults={
                            'command_name': command_name,
                            'request_hash': body_hash,
                            'request_body': body,
                            'response_body': {},
                            'status_code': 202,
                            'operator': operator,
                            'agent_name': context.agent_name,
                            'agent_run_id': context.agent_run_id,
                            'agent_request_id': context.agent_request_id,
                        },
                    )
                )
                if not created:
                    if (
                        record.command_name != command_name
                        or record.request_hash != body_hash
                    ):
                        return _json_response({
                            'error': 'idempotency_conflict',
                            'code': 'idempotency_conflict',
                            'details': {
                                'idempotency_key': context.idempotency_key,
                            },
                        }, status=409)
                    return _json_response(
                        record.response_body, status=record.status_code,
                    )
                try:
                    response_body = handler(body, operator, context)
                    status_code = 200
                except InsufficientStockError as exc:
                    response_body = {
                        'error': str(exc), 'code': 'insufficient_stock',
                        'details': exc.details,
                    }
                    status_code = 400
                except PurchaseActionError as exc:
                    response_body = _purchase_error_body(exc)
                    status_code = _purchase_error_status(exc.code)
                except Day1IncompleteError as exc:
                    response_body, status_code = _day1_error_result(exc)
                except LedgerError as exc:
                    response_body, status_code = _ledger_error_result(exc)
                except SalesOrder.DoesNotExist:
                    response_body = {
                        'error': '销售单不存在',
                        'code': 'sales_order_not_found',
                        'details': {},
                    }
                    status_code = 404
                except OrderServiceError as exc:
                    response_body, status_code = _order_service_error_result(exc)
                IdempotencyRecord.objects.filter(pk=record.pk).update(
                    response_body=response_body, status_code=status_code,
                )
            return _json_response(response_body, status=status_code)
        except PurchaseActionError as exc:
            response_body = _purchase_error_body(exc)
            return _json_response(response_body, status=_purchase_error_status(exc.code))
        except Day1IncompleteError as exc:
            response_body, status_code = _day1_error_result(exc)
            return _json_response(response_body, status=status_code)
        except LedgerError as exc:
            response_body, status_code = _ledger_error_result(exc)
            return _json_response(response_body, status=status_code)
        except OrderServiceError as exc:
            response_body, status_code = _order_service_error_result(exc)
            return _json_response(response_body, status=status_code)

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
            response_body = {
                'error': str(exc), 'code': 'insufficient_stock',
                'details': exc.details,
            }
            status_code = 400
        except PurchaseActionError as exc:
            response_body = _purchase_error_body(exc)
            status_code = _purchase_error_status(exc.code)
        except Day1IncompleteError as exc:
            response_body, status_code = _day1_error_result(exc)
        except LedgerError as exc:
            response_body, status_code = _ledger_error_result(exc)
        except OrderServiceError as exc:
            response_body, status_code = _order_service_error_result(exc)
        except SalesOrder.DoesNotExist:
            response_body = {
                'error': '销售单不存在', 'code': 'sales_order_not_found',
                'details': {},
            }
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


def _sales_orders_queryset():
    # 列表和详情共用预载，避免序列化每张订单时重复查询。
    return SalesOrder.objects.select_related(
        'customer', 'sales_shipment', 'sales_receipt', 'sales_refund',
        'sales_return', 'sales_transport_cost',
    ).prefetch_related('items__cigar', 'items__allocations__purchase_batch')


def _sales_order_response(order):
    # 所有命令返回同一销售单结构，避免动作间字段含义漂移。
    return {'sales_order': serialize_sales_order(order)}


def _sales_note(body):
    # 备注必须保留文本语义，禁止静默转换列表或对象。
    value = body.get('note', '')
    if not isinstance(value, str):
        raise OrderServiceError('note 必须是字符串', details={'note': '必须是字符串'})
    return value.strip()


def _required_business_date(body):
    # 出库和资金事实必须明确归属业务日，不使用服务器当前日期兜底。
    if not body.get('business_date'):
        raise OrderServiceError('必须提供 business_date')
    return _business_date_from_body(body)


def _fund_account_from_body(body):
    # 此处只解析账户；币种和启用状态由业务服务再次校验。
    account_id = body.get('fund_account_id')
    if type(account_id) is not int or account_id <= 0:
        raise OrderServiceError('fund_account_id 必须是正整数')
    try:
        return FundAccount.objects.get(pk=account_id)
    except FundAccount.DoesNotExist:
        raise OrderServiceError('资金账户不存在')


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


@staff_required
def supplier_list(request):
    """GET /api/agent/suppliers/?q=..."""
    query = request.GET.get('q', '').strip()
    suppliers = Supplier.objects.filter(deleted_at__isnull=True).order_by('name')
    if query:
        suppliers = suppliers.filter(name__icontains=query)
    return _json_response({
        'results': [
            {
                'supplier_id': supplier.id,
                'name': supplier.name,
            }
            for supplier in suppliers[:_parse_limit(request, default=50, maximum=100)]
        ]
    })


@csrf_exempt
@staff_required
def create_purchase_order_command(request):
    if request.method != 'POST':
        return _json_response({'error': 'Method not allowed'}, status=405)

    def handler(body, operator, context):
        canonical_items = []
        for index, raw_item in enumerate(body.get('items') or []):
            if not isinstance(raw_item, dict):
                raise PurchaseActionError('packaging_review_required', {'item_index': index})
            if 'box_quantity' in raw_item or 'unit_price_rub_per_box' in raw_item:
                canonical_items.append(canonical_purchase_item(
                    box_size=raw_item.get('box_size'),
                    box_quantity=raw_item.get('box_quantity'),
                    unit_price_rub_per_box=raw_item.get('unit_price_rub_per_box'),
                ) | {'cigar_id': raw_item.get('cigar_id')})
            else:
                legacy_cny = raw_item.get('unit_price_cny')
                if legacy_cny in (None, '') and body.get('exchange_rate') not in (None, ''):
                    try:
                        exchange_rate = Decimal(str(body.get('exchange_rate')))
                        if not exchange_rate.is_finite() or exchange_rate <= 0:
                            raise ValueError
                        legacy_cny = Decimal(str(raw_item.get('unit_price_rub'))) * exchange_rate
                    except (InvalidOperation, TypeError, ValueError):
                        raise PurchaseActionError('invalid_exchange_rate')
                canonical_items.append(normalize_legacy_purchase_item(
                    box_size=raw_item.get('box_size'),
                    quantity_sticks=raw_item.get('quantity'),
                    unit_price_rub_per_stick=raw_item.get('unit_price_rub'),
                    unit_price_cny_per_stick=legacy_cny,
                ) | {'cigar_id': raw_item.get('cigar_id')})
        purchase_order = create_purchase_order(
            supplier_id=body.get('supplier_id'),
            items=canonical_items,
            business_date=body.get('business_date') or moscow_business_date(),
            idempotency_key=context.idempotency_key,
            exchange_rate=body.get('exchange_rate'),
            operator=operator,
            note=str(body.get('note') or '').strip(),
            agent_context=context,
        )
        return {'purchase_order': serialize_purchase_order(purchase_order)}

    return _idempotent_command(request, 'create_purchase_order', handler, canonical_action=True)


@csrf_exempt
@staff_required
def update_purchase_order_command(request):
    if request.method != 'POST':
        return _json_response({'error': 'Method not allowed'}, status=405)

    def handler(body, operator, context):
        from accounting.purchase_actions import update_purchase_order_draft
        order = update_purchase_order_draft(
            purchase_order_id=body.get('purchase_order_id'),
            items=body.get('items'),
            expected_version=body.get('expected_version'),
            idempotency_key=context.idempotency_key,
            operator=operator,
            note=str(body.get('note') or '').strip(),
        )
        return {'purchase_order': serialize_purchase_order(order)}

    return _idempotent_command(request, 'update_purchase_order', handler, canonical_action=True)


@csrf_exempt
@staff_required
def cancel_purchase_order_command(request):
    if request.method != 'POST':
        return _json_response({'error': 'Method not allowed'}, status=405)

    def handler(body, operator, context):
        from accounting.purchase_actions import cancel_purchase_order
        order = cancel_purchase_order(
            purchase_order_id=body.get('purchase_order_id'),
            expected_version=body.get('expected_version'),
            idempotency_key=context.idempotency_key,
            operator=operator,
            note=str(body.get('note') or '').strip(),
        )
        return {'purchase_order': serialize_purchase_order(order)}

    return _idempotent_command(request, 'cancel_purchase_order', handler, canonical_action=True)


@csrf_exempt
@staff_required
def receive_purchase_order_command(request):
    if request.method != 'POST':
        return _json_response({'error': 'Method not allowed'}, status=405)

    def handler(body, operator, context):
        batches = receive_purchase_order(
            purchase_order_id=body.get('purchase_order_id'),
            operator=operator,
            note=str(body.get('note') or '').strip(),
            agent_context=context,
        )
        purchase_order = (
            batches[0].purchase_order_item.purchase_order
            if batches and batches[0].purchase_order_item_id else None
        )
        return {
            'purchase_order': serialize_purchase_order(purchase_order) if purchase_order else None,
            'batch_source': batches[0].source if batches else None,
        }

    return _idempotent_command(request, 'receive_purchase_order', handler)


@csrf_exempt
@staff_required
def reverse_purchase_receipt_command(request):
    # 只撤销完全未使用的整单到货，原采购付款保持不变。
    if request.method != 'POST':
        return _json_response({'error': 'Method not allowed'}, status=405)

    def handler(body, operator, context):
        batches = reverse_received_purchase_order(
            purchase_order_id=body.get('purchase_order_id'),
            business_date=_required_business_date(body),
            operator=operator,
            idempotency_key=context.idempotency_key,
            reason=str(body.get('reason') or body.get('note') or '').strip(),
        )
        order = batches[0].purchase_order_item.purchase_order if batches else None
        return {
            'purchase_order': serialize_purchase_order(order) if order else None,
            'reversed_batch_ids': [batch.pk for batch in batches],
        }

    return _idempotent_command(
        request, 'reverse_received_purchase_order', handler,
        canonical_action=True,
    )


@csrf_exempt
@staff_required
def create_sales_order_command(request):
    # 创建仅生成可编辑草稿，不预留库存。
    if request.method != 'POST':
        return _json_response({'error': 'Method not allowed'}, status=405)

    def handler(body, operator, context):
        order = create_sales_order_draft(
            items=body.get('items'), operator=operator,
            customer_id=body.get('customer_id'),
            customer_name=str(body.get('customer_name') or '').strip(),
            payment_method_id=body.get('payment_method_id'),
            payment_manual=body.get('payment_manual') or {},
            customer_transport_fee_cny=body.get('customer_transport_fee_cny', 0),
            transport_payer=body.get('transport_payer'),
            note=_sales_note(body), agent_context=context,
            business_date=_required_business_date(body),
        )
        return _sales_order_response(order)

    return _idempotent_command(request, 'create_sales_order_draft', handler, canonical_action=True)


@csrf_exempt
@staff_required
def update_sales_order_command(request):
    # 草稿更新采用整单快照替换；确认后的订单不可修改。
    if request.method != 'POST':
        return _json_response({'error': 'Method not allowed'}, status=405)

    def handler(body, operator, context):
        order = update_sales_order_draft(
            sales_order_id=body.get('sales_order_id'), items=body.get('items'),
            operator=operator, customer_id=body.get('customer_id'),
            customer_name=str(body.get('customer_name') or '').strip(),
            payment_method_id=body.get('payment_method_id'),
            payment_manual=body.get('payment_manual') or {},
            customer_transport_fee_cny=body.get('customer_transport_fee_cny', 0),
            transport_payer=body.get('transport_payer'),
            note=_sales_note(body), agent_context=context,
            business_date=_required_business_date(body),
        )
        return _sales_order_response(order)

    return _idempotent_command(request, 'update_sales_order_draft', handler, canonical_action=True)


@csrf_exempt
@staff_required
def confirm_sales_order_command(request):
    # 确认订单是预留库存的唯一销售入口。
    if request.method != 'POST':
        return _json_response({'error': 'Method not allowed'}, status=405)

    def handler(body, operator, context):
        order = confirm_sales_order(
            sales_order_id=body.get('sales_order_id'), operator=operator,
            note=_sales_note(body), agent_context=context,
            business_date=_required_business_date(body),
        )
        return _sales_order_response(order)

    return _idempotent_command(request, 'confirm_sales_order', handler, canonical_action=True)


@csrf_exempt
@staff_required
def cancel_sales_order_command(request):
    # 取消仅处理未出库订单，并释放全部预留。
    if request.method != 'POST':
        return _json_response({'error': 'Method not allowed'}, status=405)

    def handler(body, operator, context):
        order = cancel_confirmed_sales_order(
            sales_order_id=body.get('sales_order_id'), operator=operator,
            note=_sales_note(body), agent_context=context,
            business_date=_required_business_date(body),
        )
        return _sales_order_response(order)

    return _idempotent_command(request, 'cancel_confirmed_sales_order', handler, canonical_action=True)


@csrf_exempt
@staff_required
def ship_sales_order_command(request):
    # 出库确认物理库存和 FIFO 成本，与收款相互独立。
    if request.method != 'POST':
        return _json_response({'error': 'Method not allowed'}, status=405)

    def handler(body, operator, context):
        order = ship_sales_order(
            order_id=body.get('sales_order_id'),
            business_date=_required_business_date(body), operator=operator,
            idempotency_key=context.idempotency_key, note=_sales_note(body),
            agent_context=context,
        )
        return _sales_order_response(order)

    return _idempotent_command(request, 'ship_sales_order', handler, canonical_action=True)


@csrf_exempt
@staff_required
def receive_sales_order_payment_command(request):
    # 一张订单只记录一次人民币整单收款。
    if request.method != 'POST':
        return _json_response({'error': 'Method not allowed'}, status=405)

    def handler(body, operator, context):
        receipt = receive_sales_order_payment(
            order_id=body.get('sales_order_id'), amount_cny=body.get('amount_cny'),
            fund_account=_fund_account_from_body(body),
            business_date=_required_business_date(body), operator=operator,
            idempotency_key=context.idempotency_key,
        )
        return _sales_order_response(receipt.sales_order)

    return _idempotent_command(request, 'receive_sales_order_payment', handler, canonical_action=True)


@csrf_exempt
@staff_required
def refund_sales_order_payment_command(request):
    # 退款撤销已取消或已退货订单的整笔原收款。
    if request.method != 'POST':
        return _json_response({'error': 'Method not allowed'}, status=405)

    def handler(body, operator, context):
        refund = refund_sales_order_payment(
            order_id=body.get('sales_order_id'),
            business_date=_required_business_date(body), operator=operator,
            idempotency_key=context.idempotency_key,
        )
        return _sales_order_response(refund.sales_order)

    return _idempotent_command(request, 'refund_sales_order_payment', handler, canonical_action=True)


@csrf_exempt
@staff_required
def return_sales_order_command(request):
    # 退货只接受完整已出库订单，并按原分配恢复批次成本。
    if request.method != 'POST':
        return _json_response({'error': 'Method not allowed'}, status=405)

    def handler(body, operator, context):
        reason = str(body.get('reason') or body.get('note') or '').strip()
        returned = return_sales_order(
            order_id=body.get('sales_order_id'),
            business_date=_required_business_date(body), operator=operator,
            idempotency_key=context.idempotency_key, reason=reason,
            agent_context=context,
        )
        return _sales_order_response(returned.sales_order)

    return _idempotent_command(request, 'return_sales_order', handler, canonical_action=True)


@csrf_exempt
@staff_required
def record_sales_transport_cost_command(request):
    # 实际人肉成本独立入账，并扣减订单贡献利润。
    if request.method != 'POST':
        return _json_response({'error': 'Method not allowed'}, status=405)

    def handler(body, operator, context):
        cost = record_sales_transport_cost(
            order_id=body.get('sales_order_id'),
            actual_cost_cny=body.get('actual_cost_cny'),
            fund_account=_fund_account_from_body(body),
            business_date=_required_business_date(body), operator=operator,
            idempotency_key=context.idempotency_key, note=_sales_note(body),
        )
        return _sales_order_response(cost.sales_order)

    return _idempotent_command(request, 'record_sales_transport_cost', handler, canonical_action=True)


@staff_required
def sales_orders_query(request):
    # Agent 按双状态或客户/单号查询销售单。
    if request.method != 'GET':
        return _json_response({'error': 'Method not allowed'}, status=405)
    orders = _sales_orders_queryset()
    fulfillment = request.GET.get('fulfillment_status', '').strip()
    payment = request.GET.get('payment_status', '').strip()
    if fulfillment:
        if fulfillment not in SalesOrder.FulfillmentStatus.values:
            return _json_response(
                {'error': '履约状态无效', 'code': 'invalid_fulfillment_status'},
                status=400,
            )
        orders = orders.filter(fulfillment_status=fulfillment)
    if payment:
        if payment not in SalesOrder.PaymentStatus.values:
            return _json_response(
                {'error': '收款状态无效', 'code': 'invalid_payment_status'},
                status=400,
            )
        orders = orders.filter(payment_status=payment)
    query = request.GET.get('q', '').strip()
    if query:
        match = re.fullmatch(r'SO-(\d+)', query, re.IGNORECASE)
        if match:
            orders = orders.filter(id=int(match.group(1)))
        elif query.isdigit():
            orders = orders.filter(Q(id=int(query)) | Q(customer_name__icontains=query))
        else:
            orders = orders.filter(customer_name__icontains=query)
    return _json_response({
        'results': [
            serialize_sales_order(order)
            for order in orders[:_parse_limit(request)]
        ],
    })


@staff_required
def sales_order_detail_query(request, order_id):
    # 详情包含完整销售事实与当前可执行动作。
    if request.method != 'GET':
        return _json_response({'error': 'Method not allowed'}, status=405)
    order = _sales_orders_queryset().filter(pk=order_id).first()
    if order is None:
        return _json_response({
            'error': '销售单不存在', 'code': 'sales_order_not_found',
            'details': {},
        }, status=404)
    return _json_response(_sales_order_response(order))


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
            business_date=_business_date_from_body(body),
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


@csrf_exempt
@staff_required
def reverse_stock_adjustment_command(request):
    # 撤销以结构化调整动作 ID 为边界，不接受批次级猜测。
    if request.method != 'POST':
        return _json_response({'error': 'Method not allowed'}, status=405)

    def handler(body, operator, context):
        action = reverse_stock_adjustment(
            adjustment_id=body.get('adjustment_id'),
            business_date=_required_business_date(body),
            operator=operator,
            idempotency_key=context.idempotency_key,
            reason=str(body.get('reason') or body.get('note') or '').strip(),
        )
        return {
            'adjustment': {
                'id': action.pk,
                'reversal_transaction_id': action.reversal_transaction_id,
                'reversed_at': action.reversed_at.isoformat() if action.reversed_at else None,
            },
        }

    return _idempotent_command(
        request, 'reverse_stock_adjustment', handler,
        canonical_action=True,
    )


@staff_required
def inventory_audit_query(request):
    # 审计只读全量库存事实，不执行自动修复。
    if request.method != 'GET':
        return _json_response({'error': 'Method not allowed'}, status=405)
    result = audit_inventory()
    return _json_response({
        'ok': result.ok,
        'issue_count': len(result.issues),
        'issues': [
            {
                'code': issue.code,
                'message': issue.message,
                'batch_id': issue.batch_id,
                'order_id': issue.order_id,
                'allocation_id': issue.allocation_id,
                'movement_id': issue.movement_id,
            }
            for issue in result.issues
        ],
    })


@staff_required
def business_report(request):
    # 报表只读双状态和已发生的出库、收退款事实，不再依赖旧 status。
    if request.method != 'GET':
        return _json_response({'error': 'Method not allowed'}, status=405)
    fulfillment_counts = {
        status: SalesOrder.objects.filter(fulfillment_status=status).count()
        for status in SalesOrder.FulfillmentStatus.values
    }
    payment_counts = {
        status: SalesOrder.objects.filter(payment_status=status).count()
        for status in SalesOrder.PaymentStatus.values
    }
    shipment_totals = SalesShipment.objects.aggregate(
        revenue=Sum('sales_order__amount_due_cny'),
        fifo_cost=Sum('fifo_cost_cny'),
        contribution_profit=Sum('sales_order__contribution_profit_cny'),
    )
    return_totals = SalesReturn.objects.aggregate(
        revenue=Sum('amount_cny'),
        fifo_cost=Sum('fifo_cost_cny'),
    )
    returned_revenue = return_totals['revenue'] or Decimal('0.00')
    returned_cost = return_totals['fifo_cost'] or Decimal('0.00')
    receipt_total = (
        SalesReceipt.objects.aggregate(total=Sum('amount_cny'))['total']
        or Decimal('0.00')
    )
    refund_total = (
        SalesRefund.objects.aggregate(total=Sum('amount_cny'))['total']
        or Decimal('0.00')
    )
    stock_value = PurchaseBatch.objects.filter(remaining__gt=0).aggregate(
        qty=Sum('remaining'),
    )
    movement_counts = StockMovement.objects.values(
        'movement_type',
    ).annotate(count=Count('id'))
    return _json_response({
        'orders': {
            'fulfillment': fulfillment_counts,
            'payment': payment_counts,
        },
        'sales': {
            'shipped_amount_due_cny': decimal_to_number(
                (shipment_totals['revenue'] or Decimal('0.00')) - returned_revenue,
            ),
            'fifo_cost_cny': decimal_to_number(
                (shipment_totals['fifo_cost'] or Decimal('0.00')) - returned_cost,
            ),
            'contribution_profit_cny': decimal_to_number(
                (shipment_totals['contribution_profit'] or Decimal('0.00'))
                - (returned_revenue - returned_cost),
            ),
            'received_cny': decimal_to_number(receipt_total),
            'refunded_cny': decimal_to_number(refund_total),
            'net_received_cny': decimal_to_number(receipt_total - refund_total),
            'preorder_items': SalesOrderItem.objects.exclude(
                sales_order__fulfillment_status=SalesOrder.FulfillmentStatus.CANCELLED,
            ).filter(fulfillment_type='preorder').count(),
        },
        'stock': {
            'available_quantity': stock_value['qty'] or 0,
        },
        'stock_movements': {
            row['movement_type']: row['count'] for row in movement_counts
        },
        'recent_agent_commands': [
            {
                'command_name': record.command_name,
                'operator_id': record.operator_id,
                'agent_name': record.agent_name,
                'agent_run_id': record.agent_run_id,
                'agent_request_id': record.agent_request_id,
                'status_code': record.status_code,
                'created_at': record.created_at.isoformat(),
            }
            for record in IdempotencyRecord.objects.order_by('-created_at')[:20]
        ],
        'recent_order_events': [
            {
                'sales_order_id': event.sales_order_id,
                'command_name': event.command_name,
                'operator_id': event.operator_id,
                'agent_name': event.agent_name,
                'note': event.note,
                'created_at': event.created_at.isoformat(),
            }
            for event in OrderEvent.objects.order_by('-created_at')[:20]
        ],
    })
