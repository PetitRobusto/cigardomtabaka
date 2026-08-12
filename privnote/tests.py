"""
Privnote v3 测试套件
覆盖: Models / Views (创建/查看/搜索/收款方式) / 权限 / 实时渲染
"""
import json
from decimal import Decimal
from datetime import timedelta
from django.test import TestCase, Client
from django.utils import timezone
from django.contrib.auth.hashers import check_password
from django.core.exceptions import ValidationError

from privnote.models import Privnote, PaymentMethod
from privnote.services import build_payment_data
from cigars.models import User, Brand, Cigar, SalesOrder, SalesOrderItem, PurchaseBatch, PurchaseOrder, PurchaseOrderItem, CigarPrice
from accounting.models import FundAccount


# ═══════════════════════════════════════════════════
# 测试辅助
# ═══════════════════════════════════════════════════

def _create_staff_user():
    """创建 staff 用户，返回 (user, password)"""
    user = User.objects.create_user('test_staff', password='testpass', is_staff=True)
    return user, 'testpass'


def _create_cigar():
    """创建一个测试雪茄"""
    brand = Brand.objects.create(english_name='TestBrand', name='测试品牌')
    cigar = Cigar.objects.create(
        brand=brand.english_name, english_name='Test Cigar',
        name='测试雪茄', vitola='Robusto'
    )
    return cigar


def _create_batch(cigar, remaining=50, box_size=25, unit_cost=200.0, loose=False):
    """创建一个进货批次"""
    import uuid
    from cigars.models import Supplier
    supplier = Supplier.objects.create(name=f'TestSupplier-{uuid.uuid4().hex[:6]}')
    po = PurchaseOrder.objects.create(
        supplier=supplier, rub_total=10000, exchange_rate=12, cny_total=1200,
        operator=User.objects.first() or User.objects.create_user('_po_op', password='x')
    )
    poi = PurchaseOrderItem.objects.create(
        purchase_order=po, cigar=cigar, quantity=remaining,
        box_size=box_size, unit_price_rub=2400, unit_price_cny=unit_cost
    )
    packaging = {}
    if loose:
        original_boxes, original_sticks = divmod(remaining, box_size)
        packaging = {
            'original_box_quantity': original_boxes,
            'original_stick_quantity': original_sticks,
            'physical_stick_quantity': remaining,
            'available_stick_quantity': remaining,
        }
    batch = PurchaseBatch.objects.create(
        purchase_order_item=poi, cigar=cigar,
        quantity=remaining, remaining=remaining,
        physical_remaining=remaining,
        remaining_cost_cny=Decimal(str(remaining)) * Decimal(str(unit_cost)),
        original_cost_cny=Decimal(str(remaining)) * Decimal(str(unit_cost)),
        positive_adjustment_quantity=0,
        positive_adjustment_cost_cny=Decimal('0.00'),
        adjustment_cost_cny=Decimal('0.00'),
        sold_cost_cny=Decimal('0.00'),
        unit_cost_cny=unit_cost,
        **packaging,
    )
    return batch


# ═══════════════════════════════════════════════════
# MODEL 测试
# ═══════════════════════════════════════════════════

class NoteTypeTestCase(TestCase):
    """NoteType 枚举正确性"""

    def test_note_type_choices(self):
        choices = dict(Privnote.NoteType.choices)
        self.assertIn('inventory', choices)
        self.assertIn('payment', choices)
        self.assertIn('message', choices)
        self.assertEqual(choices['inventory'], '库存展示')
        self.assertEqual(choices['payment'], '收款')
        self.assertEqual(choices['message'], '消息')

    def test_note_type_default(self):
        note = Privnote.objects.create(
            token='abc123', title='test',
            expires_at=timezone.now() + timedelta(hours=1)
        )
        self.assertEqual(note.note_type, 'inventory')


class PaymentMethodModelTestCase(TestCase):
    """PaymentMethod 模型"""

    def test_create_bank_card(self):
        pm = PaymentMethod.objects.create(
            method_type='bank_card', label='Сбербанк',
            bank_name='Сбербанк', card_number='1234567890', card_holder='IVAN'
        )
        self.assertEqual(pm.method_type, 'bank_card')
        self.assertEqual(str(pm), '银行卡 · Сбербанк')

    def test_fund_account_persistence_validation(self):
        cny = FundAccount.objects.create(name='CNY', currency='CNY', creation_idempotency_key='pm-cny')
        rub = FundAccount.objects.create(name='RUB', currency='RUB', creation_idempotency_key='pm-rub')
        with self.assertRaises(ValidationError):
            PaymentMethod.objects.create(method_type='wechat', label='rub', fund_account=rub)
        with self.assertRaises(ValidationError):
            PaymentMethod(method_type='wechat', label='unsaved', fund_account=FundAccount(name='RUB2', currency='RUB', creation_idempotency_key='pm-rub2')).save()
        stale = PaymentMethod(method_type='wechat', label='stale')
        stale.fund_account_id = 999999
        with self.assertRaises(ValidationError):
            stale.save()
        PaymentMethod.objects.create(method_type='wechat', label='null')
        PaymentMethod.objects.create(method_type='wechat', label='cny', fund_account=cny)

    def test_create_wechat(self):
        pm = PaymentMethod.objects.create(
            method_type='wechat', label='微信收款码'
        )
        self.assertEqual(pm.method_type, 'wechat')
        self.assertTrue(pm.is_active)

    def test_create_alipay(self):
        pm = PaymentMethod.objects.create(
            method_type='alipay', label='支付宝收款码'
        )
        self.assertEqual(pm.method_type, 'alipay')

    def test_ordering_by_sort_order(self):
        PaymentMethod.objects.create(method_type='bank_card', label='B', sort_order=2)
        PaymentMethod.objects.create(method_type='bank_card', label='A', sort_order=1)
        PaymentMethod.objects.create(method_type='wechat', label='C', sort_order=3)
        methods = list(PaymentMethod.objects.filter(is_active=True))
        self.assertEqual(methods[0].label, 'A')
        self.assertEqual(methods[1].label, 'B')
        self.assertEqual(methods[2].label, 'C')

    def test_inactive_filtering(self):
        active = PaymentMethod.objects.create(method_type='bank_card', label='Active', is_active=True)
        PaymentMethod.objects.create(method_type='wechat', label='Inactive', is_active=False)
        methods = PaymentMethod.objects.filter(is_active=True)
        self.assertEqual(methods.count(), 1)
        self.assertEqual(methods[0].label, 'Active')


