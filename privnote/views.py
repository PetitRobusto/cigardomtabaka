from django.shortcuts import get_object_or_404, render
from django.http import JsonResponse, HttpResponseForbidden
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.db import models
from datetime import timedelta
from django.utils import timezone
import uuid
import json
import os
import re
from datetime import datetime

from cigars.models import Brand, Cigar, PurchaseBatch, User, SalesOrder, SalesOrderItem, Customer, CigarPrice
from .models import Privnote, PaymentMethod

try:
    from rapidfuzz import fuzz
    HAS_RAPIDFUZZ = True
except ImportError:
    HAS_RAPIDFUZZ = False

try:
    from price_tracker.matcher import normalize as _matcher_normalize, _basic_normalize
    HAS_MATCHER = True
except ImportError:
    HAS_MATCHER = False


# 品牌外文名 → 中文名（用于搜索聚合关键字）
BRAND_CN_MAP = {
    'Belinda': '贝琳达',
    'Bolívar': '玻利瓦',
    'Cabañas': '卡班纳',
    'Caney': '凯尼',
    'Cifuentes': '西福恩特斯',
    'Cohiba': '高希霸',
    'Cuaba': '库阿巴',
    'Cubatabaco': '古巴雪茄',
    'Davidoff': '大卫杜夫',
    'Diplomáticos': '外交官',
    'Don Alfredo': '唐、阿尔佛',
    'Don Cándido': '唐、坎迪多',
    'Dunhill': '登喜路',
    'Edmundo Dantes': '艾蒙度但丁',
    'El Rey del Mundo': '世界之王',
    'Flor del Punto': '繁花',
    'Fonseca': '科塞卡',
    'Gispert': '基斯伯',
    'Guantanamera': '关达拉美拉',
    'H. Upmann': '乌普曼',
    'Habanos': '哈伯纳斯',
    'Hoyo de Monterrey': '好友',
    'J. J. Fox Exclusives': 'J.J·福克斯 专享',
    'José L. Piedra': '荷西比雅达',
    'Juan López': '胡安佩洛斯',
    'La Corona': '皇冠雪茄',
    'La Escepción': '拉雅仕帕西安',
    'La Flor de Cano': '卡诺之花',
    'La Flor del Caney': '拉弗洛德卡妮',
    'La Gloria Cubana': '古巴荣耀',
    'Los Statos de Luxe': '劳斯登徒',
    'María Guerrero': '玛丽亚 格雷多',
    'Montecristo': '蒙特',
    'Multi-Brand Releases': '精选品牌系列',
    'Partagás': '帕特加斯',
    'Por Larrañaga': '波尔拉腊尼加',
    'Punch': '潘趣',
    "Quai d'Orsay": '希多尔赛',
    'Quintero': '金特罗',
    'Rafael González': '拉斐尔',
    'Ramón Allones': '雷蒙阿隆尼',
    'Romeo y Julieta': '罗密欧与朱丽叶',
    'Saint Luis Rey': '圣路易斯雷伊',
    'San Cristóbal': '圣克里斯多',
    'San Cristóbal de la Habana': '圣克里斯多',
    'San Luis Rey': '新路易斯雷伊',
    'Sancho Panza': '桑丘潘萨',
    'Siboney': '西波妮',
    'Small Cigars': '小雪茄',
    'Trinidad': '千里达',
    'Troya': '特洛伊',
    'Vegas Robaina': '瓦格斯陆班纳',
    'Vegueros': '威古洛',
}


DURATION_CHOICES = [
    (1, '1 小时'), (6, '6 小时'), (24, '24 小时'),
    (72, '3 天'), (168, '7 天'), (720, '30 天'),
]


def _split_search_terms(q):
    """按 CJK/非 CJK 边界拆分查询词，支持 '帕特D4' → ['帕特', 'D4']"""
    terms = re.findall(r'[\u4e00-\u9fff]+|[^\u4e00-\u9fff\s]+', q)
    return [t.lower() for t in terms if len(t) >= 1]


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

    # 额外费用
    extra_fees = sales_order.payment_manual.get('extra_fees', []) if sales_order.payment_manual else []
    extra_total = round(sum(float(f.get('amount', 0)) for f in extra_fees), 2)

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
                'remark': pm.remark,
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

    # 备注图片
    images = sales_order.payment_manual.get('images', []) if sales_order.payment_manual else []

    return {
        'mode': 'payment',
        'items': items,
        'total': total,
        'extra_fees': extra_fees,
        'extra_total': extra_total,
        'grand_total': round(total + extra_total, 2),
        'payment_methods': payment_methods,
        'customer_name': sales_order.customer_name or '',
        'remark': sales_order.payment_manual.get('remark', '') if sales_order.payment_manual else '',
        'images': images,
    }


