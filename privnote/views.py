"""privnote HTTP 入口 — 纯 request/response 层，零业务逻辑"""
import json
import os
import uuid
from datetime import datetime, timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET

from cigars.models import Brand, Cigar, CigarPrice, Customer, PurchaseBatch, SalesOrder, User
from accounting.models import FundAccount
from cigars.search import CigarSearchEngine
from cigars.constants import BRAND_CN_MAP
from .models import PaymentMethod, Privnote
from .decorators import staff_required
from .helpers import (
    decimal_to_number,
    safe_json_loads,
    get_in_stock_cigar_ids,
    serialize_payment_method,
    serialize_cigar_minimal,
)
from .services import (
    build_inventory_data,
    build_payment_data,
    build_quote_data,
)
from .services.payment import PaymentValidationError


# ── 常量 ──

NOTE_TYPE_BACKWARD_COMPAT = {
    'catalog': 'inventory',
    'sales': 'payment',
}


def _request_operator(request):
    if request.user.is_authenticated and request.user.is_staff:
        return request.user
    tg_id = request.headers.get('X-Telegram-ID', '').strip()
    if tg_id:
        try:
            return User.objects.get(telegram_id=tg_id, is_staff=True)
        except User.DoesNotExist:
            pass
    return None


# ═══════════════ CREATE ═══════════════

@csrf_exempt
@staff_required
@transaction.atomic
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
    operator = _request_operator(request)

    # ── INVENTORY ──
    if note_type == 'inventory':
        if request.POST.get('preview') == '1':
            return JsonResponse({'preview': build_inventory_data()})
        title = f'库存报价单 · {timezone.now().strftime("%Y-%m-%d")}{debug_tag}'
        data = build_inventory_data()

    # ── PAYMENT ──
    elif note_type == 'payment':
        # 收款单是已有销售单的客户文档；销售单必须先经过销售工作流创建。
        raw_order_id = request.POST.get('sales_order_id', '').strip()
        raw_payment_method_id = request.POST.get('payment_method_id', '').strip()
        try:
            sales_order_id = int(raw_order_id)
            payment_method_id = int(raw_payment_method_id)
        except (TypeError, ValueError):
            return JsonResponse({'error': '收款单必须提供有效的销售单和收款方式'}, status=400)
        if sales_order_id <= 0 or payment_method_id <= 0:
            return JsonResponse({'error': '收款单必须提供有效的销售单和收款方式'}, status=400)

        try:
            order = SalesOrder.objects.select_for_update().get(pk=sales_order_id)
        except SalesOrder.DoesNotExist:
            return JsonResponse({'error': '销售单不存在'}, status=400)
        if (
            order.fulfillment_status not in (
                SalesOrder.FulfillmentStatus.CONFIRMED,
                SalesOrder.FulfillmentStatus.SHIPPED,
            )
            or order.payment_status != SalesOrder.PaymentStatus.UNPAID
        ):
            return JsonResponse({'error': '只有已确认或已出库且未收款的销售单才能创建收款单'}, status=400)

        payment_method = PaymentMethod.objects.filter(
            pk=payment_method_id,
            is_active=True,
            fund_account__is_active=True,
            fund_account__currency=FundAccount.Currency.CNY,
        ).select_related('fund_account').first()
        if payment_method is None:
            return JsonResponse({'error': '收款方式不存在、未启用或未绑定有效人民币账户'}, status=400)

        remark = request.POST.get('remark', '').strip()
        images = safe_json_loads(request.POST.get('images', '[]'), [])
        if not isinstance(images, list):
            images = []
        title = f'收款单 · {order.order_number}{debug_tag}'
        sales_order = order
        # payment_manual / extra_fees 等旧字段永远不从 HTTP 请求写回销售单，
        # 也不进入新收款单快照；金额只来自销售单正式应收字段。
        data = {
            'payment_method_id': payment_method.id,
            'remark': remark,
            'images': images,
        }

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
    methods = PaymentMethod.objects.filter(
        is_active=True,
        fund_account__is_active=True,
        fund_account__currency=FundAccount.Currency.CNY,
    ).select_related('fund_account').order_by('sort_order')
    data = [serialize_payment_method(m, include_fund_account=True) for m in methods]
    return JsonResponse({'methods': data})


