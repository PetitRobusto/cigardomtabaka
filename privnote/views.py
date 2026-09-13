"""privnote HTTP 入口 — 纯 request/response 层，零业务逻辑"""
import json
import mimetypes
import os
import uuid
import hashlib
from datetime import datetime, timedelta

from django.conf import settings
from django.core.exceptions import RequestDataTooBig
from django.db import IntegrityError, OperationalError, transaction
from django.db.models import Prefetch, Q, prefetch_related_objects
from django.http import FileResponse, Http404, JsonResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET

from cigars.models import Brand, Cigar, CigarPrice, Customer, IdempotencyRecord, PurchaseBatch, SalesOrder, User
from accounting.models import FundAccount
from accounting.services import _acquire_sqlite_writer_gate, _retry_sqlite_locked
from cigars.search import CigarSearchEngine
from cigars.constants import BRAND_CN_MAP
from .models import PaymentAttachment, PaymentMethod, PaymentSubmission, Privnote
from .decorators import staff_required
from .access import observe_access, record as record_access
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
from .services.payment_methods import PaymentMethodActionError, create_payment_method, set_payment_method_active
from .services.payment_requests import PaymentRequestError, create_payment_request
from .services.payment_submissions import (
    PaymentSubmissionError, serialize_submission, submit_payment_evidence,
)
from .storage import private_payment_storage


# ── 常量 ──

NOTE_TYPE_BACKWARD_COMPAT = {
    'catalog': 'inventory',
    'sales': 'payment',
}

def _privnote_public_url(request, token):
    base_url = getattr(settings, 'PRIVNOTE_BASE_URL', '').strip().rstrip('/')
    return f'{base_url}/p/{token}/' if base_url else request.build_absolute_uri(f'/p/{token}/')


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


def _payment_v2(note):
    config = note.data_json if isinstance(note.data_json, dict) else {}
    return config.get('schema_version') == 2 and isinstance(config.get('payment'), dict)


def _password_authorized(request, note):
    return not note.has_password or request.session.get(f'privnote-password:{note.token}') == note.password_hash


def _payment_public_data(note):
    """Render a v2 payment snapshot without leaking internal account data."""
    config = note.data_json['payment']
    display = config.get('display') if isinstance(config.get('display'), dict) else {}
    method = {
        key: display.get(key, '')
        for key in ('method_type', 'bank_name', 'card_number', 'card_holder', 'account', 'remark')
    }
    qr_name = config.get('qr_private_name')
    officially_paid = note.sales_order.payment_status == SalesOrder.PaymentStatus.PAID
    method['qr_url'] = f'/api/privnote/{note.token}/payment-images/qr/' if qr_name and not officially_paid else None
    data = build_payment_data(note.sales_order, remark=config.get('remark', ''), images=[])
    data['payment_methods'] = [method]
    latest = PaymentSubmission.objects.filter(privnote=note).order_by('-submitted_at', '-id').first()
    data['payment_flow'] = {
        # A direct formal receipt is as authoritative as accepting an uploaded
        # proof: keep the customer on a safe terminal confirmation page.
        'status': 'accepted' if officially_paid else (latest.status if latest else 'active'),
        'review_note': latest.review_note if latest and latest.status == PaymentSubmission.Status.NEEDS_MORE else '',
        'submitted_at': latest.submitted_at.isoformat() if latest else None,
    }
    return data


def _creation_request_hash(request):
    payload = {key: request.POST.get(key, '') for key in sorted(request.POST.keys())}
    qr = request.FILES.get('temporary_qr_image')
    if qr:
        digest = hashlib.sha256()
        for chunk in qr.chunks():
            digest.update(chunk)
        qr.seek(0)
        payload['temporary_qr_image'] = {'name': qr.name, 'size': qr.size, 'sha256': digest.hexdigest()}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode('utf-8')).hexdigest()


