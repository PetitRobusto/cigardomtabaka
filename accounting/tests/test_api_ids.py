from django.test import TestCase

from cigars.models import User


class AccountingApiIdHardeningTest(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user('api-id-hardening', password='pass', is_staff=True)
        self.client.force_login(self.staff)

    def test_id_consumers_reject_nonpositive_and_unsigned_bigint_overflow(self):
        for value in (0, -1, 9223372036854775808, '9' * 100):
            with self.subTest(consumer='custodian', value=value):
                response = self.client.post('/api/accounting/accounts/', {
                    'name': f'bad custodian {value}', 'currency': 'CNY', 'custodian_id': value,
                }, content_type='application/json', HTTP_IDEMPOTENCY_KEY=f'custodian-{value}')
                self.assertEqual(response.status_code, 400)
            with self.subTest(consumer='account', value=value):
                response = self.client.post('/api/accounting/opening-balances/', {
                    'account_id': value, 'original_amount': '1', 'cny_book_cost': '1',
                    'equity_category': 'opening_capital', 'business_date': '2026-08-10',
                }, content_type='application/json', HTTP_IDEMPOTENCY_KEY=f'account-{value}')
                self.assertEqual(response.status_code, 400)
            with self.subTest(consumer='transactions', value=value):
                response = self.client.get('/api/accounting/transactions/', {'account_id': value})
                self.assertEqual(response.status_code, 400)
