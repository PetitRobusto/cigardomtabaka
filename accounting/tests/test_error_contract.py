import json

from django.test import Client, TestCase

from cigars.models import User


class AccountingErrorContractTest(TestCase):
    """内部账 API 的所有失败都使用同一 JSON 外壳。"""

    def setUp(self):
        self.client = Client()
        self.operator = User.objects.create_user(
            'accounting-error-contract', password='pass', is_staff=True,
        )

    def assert_error_contract(self, response, status):
        self.assertEqual(response.status_code, status)
        payload = response.json()
        self.assertIn('error', payload)
        self.assertIsInstance(payload.get('code'), str)
        self.assertIsInstance(payload.get('details'), dict)

    def test_staff_decorator_uses_error_contract(self):
        response = self.client.get('/api/accounting/actions/')
        self.assert_error_contract(response, 403)

    def test_method_and_validation_failures_use_error_contract(self):
        self.client.force_login(self.operator)
        cases = (
            ('post', '/api/accounting/day1/', 405),
            ('get', '/api/accounting/transfers/', 405),
            ('post', '/api/accounting/overview/', 405),
            ('post', '/api/accounting/reports/summary/', 405),
            ('get', '/api/accounting/reconciliations/1/confirm/', 405),
        )
        for method, path, status in cases:
            with self.subTest(path=path):
                response = self.client.generic(
                    method.upper(), path, data=b'{}', content_type='application/json',
                )
                self.assert_error_contract(response, status)

        invalid_transfer = self.client.post(
            '/api/accounting/transfers/',
            data=json.dumps({
                'source_account_id': 999991,
                'target_account_id': 999992,
                'amount': '1.00',
                'business_date': '2026-08-14',
            }),
            content_type='application/json',
            HTTP_IDEMPOTENCY_KEY='error-contract-transfer',
        )
        self.assert_error_contract(invalid_transfer, 404)

        invalid_reconciliation = self.client.post(
            '/api/accounting/reconciliations/',
            data=json.dumps({
                'account_id': 999993,
                'business_date': '2026-08-14',
                'actual_amount': '1.00',
            }),
            content_type='application/json',
            HTTP_IDEMPOTENCY_KEY='error-contract-reconciliation',
        )
        self.assert_error_contract(invalid_reconciliation, 404)
