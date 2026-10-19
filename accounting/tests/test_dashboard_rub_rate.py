from datetime import date
from decimal import Decimal

from django.test import TestCase

from accounting.expense_actions import record_expense
from accounting.models import Day1Initialization, FundAccount, LedgerPosting
from accounting.selectors import accounting_dashboard
from accounting.services import exchange_to_rub, record_opening_balance
from cigars.models import User


class DashboardRubRateTests(TestCase):
    day = date(2026, 9, 30)

    def setUp(self):
        self.operator = User.objects.create_user(username='rate-check', is_staff=True)
        Day1Initialization.objects.create(
            singleton_key='company', status='completed',
            business_date=date(2026, 8, 10), completed_by=self.operator,
        )

    def account(self, name, currency, amount, cost):
        account = FundAccount.objects.create(
            name=name, currency=currency, creation_idempotency_key=f'account-{name}',
        )
        record_opening_balance(
            account, Decimal(amount), Decimal(cost), LedgerPosting.Category.OPENING_CAPITAL,
            date(2026, 8, 10), self.operator, f'opening-{name}',
        )
        return account

    def rate(self):
        return accounting_dashboard(as_of=self.day)['stats']['rub_exchange_rate']

    def test_rate_uses_total_cost_including_inactive_holdings(self):
        self.account('rub-a', 'RUB', '1200', '100')
        other = self.account('rub-b', 'RUB', '2800', '200')
        self.account('cny', 'CNY', '800', '800')
        self.account('usdt', 'USDT', '100', '700')
        self.assertEqual(self.rate(), Decimal('13.3333'))
        other.is_active = False
        other.save(update_fields=['is_active'])
        self.assertEqual(self.rate(), Decimal('13.3333'))

    def test_no_rub_or_no_cost_has_no_rate(self):
        self.assertIsNone(self.rate())
        self.account('rub-free', 'RUB', '100', '0')
        self.assertIsNone(self.rate())

    def test_current_holdings_change_rate_and_empty_holdings_have_no_rate(self):
        first = self.account('rub-a', 'RUB', '1200', '100')
        second = self.account('rub-b', 'RUB', '2800', '200')
        for account, amount, key in [(first, '1200', 'spend-first'), (second, '2800', 'spend-second')]:
            record_expense(category='other', amount=amount, fund_account_id=account.pk,
                           business_date=self.day, operator=self.operator, idempotency_key=key)
            if key == 'spend-first':
                self.assertEqual(self.rate(), Decimal('14.0000'))
        self.assertIsNone(self.rate())

    def test_future_exchange_does_not_change_current_rate(self):
        rub = self.account('rub', 'RUB', '1300', '100')
        cny = self.account('cny', 'CNY', '100', '100')
        exchange_to_rub(cny, rub, '100', '2600', date(2026, 10, 1), self.operator, 'future-exchange')
        self.assertEqual(self.rate(), Decimal('13.0000'))
