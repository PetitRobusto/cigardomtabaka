from django.test import TestCase

from accounting.models import FundAccount, LedgerPosting, LedgerSequence, LedgerTransaction
from cigars.models import User


class ExternalInputApiTest(TestCase):
    def setUp(self):
        staff = User.objects.create_user('external-api-staff', password='pass', is_staff=True)
        self.client.force_login(staff)
        self.cny = FundAccount.objects.create(name='API precision CNY', currency='CNY', creation_idempotency_key='api-precision-cny')
        self.rub = FundAccount.objects.create(name='API precision RUB', currency='RUB', creation_idempotency_key='api-precision-rub')
        self.usdt = FundAccount.objects.create(name='API precision USDT', currency='USDT', creation_idempotency_key='api-precision-usdt')
        self.cny_target = FundAccount.objects.create(name='API precision CNY target', currency='CNY', creation_idempotency_key='api-precision-cny-target')

    def assert_no_ledger_residue(self):
        self.assertEqual(LedgerTransaction.objects.count(), 0)
        self.assertEqual(LedgerPosting.objects.count(), 0)
        self.assertFalse(LedgerSequence.objects.exists())

    def test_amounts_with_excess_precision_return_400_without_ledger_residue(self):
        requests = (
            ('/api/accounting/opening-balances/', {
                'account_id': self.cny.pk, 'original_amount': '1.001', 'cny_book_cost': '1.00',
                'equity_category': 'opening_capital', 'business_date': '2026-08-10',
            }, 'api-precision-opening-cny'),
            ('/api/accounting/opening-balances/', {
                'account_id': self.cny.pk, 'original_amount': '1.00', 'cny_book_cost': '1.001',
                'equity_category': 'opening_capital', 'business_date': '2026-08-10',
            }, 'api-precision-opening-cost'),
            ('/api/accounting/opening-balances/', {
                'account_id': self.usdt.pk, 'original_amount': '1.000000001', 'cny_book_cost': '0.00',
                'equity_category': 'opening_capital', 'business_date': '2026-08-10',
            }, 'api-precision-opening-usdt'),
            ('/api/accounting/exchanges/', {
                'source_account_id': self.cny.pk, 'rub_account_id': self.rub.pk,
                'source_amount': '1.001', 'rub_amount': '1.00', 'business_date': '2026-08-10',
            }, 'api-precision-exchange'),
            ('/api/accounting/transfers/', {
                'source_account_id': self.cny.pk, 'target_account_id': self.cny_target.pk,
                'amount': '1.001', 'business_date': '2026-08-10',
            }, 'api-precision-transfer'),
        )

        for path, payload, key in requests:
            with self.subTest(path=path, key=key):
                response = self.client.post(path, data=payload, content_type='application/json', HTTP_IDEMPOTENCY_KEY=key)
                self.assertEqual(response.status_code, 400)