@staff_required
@require_GET
def list_payment_orders(request):
    """GET /privnote/api/payment-orders/ — 可生成收款单的销售单。"""
    orders = (
        SalesOrder.objects
        .filter(
            fulfillment_status__in=(
                SalesOrder.FulfillmentStatus.CONFIRMED,
                SalesOrder.FulfillmentStatus.SHIPPED,
            ),
            payment_status=SalesOrder.PaymentStatus.UNPAID,
        )
        .select_related('customer')
        .prefetch_related('items__cigar')
        .order_by('-created_at', '-id')
    )
    data = []
    for order in orders:
        data.append({
            'id': order.id,
            'order_number': order.order_number,
            'status': order.status,
            'display_status': order.display_status,
            'fulfillment_status': order.fulfillment_status,
            'payment_status': order.payment_status,
            'customer_name': order.customer_name,
            'customer': ({
                'id': order.customer_id,
                'name': order.customer.name,
                'phone': order.customer.phone,
            } if order.customer_id else None),
            'amount_due_cny': decimal_to_number(order.amount_due_cny),
            'items': [{
                'id': item.id,
                'cigar_name': item.cigar.name or item.cigar.english_name,
                'quantity': item.quantity,
                'sale_unit': item.sale_unit,
                'sale_quantity': item.sale_quantity,
                'unit_price': decimal_to_number(item.unit_price),
            } for item in order.items.all()],
        })
    return JsonResponse({'orders': data})


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

    # 收款类型：实时渲染
    try:
        if note.note_type == 'payment' and note.sales_order:
            cfg = note.data_json or {}
            # 新格式由 payment_method_id 标识；旧格式保存的是完整 payment
            # 快照，不能把历史手动收款信息误当作新请求数据。
            if 'payment_method_id' not in cfg:
                data = build_payment_data(
                    note.sales_order,
                    remark=cfg.get('remark') if isinstance(cfg, dict) else None,
                    images=cfg.get('images') if isinstance(cfg, dict) else None,
                    extra_fees=cfg.get('extra_fees') if isinstance(cfg, dict) else None,
                )
                legacy_methods = cfg.get('payment_methods') if isinstance(cfg, dict) else None
                if isinstance(legacy_methods, list):
                    data['payment_methods'] = [
                        method for method in legacy_methods
                        if isinstance(method, dict) and 'fund_account_id' not in method
                    ]
                elif note.sales_order.payment_manual:
                    manual = note.sales_order.payment_manual
                    if any(manual.get(key) for key in ('bank_name', 'card_number', 'card_holder')):
                        data['payment_methods'] = [{
                            'method_type': 'bank_card',
                            'label': '手动填写',
                            'bank_name': manual.get('bank_name', ''),
                            'card_number': manual.get('card_number', ''),
                            'card_holder': manual.get('card_holder', ''),
                            'qr_url': manual.get('qr_url'),
                            'remark': '',
                        }]
                if isinstance(note.sales_order.payment_manual, dict):
                    manual = note.sales_order.payment_manual
                    if data.get('remark') == '':
                        data['remark'] = str(manual.get('remark') or '')
                    if not data.get('images'):
                        data['images'] = manual.get('images') if isinstance(manual.get('images'), list) else []
            else:
                payment_method = PaymentMethod.objects.filter(
                    pk=cfg.get('payment_method_id'),
                    is_active=True,
                    fund_account__is_active=True,
                    fund_account__currency=FundAccount.Currency.CNY,
                ).select_related('fund_account').first()
                data = build_payment_data(
                    note.sales_order,
                    payment_method=payment_method,
                    remark=cfg.get('remark'),
                    images=cfg.get('images', []),
                    # 新 note 不保存 extra_fees：让渲染器从销售单正式人肉费字段计算；
                    # 历史 note 若有快照则继续按快照兼容展示。
                    extra_fees=cfg.get('extra_fees'),
                )
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
    except PaymentValidationError:
        return JsonResponse({
            'error': 'invalid_payment_order',
            'reason': 'invalid_payment_order',
            'title': note.title,
        }, status=409)

    note.mark_viewed()

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