class PrivnoteModelTestCase(TestCase):
    """Privnote 模型属性"""

    def setUp(self):
        self.note = Privnote.objects.create(
            token='test-token', note_type='inventory', title='TestNote',
            expires_at=timezone.now() + timedelta(hours=24)
        )

    def test_not_expired_when_fresh(self):
        self.assertFalse(self.note.is_expired)

    def test_expired_when_past(self):
        self.note.expires_at = timezone.now() - timedelta(hours=1)
        self.note.save()
        self.assertTrue(self.note.is_expired)

    def test_not_destroyed_when_unviewed(self):
        self.note.burn_after_read = True
        self.note.max_views = 1
        self.note.view_count = 0
        self.assertFalse(self.note.is_destroyed)

    def test_destroyed_when_viewed_once(self):
        self.note.burn_after_read = True
        self.note.max_views = 1
        self.note.view_count = 1
        self.assertTrue(self.note.is_destroyed)

    def test_not_destroyed_without_burn_and_no_max_views(self):
        self.note.burn_after_read = False
        self.note.max_views = 0
        self.note.view_count = 999
        self.assertFalse(self.note.is_destroyed)

    def test_accessible(self):
        self.assertTrue(self.note.is_accessible)

    def test_not_accessible_when_expired(self):
        self.note.expires_at = timezone.now() - timedelta(hours=1)
        self.note.save()
        self.assertFalse(self.note.is_accessible)

    def test_password_set_and_verify(self):
        self.note.set_password('secret123')
        self.note.save()
        self.assertTrue(self.note.has_password)
        self.assertTrue(self.note.verify_password('secret123'))
        self.assertFalse(self.note.verify_password('wrong'))
        # 密码哈希不入明文
        self.assertNotIn('secret123', self.note.password_hash)

    def test_mark_viewed_increments(self):
        self.assertEqual(self.note.view_count, 0)
        self.note.mark_viewed()
        self.assertEqual(self.note.view_count, 1)
        self.note.mark_viewed()
        self.assertEqual(self.note.view_count, 2)

    def test_sales_order_fk_nullable(self):
        """sales_order 可以为空"""
        note = Privnote.objects.create(
            token='no-so', note_type='message', title='Msg',
            expires_at=timezone.now() + timedelta(hours=1)
        )
        self.assertIsNone(note.sales_order)

    def test_sales_order_fk_linked(self):
        """sales_order 可以关联"""
        cigar = _create_cigar()
        so = SalesOrder.objects.create(
            customer_name='TestCustomer', status='draft',
            operator=User.objects.first() or User.objects.create_user('_so_op', password='x')
        )
        note = Privnote.objects.create(
            token='with-so', note_type='payment', title='Pay',
            expires_at=timezone.now() + timedelta(hours=1),
            sales_order=so
        )
        self.assertEqual(note.sales_order, so)
        self.assertEqual(note.sales_order.customer_name, 'TestCustomer')

    def test_token_unique(self):
        Privnote.objects.create(
            token='dup-token', title='First',
            expires_at=timezone.now() + timedelta(hours=1)
        )
        with self.assertRaises(Exception):
            Privnote.objects.create(
                token='dup-token', title='Second',
                expires_at=timezone.now() + timedelta(hours=1)
            )


