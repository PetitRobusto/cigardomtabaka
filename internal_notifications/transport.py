"""Small, best-effort Telegram Bot API transport.

Delivery deliberately has no durable queue.  Jobs run in a bounded number of
daemon threads, retry briefly, then leave a local log entry and stop.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from collections.abc import Callable

import requests
from django.conf import settings


logger = logging.getLogger(__name__)
_slots = threading.BoundedSemaphore(value=4)
_configuration_warnings: set[tuple[str, ...]] = set()
_configuration_warning_lock = threading.Lock()


def _enabled() -> bool:
    return bool(getattr(settings, "TELEGRAM_NOTIFICATIONS_ENABLED", True))


def _configured(chat_id: str) -> bool:
    if not _enabled():
        return False
    missing = []
    if not getattr(settings, "TELEGRAM_BOT_TOKEN", ""):
        missing.append("TELEGRAM_BOT_TOKEN")
    if not chat_id:
        missing.append("chat_id")
    if not missing:
        return True
    key = tuple(missing)
    with _configuration_warning_lock:
        if key not in _configuration_warnings:
            _configuration_warnings.add(key)
            logger.warning(
                "Telegram notification disabled because configuration is missing: %s",
                ", ".join(missing),
            )
    return False


def _request(method: str, *, chat_id: str, text: str = "", file_path: str = "") -> bool:
    if not _enabled():
        return False
    token = getattr(settings, "TELEGRAM_BOT_TOKEN", "")
    if not token or not chat_id:
        return False
    attempts = max(1, int(getattr(settings, "TELEGRAM_NOTIFICATION_MAX_ATTEMPTS", 3)))
    connect_timeout = float(getattr(settings, "TELEGRAM_NOTIFICATION_CONNECT_TIMEOUT", 2.0))
    read_timeout = float(getattr(settings, "TELEGRAM_NOTIFICATION_READ_TIMEOUT", 5.0))
    url = f"https://api.telegram.org/bot{token}/{method}"
    last_error = "unknown"
    last_status = None
    for attempt in range(attempts):
        try:
            data = {"chat_id": chat_id}
            files = None
            handle = None
            if method == "sendMessage":
                data.update({"text": text, "parse_mode": "HTML", "disable_web_page_preview": "true"})
            elif method in {"sendPhoto", "sendDocument"}:
                handle = open(file_path, "rb")
                field_name = "photo" if method == "sendPhoto" else "document"
                files = {field_name: (os.path.basename(file_path), handle)}
            try:
                response = requests.post(
                    url, data=data, files=files,
                    timeout=(connect_timeout, read_timeout),
                )
            finally:
                if handle is not None:
                    handle.close()
            last_status = response.status_code
            payload = response.json() if response.content else {}
            if response.ok and payload.get("ok") is True:
                return True
            last_error = "telegram_api_error"
        except Exception as exc:  # Best effort must never escape into business code.
            last_error = type(exc).__name__
        if attempt + 1 < attempts:
            time.sleep(0.25 * (attempt + 1))
    logger.error(
        "Telegram %s delivery failed after %s attempts (status=%s, error=%s)",
        method, attempts, last_status, last_error,
    )
    return False


def send_text(chat_id: str, text: str) -> bool:
    return _request("sendMessage", chat_id=str(chat_id), text=text[:4096])


def send_photo(chat_id: str, photo_path: str) -> bool:
    return _request("sendPhoto", chat_id=str(chat_id), file_path=photo_path)


def send_evidence_image(chat_id: str, image_path: str) -> bool:
    """Send browser-friendly images as photos and WebP safely as a document."""
    method = "sendDocument" if image_path.lower().endswith(".webp") else "sendPhoto"
    return _request(method, chat_id=str(chat_id), file_path=image_path)


def dispatch(job: Callable[[], None], *, chat_id: str) -> bool:
    """Run one configured delivery job without delaying the request thread."""
    if not _configured(str(chat_id)):
        return False
    if not _slots.acquire(blocking=False):
        logger.error("Telegram delivery dropped because all worker slots are busy")
        return False

    def run() -> None:
        try:
            job()
        except Exception as exc:
            logger.error("Telegram delivery job failed (%s)", type(exc).__name__)
        finally:
            _slots.release()

    threading.Thread(target=run, name="telegram-notification", daemon=True).start()
    return True