# ═══════════════ Quote ═══════════════

def _build_quote_data(quote_mode='full', selected_ids=None, shipping_included=False, customer_name=None, custom_prices=None, shipping_fee_per_stick=None):
    """从 CigarPrice 构建报价单结构化数据"""
    qs = CigarPrice.objects.filter(is_active=True).select_related('cigar')

    if quote_mode == 'custom' and selected_ids:
        qs = qs.filter(cigar_id__in=selected_ids)

    brand_groups = {}
    total_items = 0
    custom_prices = custom_prices or {}
    shipping_fee_per_stick = shipping_fee_per_stick or (20 if shipping_included else 0)

    for cp in qs:
        cigar = cp.cigar
        brand = cigar.brand
        total_items += 1

        # 实时检查库存状态
        in_stock = PurchaseBatch.objects.filter(cigar=cigar, remaining__gt=0).exists()

        thumb_url = ''
        primary = cigar.primary_image
        if primary and primary.thumbnail:
            thumb_url = primary.thumbnail.url

        # 应用自定义价格覆盖
        wholesale_price = cp.wholesale_price
        per_stick_price = cp.per_stick_price
        if cigar.id in custom_prices:
            try:
                custom_price = int(custom_prices[cigar.id])
                if custom_price > 0:
                    wholesale_price = custom_price
                    per_stick_price = round(custom_price / cp.box_size) if cp.box_size else cp.per_stick_price
            except (ValueError, TypeError):
                pass

        item = {
            'cigar_id': cigar.id,
            'brand': brand,
            'brand_cn': '',
            'name': cigar.name or cigar.english_name,
            'english_name': cigar.english_name,
            'vitola': cigar.vitola or '—',
            'box_size': cp.box_size,
            'wholesale_price': wholesale_price,
            'per_stick_price': per_stick_price,
            'thumb_url': thumb_url,
            'in_stock': in_stock,
        }

        if brand not in brand_groups:
            brand_groups[brand] = {
                'brand': brand,
                'brand_cn': '',
                'logo_url': None,
                'items': [],
            }
        brand_groups[brand]['items'].append(item)

    # 获取品牌中文名和 logo
    brand_en_names = list(brand_groups.keys())
    for b in Brand.objects.filter(english_name__in=brand_en_names):
        if b.english_name in brand_groups:
            brand_groups[b.english_name]['brand_cn'] = b.name or b.english_name
            if b.logo:
                brand_groups[b.english_name]['logo_url'] = b.logo.url

    groups = []
    for brand in sorted(brand_groups.keys()):
        g = brand_groups[brand]
        groups.append({
            'brand': g['brand'],
            'brand_cn': g['brand_cn'] or g['brand'],
            'logo_url': g['logo_url'],
            'items': g['items'],
        })

    return {
        'mode': 'quote',
        'brand_groups': groups,
        'total_items': total_items,
        'shipping_included': shipping_included,
        'shipping_fee_per_stick': shipping_fee_per_stick,
        'customer_name': customer_name,
    }


# ═══════════════ CREATE ═══════════════

