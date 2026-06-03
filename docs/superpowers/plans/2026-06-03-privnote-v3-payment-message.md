# Privnote v3: 收款 + 消息

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Privnote 从两类型升级为三类型（库存/收款/消息），新增 PaymentMethod 模型和 SalesOrder 状态机。

**Architecture:** 单表 Privnote + NoteType 选择字段。收款类型关联 SalesOrder（可选），实时渲染。消息类型纯文本+图片附件。库存类型现有逻辑不变。

**Tech Stack:** Django 6.0 + SQLite + Django REST Framework

---

## File Structure

| 文件 | 操作 | 职责 |
|------|------|------|
| `privnote/models.py` | 修改 | NoteType 改名+扩展, PaymentMethod 新模型, Privnote +sales_order |
| `cigars/models.py` | 修改 | SalesOrder +status +payment_method_id +payment_manual |
| `privnote/views.py` | 重写 | create() 三分支, _build_payment_data(), search API, payment-methods API |
| `privnote/urls.py` | 修改 | 新路由 |
| `cigardomtabaka_backend/urls.py` | 修改 | 注册新 API 路由 |

---

## Task 1: Models — 数据模型变更

**Files:**
- Modify: `privnote/models.py`
- Modify: `cigars/models.py`

### Step 1: NoteType 重命名 + 扩展

`privnote/models.py` — 把 `NoteType` 的 `CATALOG` 改为 `INVENTORY`，加 `PAYMENT` 和 `MESSAGE`:

```python
class NoteType(models.TextChoices):
    INVENTORY = 'inventory', '库存展示'   # was CATALOG='catalog'
    PAYMENT   = 'payment',   '收款'
    MESSAGE   = 'message',   '消息'
```

同时把 `note_type` 字段的 `default` 从 `'catalog'` 改为 `'inventory'`。

### Step 2: Privnote + sales_order 字段

在 Privnote 模型 `html` 字段后面加:

```python
sales_order = models.ForeignKey(
    'cigars.SalesOrder', on_delete=models.SET_NULL,
    null=True, blank=True,
    verbose_name='关联销售单'
)
```

### Step 3: PaymentMethod 新模型

在 `privnote/models.py` 末尾加:

```python
class PaymentMethod(models.Model):
    """预配置收款方式 — 全局共用"""

    class MethodType(models.TextChoices):
        BANK_CARD = 'bank_card', '银行卡'
        WECHAT    = 'wechat',    '微信'
        ALIPAY    = 'alipay',    '支付宝'

    method_type = models.CharField('类型', max_length=20, choices=MethodType.choices)
    label = models.CharField('标签', max_length=100, help_text='如 "Сбербанк", "微信收款码"')

    # 银行卡专用
    bank_name = models.CharField('银行名', max_length=100, blank=True)
    card_number = models.CharField('卡号', max_length=50, blank=True)
    card_holder = models.CharField('持卡人', max_length=100, blank=True)

    # 二维码
    qr_image = models.ImageField('二维码', upload_to='payment_qr/', blank=True)

    sort_order = models.IntegerField('排序', default=0)
    is_active = models.BooleanField('启用', default=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        ordering = ['sort_order', '-created_at']
        verbose_name = '收款方式'
        verbose_name_plural = '收款方式'

    def __str__(self):
        return f'{self.get_method_type_display()} · {self.label}'
```

### Step 4: SalesOrder 加字段

`cigars/models.py` 的 SalesOrder 类，在 `note` 字段后面加:

```python
class SalesOrder(models.Model):
    # ... existing fields ...
    note = models.TextField('备注', blank=True)

    # NEW
    STATUS_CHOICES = [
        ('draft', '草稿'),
        ('pending_payment', '待付款'),
        ('paid', '已付款'),
        ('shipped', '已发货'),
        ('completed', '已完成'),
        ('cancelled', '已取消'),
    ]
    status = models.CharField('状态', max_length=20, choices=STATUS_CHOICES, default='draft')

    payment_method_id = models.IntegerField('收款方式ID', null=True, blank=True,
        help_text='引用 PaymentMethod.id')
    payment_manual = models.JSONField('手动收款信息', default=dict, blank=True,
        help_text='{"bank_name":"...","card_number":"...","card_holder":"...","wechat_qr":null,"alipay_qr":null}')

    locked = models.BooleanField('已锁定', default=False)
    # ... rest unchanged ...
```

