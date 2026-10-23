from functools import wraps

from django.http import JsonResponse
from rest_framework.permissions import BasePermission


class IsStaffUser(BasePermission):
    """Allow access only to authenticated Django staff users."""

    message = 'Staff access required.'

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_staff)


def staff_required_json(view_func):
    """Protect a JSON endpoint without redirecting API clients to an HTML login."""

    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated or not request.user.is_staff:
            return JsonResponse({'error': 'Forbidden'}, status=403)
        return view_func(request, *args, **kwargs)

    return wrapped
