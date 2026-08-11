from datetime import date
from decimal import Decimal

from django.test import TestCase

from accounting.models import FundAccount, LedgerPosting, LedgerSequence, LedgerTransaction
from accounting.services import LedgerError, PostingInput, exchange_to_rub, post_transaction, record_opening_balance, transfer_same_currency
from cigars.models import User


class ExternalInputHardeningTest(TestCase):
    business_date = date(2026, 8, 10)

    def setUp(self):
        self.operator = User.objects.create_user('external-input-operator', password='pass', is_staff=True)
        self.cny = FundAccount.objects.create(name='external CNY', currency='CNY', creation_idempotency_key='external-cny')
        self.rub = FundAccount.objects.create(name='external RUB', currency='RUB', creation_idempotency_key='external-rub')
        self.usdt = FundAccount.objects.create(name='external USDT', currency='USDT', creation_idempotency_key='external-usdt')

    def assert_no_ledger_residue(self):
        self.assertEqual(LedgerTransaction.objects.count(), 0)
        self.assertEqual(LedgerPosting.objects.count(), 0)
        self.assertFalse(LedgerSequence.objects.exists())

    def test_external_amounts_reject_excess_precision_without_ledger_residue(self):
        cny_target = FundAccount.objects.create(name='precision CNY target', currency='CNY', creation_idempotency_key='precision-cny-target')
        usdt_target = FundAccount.objects.create(name='precision USDT target', currency='USDT', creation_idempotency_key='precision-usdt-target')
        cases = (
            lambda: record_opening_balance(self.cny, '1.001', '1.00', LedgerPosting.Category.OPENING_CAPITAL, self.business_date, self.operator, 'precision-opening-cny'),
            lambda: record_opening_balance(self.rub, '1.001', '0.00', LedgerPosting.Category.OPENING_CAPITAL, self.business_date, self.operator, 'precision-opening-rub'),
            lambda: record_opening_balance(self.usdt, '1.000000001', '0.00', LedgerPosting.Category.OPENING_CAPITAL, self.business_date, self.operator, 'precision-opening-usdt'),
            lambda: exchange_to_rub(self.cny, self.rub, '1.001', '1.00', self.business_date, self.operator, 'precision-exchange-cny'),
            lambda: record_opening_balance(self.rub, '1.00', '0.001', LedgerPosting.Category.OPENING_CAPITAL, self.business_date, self.operator, 'precision-opening-cost'),
            lambda: exchange_to_rub(self.usdt, self.rub, '1.000000001', '1.00', self.business_date, self.operator, 'precision-exchange-usdt'),
            lambda: exchange_to_rub(self.cny, self.rub, '1.00', '1.001', self.business_date, self.operator, 'precision-exchange-rub'),
            lambda: transfer_same_currency(self.cny, cny_target, '1.001', self.business_date, self.operator, 'precision-transfer-cny'),
            lambda: transfer_same_currency(self.usdt, usdt_target, '1.000000001', self.business_date, self.operator, 'precision-transfer-usdt'),
        )

        for operation in cases:
            with self.subTest(operation=operation), self.assertRaises(LedgerError):
                operation()
            self.assert_no_ledger_residue()

    def test_external_amounts_accept_trailing_zero_precision(self):
        cny = record_opening_balance(self.cny, '1.000', '1.000', LedgerPosting.Category.OPENING_CAPITAL, self.business_date, self.operator, 'trailing-zero-cny')
        rub = record_opening_balance(self.rub, '1.000', '0.000', LedgerPosting.Category.OPENING_CAPITAL, self.business_date, self.operator, 'trailing-zero-rub')
        usdt = record_opening_balance(self.usdt, '1.000000000', '0.000', LedgerPosting.Category.OPENING_CAPITAL, self.business_date, self.operator, 'trailing-zero-usdt')

        self.assertEqual(cny.postings.get(account=self.cny).amount, Decimal('1.00000000'))
        self.assertEqual(rub.postings.get(account=self.rub).amount, Decimal('1.00000000'))
        self.assertEqual(usdt.postings.get(account=self.usdt).amount, Decimal('1.00000000'))

    def test_inactive_accounts_are_rejected_by_new_operations_without_residue(self):
        inactive_cny = FundAccount.objects.create(
            name='inactive CNY', currency='CNY', is_active=False,
            creation_idempotency_key='inactive-cny',
        )
        inactive_rub = FundAccount.objects.create(
            name='inactive RUB', currency='RUB', is_active=False,
            creation_idempotency_key='inactive-rub',
        )
        active_cny = FundAccount.objects.create(
            name='active CNY target', currency='CNY', creation_idempotency_key='active-cny-target',
        )
        cases = (
            lambda: record_opening_balance(
                inactive_cny, '1.00', '1.00', LedgerPosting.Category.OPENING_CAPITAL,
                self.business_date, self.operator, 'inactive-opening',
            ),
            lambda: exchange_to_rub(
                inactive_cny, self.rub, '1.00', '1.00', self.business_date, self.operator,
                'inactive-exchange',
            ),
            lambda: transfer_same_currency(
                inactive_cny, active_cny, '1.00', self.business_date, self.operator,
                'inactive-transfer',
            ),
            lambda: post_transaction(
                transaction_type=LedgerTransaction.TransactionType.TRANSFER,
                business_date=self.business_date,
                operator=self.operator,
                idempotency_key='inactive-generic-post',
                postings=[
                    PostingInput(account=inactive_rub, currency='RUB', amount=Decimal('1.00'), cny_amount=Decimal('1.00')),
                    PostingInput(category=LedgerPosting.Category.OPENING_CAPITAL, currency='CNY', amount=Decimal('-1.00'), cny_amount=Decimal('-1.00')),
                ],
            ),
        )

        for operation in cases:
            with self.subTest(operation=operation), self.assertRaises(LedgerError):
                operation()
            self.assert_no_ledger_residue()

    def test_identical_old_key_replays_after_account_is_deactivated(self):
        first = record_opening_balance(
            self.cny, '10.00', '10.00', LedgerPosting.Category.OPENING_CAPITAL,
            self.business_date, self.operator, 'deactivated-replay',
        )
        self.cny.is_active = False
        self.cny.save()
