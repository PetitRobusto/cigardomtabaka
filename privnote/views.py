"""privnote HTTP 入口 — 纯 request/response 层，零业务逻辑"""
import json
import os
import uuid
from datetime import datetime, timedelta

from django.conf import settings
from django.db.models import Q
from django.http import JsonResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from cigars.models import Brand, Cigar, CigarPrice, Customer, PurchaseBatch, User
from cigars.search import CigarSearchEngine
from cigars.constants import BRAND_CN_MAP
from .models import Privnote
from .decorators import staff_required
from .helpers import (
    safe_json_loads,
    get_in_stock_cigar_ids,
    serialize_payment_method,
    serialize_cigar_minimal,
)
from .services import (
    build_inventory_data,
    build_payment_data,
    build_quote_data,
    create_sales_order_from_items,
)
from .services.payment import PaymentValidationError


# ── 常量 ──

NOTE_TYPE_BACKWARD_COMPAT = {
    'catalog': 'inventory',
    'sales': 'payment',
}


# ═══════════════ CREATE ═══════════════

@csrf_exempt
@staff_required
def create(request):
    """POST /privnote/create/ — 四种类型统一创建入口"""
    note_type = request.POST.get('note_type', 'inventory')
    note_type = NOTE_TYPE_BACKWARD_COMPAT.get(note_type, note_type)
    duration_hours = int(request.POST.get('duration', 24))
    password = request.POST.get('password', '').strip()
    burn = request.POST.get('burn', 'on') == 'on'

    is_debug = settings.DEBUG
    debug_tag = ' [测试数据]' if is_debug else ''
    sales_order = None

    # ── INVENTORY ──
    if note_type == 'inventory':
        if request.POST.get('preview') == '1':
            return JsonResponse({'preview': build_inventory_data()})
        title = f'库存报价单 · {timezone.now().strftime("%Y-%m-%d")}{debug_tag}'
        data = build_inventory_data()

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
        customer_id = request.POST.get('customer_id', '').strip()
        if customer_id:
            try:
                customer = Customer.objects.get(id=int(customer_id))
                customer_name = customer.name
            except (Customer.DoesNotExist, ValueError):
                pass

        payment_method_id = request.POST.get('payment_method_id', '')
        payment_manual = safe_json_loads(request.POST.get('payment_manual', '{}'), {})
        extra_fees = safe_json_loads(request.POST.get('extra_fees', '[]'), [])
        remark = request.POST.get('remark', '').strip()
        images = safe_json_loads(request.POST.get('images', '[]'), [])

        try:
            order = create_sales_order_from_items(
                items_raw=items_raw,
                customer_name=customer_name,
                payment_method_id=payment_method_id,
                payment_manual=payment_manual,
                extra_fees=extra_fees,
                remark=remark,
                images=images,
            )
        except PaymentValidationError as exc:
            return JsonResponse({'error': str(exc)}, status=400)

        title = f'收款单 · {order.order_number}{debug_tag}'
        data = build_payment_data(order)
        sales_order = order

    # ── MESSAGE ──
    elif note_type == 'message':
        text = request.POST.get('text', '').strip()
        attachments = safe_json_loads(request.POST.get('attachments', '[]'), [])
        images = safe_json_loads(request.POST.get('images', '[]'), [])
        if not isinstance(attachments, list):
            attachments = []
        if not isinstance(images, list):
            images = []

        if not text and not attachments and not images:
            return JsonResponse({'error': '消息内容和附件至少填一个'}, status=400)

        title = f'消息 · {timezone.now().strftime("%Y-%m-%d %H:%M")}{debug_tag}'
        data = {'mode': 'message', 'text': text, 'attachments': attachments, 'images': images}

    # ── QUOTE ──
    elif note_type == 'quote':
        quote_mode = request.POST.get('quote_mode', 'full')
        selected_ids = safe_json_loads(request.POST.get('selected_ids', '[]'), [])
        shipping_included = request.POST.get('shipping_included', 'false') == 'true'
        quote_customer_name = request.POST.get('customer_name', '').strip()
        custom_prices = safe_json_loads(request.POST.get('custom_prices', '{}'), {})
        if not isinstance(custom_prices, dict):
            custom_prices = {}

        # 过滤非法值：只保留正整数
        filtered_custom_prices = {}
        for k, v in custom_prices.items():
            if not isinstance(v, (int, float, str)):
                continue
            try:
                price = int(v)
            except (TypeError, ValueError):
                continue
            if price > 0:
                filtered_custom_prices[str(k)] = price
        custom_prices = filtered_custom_prices

        if quote_mode == 'custom' and not selected_ids:
            return JsonResponse({'error': '定制选择模式下至少选择一款雪茄'}, status=400)

        title = f'批发报价单 · {timezone.now().strftime("%Y-%m-%d")}{debug_tag}'
        data = {
            'mode': 'quote',
            'quote_mode': quote_mode,
            'selected_ids': selected_ids,
            'shipping_included': shipping_included,
            'shipping_fee_per_stick': 20 if shipping_included else 0,
            'customer_name': quote_customer_name or None,
            'custom_prices': custom_prices,
        }

    else:
        return JsonResponse({'error': f'未知类型: {note_type}'}, status=400)

    # 创建 Privnote
    note = Privnote(
        token=uuid.uuid4().hex[:12],
        note_type=note_type,
        title=title,
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
@staff_required
def search_cigars(request):
    """GET /privnote/api/search-cigars/?q=xxx&stock_only=0|1"""
    q = request.GET.get('q', '').strip()
    stock_only = request.GET.get('stock_only', '0') == '1'

    cigars_qs = Cigar.objects.all()
    if stock_only:
        in_stock_ids = PurchaseBatch.objects.filter(
            remaining__gt=0
        ).values_list('cigar_id', flat=True).distinct()
        cigars_qs = cigars_qs.filter(id__in=in_stock_ids)

    cigars_list = CigarSearchEngine.search(
        cigars=cigars_qs,
        query=q,
        stock_only=False,  # 已在 QuerySet 层过滤
        limit=30,
    )

    results = [
        serialize_cigar_minimal(c, include_batches=True, stock_only=stock_only)
        for c in cigars_list
    ]

    # 补充 brand_cn
    for r in results:
        r['brand_cn'] = BRAND_CN_MAP.get(r['brand'], '')

    return JsonResponse({'results': results})


# ═══════════════ QUOTE PRODUCTS API ═══════════════

@staff_required
def list_quote_products(request):
    """GET /privnote/api/quote-products/ — 返回可预购或有现货的雪茄"""
    in_stock_cigar_ids = get_in_stock_cigar_ids()

    qs = CigarPrice.objects.filter(
        is_active=True
    ).filter(
        Q(can_preorder=True) | Q(cigar_id__in=in_stock_cigar_ids)
    ).select_related('cigar')

    # 批量查询品牌信息，避免 N+1
    brand_map = {
        b.english_name: b.name or b.english_name
        for b in Brand.objects.all()
    }

    products = []
    for cp in qs:
        cigar = cp.cigar
        products.append({
            'cigar_id': cigar.id,
            'brand': cigar.brand,
            'brand_cn': brand_map.get(cigar.brand, cigar.brand),
            'name': cigar.name or cigar.english_name,
            'english_name': cigar.english_name,
            'vitola': cigar.vitola or '—',
            'box_size': cp.box_size,
            'wholesale_price': cp.wholesale_price,
            'per_stick_price': cp.per_stick_price,
            'thumb_url': serialize_cigar_minimal(cigar)['thumb_url'],
            'in_stock': cigar.id in in_stock_cigar_ids,
            'can_preorder': cp.can_preorder,
        })

    return JsonResponse({'products': products})


# ═══════════════ PAYMENT METHODS API ═══════════════

@staff_required
def list_payment_methods(request):
    """GET /privnote/api/payment-methods/"""
    from .models import PaymentMethod
    methods = PaymentMethod.objects.filter(is_active=True).order_by('sort_order')
    data = [serialize_payment_method(m) for m in methods]
    return JsonResponse({'methods': data})


# ═══════════════ CUSTOMER SEARCH API ═══════════════

@staff_required
def search_customers(request):
    """GET /privnote/api/search-customers/?q=xxx"""
    q = request.GET.get('q', '').strip()
    if not q:
        return JsonResponse({'results': []})
    customers = Customer.objects.filter(name__icontains=q)[:20]
    results = [{'id': c.id, 'name': c.name, 'phone': c.phone} for c in customers]
    return JsonResponse({'results': results})


# ═══════════════ UPLOAD IMAGE ═══════════════

@csrf_exempt
@staff_required
def upload_image(request):
    """POST /privnote/api/upload-image/ — 上传图片到 media/privnote/YYYYMMDD/"""
    if request.method != 'POST':
        return JsonResponse({'error': '仅支持 POST'}, status=405)

    file = request.FILES.get('image')
    if not file:
        return JsonResponse({'error': '未提供图片文件'}, status=400)

    allowed_types = ('image/jpeg', 'image/png', 'image/gif', 'image/webp')
    if file.content_type not in allowed_types:
        return JsonResponse({'error': '仅支持 jpg/png/gif/webp 格式'}, status=400)

    if file.size > 10 * 1024 * 1024:
        return JsonResponse({'error': '图片大小不能超过 10MB'}, status=400)

    today = datetime.now().strftime('%Y%m%d')
    upload_dir = os.path.join('privnote', today)
    full_dir = os.path.join(settings.MEDIA_ROOT, upload_dir)
    os.makedirs(full_dir, exist_ok=True)

    ext = os.path.splitext(file.name)[1].lower() or '.jpg'
    unique_name = f"{uuid.uuid4().hex[:16]}{ext}"
    rel_path = os.path.join(upload_dir, unique_name)
    full_path = os.path.join(settings.MEDIA_ROOT, rel_path)

    with open(full_path, 'wb+') as destination:
        for chunk in file.chunks():
            destination.write(chunk)

    url = f"/media/{rel_path.replace(os.sep, '/')}"
    return JsonResponse({'url': url, 'name': file.name})


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
        data = build_payment_data(note.sales_order)
    elif note.note_type == 'quote':
        cfg = note.data_json or {}
        data = build_quote_data(
            quote_mode=cfg.get('quote_mode', 'full'),
            selected_ids=cfg.get('selected_ids', []),
            shipping_included=cfg.get('shipping_included', False),
            customer_name=cfg.get('customer_name'),
            custom_prices=cfg.get('custom_prices'),
            shipping_fee_per_stick=cfg.get('shipping_fee_per_stick'),
        )
    else:
        data = note.data_json

    return JsonResponse({
        'title': note.title,
        'note_type': note.note_type,
        'data': data,
        'burn_after_read': note.burn_after_read,
        'is_destroyed': note.is_destroyed,
        'created_at': note.created_at.isoformat(),
        'expires_at': note.expires_at.isoformat(),
    })


# Compatibility alias
def create_note(request):
    return create(request)


