from functools import wraps

from django.http import JsonResponse


def staff_json_required(view_func):
    """Require an authenticated Django staff user for internal accounting."""
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated or not request.user.is_staff:
            return JsonResponse({
                'error': '仅限工作人员访问',
                'code': 'forbidden', 'details': {},
            }, status=403)
        request.accounting_operator = request.user
        return view_func(request, *args, **kwargs)
    return _wrapped
