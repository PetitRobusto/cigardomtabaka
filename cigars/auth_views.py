"""认证接口 — 用户名密码登录 + 退出"""
from django.contrib.auth import authenticate, login, logout
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST


def login_page(request):
    """GET /login/ — 登录页面；已登录则跳首页"""
    if request.user.is_authenticated:
        return redirect('brand_list')
    return render(request, 'cigars/login.html')


@csrf_exempt
@require_POST
def api_login(request):
    """POST /api/login/
    Body: { "username": "...", "password": "..." }
    成功 → 200 { ok: true, user: {...} } + Set-Cookie sessionid
    失败 → 401 { ok: false, error: "..." }
    """
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
    """POST /api/logout/ — 清除 session"""
    logout(request)
    return JsonResponse({'ok': True})
