"""Staff JSON API for the sales-order draft workflow."""
from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import date, timedelta
from decimal import Decimal

from django.db import IntegrityError, OperationalError

from django.db import transaction
from django.db.models import Count, Max, Q, Sum
from django.http import JsonResponse
from django.utils import timezone

from accounting.models import FundAccount
from accounting.guards import Day1IncompleteError
from accounting.services import LedgerError

from .models import Customer, IdempotencyRecord, SalesOrder


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


class ActionConflictError(OrderServiceError):
    """动作因订单当前状态或事实冲突而无法执行。"""


class ActionInputError(OrderServiceError):
    """动作请求参数无效。"""


from .sales_accounting import (
    ship_sales_order, receive_sales_order_payment, refund_sales_order_payment,
    record_sales_transport_cost, return_sales_order,
)


def _json(payload, status=200):
    return JsonResponse(payload, status=status, json_dumps_params={"ensure_ascii": False})


def _error(message, status, details=None, code=None):
    payload = {"error": message, "code": code or "input_error", "details": details or {}}
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
        except ActionInputError as exc:
            return _error(str(exc), 400, getattr(exc, "details", None))
        except ActionConflictError as exc:
            return _error(str(exc), 409, getattr(exc, "details", None))
        except Day1IncompleteError as exc:
            return _error(str(exc), 409, getattr(exc, "details", None), exc.code)
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
        return SalesOrder.objects.select_related(
            "customer", "sales_shipment", "sales_receipt", "sales_refund",
            "sales_return", "sales_transport_cost",
        ).prefetch_related("privnote_set").get(id=order_id)
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
        transport_payer=body.get("transport_payer"),
        note=_optional_note(body).strip(), agent_context=context,
    ))


def _iso_date_query(request, name):
    value = request.GET.get(name, "").strip()
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ActionInputError(f"{name} 必须是 ISO 日期") from exc


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
    orders = SalesOrder.objects.select_related(
        "customer", "sales_shipment", "sales_receipt", "sales_refund",
        "sales_return", "sales_transport_cost",
    ).prefetch_related(
        "items__cigar", "items__allocations__purchase_batch", "privnote_set"
    ).all()
    fulfillment = request.GET.get("fulfillment_status", "").strip()
    payment = request.GET.get("payment_status", "").strip()
    try:
        date_from = _iso_date_query(request, "date_from")
        date_to = _iso_date_query(request, "date_to")
    except ActionInputError as exc:
        return _error(str(exc), 400)
    if date_from and date_to and date_from > date_to:
        return _error("date_from 不能晚于 date_to", 400)
    if date_from:
        orders = orders.filter(created_at__date__gte=date_from)
    if date_to:
        orders = orders.filter(created_at__date__lte=date_to)
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


def _customer_payload(customer, include_orders=False):
    orders = SalesOrder.objects.filter(customer=customer).order_by("-created_at")
    has_summary = all(hasattr(customer, field) for field in (
        "order_count", "active_order_count", "total_amount_cny",
    ))
    if has_summary:
        order_count = customer.order_count or 0
        active_order_count = customer.active_order_count or 0
        total_amount_cny = customer.total_amount_cny or 0
    else:
        active_orders = orders.filter(fulfillment_status__in=(
            SalesOrder.FulfillmentStatus.CONFIRMED,
            SalesOrder.FulfillmentStatus.SHIPPED,
        ))
        summary = active_orders.aggregate(order_count=Count("id"), total_amount_cny=Sum("amount_due_cny"))
        order_count = orders.count()
        active_order_count = summary["order_count"] or 0
        total_amount_cny = summary["total_amount_cny"] or 0
    payload = {
        "id": customer.id,
        "name": customer.name,
        "phone": customer.phone,
        "remark": customer.remark,
        "created_at": customer.created_at.isoformat(),
        "deleted_at": customer.deleted_at.isoformat() if customer.deleted_at else None,
        "order_count": order_count,
        "active_order_count": active_order_count,
        "total_amount_cny": float(total_amount_cny),
        "last_order_at": (
            customer.last_order_at.isoformat()
            if getattr(customer, "last_order_at", None) else None
        ),
    }
    if include_orders:
        recent_orders = orders.select_related(
            "customer", "sales_shipment", "sales_receipt", "sales_refund",
            "sales_return", "sales_transport_cost",
        ).prefetch_related(
            "items__cigar", "items__allocations__purchase_batch", "privnote_set",
        )[:20]
        payload["recent_orders"] = [serialize_sales_order(order) for order in recent_orders]
    return payload


