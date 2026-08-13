"""认证接口 — 用户名密码登录 + 退出 + 当前用户"""
from django.contrib.auth import authenticate, login, logout
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import ensure_csrf_cookie

from .guide_views import _summary


@csrf_exempt
@require_POST
def api_login(request):
    """POST /api/login/"""
    username = request.POST.get('username', '').strip()
    password = request.POST.get('password', '')

    if not username or not password:
        return JsonResponse({'ok': False, 'error': '用户名和密码不能为空'}, status=400)

    user = authenticate(request, username=username, password=password)
    if user is None:
        return JsonResponse({'ok': False, 'error': '用户名或密码错误'}, status=401)

    if not user.is_active:
        return JsonResponse({'ok': False, 'error': '账户已禁用'}, status=403)

    login(request, user)
    return JsonResponse({
        'ok': True,
        'user': {
            'username': user.username,
            'display_name': str(user),
            'is_staff': user.is_staff,
            'is_superuser': user.is_superuser,
            'telegram_id': user.telegram_id or '',
        },
    })


@csrf_exempt
@require_POST
def api_logout(request):
    """POST /api/logout/"""
    logout(request)
    return JsonResponse({'ok': True})


@ensure_csrf_cookie
def api_me(request):
    """GET /api/auth/me/"""
    if request.user.is_authenticated:
        user_data = {
            'username': request.user.username,
            'is_staff': request.user.is_staff,
            'is_superuser': request.user.is_superuser,
        }
        if request.user.is_staff:
            user_data['guide'] = _summary(request.user)
        return JsonResponse({
            'authenticated': True,
            'user': user_data,
        })
    return JsonResponse({'authenticated': False})
