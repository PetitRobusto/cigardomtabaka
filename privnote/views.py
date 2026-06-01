from django.shortcuts import get_object_or_404
from django.http import JsonResponse, HttpResponseForbidden
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from datetime import timedelta
from django.utils import timezone

from cigars.models import Brand, Cigar, PurchaseBatch, User
from .models import Privnote


DURATION_CHOICES = [
    (1, '1 小时'), (6, '6 小时'), (24, '24 小时'),
    (72, '3 天'), (168, '7 天'), (720, '30 天'),
]


def _is_staff(request):
    """检查请求者是否为 staff"""
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


def _build_inventory_data():
    """从 PurchaseBatch 构建盒装库存结构化数据"""
    import random
    random.seed(42)

    batches = list(
        PurchaseBatch.objects
        .filter(remaining__gt=0)
        .select_related('cigar', 'purchase_order_item')
        .order_by('cigar__brand', 'cigar__english_name')
    )

    if not batches:
        return {
            'mode': 'inventory',
            'brand_groups': [],
            'total_items': 0,
            'total_boxes': 0,
            'total_loose': 0,
            'empty': True,
        }

    from collections import OrderedDict
    keyed = OrderedDict()
    for b in batches:
        box_size = b.purchase_order_item.box_size or 25
        key = (b.cigar.brand, b.cigar.english_name, box_size)
        if key not in keyed:
            keyed[key] = {'cigar': b.cigar, 'box_size': box_size, 'remaining': 0, 'cost': 0}
        keyed[key]['remaining'] += b.remaining
        keyed[key]['cost'] = round(
            (keyed[key]['cost'] * (keyed[key]['remaining'] - b.remaining) + b.unit_cost_cny * b.remaining)
            / keyed[key]['remaining'], 2
        ) if keyed[key]['remaining'] > 0 else b.unit_cost_cny

    brand_groups = OrderedDict()
    brand_info = {}
    for b in Brand.objects.all():
        brand_info[b.english_name] = {
            'name': b.name or b.english_name,
            'logo_url': b.logo.url if b.logo else None,
        }

    for (brand, ename, bs), entry in keyed.items():
        if brand not in brand_groups:
            brand_groups[brand] = []
            if brand not in brand_info:
                brand_info[brand] = {'name': brand, 'logo_url': None}

        r = entry['remaining']
        full_boxes = r // bs
        loose = r % bs
        cost = entry['cost']
        cigar = entry['cigar']

        stick_price = round(cost * (1.3 + random.random() * 0.3))
        box_price = round(stick_price * bs * 0.88)

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

    return {
        'mode': 'inventory',
        'brand_groups': groups,
        'total_items': total_items,
        'total_boxes': total_boxes,
        'total_loose': total_loose,
        'empty': False,
    }


@csrf_exempt
def create(request):
    """POST /privnote/create/ — 创建 privnote"""
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
        data = _build_inventory_data()
        brand = None
    else:
        title = f'销售单据 · {timezone.now().strftime("%Y-%m-%d")}{debug_tag}'
        data = {'mode': 'sales', 'empty': True}
        brand = None

    import uuid
    note = Privnote(
        token=uuid.uuid4().hex[:12],
        note_type=note_type, title=title, brand=brand,
        data_json=data,
        burn_after_read=burn, max_views=1 if burn else 999,
        expires_at=timezone.now() + timedelta(hours=duration_hours),
    )
    if password:
        note.set_password(password)
    note.save()

    url = request.build_absolute_uri(f'/p/{note.token}/')
    return JsonResponse({'url': url, 'token': note.token, 'has_password': note.has_password})


# =================== API VIEWS ===================

@csrf_exempt
def create_note(request):
    """POST /privnote/create/ — API wrapper"""
    return create(request)


@csrf_exempt
def api_privnote(request, token):
    """GET/POST /api/privnote/<token>/"""
    note = get_object_or_404(Privnote, token=token)

    if request.method == 'POST':
        if note.has_password:
            import json
            try:
                body = json.loads(request.body)
                pwd = body.get('password', '')
            except json.JSONDecodeError:
                pwd = request.POST.get('password', '')
            if not note.verify_password(pwd):
                return JsonResponse({'error': '密码错误', 'requires_password': True}, status=401)

    if note.is_expired:
        return JsonResponse({'error': 'expired', 'reason': 'expired', 'title': note.title}, status=410)

    if note.is_destroyed:
        return JsonResponse({'error': 'destroyed', 'reason': 'viewed', 'title': note.title}, status=410)

    if note.has_password and request.method == 'GET':
        return JsonResponse({
            'title': note.title,
            'has_password': True,
            'requires_password': True,
        })

    note.mark_viewed()

    return JsonResponse({
        'title': note.title,
        'note_type': note.note_type,
        'data': note.data_json,
        'burn_after_read': note.burn_after_read,
        'is_destroyed': note.is_destroyed,
        'expires_at': note.expires_at.isoformat(),
    })