@_retry_sqlite_locked
def _create_payment_note(request, operator):
    """Multipart payment-request creation with the standard idempotency record."""
    key = request.headers.get('Idempotency-Key', '').strip()
    legacy_key = not key
    if legacy_key:
        key = f'legacy-payment-request:{uuid.uuid4().hex}'
    request_hash = _creation_request_hash(request)
    with transaction.atomic():
        _acquire_sqlite_writer_gate()
        record = IdempotencyRecord.objects.select_for_update().filter(key=key).first()
        if record:
            if record.command_name != 'create_payment_request' or record.request_hash != request_hash or record.operator_id != operator.id:
                return JsonResponse({'error': 'Idempotency-Key 已用于不同请求'}, status=409)
            if record.status_code:
                return JsonResponse(record.response_body, status=record.status_code)
            return JsonResponse({'error': '请求正在处理中，请稍后重试'}, status=409)
        if not legacy_key:
            record = IdempotencyRecord.objects.create(
                key=key, command_name='create_payment_request', request_hash=request_hash,
                request_body={'sales_order_id': request.POST.get('sales_order_id', '')},
                response_body={}, status_code=0, operator=operator, agent_name='web',
            )
        try:
            note = create_payment_request(
                sales_order_id=request.POST.get('sales_order_id'),
                duration_hours=request.POST.get('duration', 24),
                password=request.POST.get('password', '').strip(),
                source=request.POST.get('payment_source', 'saved'),
                payment_method_id=request.POST.get('payment_method_id'),
                fund_account_id=request.POST.get('fund_account_id'),
                method_type=request.POST.get('temporary_method_type', ''),
                bank_name=request.POST.get('temporary_bank_name', ''),
                card_number=request.POST.get('temporary_card_number', ''),
                card_holder=request.POST.get('temporary_card_holder', ''),
                account=request.POST.get('temporary_account', ''),
                qr_file=request.FILES.get('temporary_qr_image'),
                remark=request.POST.get('remark', ''),
                legacy_images=safe_json_loads(request.POST.get('images', '[]'), []),
                operator=operator,
            )
        except PaymentRequestError as exc:
            if not legacy_key:
                transaction.set_rollback(True)
            if exc.existing_note:
                return JsonResponse({
                    'error': str(exc), 'payment_note': {
                        'id': exc.existing_note.id, 'token': exc.existing_note.token,
                        'url': _privnote_public_url(request, exc.existing_note.token),
                        'expires_at': exc.existing_note.expires_at.isoformat(),
                    },
                }, status=exc.status)
            return JsonResponse({'error': str(exc)}, status=exc.status)
        response = {
            'url': _privnote_public_url(request, note.token), 'token': note.token,
            'has_password': note.has_password, 'sales_order_id': note.sales_order_id,
        }
        if not legacy_key:
            IdempotencyRecord.objects.filter(pk=record.pk).update(response_body=response, status_code=200)
        return JsonResponse(response)


# ═══════════════ CREATE ═══════════════