def _customer_values(body):
    name = body.get("name", "")
    phone = body.get("phone", "")
    remark = body.get("remark", "")
    if not isinstance(name, str) or not name.strip():
        raise ActionInputError("客户姓名不能为空", details={"name": "不能为空"})
    if not isinstance(phone, str):
        raise ActionInputError("客户电话必须是字符串", details={"phone": "必须是字符串"})
    if not isinstance(remark, str):
        raise ActionInputError("客户备注必须是字符串", details={"remark": "必须是字符串"})
    name = name.strip()
    phone = phone.strip()
    if len(name) > 200:
        raise ActionInputError("客户姓名不能超过 200 个字符", details={"name": "不能超过 200 个字符"})
    if len(phone) > 50:
        raise ActionInputError("客户电话不能超过 50 个字符", details={"phone": "不能超过 50 个字符"})
    if len(remark) > 2000:
        raise ActionInputError("客户备注不能超过 2000 个字符", details={"remark": "不能超过 2000 个字符"})
    return name, phone, remark


def sales_customers(request):
    denied = _denied(request)
    if denied:
        return denied
    method_error = _method(request, {"GET", "POST"})
    if method_error:
        return method_error
    if request.method == "GET":
        query = request.GET.get("q", "").strip()
        activity = request.GET.get("activity", "all").strip()
        if activity not in {"all", "with_orders", "without_orders", "recent"}:
            return _error("客户活跃度筛选无效", 400)
        try:
            limit = int(request.GET.get("limit", "50"))
            if not 1 <= limit <= 100:
                raise ValueError
        except (TypeError, ValueError):
            return _error("limit 必须是 1 到 100 之间的整数", 400)
        recent_since = timezone.now() - timedelta(days=30)
        active_statuses = (
            SalesOrder.FulfillmentStatus.CONFIRMED,
            SalesOrder.FulfillmentStatus.SHIPPED,
        )
        stats = Customer.objects.filter(deleted_at__isnull=True).aggregate(
            customer_count=Count("id", distinct=True),
            with_orders_count=Count(
                "id", filter=Q(salesorder__isnull=False), distinct=True,
            ),
            recent_customer_count=Count(
                "id", filter=Q(salesorder__created_at__gte=recent_since), distinct=True,
            ),
            total_amount_cny=Sum(
                "salesorder__amount_due_cny",
                filter=Q(salesorder__fulfillment_status__in=active_statuses),
            ),
        )
        customers = Customer.objects.filter(deleted_at__isnull=True).annotate(
            order_count=Count("salesorder", distinct=True),
            active_order_count=Count(
                "salesorder",
                filter=Q(salesorder__fulfillment_status__in=(
                    SalesOrder.FulfillmentStatus.CONFIRMED,
                    SalesOrder.FulfillmentStatus.SHIPPED,
                )),
                distinct=True,
            ),
            total_amount_cny=Sum(
                "salesorder__amount_due_cny",
                filter=Q(salesorder__fulfillment_status__in=(
                    SalesOrder.FulfillmentStatus.CONFIRMED,
                    SalesOrder.FulfillmentStatus.SHIPPED,
                )),
            ),
            last_order_at=Max("salesorder__created_at"),
            recent_order_count=Count(
                "salesorder",
                filter=Q(salesorder__created_at__gte=recent_since),
                distinct=True,
            ),
        )
        if query:
            customers = customers.filter(Q(name__icontains=query) | Q(phone__icontains=query))
        if activity == "with_orders":
            customers = customers.filter(order_count__gt=0)
        elif activity == "without_orders":
            customers = customers.filter(order_count=0)
        elif activity == "recent":
            customers = customers.filter(recent_order_count__gt=0)
        return _json({
            "results": [_customer_payload(customer) for customer in customers[:limit]],
            "stats": {
                "customer_count": stats["customer_count"] or 0,
                "with_orders_count": stats["with_orders_count"] or 0,
                "recent_customer_count": stats["recent_customer_count"] or 0,
                "total_amount_cny": float(stats["total_amount_cny"] or 0),
            },
        })

    def handler(body, operator, context):
        name, phone, remark = _customer_values(body)
        if Customer.objects.filter(name=name).exists():
            raise ActionConflictError("客户姓名已存在", details={"name": "客户姓名已存在"})
        try:
            with transaction.atomic():
                customer = Customer.objects.create(name=name, phone=phone, remark=remark)
        except IntegrityError as exc:
            raise ActionConflictError(
                "客户姓名已存在", details={"name": "客户姓名已存在"}
            ) from exc
        return {"customer": _customer_payload(customer, include_orders=True)}

    return _write(request, "create_sales_customer", handler, 201)


