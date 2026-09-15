"""Format and schedule Telegram notifications for committed business facts."""
from __future__ import annotations

import html
import logging
from decimal import Decimal

from django.conf import settings
from django.db import transaction

from .transport import dispatch, send_evidence_image, send_text


logger = logging.getLogger(__name__)


def _value(value, *, max_chars: int | None = None) -> str:
    raw = str(value or "")
    if max_chars is not None and len(raw) > max_chars:
        raw = raw[:max_chars - 1] + "…"
    return html.escape(raw, quote=True)


def _money(value) -> str:
    try:
        return f"¥{Decimal(value):,.2f}"
    except Exception:
        return "¥0.00"


def _operator_name(operator) -> str:
    try:
        return operator.get_full_name().strip() or str(operator)
    except Exception:
        return "未知"


def _site_url() -> str:
    configured = str(getattr(settings, "INTERNAL_SITE_URL", "") or "").strip().rstrip("/")
    if configured:
        return configured
    return str(getattr(settings, "PRIVNOTE_BASE_URL", "") or "").strip().rstrip("/")


def _sales_url() -> str:
    base = _site_url()
    return f"{base}/sales" if base else ""


def _item_lines(items) -> list[str]:
    lines = []
    values = list(items)
    for item in values[:20]:
        cigar = getattr(item, "cigar", None)
        name = getattr(cigar, "name", "") or getattr(cigar, "english_name", "") or f"商品#{item.cigar_id}"
        if item.sale_unit == "box" and item.sale_quantity and item.box_size:
            amount = f"{item.sale_quantity}盒（{item.box_size}支/盒）"
        else:
            amount = f"{item.quantity}支"
        lines.append(f"• {_value(name)} × {_value(amount)}")
    if len(values) > 20:
        lines.append(f"• 另有 {len(values) - 20} 项")
    return lines


def _order_snapshot(order, operator, *, items=None, account_name="", amount=None, reason="") -> dict:
    if items is None:
        items = list(order.items.select_related("cigar").order_by("id"))
    return {
        "order_number": order.order_number,
        "customer_name": order.customer_name or (order.customer.name if order.customer_id else "散客"),
        "items": tuple(_item_lines(items)),
        "amount_due": str(order.amount_due_cny),
        "payment_status": order.payment_status,
        "operator": _operator_name(operator),
        "account_name": account_name,
        "amount": str(amount if amount is not None else order.amount_due_cny),
        "reason": str(reason or "").strip(),
        "url": _sales_url(),
    }


def _render_order(kind: str, snapshot: dict) -> str:
    titles = {
        "waiting_shipment": "📦 <b>待出库提醒</b>",
        "shipped": "🚚 <b>出库成功</b>",
        "received": "💰 <b>收款成功</b>",
        "cancelled": "🛑 <b>订单已取消</b>",
    }
    paid = "已收款" if snapshot["payment_status"] == "paid" else "未收款"
    lines = [
        titles[kind],
        f"订单：<b>{_value(snapshot['order_number'])}</b>",
        f"客户：{_value(snapshot['customer_name'])}",
    ]
    if kind == "received":
        lines.extend([
            f"实收：<b>{_money(snapshot['amount'])}</b>",
            f"账户：{_value(snapshot['account_name'])}",
        ])
    else:
        lines.extend(snapshot["items"])
        lines.extend([
            f"应收：<b>{_money(snapshot['amount_due'])}</b>",
            f"收款：{paid}",
        ])
    if kind == "cancelled" and snapshot["reason"]:
        lines.append(f"原因：{_value(snapshot['reason'])}")
    lines.append(f"操作人：{_value(snapshot['operator'])}")
    if snapshot["url"]:
        lines.append(f'<a href="{_value(snapshot["url"])}">打开销售页面</a>')
    message = "\n".join(lines)
    if len(message) <= 4000:
        return message

    # Telegram limits messages to 4096 characters. Fall back to a compact,
    # still-valid HTML summary instead of slicing through a tag or entity.
    compact = [
        titles[kind],
        f"订单：<b>{_value(snapshot['order_number'], max_chars=80)}</b>",
        f"客户：{_value(snapshot['customer_name'], max_chars=100)}",
    ]
    if kind == "received":
        compact.extend([
            f"实收：<b>{_money(snapshot['amount'])}</b>",
            f"账户：{_value(snapshot['account_name'], max_chars=100)}",
        ])
    else:
        compact.extend([
            "商品明细较长，请在网站查看",
            f"应收：<b>{_money(snapshot['amount_due'])}</b>",
            f"收款：{paid}",
        ])
    if kind == "cancelled" and snapshot["reason"]:
        compact.append(f"原因：{_value(snapshot['reason'], max_chars=160)}")
    compact.append(f"操作人：{_value(snapshot['operator'], max_chars=100)}")
    if snapshot["url"]:
        compact.append(f'<a href="{_value(snapshot["url"], max_chars=500)}">打开销售页面</a>')
    return "\n".join(compact)


def _after_commit(job, chat_id: str) -> None:
    transaction.on_commit(lambda: dispatch(job, chat_id=chat_id), robust=True)


def schedule_order_notification(kind: str, order, operator, *, items=None, account_name="", amount=None, reason="") -> None:
    """Capture ORM data now and send only after the surrounding commit."""
    try:
        snapshot = _order_snapshot(
            order, operator, items=items, account_name=account_name,
            amount=amount, reason=reason,
        )
        message = _render_order(kind, snapshot)
        chat_id = str(getattr(settings, "TELEGRAM_BUSINESS_CHAT_ID", "") or "")
        _after_commit(lambda: send_text(chat_id, message), chat_id)
    except Exception as exc:
        logger.error("Could not schedule %s notification (%s)", kind, type(exc).__name__)


def schedule_payment_submission_notification(submission, order, attachment_paths) -> None:
    try:
        chat_id = str(getattr(settings, "TELEGRAM_BUSINESS_CHAT_ID", "") or "")
        paths = tuple(str(path) for path in attachment_paths)
        message = "\n".join([
            "🧾 <b>付款凭证待核实</b>",
            f"订单：<b>{_value(order.order_number)}</b>",
            f"客户：{_value(order.customer_name or (order.customer.name if order.customer_id else '散客'))}",
            f"应收：<b>{_money(submission.amount_cny)}</b>",
            f"截图：{len(paths)} 张",
            "状态：待工作人员核实，尚未正式收款",
            *( [f'<a href="{_value(_sales_url())}">打开销售页面</a>'] if _sales_url() else [] ),
        ])

        def send() -> None:
            send_text(chat_id, message)
            for path in paths:
                send_evidence_image(chat_id, path)

        _after_commit(send, chat_id)
    except Exception as exc:
        logger.error("Could not schedule payment submission notification (%s)", type(exc).__name__)
