"""Staff JSON API for the sales-order draft workflow."""
from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import date
from decimal import Decimal

from django.db import IntegrityError, OperationalError

from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse

from accounting.models import FundAccount
from accounting.services import LedgerError

from .models import IdempotencyRecord, SalesOrder
from .services import (
    AgentContext,
    InsufficientStockError,
    OrderServiceError,
    cancel_confirmed_sales_order,
    confirm_sales_order,
    create_sales_order_draft,
    serialize_sales_order,
    update_sales_order_draft,
)
from .sales_accounting import (
    ship_sales_order, receive_sales_order_payment, refund_sales_order_payment,
    record_sales_transport_cost,
)


def _json(payload, status=200):
    return JsonResponse(payload, status=status, json_dumps_params={"ensure_ascii": False})


def _error(message, status, details=None):
    payload = {"error": message}
    if details:
        payload["details"] = details
    return _json(payload, status=status)


def _staff(request):
    return bool(getattr(request.user, "is_authenticated", False) and request.user.is_staff)


def _method(request, allowed):
    if request.method not in allowed:
        return _error("不支持的请求方法", 405)
    return None


def _body(request):
    try:
        value = json.loads(request.body.decode("utf-8") or "{}")
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise OrderServiceError("请求体必须是有效 JSON")
    if not isinstance(value, dict):
        raise OrderServiceError("请求体必须是 JSON 对象")
    return value


def _request_context(request, command):
    key = str(request.headers.get("Idempotency-Key", "")).strip()
    if not key:
        raise OrderServiceError("写请求必须提供 Idempotency-Key（幂等键）")
    return AgentContext(agent_name="web", command_name=command, idempotency_key=key)