@csrf_exempt
def create(request):
    """POST /privnote/create/ — 三种类型统一创建入口"""
    if not _is_staff(request):
        return HttpResponseForbidden("仅限工作人员访问")

    note_type = request.POST.get('note_type', 'inventory')
    # Backward compat: old NoteType values
    if note_type == 'catalog':
        note_type = 'inventory'
    elif note_type == 'sales':
        note_type = 'payment'
    duration_hours = int(request.POST.get('duration', 24))
    password = request.POST.get('password', '').strip()
    burn = request.POST.get('burn', 'on') == 'on'

    is_debug = settings.DEBUG
    debug_tag = ' [测试数据]' if is_debug else ''

    # ── INVENTORY ──
    if note_type == 'inventory':
        # Preview mode: return inventory data without creating privnote
        if request.POST.get('preview') == '1':
            return JsonResponse({'preview': _build_inventory_data()})
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
        customer_id = request.POST.get('customer_id', '').strip()
        # customer_id 优先
        if customer_id:
            try:
                customer = Customer.objects.get(id=int(customer_id))
                customer_name = customer.name
            except (Customer.DoesNotExist, ValueError):
                pass

        payment_method_id = request.POST.get('payment_method_id', '')
        payment_manual_raw = request.POST.get('payment_manual', '{}')
        extra_fees_raw = request.POST.get('extra_fees', '[]')
        remark = request.POST.get('remark', '').strip()
        images_raw = request.POST.get('images', '[]')

        try:
            payment_manual = json.loads(payment_manual_raw) if payment_manual_raw else {}
        except json.JSONDecodeError:
            payment_manual = {}

        try:
            extra_fees = json.loads(extra_fees_raw)
        except json.JSONDecodeError:
            extra_fees = []

        try:
            images = json.loads(images_raw)
        except json.JSONDecodeError:
            images = []

        total_extra = round(sum(float(f.get('amount', 0)) for f in extra_fees), 2)

        # 创建 SalesOrder
        order = SalesOrder.objects.create(
            customer_name=customer_name or '',
            operator=None,
            status='draft',
            payment_method_id=int(payment_method_id) if payment_method_id else None,
            payment_manual=dict(payment_manual, extra_fees=extra_fees, remark=remark, images=images),
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
        images_raw = request.POST.get('images', '[]')
        try:
            attachments = json.loads(attachments_raw)
        except json.JSONDecodeError:
            attachments = []

        try:
            images = json.loads(images_raw)
        except json.JSONDecodeError:
            images = []

        if not text and not attachments and not images:
            return JsonResponse({'error': '消息内容和附件至少填一个'}, status=400)

        title = f'消息 · {timezone.now().strftime("%Y-%m-%d %H:%M")}{debug_tag}'
        data = {'mode': 'message', 'text': text, 'attachments': attachments, 'images': images}
        sales_order = None

    # ── QUOTE ──
    elif note_type == 'quote':
        quote_mode = request.POST.get('quote_mode', 'full')
        selected_ids_raw = request.POST.get('selected_ids', '[]')
        shipping_included = request.POST.get('shipping_included', 'false') == 'true'
        quote_customer_name = request.POST.get('customer_name', '').strip()
        custom_prices_raw = request.POST.get('custom_prices', '{}')

        try:
            selected_ids = json.loads(selected_ids_raw) if selected_ids_raw else []
        except json.JSONDecodeError:
            selected_ids = []

        try:
            custom_prices = json.loads(custom_prices_raw) if custom_prices_raw else {}
        except json.JSONDecodeError:
            custom_prices = {}

        # 过滤非法值：只保留正整数
        custom_prices = {
            int(k): int(v) for k, v in custom_prices.items()
            if isinstance(v, (int, float, str)) and int(v) > 0
        }

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

    cigars = Cigar.objects.all()

    if stock_only:
        in_stock_ids = PurchaseBatch.objects.filter(
            remaining__gt=0
        ).values_list('cigar_id', flat=True).distinct()
        cigars = cigars.filter(id__in=in_stock_ids)

    # 不过滤：直接全量取，让 RapidFuzz 在聚合关键字上做匹配
    # （库中仅 ~1300 条，全量排序性能可接受）
    cigars = list(cigars)

    # ── RapidFuzz 精排 ──
    if HAS_RAPIDFUZZ and q and len(cigars) > 1:
        q_lower = q.lower().strip()
        terms = _split_search_terms(q)
        is_multi_term = len(terms) > 1
        scored = []

        for c in cigars:
            brand = c.brand or ''
            brand_cn = BRAND_CN_MAP.get(brand, '')
            name = c.name or ''
            ename = c.english_name or ''
            vitola = c.vitola or ''
            vitola_cn = c.vitola_cn or ''
            common = c.common_name or ''
            common_cn = c.common_name_cn or ''

            # 生成缩写别名，用于提升模糊搜索召回率
            abbreviations = []
            # 从英文名提取 Serie X No.Y → XY
            for m in re.finditer(r'\b([A-Z])\s*No\.\s*(\d+)', ename, re.I):
                abbreviations.append(f"{m.group(1)}{m.group(2)}")  # e.g. D4
            # 从中文名提取 X系列 Y号 → XY
            for m in re.finditer(r'([A-Z])系列\s*(\d+)号', name):
                abbreviations.append(f"{m.group(1)}{m.group(2)}")  # e.g. D4
            # 英文名 BHK 54 → BHK54
            for m in re.finditer(r'\b(BHK)\s+(\d+)', ename, re.I):
                abbreviations.append(f"{m.group(1)}{m.group(2)}")  # e.g. BHK54
            # 英文名 Magnum 54 → Magnum54
            for m in re.finditer(r'\b(Magnum)\s+(\d+)', ename, re.I):
                abbreviations.append(f"{m.group(1)}{m.group(2)}")

            # 聚合搜索关键字：包含中/外文品牌、品名、型号、常见名 + 缩写别名
            search_text = f"{brand_cn} {brand} {name} {ename} {vitola} {vitola_cn} {common} {common_cn} {' '.join(abbreviations)}"
            search_lower = search_text.lower()
            # 去除所有空格，用于模糊匹配（解决"宽丘"无法匹配"宽 丘吉尔"的问题）
            search_compact = search_lower.replace(' ', '')

            # 基础分：token_set_ratio + partial_ratio + ratio（使用 compact 文本提升子串匹配）
            base_score = max(
                fuzz.token_set_ratio(q_lower, search_compact),
                fuzz.partial_ratio(q_lower, search_compact),
                fuzz.ratio(q_lower, search_compact) * 0.85,
            )
            score = base_score

            # ── 多词查询 AND 语义加分 ──
            if is_multi_term:
                all_terms_hit = True
                for term in terms:
                    term_lower = term.lower()
                    # 纯数字要求非数字边界匹配，避免 "4" 匹配 "2024"
                    if term.isdigit():
                        has_term = bool(re.search(rf'(?<!\d){re.escape(term_lower)}(?!\d)', search_compact))
                    else:
                        has_term = term_lower in search_compact
                    if has_term:
                        # 命中品牌名区域（靠前）权重更高
                        brand_zone = f"{brand_cn} {brand}".lower().replace(' ', '')
                        if term_lower in brand_zone:
                            score += 20
                        else:
                            score += 10
                    else:
                        all_terms_hit = False
                if all_terms_hit:
                    score += 25  # 全匹配奖励

            # ── 单查询词额外加分 ──
            if not is_multi_term:
                if q_lower in search_compact:
                    score += 15

            # ── 常规款优先：特殊版/保湿盒/周年款降权 ──
            if c.release_type in ('Limited Edition Series', 'Replica Antique Humidor Series',
                                  'Commemorative Release', 'Grand Reserve Series',
                                  'Reserve Series', 'Aged Habanos Series',
                                  'Vintage Series', 'Chinese Year Series',
                                  'Millennium Reserve Series', 'Special Production'):
                score -= 10
            elif c.release_type:
                score -= 3
            else:
                score += 5  # 常规款加分

            scored.append((c, score))

        scored.sort(key=lambda x: -x[1])
        # 去重：保留同 (brand, english_name, vitola) 中最高分的
        seen = set()
        deduped = []
        for c, s in scored:
            key = (c.brand, c.english_name, c.vitola)
            if key not in seen:
                seen.add(key)
                deduped.append(c)
        cigars = deduped[:30]
    else:
        cigars = cigars[:30]

    results = []
    for c in cigars:
        batches = []
        total_stock = 0
        if stock_only:
            for b in c.purchasebatch_set.filter(remaining__gt=0).select_related('purchase_order_item'):
                box_size = b.purchase_order_item.box_size or 25
                batches.append({
                    'batch_id': b.id,
                    'box_size': box_size,
                    'remaining': b.remaining,
                    'unit_cost_cny': b.unit_cost_cny,
                })
                total_stock += b.remaining
        else:
            total_stock = c.purchasebatch_set.filter(remaining__gt=0).aggregate(
                total=models.Sum('remaining')
            )['total'] or 0

        thumb_url = ''
        primary = c.primary_image
        if primary and primary.thumbnail:
            thumb_url = primary.thumbnail.url

        results.append({
            'id': c.id,
            'name': c.name or c.english_name,
            'english_name': c.english_name,
            'brand': c.brand,
            'brand_cn': BRAND_CN_MAP.get(c.brand, ''),
            'vitola': c.vitola or '',
            'length': c.length,
            'ring_gauge': c.ring_gauge,
            'thumb_url': thumb_url,
            'batches': batches,
            'stock_qty': total_stock,
        })

    return JsonResponse({'results': results})


# ═══════════════ QUOTE PRODUCTS API ═══════════════

def list_quote_products(request):
    """GET /privnote/api/quote-products/ — 返回全部有批发价的雪茄"""
    if not _is_staff(request):
        return HttpResponseForbidden("仅限工作人员访问")

    qs = CigarPrice.objects.filter(is_active=True).select_related('cigar')
    products = []

    # 批量查询品牌信息，避免 N+1
    brand_map = {}
    for b in Brand.objects.all():
        brand_map[b.english_name] = b.name or b.english_name

    # 批量查询库存状态
    in_stock_ids = set(
        PurchaseBatch.objects.filter(remaining__gt=0)
        .values_list('cigar_id', flat=True)
        .distinct()
    )

    for cp in qs:
        cigar = cp.cigar
        in_stock = cigar.id in in_stock_ids

        thumb_url = ''
        primary = cigar.primary_image
        if primary and primary.thumbnail:
            thumb_url = primary.thumbnail.url

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
            'thumb_url': thumb_url,
            'in_stock': in_stock,
        })

    return JsonResponse({'products': products})


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
            'remark': m.remark,
        })
    return JsonResponse({'methods': data})


