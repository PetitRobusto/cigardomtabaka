"""Logging handler that sends rate-limited, redacted error summaries."""
from __future__ import annotations

import hashlib
import html
import logging
import os
import re
import threading
import time
import uuid

from django.conf import settings

from .transport import dispatch, send_text


logger = logging.getLogger(__name__)
_seen: dict[str, float] = {}
_seen_lock = threading.Lock()
_SECRET_PATTERN = re.compile(
    r"(?i)(authorization|password|passwd|secret|token|api[_-]?key)\s*[:=]\s*[^\s,;]+"
)
_BOT_TOKEN_PATTERN = re.compile(r"\b\d{6,12}:[A-Za-z0-9_-]{20,}\b")
_URL_CREDENTIAL_PATTERN = re.compile(r"(https?://)[^/@\s]+@", re.IGNORECASE)


def _safe_message(record: logging.LogRecord) -> str:
    value = str(record.getMessage()).replace("\n", " ").replace("\r", " ")
    value = _SECRET_PATTERN.sub(r"\1=[redacted]", value)
    value = _BOT_TOKEN_PATTERN.sub("[redacted-bot-token]", value)
    value = _URL_CREDENTIAL_PATTERN.sub(r"\1[redacted]@", value)
    return value[:300]


def _location(record: logging.LogRecord) -> str:
    if record.exc_info and record.exc_info[2]:
        tb = record.exc_info[2]
        while tb.tb_next:
            tb = tb.tb_next
        return f"{os.path.basename(tb.tb_frame.f_code.co_filename)}:{tb.tb_lineno} in {tb.tb_frame.f_code.co_name}"
    return f"{os.path.basename(record.pathname)}:{record.lineno}"


class TelegramErrorHandler(logging.Handler):
    """Notify the configured owner without letting notification logs recurse."""

    def emit(self, record: logging.LogRecord) -> None:
        # Notification transport failures must not recurse. Django security
        # errors (especially hostile Host headers) are internet background
        # noise rather than application failures and would otherwise page the
        # owner at ERROR level.
        if not getattr(settings, "TELEGRAM_NOTIFICATIONS_ENABLED", True):
            return
        if record.name.startswith(("internal_notifications", "django.security")):
            return
        try:
            request = getattr(record, "request", None)
            path = getattr(request, "path", "") if request is not None else ""
            method = getattr(request, "method", "") if request is not None else ""
            exception_name = record.exc_info[0].__name__ if record.exc_info else ""
            location = _location(record)
            fingerprint = hashlib.sha256(
                f"{record.name}|{exception_name}|{location}|{method}|{path}".encode("utf-8")
            ).hexdigest()
            now = time.monotonic()
            cooldown = float(getattr(settings, "TELEGRAM_ERROR_COOLDOWN_SECONDS", 300))
            with _seen_lock:
                previous = _seen.get(fingerprint)
                if previous is not None and now - previous < cooldown:
                    return
                _seen[fingerprint] = now
                if len(_seen) > 256:
                    oldest = sorted(_seen, key=_seen.get)[:64]
                    for key in oldest:
                        _seen.pop(key, None)
            event_id = uuid.uuid4().hex[:12]
            lines = [
                "🚨 <b>生产应用错误</b>",
                f"编号：<code>{event_id}</code>",
                f"级别：{html.escape(record.levelname)}",
                f"来源：<code>{html.escape(record.name)}</code>",
            ]
            if exception_name:
                lines.append(f"异常：<code>{html.escape(exception_name)}</code>")
            lines.append(f"位置：<code>{html.escape(location)}</code>")
            if method or path:
                lines.append(f"请求：<code>{html.escape((method + ' ' + path).strip())}</code>")
            safe_message = _safe_message(record)
            if safe_message:
                lines.append(f"摘要：{html.escape(safe_message)}")
            chat_id = str(getattr(settings, "TELEGRAM_ERROR_CHAT_ID", "") or "")
            message = "\n".join(lines)
            logger.info(
                "Error alert reference event_id=%s fingerprint=%s source=%s location=%s",
                event_id, fingerprint[:12], record.name, location,
            )
            dispatch(lambda: send_text(chat_id, message), chat_id=chat_id)
        except Exception:
            self.handleError(record)