@csrf_exempt
@staff_required
@transaction.atomic
def create(request):
    """POST /privnote/create/ — 四种类型统一创建入口"""
    note_type = request.POST.get('note_type', 'inventory')
    note_type = NOTE_TYPE_BACKWARD_COMPAT.get(note_type, note_type)
    try:
        duration_hours = int(request.POST.get('duration', 24))
    except (TypeError, ValueError):
        return JsonResponse({'error': '有效期必须是指定小时数'}, status=400)
    password = request.POST.get('password', '').strip()
    burn = request.POST.get('burn', 'on') == 'on'
    try:
        requested_max_views = int(request.POST.get('max_views', '1' if burn else '0'))
    except (TypeError, ValueError):
        return JsonResponse({'error': '最大查看次数必须是整数'}, status=400)
    if requested_max_views < 0 or requested_max_views > 9999:
        return JsonResponse({'error': '最大查看次数必须在 0 到 9999 之间'}, status=400)
    max_views = 1 if burn else requested_max_views

    is_debug = settings.DEBUG
    debug_tag = ' [测试数据]' if is_debug else ''
    sales_order = None
    operator = _request_operator(request)

    if note_type == 'payment':
        try:
            return _create_payment_note(request, operator)
        except OperationalError:
            return JsonResponse({'error': '请求正在处理中，请稍后重试'}, status=409)

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

        active_note = next((
            note for note in Privnote.objects.select_for_update().filter(
                sales_order=order, note_type=Privnote.NoteType.PAYMENT,
            ).order_by('-created_at', '-id')
            if note.is_accessible
        ), None)
        if active_note is not None:
            return JsonResponse({
                'error': '该订单已有有效收款单，请先使用当前链接或等待它过期',
                'payment_note': {
                    'id': active_note.id,
                    'token': active_note.token,
                    'url': _privnote_public_url(request, active_note.token),
                    'expires_at': active_note.expires_at.isoformat(),
                },
            }, status=409)

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
            'payment_method_snapshot': serialize_payment_method(payment_method),
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
        created_by=operator,
        burn_after_read=burn,
        max_views=max_views,
        expires_at=timezone.now() + timedelta(hours=duration_hours),
    )
    if password:
        note.set_password(password)
    note.save()

    url = _privnote_public_url(request, note.token)
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

    # 空查询用于聚焦时展开库存候选，限制 20 条避免卡顿。
    result_limit = 20 if stock_only and not q else 30
    if stock_only and not q:
        # 无需评分的空查询直接在数据库限制候选，避免物化全库存。
        cigars_qs = cigars_qs[:result_limit]
    cigars_list = CigarSearchEngine.search(
        cigars=cigars_qs,
        query=q,
        stock_only=False,  # 已在 QuerySet 层过滤
        limit=result_limit,
    )
    # 图片和批次仅对最终候选批量查询，避免 autocomplete N+1。
    prefetch_related_objects(
        cigars_list,
        'images',
        Prefetch(
            'purchasebatch_set',
            queryset=PurchaseBatch.objects.filter(remaining__gt=0).select_related(
                'purchase_order_item',
            ),
            to_attr='_search_batches',
        ),
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
    """列出全部收款方式，或创建一个立即启用的不可变配置。"""
    if request.method == 'GET':
        methods = PaymentMethod.objects.select_related('fund_account')
        management = request.GET.get('include_inactive') == '1'
        if management:
            methods = methods.order_by('-is_active', 'sort_order', '-created_at')
        else:
            methods = methods.filter(
                is_active=True, fund_account__is_active=True,
                fund_account__currency=FundAccount.Currency.CNY,
            ).order_by('sort_order', '-created_at')
        data = [serialize_payment_method(m, include_fund_account=True, include_management=management) for m in methods]
        return JsonResponse({'methods': data})
    if request.method != 'POST':
        return JsonResponse({'error': '不支持的请求方法'}, status=405)
    try:
        payload = {key: request.POST.get(key, '') for key in ('method_type', 'label', 'bank_name', 'card_number', 'card_holder', 'account', 'remark', 'sort_order', 'fund_account_id')}
        result = create_payment_method(request=request, payload=payload, uploaded_file=request.FILES.get('qr_image'))
        return JsonResponse(result, status=201)
    except PaymentMethodActionError as exc:
        return JsonResponse({'error': str(exc), 'details': exc.details}, status=exc.status)


@staff_required
def payment_method_action(request, method_id, action):
    if request.method != 'POST' or action not in ('activate', 'deactivate'):
        return JsonResponse({'error': '不支持的请求方法或操作'}, status=405)
    try:
        result = set_payment_method_active(request=request, method_id=method_id, active=action == 'activate')
        return JsonResponse(result)
    except PaymentMethodActionError as exc:
        return JsonResponse({'error': str(exc), 'details': exc.details}, status=exc.status)


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
    customers = Customer.objects.filter(deleted_at__isnull=True)
    if q:
        customers = customers.filter(name__icontains=q)
    customers = customers[:20]
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
@observe_access
def api_privnote(request, token):
    """GET/POST /api/privnote/<token>/"""
    note = get_object_or_404(Privnote, token=token)
    request._access_note = note

    if request.method == 'POST':
        if note.has_password:
            try:
                body = json.loads(request.body)
                pwd = body.get('password', '')
            except json.JSONDecodeError:
                pwd = request.POST.get('password', '')
            if not note.verify_password(pwd):
                return JsonResponse({'error': '密码错误', 'requires_password': True}, status=401)
            request.session[f'privnote-password:{note.token}'] = note.password_hash

    if note.is_expired:
        return JsonResponse({'error': 'expired', 'reason': 'expired', 'title': note.title}, status=410)

    if note.is_destroyed:
        return JsonResponse({'error': 'destroyed', 'reason': 'viewed', 'title': note.title}, status=410)

    if note.note_type == 'payment' and note.sales_order:
        order = note.sales_order
        if (
            order.fulfillment_status not in (
                SalesOrder.FulfillmentStatus.CONFIRMED,
                SalesOrder.FulfillmentStatus.SHIPPED,
            )
            or (
                order.payment_status != SalesOrder.PaymentStatus.UNPAID
                and not _payment_v2(note)
            )
        ):
            return JsonResponse({
                'error': 'closed',
                'reason': 'closed',
                'title': note.title,
            }, status=410)

    if note.has_password and not _password_authorized(request, note):
        return JsonResponse({
            'title': note.title,
            'has_password': True,
            'requires_password': True,
        })

    # 收款类型：实时渲染
    try:
        if note.note_type == 'payment' and note.sales_order:
            cfg = note.data_json or {}
            if _payment_v2(note):
                data = _payment_public_data(note)
            # 新格式由 payment_method_id 标识；旧格式保存的是完整 payment
            # 快照，不能把历史手动收款信息误当作新请求数据。
            elif 'payment_method_id' not in cfg:
                data = build_payment_data(
                    note.sales_order,
                    remark=cfg.get('remark') if isinstance(cfg, dict) else None,
                    images=cfg.get('images') if isinstance(cfg, dict) else None,
                    extra_fees=cfg.get('extra_fees') if isinstance(cfg, dict) else None,
                )
                legacy_methods = cfg.get('payment_methods') if isinstance(cfg, dict) else None
                if isinstance(legacy_methods, list):
                    data['payment_methods'] = [
                        {key: value for key, value in method.items() if key not in ('label', 'fund_account_id', 'fund_account_name', 'is_active', 'sort_order', 'created_at')}
                        for method in legacy_methods
                        if isinstance(method, dict) and 'fund_account_id' not in method
                    ]
                elif note.sales_order.payment_manual:
                    manual = note.sales_order.payment_manual
                    if any(manual.get(key) for key in ('bank_name', 'card_number', 'card_holder')):
                        data['payment_methods'] = [{
                            'method_type': 'bank_card',
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
                snapshot = cfg.get('payment_method_snapshot')
                payment_method = None
                if not isinstance(snapshot, dict):
                    # 兼容上线前只保存 payment_method_id 的旧链接；停用不应让旧链接失去收款信息。
                    payment_method = PaymentMethod.objects.filter(pk=cfg.get('payment_method_id')).first()
                data = build_payment_data(
                    note.sales_order,
                    payment_method=payment_method,
                    remark=cfg.get('remark'),
                    images=cfg.get('images', []),
                    # 新 note 不保存 extra_fees：让渲染器从销售单正式人肉费字段计算；
                    # 历史 note 若有快照则继续按快照兼容展示。
                    extra_fees=cfg.get('extra_fees'),
                )
                if isinstance(snapshot, dict):
                    data['payment_methods'] = [{
                        key: value for key, value in snapshot.items()
                        if key not in ('label', 'fund_account_id', 'fund_account_name', 'is_active', 'sort_order', 'created_at')
                    }]
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


@csrf_exempt
def payment_submission(request, token):
    """Anonymous multipart submission, authorised by the payment-link token."""
    if request.method != 'POST':
        return JsonResponse({'error': '仅支持 POST'}, status=405)
    note = get_object_or_404(Privnote.objects.select_related('sales_order'), token=token)
    if note.note_type != Privnote.NoteType.PAYMENT or not _payment_v2(note):
        return JsonResponse({'error': '此链接不支持付款凭证'}, status=409)
    if note.has_password and not _password_authorized(request, note):
        return JsonResponse({'error': '需要先验证访问密码', 'requires_password': True}, status=401)
    if note.is_expired:
        return JsonResponse({'error': 'expired', 'reason': 'expired'}, status=410)
    raw_content_length = request.META.get('CONTENT_LENGTH')
    try:
        content_length = int(raw_content_length) if raw_content_length else 0
    except (TypeError, ValueError):
        return JsonResponse({'error': '请求大小无效'}, status=400)
    if content_length > settings.PAYMENT_SUBMISSION_MAX_REQUEST_BYTES:
        return JsonResponse({'error': '付款凭证总大小不能超过 25MB'}, status=413)
    try:
        result, replayed = submit_payment_evidence(
            note=note,
            files=request.FILES.getlist('files'),
            idempotency_key=request.headers.get('Idempotency-Key', ''),
        )
    except RequestDataTooBig:
        return JsonResponse({'error': '付款凭证总大小不能超过 25MB'}, status=413)
    except PaymentSubmissionError as exc:
        return JsonResponse({'error': str(exc)}, status=exc.status)
    except OperationalError:
        return JsonResponse({'error': '付款凭证正在处理中，请使用相同幂等键重试'}, status=409)
    record_access(request, note, 'submission', dedupe_key=f'submission:{result.pk}')
    return JsonResponse({'payment_submission': serialize_submission(result)}, status=200 if replayed else 201)


@require_GET
def payment_image(request, token, image_id):
    """Serve a private QR snapshot or submitted proof after link authorisation."""
    note = get_object_or_404(
        Privnote.objects.select_related('sales_order'), token=token, note_type=Privnote.NoteType.PAYMENT,
    )
    if note.is_expired:
        raise Http404
    if note.has_password and not _password_authorized(request, note):
        return JsonResponse({'error': '需要先验证访问密码', 'requires_password': True}, status=401)
    storage_name = ''
    content_type = 'application/octet-stream'
    order = note.sales_order
    if order and (
        order.payment_status != SalesOrder.PaymentStatus.UNPAID
        or order.fulfillment_status not in (
            SalesOrder.FulfillmentStatus.CONFIRMED,
            SalesOrder.FulfillmentStatus.SHIPPED,
        )
    ):
        # Links may show the safe terminal confirmation page after a formal
        # receipt, but previously exposed QR/proof URLs must stop working.
        raise Http404
    if image_id == 'qr' and _payment_v2(note):
        storage_name = str(note.data_json.get('payment', {}).get('qr_private_name') or '')
        content_type = mimetypes.guess_type(storage_name)[0] or content_type
    elif image_id.isdigit():
        attachment = PaymentAttachment.objects.select_related('submission').filter(
            pk=int(image_id), submission__privnote=note,
        ).first()
        if attachment:
            storage_name = attachment.file.name
            content_type = attachment.content_type
    if not storage_name or not private_payment_storage.exists(storage_name):
        raise Http404
    response = FileResponse(private_payment_storage.open(storage_name, 'rb'), content_type=content_type)
    response['Cache-Control'] = 'private, no-store'
    response['X-Content-Type-Options'] = 'nosniff'
    return response


# Compatibility alias
def create_note(request):
    return create(request)