### Step 5: 确认代码无语法错误

```bash
cd /home/jason/moscow_cigar && python -c "import cigars.models; import privnote.models; print('OK')"
```

### Step 6: Commit

```bash
git add cigars/models.py privnote/models.py
git commit -m "feat: add PaymentMethod model, SalesOrder status/payment fields, NoteType inventory/payment/message"
```

---

## Task 2: Migrations

**Files:**
- Create: `privnote/migrations/0004_*.py` (auto)
- Create: `cigars/migrations/01XX_*.py` (auto)

### Step 1: 生成并执行 migration

```bash
cd /home/jason/moscow_cigar
python manage.py makemigrations privnote cigars
python manage.py migrate
```

Expected: makemigrations 生成两个新文件，migrate 无报错。

### Step 2: 验证数据库

```bash
python -c "
import django; import os
os.environ['DJANGO_SETTINGS_MODULE'] = 'cigardomtabaka_backend.settings'
django.setup()
from privnote.models import Privnote, PaymentMethod
from cigars.models import SalesOrder
print('Privnote fields:', [f.name for f in Privnote._meta.get_fields()])
print('SalesOrder fields:', [f.name for f in SalesOrder._meta.get_fields()])
print('PaymentMethod exists:', PaymentMethod is not None)
"
```

### Step 3: Commit

```bash
git add privnote/migrations/ cigars/migrations/
git commit -m "migrations: NoteType rename + SalesOrder status + PaymentMethod"
```

---

## Task 3: Views — 创建/查看/API

**Files:**
- Modify: `privnote/views.py`

### Step 1: 重写 `create()` — 三分支

把现有 `create()` 函数替换为:

```python
from django.shortcuts import get_object_or_404
from django.http import JsonResponse, HttpResponseForbidden
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from datetime import timedelta
from django.utils import timezone
from django.template.loader import render_to_string
import uuid
import json

from cigars.models import Brand, Cigar, PurchaseBatch, User, SalesOrder, SalesOrderItem
from .models import Privnote, PaymentMethod


DURATION_CHOICES = [
    (1, '1 小时'), (6, '6 小时'), (24, '24 小时'),
    (72, '3 天'), (168, '7 天'), (720, '30 天'),
]


def _is_staff(request):
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


# ── Inventory (现有逻辑不变) ──────────────────────────

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


# ── Payment ──────────────────────────────────────────

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

    # 收款方式
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
        if manual.get('bank_name') or manual.get('card_number'):
            payment_methods.append({
                'method_type': 'bank_card',
                'label': '手动填写',
                'bank_name': manual.get('bank_name', ''),
                'card_number': manual.get('card_number', ''),
                'card_holder': manual.get('card_holder', ''),
                'qr_url': None,
            })

    return {
        'mode': 'payment',
        'items': items,
        'total': total,
        'payment_methods': payment_methods,
        'customer_name': sales_order.customer_name or '',
    }


# ── CREATE ───────────────────────────────────────────

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
        # 从 POST 解析订单数据
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
            operator=None,   # TODO: 关联当前 staff
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
        # 附件由前端上传到 media，这里只收文件路径列表
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


# ── SEARCH API ───────────────────────────────────────

@csrf_exempt
def search_cigars(request):
    """GET /api/cigars/search/?q=xxx&stock_only=1"""
    if not _is_staff(request):
        return HttpResponseForbidden("仅限工作人员访问")

    q = request.GET.get('q', '').strip()
    stock_only = request.GET.get('stock_only', '0') == '1'

    cigars = Cigar.objects.select_related('brand').all()

    if stock_only:
        # 只显示有库存的
        in_stock_ids = PurchaseBatch.objects.filter(
            remaining__gt=0
        ).values_list('cigar_id', flat=True).distinct()
        cigars = cigars.filter(id__in=in_stock_ids)

    if q:
        cigars = cigars.filter(
            models.Q(name__icontains=q) |
            models.Q(english_name__icontains=q) |
            models.Q(brand__name__icontains=q) |
            models.Q(brand__english_name__icontains=q)
        )

    cigars = cigars[:30]

    results = []
    for c in cigars:
        # 如果是从库存模式，附带 batch 信息
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
            'brand': c.brand.name or c.brand.english_name,
            'vitola': c.vitola or '',
            'thumb_url': thumb_url,
            'batches': batches,
        })

    return JsonResponse({'results': results})


# ── PAYMENT METHODS API ──────────────────────────────

def list_payment_methods(request):
    """GET /api/payment-methods/"""
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


# ── API: VIEW NOTE (客户查看) ─────────────────────────

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
```

