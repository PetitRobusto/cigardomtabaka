from django.shortcuts import get_object_or_404
from django.http import JsonResponse, HttpResponseForbidden
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.db import models
from datetime import timedelta
from django.utils import timezone
import uuid
import json

from cigars.models import Brand, Cigar, PurchaseBatch, User, SalesOrder, SalesOrderItem
from .models import Privnote, PaymentMethod


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


# ═══════════════ Inventory ═══════════════

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
            'mode': 'inventory', 'brand_groups': [],
            'total_items': 0, 'total_boxes': 0, 'total_loose': 0, 'empty': True,
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
    for (brand, ename, bs), entry in keyed.items():
        if brand not in brand_groups:
            brand_groups[brand] = []
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

    brand_info = {}
    for b in Brand.objects.all():
        brand_info[b.english_name] = {
            'name': b.name or b.english_name,
            'logo_url': b.logo.url if b.logo else None,
        }

    groups = []
    for brand, items in brand_groups.items():
        info = brand_info.get(brand, {'name': brand, 'logo_url': None})
        groups.append({'brand': brand, 'name': info['name'], 'logo_url': info['logo_url'], 'items': items})

    total_boxes = sum(item['full_boxes'] for g in groups for item in g['items'])
    total_loose = sum(item['loose'] for g in groups for item in g['items'])
    total_items = sum(len(g['items']) for g in groups)

    return {
        'mode': 'inventory', 'brand_groups': groups,
        'total_items': total_items, 'total_boxes': total_boxes, 'total_loose': total_loose,
        'empty': False,
    }


# ═══════════════ Payment ═══════════════

def _build_payment_data(sales_order):
    """实时渲染收款 privnote 数据"""
    items = []
    for item in sales_order.items.select_related('cigar').all():
        cigar = item.cigar
        thumb_url = ''
        primary = cigar.primary_image
        if primary and primary.thumbnail:
            thumb_url = primary.thumbnail.url
        items.append({
            'name': cigar.name or cigar.english_name,
            'english_name': cigar.english_name,
            'vitola': cigar.vitola or '—',
            'quantity': item.quantity,
            'unit_price': item.unit_price,
            'subtotal': round(item.quantity * item.unit_price, 2),
            'thumb_url': thumb_url,
        })

    total = round(sum(it['subtotal'] for it in items), 2)

    payment_methods = []
    if sales_order.payment_method_id:
        try:
            pm = PaymentMethod.objects.get(id=sales_order.payment_method_id, is_active=True)
            payment_methods.append({
                'method_type': pm.method_type,
                'label': pm.label,
                'bank_name': pm.bank_name,
                'card_number': pm.card_number,
                'card_holder': pm.card_holder,
                'qr_url': pm.qr_image.url if pm.qr_image else None,
            })
        except PaymentMethod.DoesNotExist:
            pass

    if sales_order.payment_manual:
        manual = sales_order.payment_manual
        if manual.get('bank_name') or manual.get('card_number') or manual.get('card_holder'):
            payment_methods.append({
                'method_type': 'bank_card',
                'label': '手动填写',
                'bank_name': manual.get('bank_name', ''),
                'card_number': manual.get('card_number', ''),
                'card_holder': manual.get('card_holder', ''),
                'qr_url': manual.get('qr_url'),
            })

    return {
        'mode': 'payment',
        'items': items,
        'total': total,
        'payment_methods': payment_methods,
        'customer_name': sales_order.customer_name or '',
    }


# ═══════════════ CREATE ═══════════════