def sales_customer_detail(request, customer_id):
    denied = _denied(request)
    if denied:
        return denied
    method_error = _method(request, {"GET", "PATCH", "DELETE"})
    if method_error:
        return method_error
    try:
        customer = Customer.objects.get(pk=customer_id)
    except Customer.DoesNotExist:
        return _error("客户不存在", 404)
    if request.method == "GET":
        if customer.deleted_at:
            return _error("客户不存在", 404)
        return _json({"customer": _customer_payload(customer, include_orders=True)})

    def handler(body, operator, context):
        locked = Customer.objects.select_for_update().get(pk=customer_id)
        if locked.deleted_at:
            raise ActionConflictError("客户已删除")
        if request.method == "DELETE":
            locked.deleted_at = timezone.now()
            locked.save(update_fields=["deleted_at"])
            return {"customer": _customer_payload(locked, include_orders=True)}
        name, phone, remark = _customer_values(body)
        if Customer.objects.exclude(pk=locked.pk).filter(name=name).exists():
            raise ActionConflictError("客户姓名已存在", details={"name": "客户姓名已存在"})
        locked.name = name
        locked.phone = phone
        locked.remark = remark
        try:
            with transaction.atomic():
                locked.save(update_fields=["name", "phone", "remark"])
        except IntegrityError as exc:
            raise ActionConflictError(
                "客户姓名已存在", details={"name": "客户姓名已存在"}
            ) from exc
        return {"customer": _customer_payload(locked, include_orders=True)}

    command = "delete_sales_customer" if request.method == "DELETE" else "update_sales_customer"
    return _write(request, command, handler)


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
            transport_payer=body.get("transport_payer"),
            note=_optional_note(body).strip(), agent_context=context,
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
            note=_optional_note(body).strip(), agent_context=context,
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
            note=_optional_note(body).strip(), agent_context=context,
        ))
    return _write(request, "cancel_confirmed_sales_order", handler)


def _business_date(body):
    value = body.get("business_date")
    try:
        parsed = date.fromisoformat(str(value))
    except (TypeError, ValueError):
        raise ActionInputError("business_date 必须是 ISO 日期")
    return parsed


def _optional_note(body):
    """正式动作备注只接受文本，避免容器被静默字符串化。"""
    value = body.get("note", "")
    if not isinstance(value, str):
        raise ActionInputError(
            "note 必须是字符串", details={"note": "必须是字符串"},
        )
    return value


def _required_reason(body):
    value = body.get("reason", body.get("note", ""))
    if not isinstance(value, str) or not value.strip():
        raise ActionInputError("reason 必须是非空字符串")
    return value.strip()


def _account(body, operator):
    value = body.get("fund_account_id")
    if type(value) is not int or value <= 0:
        raise ActionInputError("fund_account_id 必须是正整数")
    account_id = value
    try:
        return FundAccount.objects.get(pk=account_id)
    except FundAccount.DoesNotExist:
        raise ActionInputError("资金账户不存在")


def _action(request, order_id, command, handler):
    denied = _denied(request)
    if denied:
        return denied
    method_error = _method(request, {"POST"})
    if method_error:
        return method_error
    if _get_order(order_id) is None:
        return _error("销售单不存在", 404)
    def action_handler(body, operator, context):
        try:
            return _response(handler(body, operator, context))
        except ActionInputError:
            raise
        except OrderServiceError as exc:
            raise ActionConflictError(str(exc), details=exc.details)
    return _write(request, command, action_handler)


def sales_order_ship(request, order_id):
    return _action(request, order_id, "ship_sales_order", lambda body, operator, context: ship_sales_order(
        order_id=order_id, business_date=_business_date(body), operator=operator,
        idempotency_key=context.idempotency_key, note=_optional_note(body),
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


def sales_order_return(request, order_id):
    return _action(request, order_id, "return_sales_order", lambda body, operator, context: return_sales_order(
        order_id=order_id, business_date=_business_date(body), operator=operator,
        idempotency_key=context.idempotency_key, reason=_required_reason(body),
        agent_context=context,
    ).sales_order)


def sales_order_transport_cost(request, order_id):
    return _action(request, order_id, "record_sales_transport_cost", lambda body, operator, context: record_sales_transport_cost(
        order_id=order_id, actual_cost_cny=body.get("actual_cost_cny"),
        fund_account=_account(body, operator), business_date=_business_date(body),
        operator=operator, idempotency_key=context.idempotency_key,
        note=_optional_note(body),
    ).sales_order)
