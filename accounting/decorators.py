from functools import wraps

from django.http import JsonResponse

from privnote.views import _request_operator


def staff_json_required(view_func):
    """Require the same staff identity resolution used by privnote."""
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        operator = _request_operator(request)
        if operator is None:
            return JsonResponse({'error': '仅限工作人员访问'}, status=403)
        request.accounting_operator = operator
        return view_func(request, *args, **kwargs)
    return _wrapped
