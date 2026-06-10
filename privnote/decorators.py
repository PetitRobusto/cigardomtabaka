"""privnote 专用 decorators"""
from functools import wraps
from django.http import HttpResponseForbidden

from cigars.models import User


def staff_required(view_func):
    """
    检查请求者是否为 staff。
    支持 Django 认证用户和 X-Telegram-ID header。
    """
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if request.user.is_authenticated and request.user.is_staff:
            return view_func(request, *args, **kwargs)

        tg_id = request.headers.get('X-Telegram-ID', '').strip()
        if tg_id:
            try:
                u = User.objects.get(telegram_id=tg_id)
                if u.is_staff:
                    return view_func(request, *args, **kwargs)
            except User.DoesNotExist:
                pass

        return HttpResponseForbidden("仅限工作人员访问")
    return _wrapped