@csrf_exempt
def create(request):
    """POST /privnote/create/ — 三种类型统一创建入口"""
    if not _is_staff(request):
        return HttpResponseForbidden("仅限工作人员访问")

    note_type = request.POST.get('note_type', 'inventory')
    duration_hours = int(request.POST.get('duration', 24))
    password = request.POST.get('password', '').strip()
    burn = request.POST.get('burn', 'on') == 'on'

    is_debug = settings.DEBUG
    debug_tag = ' [测试数据]' if is_debug else ''

    # ── INVENTORY ──
    if note_type == 'inventory':
        title = f'库存报价单 · {timezone.now().strftime("%Y-%m-%d")}{debug_tag}'
        data = _build_inventory_data()
        sales_order = None

    # ── PAYMENT ──
    elif note_type == 'payment':
        items_json = request.POST.get('items', '[]')
        try:
            items_raw = json.loads(items_json)
        except json.JSONDecodeError:
            return JsonResponse({'error': '商品数据格式错误'}, status=400)

        if not items_raw:
            return JsonResponse({'error': '至少需要一个商品'}, status=400)

        customer_name = request.POST.get('customer_name', '').strip()
        payment_method_id = request.POST.get('payment_method_id', '')
        payment_manual_raw = request.POST.get('payment_manual', '{}')

        try:
            payment_manual = json.loads(payment_manual_raw) if payment_manual_raw else {}
        except json.JSONDecodeError:
            payment_manual = {}

        # 创建 SalesOrder
        order = SalesOrder.objects.create(
            customer_name=customer_name or None,
            operator=None,
            status='draft',
            payment_method_id=int(payment_method_id) if payment_method_id else None,
            payment_manual=payment_manual,
        )

        total_revenue = 0
        total_cost = 0
        for it in items_raw:
            cigar_id = it.get('cigar_id')
            quantity = int(it.get('quantity', 1))
            unit_price = float(it.get('unit_price', 0))

            cigar = get_object_or_404(Cigar, id=cigar_id)

            # 如果关联库存，自动填成本
            unit_cost = 0
            purchase_batch_id = it.get('batch_id')
            if purchase_batch_id:
                batch = PurchaseBatch.objects.filter(id=purchase_batch_id).first()
                if batch:
                    unit_cost = batch.unit_cost_cny or 0

            revenue = round(quantity * unit_price, 2)
            cost = round(quantity * unit_cost, 2)
            total_revenue += revenue
            total_cost += cost

            SalesOrderItem.objects.create(
                sales_order=order,
                cigar=cigar,
                quantity=quantity,
                unit_price=unit_price,
                unit_cost=unit_cost,
                revenue=revenue,
                cost=cost,
                profit=round(revenue - cost, 2),
            )

        order.total_revenue = round(total_revenue, 2)
        order.total_cost = round(total_cost, 2)
        order.total_profit = round(total_revenue - total_cost, 2)
        order.save(update_fields=['total_revenue', 'total_cost', 'total_profit'])

        title = f'收款单 · {order.order_number}{debug_tag}'
        data = _build_payment_data(order)
        sales_order = order

    # ── MESSAGE ──
    elif note_type == 'message':
        text = request.POST.get('text', '').strip()
        attachments_raw = request.POST.get('attachments', '[]')
        try:
            attachments = json.loads(attachments_raw)
        except json.JSONDecodeError:
            attachments = []

        if not text and not attachments:
            return JsonResponse({'error': '消息内容和附件至少填一个'}, status=400)

        title = f'消息 · {timezone.now().strftime("%Y-%m-%d %H:%M")}{debug_tag}'
        data = {'mode': 'message', 'text': text, 'attachments': attachments}
        sales_order = None

    else:
        return JsonResponse({'error': f'未知类型: {note_type}'}, status=400)

    # 创建 Privnote
    note = Privnote(
        token=uuid.uuid4().hex[:12],
        note_type=note_type,
        title=title,
        brand=None,
        data_json=data,
        sales_order=sales_order,
        burn_after_read=burn,
        max_views=1 if burn else 999,
        expires_at=timezone.now() + timedelta(hours=duration_hours),
    )
    if password:
        note.set_password(password)
    note.save()

    url = request.build_absolute_uri(f'/p/{note.token}/')
    return JsonResponse({
        'url': url,
        'token': note.token,
        'has_password': note.has_password,
        'sales_order_id': sales_order.id if sales_order else None,
    })


# ═══════════════ SEARCH API ═══════════════

@csrf_exempt
def search_cigars(request):
    """GET /privnote/api/search-cigars/?q=xxx&stock_only=0|1"""
    if not _is_staff(request):
        return HttpResponseForbidden("仅限工作人员访问")

    q = request.GET.get('q', '').strip()
    stock_only = request.GET.get('stock_only', '0') == '1'

    cigars = Cigar.objects.select_related('brand').all()

    if stock_only:
        in_stock_ids = PurchaseBatch.objects.filter(
            remaining__gt=0
        ).values_list('cigar_id', flat=True).distinct()
        cigars = cigars.filter(id__in=in_stock_ids)

    if q:
        cigars = cigars.filter(
            models.Q(name__icontains=q) |
            models.Q(english_name__icontains=q) |
            models.Q(brand__icontains=q)
        )

    cigars = cigars[:30]

    results = []
    for c in cigars:
        batches = []
        if stock_only:
            for b in c.purchase_batches.filter(remaining__gt=0).select_related('purchase_order_item'):
                box_size = b.purchase_order_item.box_size or 25
                batches.append({
                    'batch_id': b.id,
                    'box_size': box_size,
                    'remaining': b.remaining,
                    'unit_cost_cny': b.unit_cost_cny,
                })

        thumb_url = ''
        primary = c.primary_image
        if primary and primary.thumbnail:
            thumb_url = primary.thumbnail.url

        results.append({
            'id': c.id,
            'name': c.name or c.english_name,
            'english_name': c.english_name,
            'brand': c.brand,
            'vitola': c.vitola or '',
            'thumb_url': thumb_url,
            'batches': batches,
        })

    return JsonResponse({'results': results})


# ═══════════════ PAYMENT METHODS API ═══════════════

def list_payment_methods(request):
    """GET /privnote/api/payment-methods/"""
    if not _is_staff(request):
        return HttpResponseForbidden("仅限工作人员访问")

    methods = PaymentMethod.objects.filter(is_active=True).order_by('sort_order')
    data = []
    for m in methods:
        data.append({
            'id': m.id,
            'method_type': m.method_type,
            'label': m.label,
            'bank_name': m.bank_name,
            'card_number': m.card_number,
            'card_holder': m.card_holder,
            'qr_url': m.qr_image.url if m.qr_image else None,
        })
    return JsonResponse({'methods': data})


# ═══════════════ API: VIEW NOTE ═══════════════

@csrf_exempt
def api_privnote(request, token):
    """GET/POST /api/privnote/<token>/"""
    note = get_object_or_404(Privnote, token=token)

    if request.method == 'POST':
        if note.has_password:
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

    # 收款类型：实时渲染
    if note.note_type == 'payment' and note.sales_order:
        data = _build_payment_data(note.sales_order)
    else:
        data = note.data_json

    return JsonResponse({
        'title': note.title,
        'note_type': note.note_type,
        'data': data,
        'burn_after_read': note.burn_after_read,
        'is_destroyed': note.is_destroyed,
        'expires_at': note.expires_at.isoformat(),
    })


# Compatibility alias
def create_note(request):
    return create(request)