# ═══════════════ CUSTOMER SEARCH API ═══════════════

def search_customers(request):
    """GET /privnote/api/search-customers/?q=xxx"""
    if not _is_staff(request):
        return HttpResponseForbidden("仅限工作人员访问")
    q = request.GET.get('q', '').strip()
    if not q:
        return JsonResponse({'results': []})
    customers = Customer.objects.filter(name__icontains=q)[:20]
    results = [{'id': c.id, 'name': c.name, 'phone': c.phone} for c in customers]
    return JsonResponse({'results': results})


# ═══════════════ UPLOAD IMAGE ═══════════════

@csrf_exempt
def upload_image(request):
    """POST /privnote/api/upload-image/ — 上传图片到 media/privnote/YYYYMMDD/"""
    if not _is_staff(request):
        return HttpResponseForbidden("仅限工作人员访问")

    if request.method != 'POST':
        return JsonResponse({'error': '仅支持 POST'}, status=405)

    file = request.FILES.get('image')
    if not file:
        return JsonResponse({'error': '未提供图片文件'}, status=400)

    # Validate file type
    allowed_types = ('image/jpeg', 'image/png', 'image/gif', 'image/webp')
    if file.content_type not in allowed_types:
        return JsonResponse({'error': '仅支持 jpg/png/gif/webp 格式'}, status=400)

    # Validate file size (max 10MB)
    if file.size > 10 * 1024 * 1024:
        return JsonResponse({'error': '图片大小不能超过 10MB'}, status=400)

    # Build path: media/privnote/YYYYMMDD/filename
    today = datetime.now().strftime('%Y%m%d')
    upload_dir = os.path.join('privnote', today)
    full_dir = os.path.join(settings.MEDIA_ROOT, upload_dir)
    os.makedirs(full_dir, exist_ok=True)

    # Generate unique filename
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
        data = _build_payment_data(note.sales_order)
    elif note.note_type == 'quote':
        cfg = note.data_json or {}
        data = _build_quote_data(
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


# ═══════════════ PAGES ═══════════════

def index(request):
    """GET /privnote/ — 创建页面 (仅 staff)"""
    if not _is_staff(request):
        return HttpResponseForbidden("仅限工作人员访问")
    return render(request, 'privnote/index.html')


# ═══════════════ VIEW NOTE PAGE ═══════════════

def view_note(request, token):
    """GET /p/<token>/ — 客户查看页面 (JS 渲染版)"""
    from django.shortcuts import render
    return render(request, 'privnote/view.html', {'token': token})
