from datetime import date
from decimal import Decimal

from django.test import TestCase

from accounting.models import FundAccount, LedgerPosting, LedgerTransaction
from accounting.selectors import account_snapshot
from accounting.services import (
    LedgerError,
    PostingInput,
    exchange_to_rub,
    post_transaction,
    record_opening_balance,
    transfer_same_currency,
)
from cigars.models import User


class AccountingOperationTest(TestCase):
    business_date = date(2026, 8, 10)

    def setUp(self):
        self.operator = User.objects.create_user('operations-operator', password='pass', is_staff=True)
        self.cny = self.account('CNY cash', 'CNY', 'operations-cny')
        self.rub = self.account('RUB cash', 'RUB', 'operations-rub')
        self.usdt = self.account('USDT cash', 'USDT', 'operations-usdt')

    def account(self, name, currency, key):
        return FundAccount.objects.create(name=name, currency=currency, creation_idempotency_key=key)

    def opening(self, account, original, cost, key, category=LedgerPosting.Category.OPENING_CAPITAL):
        return record_opening_balance(
            account, original, cost, category, self.business_date, self.operator, key,
        )

    def snapshot(self, account):
        return account_snapshot(account)

    def assert_no_ledger_residue(self):
        self.assertEqual(LedgerTransaction.objects.count(), 0)
        self.assertEqual(LedgerPosting.objects.count(), 0)

    def test_cny_opening_is_cutover_only_and_balanced_by_opening_equity(self):
        transaction = self.opening(self.cny, '1000', '1000', 'cny-opening')

        posting = transaction.postings.get(account=self.cny)
        category = transaction.postings.get(account__isnull=True)
        self.assertEqual(transaction.transaction_type, LedgerTransaction.TransactionType.OPENING_BALANCE)
        self.assertEqual((posting.amount, posting.cny_amount), (Decimal('1000.00000000'), Decimal('1000.00')))
        self.assertEqual((category.category, category.amount), (LedgerPosting.Category.OPENING_CAPITAL, Decimal('-1000.00000000')))

        for original, cost, category, business_date in (
            ('0', '0', LedgerPosting.Category.OPENING_CAPITAL, self.business_date),
            ('100', '-1', LedgerPosting.Category.OPENING_CAPITAL, self.business_date),
            ('100', '99', LedgerPosting.Category.OPENING_CAPITAL, self.business_date),
            ('100', '100', 'invalid', self.business_date),
            ('100', '100', LedgerPosting.Category.OPENING_CAPITAL, date(2026, 8, 11)),
        ):
            account = self.account(f'CNY invalid {original}-{cost}-{category}-{business_date}', 'CNY', f'cny-invalid-{original}-{cost}-{category}-{business_date}')
            with self.subTest(original=original, cost=cost, category=category, date=business_date), self.assertRaises(LedgerError):
                record_opening_balance(account, original, cost, category, business_date, self.operator, f'cny-invalid-{account.pk}')

    def test_opening_idempotency_cannot_bypass_cutover_date_validation(self):
        first = self.opening(self.cny, '100', '100', 'opening-repeat')

        with self.assertRaises(LedgerError):
            record_opening_balance(
                self.cny, '0', '0', LedgerPosting.Category.OPENING_CAPITAL,
                date(2026, 8, 11), self.operator, 'opening-repeat',
            )
        self.assertEqual(LedgerTransaction.objects.get(pk=first.pk).postings.count(), 2)

    def test_foreign_opening_requires_positive_amount_nonnegative_cost_and_unused_account(self):
        transaction = self.opening(self.rub, '12000', '0', 'rub-opening', LedgerPosting.Category.OPENING_RETAINED_EARNINGS)
        self.assertEqual(transaction.postings.get(account=self.rub).cny_amount, Decimal('0.00'))

        for original, cost in (('0', '0'), ('-1', '0'), ('1', '-0.01')):
            account = self.account(f'foreign invalid {original}-{cost}', 'USDT', f'foreign-invalid-{original}-{cost}')
            with self.subTest(original=original, cost=cost), self.assertRaises(LedgerError):
                self.opening(account, original, cost, f'foreign-invalid-{account.pk}')

        with self.assertRaises(LedgerError):
            self.opening(self.rub, '1', '0', 'rub-second')

        used = self.account('used account', 'RUB', 'used-account')
        post_transaction(
            transaction_type=LedgerTransaction.TransactionType.OPENING_BALANCE,
            business_date=self.business_date,
            operator=self.operator,
            idempotency_key='used-posting',
            postings=[
                PostingInput(account=used, currency='RUB', amount=Decimal('1'), cny_amount=Decimal('1')),
                PostingInput(category=LedgerPosting.Category.OPENING_CAPITAL, currency='CNY', amount=Decimal('-1'), cny_amount=Decimal('-1')),
            ],
        )
        with self.assertRaises(LedgerError):
            self.opening(used, '1', '0', 'used-opening')

    def test_exchange_cny_to_rub_moves_cost_without_profit_or_category(self):
        self.opening(self.cny, '1000', '1000', 'cny-for-rub')
        transaction = exchange_to_rub(
            self.cny, self.rub, '1000', '12000', self.business_date, self.operator, 'exchange-cny-rub', '换汇',
        )

        self.assertEqual(transaction.transaction_type, LedgerTransaction.TransactionType.EXCHANGE)
        self.assertEqual(transaction.postings.filter(category__gt='').count(), 0)
        self.assertEqual(
            list(transaction.postings.order_by('account_id').values_list('account__currency', 'amount', 'cny_amount')),
            [('CNY', Decimal('-1000.00000000'), Decimal('-1000.00')), ('RUB', Decimal('12000.00000000'), Decimal('1000.00'))],
        )
        self.assertEqual(self.snapshot(self.cny).cny_book_cost, Decimal('0.00'))
        self.assertEqual(self.snapshot(self.rub).cny_book_cost, Decimal('1000.00'))

    def test_foreign_partial_and_final_outflow_use_moving_average_then_exact_remainder(self):
        self.opening(self.usdt, '3', '10', 'usdt-opening')
        target = self.account('USDT target', 'USDT', 'operations-usdt-target')

        self.assertEqual(
            transfer_same_currency(self.usdt, target, '1', self.business_date, self.operator, 'usdt-partial').postings.get(account=target).cny_amount,
            Decimal('3.33'),
        )
        transfer_same_currency(self.usdt, target, '2', self.business_date, self.operator, 'usdt-final')

        self.assertEqual((self.snapshot(self.usdt).original_balance, self.snapshot(self.usdt).cny_book_cost), (Decimal('0.00000000'), Decimal('0.00')))
        self.assertEqual((self.snapshot(target).original_balance, self.snapshot(target).cny_book_cost), (Decimal('3.00000000'), Decimal('10.00')))

    def test_rub_account_accumulates_cost_from_cny_and_usdt_exchanges(self):
        self.opening(self.cny, '1000', '1000', 'cny-opening-for-rub')
        self.opening(self.usdt, '2', '300', 'usdt-opening-for-rub')
        exchange_to_rub(self.cny, self.rub, '1000', '12000', self.business_date, self.operator, 'cny-rub')
        exchange_to_rub(self.usdt, self.rub, '2', '3600', self.business_date, self.operator, 'usdt-rub')

        snapshot = self.snapshot(self.rub)
        self.assertEqual((snapshot.original_balance, snapshot.cny_book_cost), (Decimal('15600.00000000'), Decimal('1300.00')))
        self.assertEqual(snapshot.moving_average_cny, Decimal('1300') / Decimal('15600'))

    def test_same_currency_transfer_moves_cny_one_to_one_and_rejects_invalid_pairs(self):
        cny_target = self.account('CNY target', 'CNY', 'operations-cny-target')
        self.opening(self.cny, '100', '100', 'cny-transfer-opening')
        transfer_same_currency(self.cny, cny_target, '100', self.business_date, self.operator, 'cny-transfer')
        self.assertEqual((self.snapshot(cny_target).original_balance, self.snapshot(cny_target).cny_book_cost), (Decimal('100.00000000'), Decimal('100.00')))

        for source, target, amount, key in (
            (self.cny, self.rub, '1', 'different-currency'),
            (self.cny, self.cny, '1', 'same-account'),
            (cny_target, self.cny, '0', 'zero'),
            (cny_target, self.cny, '-1', 'negative'),
            (cny_target, self.cny, '101', 'insufficient'),
        ):
            with self.subTest(key=key), self.assertRaises(LedgerError):
                transfer_same_currency(source, target, amount, self.business_date, self.operator, key)

    def test_exchange_rejects_invalid_accounts_amounts_and_leaves_no_residue(self):
        bad_rub_source = self.account('RUB source', 'RUB', 'operations-rub-source')
        non_rub_target = self.account('USDT target invalid', 'USDT', 'operations-usdt-invalid-target')
        unsaved = FundAccount(name='unsaved', currency='CNY', creation_idempotency_key='unsaved-operation')
        cases = (
            (bad_rub_source, self.rub, '1', '1', 'rub-source'),
            (self.cny, non_rub_target, '1', '1', 'non-rub-target'),
            (self.cny, self.cny, '1', '1', 'same-account'),
            (self.cny, self.rub, '0', '1', 'zero-source'),
            (self.cny, self.rub, '1', '0', 'zero-rub'),
            (self.cny, self.rub, '-1', '1', 'negative'),
            (self.cny, self.rub, '1', '1', 'insufficient'),
            (unsaved, self.rub, '1', '1', 'unsaved'),
        )
        for source, target, source_amount, rub_amount, key in cases:
            with self.subTest(key=key), self.assertRaises(LedgerError):
                exchange_to_rub(source, target, source_amount, rub_amount, self.business_date, self.operator, key)
        self.assert_no_ledger_residue()

    def test_idempotency_returns_existing_without_recomputing_cost_but_validates_metadata_and_operator(self):
        self.opening(self.cny, '100', '100', 'idempotency-opening')
        first = exchange_to_rub(self.cny, self.rub, '100', '1200', self.business_date, self.operator, 'repeat-exchange')
        duplicate = exchange_to_rub(self.cny, self.rub, '100', '1200', self.business_date, self.operator, 'repeat-exchange')
        self.assertEqual(first.pk, duplicate.pk)
        self.assertEqual(LedgerTransaction.objects.filter(transaction_type='exchange').count(), 1)

        with self.assertRaises(LedgerError):
            exchange_to_rub(self.cny, self.rub, '1', '1', '2026-08-10', self.operator, 'repeat-exchange')
        with self.assertRaises(LedgerError):
            exchange_to_rub(self.cny, self.rub, '1', '1', self.business_date, User(username='unsaved', is_staff=True), 'repeat-exchange')
        with self.assertRaises(LedgerError):
            transfer_same_currency(self.rub, self.rub, '1', self.business_date, self.operator, 'repeat-exchange')
