"""Shared service guards for the one-time Day 1 accounting cutover."""

from accounting.models import Day1Initialization


class Day1IncompleteError(Exception):
    """Raised when a normal business action runs before opening facts exist."""

    code = 'day1_incomplete'

    def __init__(self, details=None):
        super().__init__(self.code)
        self.details = details or {}


def require_day1_completed(*, allow_day1=False):
    """Block formal actions until the singleton Day 1 initialization is complete."""
    if allow_day1:
        return
    if not Day1Initialization.objects.filter(
        singleton_key='company', status=Day1Initialization.Status.COMPLETED,
    ).exists():
        raise Day1IncompleteError()
