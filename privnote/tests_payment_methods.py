import base64

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.core.exceptions import ValidationError

from accounting.models import FundAccount
from cigars.models import User
from privnote.models import PaymentMethod, PaymentMethodAudit


PNG = base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII='
)


class PaymentMethodManagementAPITest(TestCase):
    def setUp(self):
        self.client = Client()
        self.staff = User.objects.create_user('pm_staff', password='pass', is_staff=True)
        self.client.login(username='pm_staff', password='pass')
        self.account = FundAccount.objects.create(
            name='PM CNY', currency='CNY', creation_idempotency_key='pm-management-cny',
        )

    def _file(self, name='qr.png'):
        return SimpleUploadedFile(name, PNG, content_type='image/png')

    def _create_payload(self, **overrides):
        payload = {
            'method_type': 'bank_card', 'label': '主银行卡', 'bank_name': '测试银行',
            'card_number': '123456', 'card_holder': '测试人', 'account': '',
            'remark': '备注订单号', 'sort_order': '1', 'fund_account_id': str(self.account.id),
        }
        payload.update(overrides)
        return payload

    def test_create_is_idempotent_and_audited(self):
        payload = self._create_payload()
        headers = {'HTTP_IDEMPOTENCY_KEY': 'pm-create-1'}
        first = self.client.post('/privnote/api/payment-methods/', payload, **headers)
        self.assertEqual(first.status_code, 201)
        second = self.client.post('/privnote/api/payment-methods/', payload, **headers)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(first.json(), second.json())
        self.assertEqual(PaymentMethod.objects.count(), 1)
        self.assertEqual(PaymentMethodAudit.objects.count(), 1)
        conflict = self.client.post('/privnote/api/payment-methods/', self._create_payload(label='另一个标签'), **headers)
        self.assertEqual(conflict.status_code, 409)

    def test_wechat_accepts_account_without_qr_and_requires_one_payment_detail(self):
        response = self.client.post(
            '/privnote/api/payment-methods/',
            self._create_payload(method_type='wechat', bank_name='', card_number='', card_holder='', account='wx-id'),
            HTTP_IDEMPOTENCY_KEY='pm-wechat-1',
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['payment_method']['account'], 'wx-id')
        invalid = self.client.post(
            '/privnote/api/payment-methods/',
            self._create_payload(method_type='alipay', bank_name='', card_number='', card_holder='', account=''),
            HTTP_IDEMPOTENCY_KEY='pm-alipay-invalid',
        )
        self.assertEqual(invalid.status_code, 400)

    def test_management_list_includes_inactive_but_default_list_does_not(self):
        method = PaymentMethod.objects.create(method_type='bank_card', label='旧卡', bank_name='银行', card_number='1', card_holder='人', fund_account=self.account)
        self.client.post(f'/privnote/api/payment-methods/{method.id}/deactivate/', HTTP_IDEMPOTENCY_KEY='pm-deactivate-1')
        self.assertEqual(self.client.get('/privnote/api/payment-methods/').json()['methods'], [])
        data = self.client.get('/privnote/api/payment-methods/?include_inactive=1').json()['methods']
        self.assertEqual(len(data), 1)
        self.assertFalse(data[0]['is_active'])

    def test_activate_is_idempotent_and_method_cannot_be_edited_or_deleted(self):
        method = PaymentMethod.objects.create(method_type='bank_card', label='旧卡', bank_name='银行', card_number='1', card_holder='人', fund_account=self.account)
        method.is_active = False
        method.save(update_fields=['is_active'])
        first = self.client.post(f'/privnote/api/payment-methods/{method.id}/activate/', HTTP_IDEMPOTENCY_KEY='pm-activate-1')
        second = self.client.post(f'/privnote/api/payment-methods/{method.id}/activate/', HTTP_IDEMPOTENCY_KEY='pm-activate-1')
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json(), second.json())
        method.refresh_from_db()
        method.label = '不能编辑'
        with self.assertRaises(ValidationError):
            method.save()
        with self.assertRaises(ValidationError):
            method.delete()

    def test_invalid_sort_order_returns_validation_error(self):
        response = self.client.post(
            '/privnote/api/payment-methods/',
            self._create_payload(sort_order='not-a-number'),
            HTTP_IDEMPOTENCY_KEY='pm-sort-invalid',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('排序必须是整数', response.json()['error'])

    def test_qr_upload_is_stored_and_returned(self):
        response = self.client.post(
            '/privnote/api/payment-methods/',
            {**self._create_payload(method_type='wechat', bank_name='', card_number='', card_holder=''), 'qr_image': self._file()},
            HTTP_IDEMPOTENCY_KEY='pm-qr-1',
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.json()['payment_method']['qr_url'])
