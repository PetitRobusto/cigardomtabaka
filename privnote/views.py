from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse, HttpResponseForbidden
from django.views.decorators.csrf import csrf_exempt
from django.template.loader import render_to_string
from django.conf import settings
from django.db.models import Sum
from django.contrib.auth.models import AnonymousUser
from datetime import timedelta
from django.utils import timezone

from cigars.models import Brand, Cigar, PurchaseBatch, User
from .models import Privnote


DURATION_CHOICES = [
    (1, '1 小时'), (6, '6 小时'), (24, '24 小时'),
    (72, '3 天'), (168, '7 天'), (720, '30 天'),
]


def _is_staff(request):
    """检查请求者是否为 staff：Django admin 登录 或 X-Telegram-ID 头匹配 staff 用户"""
    if request.user.is_authenticated and request.user.is_staff:
        return True
    tg_id = request.headers.get('X-Telegram-ID', '').strip()
    if tg_id:
        try:
            u = User.objects.get(telegram_id=tg_id)
            return u.is_staff
        except User.DoesNotExist:
            pass
    return False


def _build_inventory_html():
    """从 PurchaseBatch 构建盒装库存 HTML（盒为单位，拆盒才展示散支）"""
    import random
    random.seed(42)

    # 预加载 box_size
    batches = list(
        PurchaseBatch.objects
        .filter(remaining__gt=0)
        .select_related('cigar', 'purchase_order_item')
        .order_by('cigar__brand', 'cigar__english_name')
    )

    if not batches:
        return render_to_string('privnote/view_content.html', {
            'mode': 'inventory', 'brand_groups': [], 'empty': True,
            'debug': settings.DEBUG,
        })

    # 按 (brand, cigar.english_name, box_size) 合并
    from collections import OrderedDict
    keyed = OrderedDict()
    for b in batches:
        box_size = b.purchase_order_item.box_size or 25
        key = (b.cigar.brand, b.cigar.english_name, box_size)
        if key not in keyed:
            keyed[key] = {'cigar': b.cigar, 'box_size': box_size, 'remaining': 0, 'cost': 0}
        keyed[key]['remaining'] += b.remaining
        # 加权平均成本
        keyed[key]['cost'] = round(
            (keyed[key]['cost'] * (keyed[key]['remaining'] - b.remaining) + b.unit_cost_cny * b.remaining)
            / keyed[key]['remaining'], 2
        ) if keyed[key]['remaining'] > 0 else b.unit_cost_cny

    # 按品牌分组 + 取中文名/logo
    brand_groups = OrderedDict()
    brand_info = {}  # {english_name: {name, logo_url}}
    for b in Brand.objects.all():
        brand_info[b.english_name] = {
            'name': b.name or b.english_name,
            'logo_url': b.logo.url if b.logo else None,
        }

    for (brand, ename, bs), entry in keyed.items():
        if brand not in brand_groups:
            brand_groups[brand] = []
            # 确保未知品牌也有默认值
            if brand not in brand_info:
                brand_info[brand] = {'name': brand, 'logo_url': None}

        r = entry['remaining']
        full_boxes = r // bs
        loose = r % bs
        cost = entry['cost']
        cigar = entry['cigar']

        # 假售价：成本上浮 30-60%
        stick_price = round(cost * (1.3 + random.random() * 0.3))
        box_price = round(stick_price * bs * 0.88)  # 盒装约 12% 折扣

        # 取缩略图
        thumb_url = ''
        primary = cigar.primary_image
        if primary and primary.thumbnail:
            thumb_url = primary.thumbnail.url

        brand_groups[brand].append({
            'name': cigar.name or cigar.english_name,
            'english_name': cigar.english_name,
            'vitola': cigar.vitola or '—',
            'box_size': bs,
            'full_boxes': full_boxes,
            'loose': loose,
            'total_sticks': r,
            'box_price': box_price,
            'stick_price': stick_price,
            'thumb_url': thumb_url,
        })

    # 组装返回数据：品牌名+logo+产品列表
    groups = []
    for brand, items in brand_groups.items():
        info = brand_info.get(brand, {'name': brand, 'logo_url': None})
        groups.append({
            'brand': brand,
            'name': info['name'],
            'logo_url': info['logo_url'],
            'items': items,
        })

    total_boxes = sum(item['full_boxes'] for g in groups for item in g['items'])
    total_loose = sum(item['loose'] for g in groups for item in g['items'])
    total_items = sum(len(g['items']) for g in groups)

    return render_to_string('privnote/view_content.html', {
        'mode': 'inventory',
        'brand_groups': groups,
        'total_items': total_items,
        'total_boxes': total_boxes,
        'total_loose': total_loose,
        'empty': False,
        'debug': settings.DEBUG,
    })


def index(request):
    if not _is_staff(request):
        return HttpResponseForbidden("仅限工作人员访问")
    brands = Brand.objects.all().order_by('id')
    return render(request, 'privnote/index.html', {
        'brands': brands,
        'durations': DURATION_CHOICES,
    })


@csrf_exempt
def create(request):
    if not _is_staff(request):
        return HttpResponseForbidden("仅限工作人员访问")
    note_type = request.POST.get('note_type', 'catalog')
    duration_hours = int(request.POST.get('duration', 24))
    password = request.POST.get('password', '').strip()
    burn = request.POST.get('burn', 'on') == 'on'

    is_debug = settings.DEBUG
    debug_tag = ' [测试数据]' if is_debug else ''

    if note_type == 'catalog':
        title = f'库存报价单 · {timezone.now().strftime("%Y-%m-%d")}{debug_tag}'
        html = _build_inventory_html()
        brand = None
    else:
        title = f'销售单据 · {timezone.now().strftime("%Y-%m-%d")}{debug_tag}'
        html = render_to_string('privnote/view_content.html', {
            'mode': 'sales', 'empty': True, 'debug': is_debug,
        })
        brand = None

    import uuid
    note = Privnote(
        token=uuid.uuid4().hex[:12],
        note_type=note_type, title=title, brand=brand, html=html,
        burn_after_read=burn, max_views=1 if burn else 999,
        expires_at=timezone.now() + timedelta(hours=duration_hours),
    )
    if password:
        note.set_password(password)
    note.save()

    url = request.build_absolute_uri(f'/p/{note.token}/')
    return JsonResponse({'url': url, 'token': note.token, 'has_password': note.has_password})


def view_note(request, token):
    note = get_object_or_404(Privnote, token=token)

    if note.is_expired:
        return render(request, 'privnote/destroyed.html', {'reason': 'expired'})

    if note.is_destroyed:
        return render(request, 'privnote/destroyed.html', {'reason': 'viewed'})

    if note.has_password:
        if request.method == 'POST':
            pwd = request.POST.get('password', '')
            if note.verify_password(pwd):
                note.mark_viewed()
                return render(request, 'privnote/view.html', {'note': note, 'html': note.html})
            return render(request, 'privnote/password.html', {'note': note, 'error': '密码错误'})
        return render(request, 'privnote/password.html', {'note': note})

    note.mark_viewed()
    return render(request, 'privnote/view.html', {'note': note, 'html': note.html})