def _request_hash(body, scope=""):
    value = json.dumps({"scope": scope, "body": body}, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _write(request, command, handler, success_status=200):
    try:
        body = _body(request)
        context = _request_context(request, command)
    except OrderServiceError as exc:
        return _error(str(exc), 400, exc.details)
    request_hash = _request_hash(body, request.path)
    for attempt in range(8):
        try:
            with transaction.atomic():
                record = IdempotencyRecord.objects.select_for_update().filter(key=context.idempotency_key).first()
                if record:
                    if record.command_name != command or record.request_hash != request_hash:
                        return _error("Idempotency-Key 已用于不同请求", 409)
                    if record.status_code:
                        if record.operator_id != request.user.pk:
                            return _error("幂等键属于其他操作人", 409)
                        return _json(record.response_body, record.status_code)
                    # Another transaction currently owns the claim.  SQLite has no
                    # useful row lock here; retry after its short transaction commits.
                    raise OperationalError("idempotency claim is in progress")
                try:
                    with transaction.atomic():
                        IdempotencyRecord.objects.create(
                            key=context.idempotency_key,
                            command_name=command,
                            request_hash=request_hash,
                            request_body=body,
                            response_body={},
                            status_code=0,
                            operator=request.user,
                            agent_name=context.agent_name,
                            agent_run_id=context.agent_run_id,
                            agent_request_id=context.agent_request_id,
                        )
                except IntegrityError:
                    raise OperationalError("idempotency claim is in progress")
                response_body = handler(body, request.user, context)
                IdempotencyRecord.objects.filter(key=context.idempotency_key).update(
                    response_body=response_body, status_code=success_status,
                )
            return _json(response_body, success_status)
        except InsufficientStockError as exc:
            return _error(str(exc), 409, exc.details)
        except SalesOrder.DoesNotExist:
            return _error("销售单不存在", 404)
        except (OrderServiceError, LedgerError) as exc:
            return _error(str(exc), 400, getattr(exc, "details", None))
        except OperationalError as exc:
            if "locked" not in str(exc).lower() and "in progress" not in str(exc).lower():
                raise
            if attempt == 7:
                return _error("请求正在处理中，请稍后重试", 409)
            time.sleep(0.02 * (attempt + 1))
    return _error("请求正在处理中，请稍后重试", 409)


def _denied(request):
    return None if _staff(request) else _error("仅限工作人员访问", 403)


def _get_order(order_id):
    try:
        return SalesOrder.objects.select_related("customer", "sales_shipment", "sales_receipt", "sales_refund", "sales_transport_cost").get(id=order_id)
    except (SalesOrder.DoesNotExist, ValueError, TypeError):
        return None


def _response(order):
    return {"sales_order": serialize_sales_order(order)}


def _create_handler(body, operator, context):
    return _response(create_sales_order_draft(
        items=body.get("items"), operator=operator,
        customer_id=body.get("customer_id"),
        customer_name=str(body.get("customer_name") or "").strip(),
        payment_method_id=body.get("payment_method_id"),
        payment_manual=body.get("payment_manual") or {},
        customer_transport_fee_cny=body.get("customer_transport_fee_cny", 0),
        note=str(body.get("note") or "").strip(), agent_context=context,
    ))


def sales_orders(request):
    denied = _denied(request)
    if denied:
        return denied
    method_error = _method(request, {"GET", "POST"})
    if method_error:
        return method_error
    if request.method == "POST":
        return _write(request, "create_sales_order_draft", _create_handler, 201)
    try:
        limit = int(request.GET.get("limit", "30"))
        if not 1 <= limit <= 100:
            raise ValueError
    except (TypeError, ValueError):
        return _error("limit 必须是 1 到 100 之间的整数", 400)
    orders = SalesOrder.objects.select_related("customer", "sales_shipment", "sales_receipt", "sales_refund", "sales_transport_cost").prefetch_related(
        "items__cigar", "items__allocations__purchase_batch"
    ).all()
    fulfillment = request.GET.get("fulfillment_status", "").strip()
    payment = request.GET.get("payment_status", "").strip()
    if fulfillment:
        if fulfillment not in SalesOrder.FulfillmentStatus.values:
            return _error("履约状态无效", 400)
        orders = orders.filter(fulfillment_status=fulfillment)
    if payment:
        if payment not in SalesOrder.PaymentStatus.values:
            return _error("付款状态无效", 400)
        orders = orders.filter(payment_status=payment)
    query = request.GET.get("q", "").strip()
    if query:
        if query.isdigit():
            orders = orders.filter(Q(customer_name__icontains=query) | Q(id=int(query)))
        else:
            order_match = re.fullmatch(r"SO-(\d+)", query, re.IGNORECASE)
            if order_match:
                orders = orders.filter(id=int(order_match.group(1)))
            else:
                orders = orders.filter(customer_name__icontains=query)
    return _json({"results": [serialize_sales_order(order) for order in orders[:limit]]})


def sales_order_detail(request, order_id):
    denied = _denied(request)
    if denied:
        return denied
    method_error = _method(request, {"GET", "PATCH"})
    if method_error:
        return method_error
    order = _get_order(order_id)
    if order is None:
        return _error("销售单不存在", 404)
    if request.method == "GET":
        return _json(_response(order))

    def handler(body, operator, context):
        return _response(update_sales_order_draft(
            sales_order_id=order.id, items=body.get("items"), operator=operator,
            customer_id=body.get("customer_id"),
            customer_name=str(body.get("customer_name") or "").strip(),
            payment_method_id=body.get("payment_method_id"),
            payment_manual=body.get("payment_manual") or {},
            customer_transport_fee_cny=body.get("customer_transport_fee_cny", 0),
            note=str(body.get("note") or "").strip(), agent_context=context,
        ))
    return _write(request, "update_sales_order_draft", handler)


def sales_order_confirm(request, order_id):
    denied = _denied(request)
    if denied:
        return denied
    method_error = _method(request, {"POST"})
    if method_error:
        return method_error
    if _get_order(order_id) is None:
        return _error("销售单不存在", 404)

    def handler(body, operator, context):
        return _response(confirm_sales_order(
            sales_order_id=order_id, operator=operator,
            note=str(body.get("note") or "").strip(), agent_context=context,
        ))
    return _write(request, "confirm_sales_order", handler)


def sales_order_cancel(request, order_id):
    denied = _denied(request)
    if denied:
        return denied
    method_error = _method(request, {"POST"})
    if method_error:
        return method_error
    if _get_order(order_id) is None:
        return _error("销售单不存在", 404)

    def handler(body, operator, context):
        return _response(cancel_confirmed_sales_order(
            sales_order_id=order_id, operator=operator,
            note=str(body.get("note") or "").strip(), agent_context=context,
        ))
    return _write(request, "cancel_confirmed_sales_order", handler)


def _business_date(body):
    value = body.get("business_date")
    try:
        parsed = date.fromisoformat(str(value))
    except (TypeError, ValueError):
        raise OrderServiceError("business_date 必须是 ISO 日期")
    return parsed


def _account(body, operator):
    try:
        account_id = int(body.get("fund_account_id"))
    except (TypeError, ValueError):
        raise OrderServiceError("fund_account_id 必须是整数")
    try:
        return FundAccount.objects.get(pk=account_id)
    except FundAccount.DoesNotExist:
        raise OrderServiceError("资金账户不存在")


def _action(request, order_id, command, handler):
    denied = _denied(request)
    if denied:
        return denied
    method_error = _method(request, {"POST"})
    if method_error:
        return method_error
    if _get_order(order_id) is None:
        return _error("销售单不存在", 404)
    return _write(request, command, lambda body, operator, context: _response(handler(body, operator, context)))


def sales_order_ship(request, order_id):
    return _action(request, order_id, "ship_sales_order", lambda body, operator, context: ship_sales_order(
        order_id=order_id, business_date=_business_date(body), operator=operator,
        idempotency_key=context.idempotency_key, note=str(body.get("note") or ""),
    ))


def sales_order_receive(request, order_id):
    return _action(request, order_id, "receive_sales_order_payment", lambda body, operator, context: receive_sales_order_payment(
        order_id=order_id, amount_cny=body.get("amount_cny"),
        fund_account=_account(body, operator), business_date=_business_date(body),
        operator=operator, idempotency_key=context.idempotency_key,
    ).sales_order)


def sales_order_refund(request, order_id):
    return _action(request, order_id, "refund_sales_order_payment", lambda body, operator, context: refund_sales_order_payment(
        order_id=order_id, business_date=_business_date(body), operator=operator,
        idempotency_key=context.idempotency_key,
    ).sales_order)


def sales_order_transport_cost(request, order_id):
    return _action(request, order_id, "record_sales_transport_cost", lambda body, operator, context: record_sales_transport_cost(
        order_id=order_id, actual_cost_cny=body.get("actual_cost_cny"),
        fund_account=_account(body, operator), business_date=_business_date(body),
        operator=operator, idempotency_key=context.idempotency_key,
        note=str(body.get("note") or ""),
    ).sales_order)