class SalesOrderStatusTestCase(TestCase):
    """SalesOrder 状态字段"""

    def test_default_status_is_draft(self):
        so = SalesOrder.objects.create(
            operator=User.objects.first() or User.objects.create_user('_so_op2', password='x')
        )
        self.assertEqual(so.status, 'draft')

    def test_status_choices_valid(self):
        so = SalesOrder.objects.create(
            operator=User.objects.first() or User.objects.create_user('_so_op3', password='x'),
            status='paid'
        )
        self.assertEqual(so.status, 'paid')

    def test_payment_method_id_nullable(self):
        so = SalesOrder.objects.create(
            operator=User.objects.first() or User.objects.create_user('_so_op4', password='x')
        )
        self.assertIsNone(so.payment_method_id)

    def test_payment_manual_default_empty_dict(self):
        so = SalesOrder.objects.create(
            operator=User.objects.first() or User.objects.create_user('_so_op5', password='x')
        )
        self.assertEqual(so.payment_manual, {})

    def test_payment_manual_stores_data(self):
        so = SalesOrder.objects.create(
            operator=User.objects.first() or User.objects.create_user('_so_op6', password='x'),
            payment_manual={'bank_name': 'TestBank', 'card_number': '9999'}
        )
        self.assertEqual(so.payment_manual['bank_name'], 'TestBank')
        self.assertEqual(so.payment_manual['card_number'], '9999')


# ═══════════════════════════════════════════════════
# VIEW 测试 — 权限
# ═══════════════════════════════════════════════════

class AuthTestCase(TestCase):
    """权限守卫"""

    def setUp(self):
        self.client = Client()
        self.user, self.password = _create_staff_user()

    def test_create_blocked_for_anonymous(self):
        resp = self.client.post('/privnote/create/', {'note_type': 'inventory', 'duration': 24})
        self.assertEqual(resp.status_code, 403)

    def test_create_allowed_for_staff(self):
        self.client.login(username=self.user.username, password=self.password)
        resp = self.client.post('/privnote/create/', {'note_type': 'inventory', 'duration': 24})
        self.assertEqual(resp.status_code, 200)

    def test_search_cigars_blocked_for_anonymous(self):
        resp = self.client.get('/privnote/api/search-cigars/?q=test')
        self.assertEqual(resp.status_code, 403)

    def test_search_cigars_allowed_for_staff(self):
        self.client.login(username=self.user.username, password=self.password)
        resp = self.client.get('/privnote/api/search-cigars/?q=test')
        self.assertEqual(resp.status_code, 200)

    def test_payment_methods_blocked_for_anonymous(self):
        resp = self.client.get('/privnote/api/payment-methods/')
        self.assertEqual(resp.status_code, 403)

    def test_payment_methods_allowed_for_staff(self):
        self.client.login(username=self.user.username, password=self.password)
        resp = self.client.get('/privnote/api/payment-methods/')
        self.assertEqual(resp.status_code, 200)


# ═══════════════════════════════════════════════════
# VIEW 测试 — 创建
# ═══════════════════════════════════════════════════

