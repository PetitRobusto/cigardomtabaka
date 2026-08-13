"""Business-date helpers for Moscow-based accounting records."""

from zoneinfo import ZoneInfo

from django.utils import timezone


MOSCOW_TIME_ZONE = ZoneInfo('Europe/Moscow')


def moscow_business_date(now=None):
    """Return the calendar date used by the Moscow operating business."""
    instant = now or timezone.now()
    return timezone.localtime(instant, MOSCOW_TIME_ZONE).date()