### Step 2: 添加 models.Q 导入

确认 `privnote/views.py` 顶部有:

```python
from django.db import models
```

### Step 3: 验证语法

```bash
cd /home/jason/moscow_cigar && python -c "import privnote.views; print('OK')"
```

### Step 4: Commit

```bash
git add privnote/views.py
git commit -m "feat: privnote create() three-branch, search API, payment-methods API, real-time payment view"
```

---

## Task 4: URLs

**Files:**
- Modify: `privnote/urls.py`
- Modify: `cigardomtabaka_backend/urls.py`

### Step 1: `privnote/urls.py`

```python
from django.urls import path
from . import views

urlpatterns = [
    path('create/', views.create, name='privnote_create'),
    path('api/search-cigars/', views.search_cigars, name='privnote_search_cigars'),
    path('api/payment-methods/', views.list_payment_methods, name='privnote_payment_methods'),
]
```

### Step 2: 主 `urls.py` 注册 privnote urls

`cigardomtabaka_backend/urls.py`:

```python
# 已有: path('privnote/create/', create_note, name='privnote_create'),
# 改为:
path('privnote/', include('privnote.urls')),
```

同时删除顶部的 `from privnote.views import create_note`（因为现在通过 include 走）。

### Step 3: 验证路由

```bash
cd /home/jason/moscow_cigar && python manage.py show_urls 2>/dev/null || python -c "
from cigardomtabaka_backend.urls import urlpatterns
for u in urlpatterns:
    print(u.pattern)
"
```

### Step 4: Commit

```bash
git add privnote/urls.py cigardomtabaka_backend/urls.py
git commit -m "feat: register privnote URLs via include, add search/payment-methods routes"
```

---

## Task 5: Django Admin 注册 (可选)

**Files:**
- Modify: `privnote/admin.py` (不存在则创建)

### Step 1: 注册 PaymentMethod 到 Admin

```bash
cat > /home/jason/moscow_cigar/privnote/admin.py << 'EOF'
from django.contrib import admin
from .models import Privnote, PaymentMethod


@admin.register(Privnote)
class PrivnoteAdmin(admin.ModelAdmin):
    list_display = ['token', 'note_type', 'title', 'burn_after_read', 'view_count', 'created_at', 'expires_at']
    list_filter = ['note_type', 'burn_after_read']
    search_fields = ['token', 'title']
    readonly_fields = ['token', 'view_count', 'created_at']


@admin.register(PaymentMethod)
class PaymentMethodAdmin(admin.ModelAdmin):
    list_display = ['label', 'method_type', 'is_active', 'sort_order']
    list_filter = ['method_type', 'is_active']
    search_fields = ['label', 'bank_name', 'card_number']
EOF
```

### Step 2: Commit

```bash
git add privnote/admin.py
git commit -m "feat: register Privnote+PaymentMethod in Django Admin"
```