class CreateInventoryTestCase(TestCase):
    """创建库存 privnote"""

    def setUp(self):
        self.client = Client()
        self.user, self.password = _create_staff_user()
        self.client.login(username=self.user.username, password=self.password)

    def test_create_inventory_success(self):
        resp = self.client.post('/privnote/create/', {
            'note_type': 'inventory',
            'duration': 24,
            'burn': 'on',
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn('url', data)
        self.assertIn('token', data)
        self.assertIn('/p/', data['url'])
        self.assertIn(data['token'], data['url'])

    def test_create_inventory_with_password(self):
        resp = self.client.post('/privnote/create/', {
            'note_type': 'inventory',
            'duration': 24,
            'password': 'secret',
            'burn': 'on',
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['has_password'])

    def test_create_inventory_without_burn(self):
        resp = self.client.post('/privnote/create/', {
            'note_type': 'inventory',
            'duration': 24,
            'burn': 'off',
        })
        self.assertEqual(resp.status_code, 200)


class CreatePaymentTestCase(TestCase):
    """创建收款 privnote"""

    def setUp(self):
        self.client = Client()
        self.user, self.password = _create_staff_user()
        self.client.login(username=self.user.username, password=self.password)
        self.cigar = _create_cigar()
        self.batch = _create_batch(self.cigar, remaining=50, box_size=25, unit_cost=280.0, loose=True)
        self.pm = PaymentMethod.objects.create(
            method_type='bank_card', label='TestBank',
            bank_name='TestBank', card_number='1111222233334444', card_holder='TEST'
        )

    def test_create_payment_success(self):
        items = [{'cigar_id': self.cigar.id, 'quantity': 10, 'unit_price': 350}]
        resp = self.client.post('/privnote/create/', {
            'note_type': 'payment',
            'duration': 24,
            'customer_name': '张三',
            'items': json.dumps(items),
            'payment_method_id': str(self.pm.id),
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn('url', data)
        self.assertIsNotNone(data.get('sales_order_id'))

        # 验证 SalesOrder 创建
        so = SalesOrder.objects.get(id=data['sales_order_id'])
        self.assertEqual(so.status, 'pending_payment')
        self.assertEqual(so.customer_name, '张三')
        self.assertEqual(so.payment_method_id, self.pm.id)
        self.assertEqual(so.total_revenue, Decimal('3500.00'))

        # 验证 SalesOrderItem 创建
        items_qs = so.items.all()
        self.assertEqual(items_qs.count(), 1)
        self.assertEqual(items_qs[0].cigar.id, self.cigar.id)
        self.assertEqual(items_qs[0].quantity, 10)
        self.assertEqual(items_qs[0].unit_price, Decimal('350.00'))

        # 验证 Privnote 关联
        note = Privnote.objects.get(token=data['token'])
        self.assertEqual(note.sales_order.id, so.id)

    def test_create_payment_multiple_items(self):
        cigar2 = Cigar.objects.create(
            brand='TestBrand', english_name='Cigar2', name='雪茄2'
        )
        _create_batch(cigar2, remaining=30, box_size=15, unit_cost=150.0, loose=True)

        items = [
            {'cigar_id': self.cigar.id, 'quantity': 5, 'unit_price': 350},
            {'cigar_id': cigar2.id, 'quantity': 3, 'unit_price': 200},
        ]
        resp = self.client.post('/privnote/create/', {
            'note_type': 'payment',
            'duration': 24,
            'items': json.dumps(items),
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        so = SalesOrder.objects.get(id=data['sales_order_id'])
        self.assertEqual(so.items.count(), 2)
        self.assertEqual(so.total_revenue, Decimal('2350.00'))

    def test_create_payment_with_batch_cost(self):
        """关联 batch 自动填成本"""
        items = [{'cigar_id': self.cigar.id, 'quantity': 10, 'unit_price': 350, 'batch_id': self.batch.id}]
        resp = self.client.post('/privnote/create/', {
            'note_type': 'payment',
            'duration': 24,
            'items': json.dumps(items),
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        so = SalesOrder.objects.get(id=data['sales_order_id'])
        item = so.items.first()
        self.assertEqual(item.unit_cost, Decimal('0.00'))
        self.assertEqual(item.cost, Decimal('0.00'))

    def test_create_payment_without_sales_order(self):
        """可以不绑定 SalesOrder（但当前 create 总是创建一个）"""
        # 当前实现：payment 类型总是创建 SalesOrder
        # sales_order FK 在 Privnote 上是 nullable 的，但 create() 总是设值
        items = [{'cigar_id': self.cigar.id, 'quantity': 1, 'unit_price': 100}]
        resp = self.client.post('/privnote/create/', {
            'note_type': 'payment',
            'duration': 24,
            'items': json.dumps(items),
        })
        self.assertEqual(resp.status_code, 200)

    def test_create_payment_empty_items_rejected(self):
        resp = self.client.post('/privnote/create/', {
            'note_type': 'payment',
            'duration': 24,
            'items': '[]',
        })
        self.assertEqual(resp.status_code, 400)
        self.assertIn('至少需要一个商品', resp.json()['error'])

    def test_create_payment_invalid_json_rejected(self):
        resp = self.client.post('/privnote/create/', {
            'note_type': 'payment',
            'duration': 24,
            'items': 'not-json',
        })
        self.assertEqual(resp.status_code, 400)
        self.assertIn('格式错误', resp.json()['error'])

    def test_create_payment_with_manual_payment_info(self):
        items = [{'cigar_id': self.cigar.id, 'quantity': 5, 'unit_price': 300}]
        resp = self.client.post('/privnote/create/', {
            'note_type': 'payment',
            'duration': 24,
            'items': json.dumps(items),
            'payment_manual': json.dumps({
                'bank_name': 'ManualBank', 'card_number': '9999', 'card_holder': 'Me'
            }),
        })
        self.assertEqual(resp.status_code, 200)
        so = SalesOrder.objects.get(id=resp.json()['sales_order_id'])
        self.assertEqual(so.payment_manual['bank_name'], 'ManualBank')

    def test_create_payment_cigar_not_found(self):
        items = [{'cigar_id': 999999, 'quantity': 1, 'unit_price': 100}]
        resp = self.client.post('/privnote/create/', {
            'note_type': 'payment',
            'duration': 24,
            'items': json.dumps(items),
        })
        self.assertEqual(resp.status_code, 400)
        self.assertIn('商品不存在', resp.json()['error'])

    def test_create_payment_rejects_negative_price(self):
        items = [{'cigar_id': self.cigar.id, 'quantity': 1, 'unit_price': -100}]
        resp = self.client.post('/privnote/create/', {
            'note_type': 'payment',
            'duration': 24,
            'items': json.dumps(items),
        })
        self.assertEqual(resp.status_code, 400)
        self.assertIn('不能为负数', resp.json()['error'])

    def test_create_payment_rejects_mismatched_batch(self):
        cigar2 = Cigar.objects.create(
            brand='TestBrand', english_name='Other Cigar', name='其他雪茄'
        )
        items = [{'cigar_id': cigar2.id, 'quantity': 1, 'unit_price': 100, 'batch_id': self.batch.id}]
        resp = self.client.post('/privnote/create/', {
            'note_type': 'payment',
            'duration': 24,
            'items': json.dumps(items),
        })
        self.assertEqual(resp.status_code, 400)
        self.assertIn('批次不存在或不匹配', resp.json()['error'])


class CreateMessageTestCase(TestCase):
    """创建消息 privnote"""

    def setUp(self):
        self.client = Client()
        self.user, self.password = _create_staff_user()
        self.client.login(username=self.user.username, password=self.password)

    def test_create_message_text_only(self):
        resp = self.client.post('/privnote/create/', {
            'note_type': 'message',
            'duration': 24,
            'text': 'Hello World',
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn('url', data)
        self.assertIsNone(data.get('sales_order_id'))

        # 验证 data_json
        note = Privnote.objects.get(token=data['token'])
        self.assertEqual(note.data_json['mode'], 'message')
        self.assertEqual(note.data_json['text'], 'Hello World')
        self.assertEqual(note.data_json['attachments'], [])

    def test_create_message_with_attachments(self):
        resp = self.client.post('/privnote/create/', {
            'note_type': 'message',
            'duration': 24,
            'text': 'Check these',
            'attachments': json.dumps(['/media/img1.jpg', '/media/img2.jpg']),
        })
        self.assertEqual(resp.status_code, 200)
        note = Privnote.objects.get(token=resp.json()['token'])
        self.assertEqual(len(note.data_json['attachments']), 2)

    def test_create_message_empty_rejected(self):
        resp = self.client.post('/privnote/create/', {
            'note_type': 'message',
            'duration': 24,
            'text': '',
            'attachments': '[]',
        })
        self.assertEqual(resp.status_code, 400)
        self.assertIn('至少填一个', resp.json()['error'])

    def test_create_message_attachments_only(self):
        """只有附件没有文字也行"""
        resp = self.client.post('/privnote/create/', {
            'note_type': 'message',
            'duration': 24,
            'attachments': json.dumps(['/media/test.jpg']),
        })
        self.assertEqual(resp.status_code, 200)


class CreateUnknownTypeTestCase(TestCase):
    """未知类型拒绝"""

    def setUp(self):
        self.client = Client()
        self.user, self.password = _create_staff_user()
        self.client.login(username=self.user.username, password=self.password)

    def test_unknown_type_rejected(self):
        resp = self.client.post('/privnote/create/', {
            'note_type': 'invalid_type',
            'duration': 24,
        })
        self.assertEqual(resp.status_code, 400)
        self.assertIn('未知类型', resp.json()['error'])


# ═══════════════════════════════════════════════════
# VIEW 测试 — 搜索 API
# ═══════════════════════════════════════════════════

class SearchCigarsTestCase(TestCase):
    """雪茄搜索 API"""

    def setUp(self):
        self.client = Client()
        self.user, self.password = _create_staff_user()
        self.client.login(username=self.user.username, password=self.password)
        self.cigar = _create_cigar()
        self.batch = _create_batch(self.cigar, remaining=30, box_size=25, unit_cost=280.0)

    def test_search_all_cigars(self):
        resp = self.client.get('/privnote/api/search-cigars/?q=Test')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn('results', data)
        self.assertGreaterEqual(len(data['results']), 1)
        result = data['results'][0]
        self.assertEqual(result['name'], '测试雪茄')
        self.assertEqual(result['brand'], 'TestBrand')
        # stock_only=0 时不返回 batches
        self.assertEqual(result['batches'], [])

    def test_search_stock_only(self):
        resp = self.client.get('/privnote/api/search-cigars/?q=Test&stock_only=1')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertGreaterEqual(len(data['results']), 1)
        result = data['results'][0]
        self.assertGreater(len(result['batches']), 0)
        batch = result['batches'][0]
        self.assertIn('batch_id', batch)
        self.assertIn('box_size', batch)
        self.assertIn('remaining', batch)
        self.assertIn('unit_cost_cny', batch)
        self.assertEqual(batch['remaining'], 30)
        self.assertEqual(batch['unit_cost_cny'], 280.0)

    def test_search_no_results(self):
        resp = self.client.get('/privnote/api/search-cigars/?q=ZZZZZNotFound')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(len(data['results']), 0)

    def test_search_empty_query_returns_all(self):
        resp = self.client.get('/privnote/api/search-cigars/?q=')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertGreater(len(data['results']), 0)

    def test_search_stock_only_excludes_out_of_stock(self):
        # 创建一款零库存雪茄
        brand = Brand.objects.first() or Brand.objects.create(english_name='OutOfStockBrand')
        out_of_stock = Cigar.objects.create(
            brand=brand.english_name, english_name='OOS Cigar', name='缺货雪茄'
        )
        resp = self.client.get(f'/privnote/api/search-cigars/?q=缺货&stock_only=1')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        # 缺货雪茄不应该出现
        names = [r['name'] for r in data['results']]
        self.assertNotIn('缺货雪茄', names)


# ═══════════════════════════════════════════════════
# VIEW 测试 — 收款方式 API
# ═══════════════════════════════════════════════════

class PaymentMethodsAPITestCase(TestCase):
    """收款方式列表 API"""

    def setUp(self):
        self.client = Client()
        self.user, self.password = _create_staff_user()
        self.client.login(username=self.user.username, password=self.password)

    def test_list_active_only(self):
        PaymentMethod.objects.create(method_type='bank_card', label='A', is_active=True)
        PaymentMethod.objects.create(method_type='wechat', label='B', is_active=False)
        PaymentMethod.objects.create(method_type='alipay', label='C', is_active=True)

        resp = self.client.get('/privnote/api/payment-methods/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(len(data['methods']), 2)

    def test_list_empty(self):
        resp = self.client.get('/privnote/api/payment-methods/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(len(data['methods']), 0)

    def test_list_structure(self):
        PaymentMethod.objects.create(
            method_type='bank_card', label='TestBank',
            bank_name='TestBank', card_number='1234', card_holder='ME'
        )
        resp = self.client.get('/privnote/api/payment-methods/')
        data = resp.json()
        method = data['methods'][0]
        self.assertIn('id', method)
        self.assertEqual(method['method_type'], 'bank_card')
        self.assertEqual(method['label'], 'TestBank')
        self.assertEqual(method['bank_name'], 'TestBank')
        self.assertEqual(method['card_number'], '1234')
        self.assertEqual(method['card_holder'], 'ME')
        self.assertIsNone(method['qr_url'])  # 没上传图片


# ═══════════════════════════════════════════════════
# VIEW 测试 — 查看 privnote (客户)
# ═══════════════════════════════════════════════════

class ViewPrivnoteTestCase(TestCase):
    """客户查看 privnote"""

    def setUp(self):
        self.client = Client()
        self.staff, self.staff_pass = _create_staff_user()
        self.cigar = _create_cigar()
        self.batch = _create_batch(self.cigar, remaining=50, unit_cost=280.0, loose=True)

    def _create_privnote(self, note_type='inventory', data=None, **kwargs):
        """辅助：通过 create view 创建 privnote"""
        self.client.login(username=self.staff.username, password=self.staff_pass)
        post_data = {'note_type': note_type, 'duration': 24}
        post_data.update(kwargs)

        if note_type == 'payment' and 'items' not in post_data:
            post_data['items'] = json.dumps([
                {'cigar_id': self.cigar.id, 'quantity': 5, 'unit_price': 350}
            ])

        resp = self.client.post('/privnote/create/', post_data)
        self.assertEqual(resp.status_code, 200)
        token = resp.json()['token']
        self.client.logout()
        return token

    def test_view_inventory_note(self):
        token = self._create_privnote('inventory')
        resp = self.client.get(f'/api/privnote/{token}/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['note_type'], 'inventory')
        self.assertEqual(data['data']['mode'], 'inventory')

    def test_view_payment_note_real_time(self):
        """收款 privnote 实时渲染"""
        token = self._create_privnote('payment')
        resp = self.client.get(f'/api/privnote/{token}/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['note_type'], 'payment')
        self.assertEqual(data['data']['mode'], 'payment')
        self.assertEqual(len(data['data']['items']), 1)
        self.assertEqual(data['data']['items'][0]['quantity'], 5)
        self.assertEqual(data['data']['items'][0]['unit_price'], 350)
        self.assertEqual(data['data']['items'][0]['subtotal'], 1750)
        self.assertEqual(data['data']['total'], 1750)

    def test_view_message_note(self):
        token = self._create_privnote('message', text='Hello', attachments=json.dumps(['/media/x.jpg']))
        resp = self.client.get(f'/api/privnote/{token}/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['note_type'], 'message')
        self.assertEqual(data['data']['text'], 'Hello')
        self.assertEqual(data['data']['attachments'], ['/media/x.jpg'])

    def test_view_note_destroyed_after_read(self):
        token = self._create_privnote('inventory', burn='on')
        # 第一次查看
        resp1 = self.client.get(f'/api/privnote/{token}/')
        self.assertEqual(resp1.status_code, 200)
        # 第二次查看 — 已销毁
        resp2 = self.client.get(f'/api/privnote/{token}/')
        self.assertEqual(resp2.status_code, 410)
        self.assertIn('viewed', resp2.json()['reason'])

    def test_view_note_expired(self):
        # 创建一个已过期的 privnote
        self.client.login(username=self.staff.username, password=self.staff_pass)
        note = Privnote.objects.create(
            token='exp-token', note_type='inventory', title='Expired',
            expires_at=timezone.now() - timedelta(hours=1)
        )
        self.client.logout()
        resp = self.client.get('/api/privnote/exp-token/')
        self.assertEqual(resp.status_code, 410)
        self.assertEqual(resp.json()['reason'], 'expired')

    def test_view_password_gate(self):
        token = self._create_privnote('inventory', password='secret123')
        # GET without password
        resp = self.client.get(f'/api/privnote/{token}/')
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()['requires_password'])

    def test_view_password_correct(self):
        token = self._create_privnote('message', text='SecretMsg', password='pswd')
        # POST with correct password
        resp = self.client.post(
            f'/api/privnote/{token}/',
            json.dumps({'password': 'pswd'}),
            content_type='application/json'
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['data']['text'], 'SecretMsg')

    def test_view_password_wrong(self):
        token = self._create_privnote('message', text='SecretMsg', password='pswd')
        resp = self.client.post(
            f'/api/privnote/{token}/',
            json.dumps({'password': 'WRONG'}),
            content_type='application/json'
        )
        self.assertEqual(resp.status_code, 401)
        self.assertIn('密码错误', resp.json()['error'])

    def test_view_nonexistent_note(self):
        resp = self.client.get('/api/privnote/nonexist/')
        self.assertEqual(resp.status_code, 404)

    def test_view_payment_with_payment_methods(self):
        """收款 privnote 带预设收款方式"""
        pm = PaymentMethod.objects.create(
            method_type='bank_card', label='TestBank',
            bank_name='TestBank', card_number='11112222', card_holder='HOLDER'
        )
        token = self._create_privnote('payment', payment_method_id=str(pm.id))
        resp = self.client.get(f'/api/privnote/{token}/')
        self.assertEqual(resp.status_code, 200)
        methods = resp.json()['data']['payment_methods']
        self.assertEqual(len(methods), 1)
        self.assertEqual(methods[0]['bank_name'], 'TestBank')
        self.assertEqual(methods[0]['card_number'], '11112222')

    def test_view_payment_with_manual_payment(self):
        """收款 privnote 带手动收款方式"""
        token = self._create_privnote('payment', payment_manual=json.dumps({
            'bank_name': 'ManualBank', 'card_number': '9999', 'card_holder': 'Me'
        }))
        resp = self.client.get(f'/api/privnote/{token}/')
        self.assertEqual(resp.status_code, 200)
        methods = resp.json()['data']['payment_methods']
        self.assertGreaterEqual(len(methods), 1)
        manual = [m for m in methods if m['label'] == '手动填写']
        self.assertEqual(len(manual), 1)
        self.assertEqual(manual[0]['bank_name'], 'ManualBank')


# ═══════════════════════════════════════════════════
# 实时渲染 测试
# ═══════════════════════════════════════════════════

class RealTimeRenderingTestCase(TestCase):
    """收款 privnote 实时渲染：修改 SalesOrder 后客户看到最新数据"""

    def setUp(self):
        self.client = Client()
        self.staff, self.staff_pass = _create_staff_user()
        self.cigar = _create_cigar()
        _create_batch(self.cigar, remaining=50, unit_cost=300.0, loose=True)

        # 创建收款 privnote
        self.client.login(username=self.staff.username, password=self.staff_pass)
        resp = self.client.post('/privnote/create/', {
            'note_type': 'payment',
            'duration': 24,
            'items': json.dumps([
                {'cigar_id': self.cigar.id, 'quantity': 3, 'unit_price': 400}
            ]),
        })
        self.token = resp.json()['token']
        self.so_id = resp.json()['sales_order_id']
        self.client.logout()

    def test_initial_view(self):
        resp = self.client.get(f'/api/privnote/{self.token}/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['data']['total'], 1200)  # 3 * 400

    def test_real_time_reflects_price_change(self):
        """修改售价后，客户看到最新价格"""
        so = SalesOrder.objects.get(id=self.so_id)
        item = so.items.first()
        item.unit_price = 500
        item.revenue = item.quantity * Decimal('500.00')
        item.profit = item.revenue - item.cost
        item.save()
        so.total_revenue = item.revenue
        so.save(update_fields=['total_revenue'])

        resp = self.client.get(f'/api/privnote/{self.token}/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['data']['total'], 1500)

    def test_real_time_reflects_quantity_change(self):
        """修改数量后实时更新"""
        so = SalesOrder.objects.get(id=self.so_id)
        item = so.items.first()
        item.quantity = 10
        item.sale_unit = SalesOrderItem.SaleUnit.STICK
        item.sale_quantity = 10
        item.box_size = None
        item.revenue = 10 * item.unit_price
        item.profit = item.revenue - item.cost
        item.save()
        so.total_revenue = item.revenue
        so.save(update_fields=['total_revenue'])

        resp = self.client.get(f'/api/privnote/{self.token}/')
        self.assertEqual(resp.json()['data']['total'], 4000)
        self.assertEqual(resp.json()['data']['items'][0]['quantity'], 10)


# ═══════════════════════════════════════════════════
# QUOTE 自定义价格测试 — 修复 int("1:10") ValueError
# ═══════════════════════════════════════════════════

class QuoteCustomPricesTestCase(TestCase):
    """报价单自定义价格：cigar_id:box_size 作为 key"""

    def setUp(self):
        self.client = Client()
        self.staff, self.staff_pass = _create_staff_user()
        self.client.login(username=self.staff.username, password=self.staff_pass)

        # 创建一款雪茄，两个包装规格
        brand = Brand.objects.create(english_name='TestBrand', name='测试品牌')
        self.cigar = Cigar.objects.create(
            brand=brand.english_name, english_name='Test Cigar',
            name='测试雪茄', vitola='Robusto'
        )
        # 10支/盒 批发价 1000
        self.cp10 = CigarPrice.objects.create(
            cigar=self.cigar, box_size=10, wholesale_price=1000, is_active=True
        )
        # 25支/盒 批发价 2500
        self.cp25 = CigarPrice.objects.create(
            cigar=self.cigar, box_size=25, wholesale_price=2500, is_active=True
        )

    def test_create_quote_with_custom_prices_string_keys(self):
        """custom_prices key 为 'cigar_id:box_size' 字符串时不应 500"""
        custom_prices = {
            f"{self.cigar.id}:10": 1500,   # 10支装改 1500
            f"{self.cigar.id}:25": 3000,   # 25支装改 3000
        }
        resp = self.client.post('/privnote/create/', {
            'note_type': 'quote',
            'duration': 24,
            'quote_mode': 'custom',
            'selected_ids': json.dumps([self.cigar.id]),
            'custom_prices': json.dumps(custom_prices),
            'shipping_included': 'false',
        })
        self.assertEqual(resp.status_code, 200, f"Expected 200, got {resp.status_code}: {resp.content}")
        data = resp.json()
        self.assertIn('url', data)
        self.assertIn('token', data)

    def test_custom_price_per_box_size_independent(self):
        """同一款式不同包装，自定义价格互不影响"""
        custom_prices = {
            f"{self.cigar.id}:10": 1200,   # 只改 10支装
        }
        resp = self.client.post('/privnote/create/', {
            'note_type': 'quote',
            'duration': 24,
            'quote_mode': 'custom',
            'selected_ids': json.dumps([self.cigar.id]),
            'custom_prices': json.dumps(custom_prices),
            'shipping_included': 'false',
        })
        self.assertEqual(resp.status_code, 200)
        token = resp.json()['token']

        # 查看渲染结果
        view_resp = self.client.get(f'/api/privnote/{token}/')
        self.assertEqual(view_resp.status_code, 200)
        quote_data = view_resp.json()['data']

        items = []
        for g in quote_data['brand_groups']:
            items.extend(g['items'])

        # 找到两个包装
        item10 = next(i for i in items if i['box_size'] == 10)
        item25 = next(i for i in items if i['box_size'] == 25)

        self.assertEqual(item10['wholesale_price'], 1200, "10支装应被自定义为1200")
        self.assertEqual(item25['wholesale_price'], 2500, "25支装应保持原价2500")

    def test_custom_price_applies_correctly(self):
        """自定义价格正确覆盖并计算单价"""
        custom_prices = {
            f"{self.cigar.id}:10": 1500,   # 10支装改 1500 → 单价 150
        }
        resp = self.client.post('/privnote/create/', {
            'note_type': 'quote',
            'duration': 24,
            'quote_mode': 'custom',
            'selected_ids': json.dumps([self.cigar.id]),
            'custom_prices': json.dumps(custom_prices),
            'shipping_included': 'false',
        })
        self.assertEqual(resp.status_code, 200)
        token = resp.json()['token']

        view_resp = self.client.get(f'/api/privnote/{token}/')
        quote_data = view_resp.json()['data']

        items = []
        for g in quote_data['brand_groups']:
            items.extend(g['items'])

        item10 = next(i for i in items if i['box_size'] == 10)
        self.assertEqual(item10['wholesale_price'], 1500)
        self.assertEqual(item10['per_stick_price'], 150)  # 1500 / 10 = 150

    def test_custom_price_with_shipping_fee(self):
        """自定义价格 + 运费正确叠加"""
        custom_prices = {
            f"{self.cigar.id}:10": 1000,
        }
        resp = self.client.post('/privnote/create/', {
            'note_type': 'quote',
            'duration': 24,
            'quote_mode': 'custom',
            'selected_ids': json.dumps([self.cigar.id]),
            'custom_prices': json.dumps(custom_prices),
            'shipping_included': 'true',
        })
        self.assertEqual(resp.status_code, 200)
        token = resp.json()['token']

        view_resp = self.client.get(f'/api/privnote/{token}/')
        quote_data = view_resp.json()['data']

        items = []
        for g in quote_data['brand_groups']:
            items.extend(g['items'])

        item10 = next(i for i in items if i['box_size'] == 10)
        # 批发价 1000 + 运费 20*10 = 1200
        self.assertEqual(item10['wholesale_price'], 1200)
        # 单价 100 + 20 = 120
        self.assertEqual(item10['per_stick_price'], 120)


class PaymentSaleUnitRenderingTest(TestCase):
    def test_box_item_uses_persisted_revenue_and_sale_unit_snapshot(self):
        operator, _ = _create_staff_user()
        cigar = _create_cigar()
        order = SalesOrder.objects.create(operator=operator)
        SalesOrderItem.objects.create(
            sales_order=order, cigar=cigar, quantity=50,
            sale_unit=SalesOrderItem.SaleUnit.BOX, sale_quantity=2, box_size=25,
            unit_price=Decimal('100.01'), unit_cost=Decimal('0.00'),
            revenue=Decimal('200.02'), cost=Decimal('0.00'), profit=Decimal('200.02'),
        )

        data = build_payment_data(order)

        item = data['items'][0]
        self.assertEqual(item['unit_price'], 100.01)
        self.assertEqual(item['subtotal'], 200.02)
        self.assertEqual(item['sale_unit'], 'box')
        self.assertEqual(item['sale_quantity'], 2)
        self.assertEqual(item['box_size'], 25)
        self.assertEqual(data['total'], 200.02)
        self.assertEqual(data['grand_total'], 200.02)

    def test_stick_item_keeps_unit_price_and_persisted_revenue(self):
        operator, _ = _create_staff_user()
        cigar = _create_cigar()
        order = SalesOrder.objects.create(operator=operator)
        SalesOrderItem.objects.create(
            sales_order=order, cigar=cigar, quantity=3,
            sale_unit=SalesOrderItem.SaleUnit.STICK, sale_quantity=3, box_size=None,
            unit_price=Decimal('400.00'), unit_cost=Decimal('0.00'),
            revenue=Decimal('1200.00'), cost=Decimal('0.00'), profit=Decimal('1200.00'),
        )

        item = build_payment_data(order)['items'][0]

        self.assertEqual(item['unit_price'], 400)
        self.assertEqual(item['subtotal'], 1200)
        self.assertEqual(item['sale_unit'], 'stick')
        self.assertEqual(item['sale_quantity'], 3)
        self.assertIsNone(item['box_size'])
