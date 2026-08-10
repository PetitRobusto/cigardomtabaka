from datetime import date, datetime
from decimal import Decimal
import threading

from django.db import close_old_connections
from django.test import TestCase, TransactionTestCase

from accounting.models import FundAccount, LedgerPosting, LedgerSequence, LedgerTransaction
from accounting.selectors import account_snapshot
from accounting.services import LedgerError, PostingInput, post_transaction
from cigars.models import User


class LedgerServiceTest(TestCase):
    def setUp(self):
        self.operator = User.objects.create_user('ledger-operator', password='pass', is_staff=True)
        self.other_operator = User.objects.create_user('ledger-operator-b', password='pass', is_staff=True)
        self.cny_account = self.make_account('现金 CNY', 'CNY', 'cash-cny')
        self.rub_account = self.make_account('现金 RUB', 'RUB', 'cash-rub')

    def make_account(self, name, currency, key):
        return FundAccount.objects.create(
            name=name,
            currency=currency,
            creation_idempotency_key=key,
        )

    def input(self, account, amount, cny_amount, category=''):
        return PostingInput(
            account=account,
            category=category,
            currency=account.currency if account else 'CNY',
            amount=Decimal(amount),
            cny_amount=Decimal(cny_amount),
        )

    def category(self, amount):
        return PostingInput(
            category=LedgerPosting.Category.OPENING_CAPITAL,
            currency='CNY',
            amount=Decimal(amount),
            cny_amount=Decimal(amount),
        )

    def post(self, *, business_date=date(2026, 8, 10), postings=None,
             key='key-1', transaction_type=LedgerTransaction.TransactionType.OPENING_BALANCE,
             operator=None):
        return post_transaction(
            transaction_type=transaction_type,
            business_date=business_date,
            postings=postings or [self.input(self.cny_account, '100', '100'), self.category('-100')],
            operator=operator or self.operator,
            idempotency_key=key,
            description='test',
            source_type='test',
            source_id='source-1',
        )

    def test_balanced_posting_assigns_global_sequence_and_snapshot(self):
        first = self.post()
        second = self.post(
            key='key-2',
            postings=[self.input(self.rub_account, '100.00', '100.00'), self.category('-100')],
        )

        snapshot = account_snapshot(self.cny_account)
        self.assertEqual(first.effective_sequence, 1)
        self.assertEqual(second.effective_sequence, 2)
        self.assertEqual(snapshot.original_balance, Decimal('100.00000000'))
        self.assertEqual(snapshot.cny_book_cost, Decimal('100.00'))
        self.assertEqual(snapshot.moving_average_cny, Decimal('1'))

    def test_rejects_cny_posting_with_different_book_amount_without_residue(self):
        with self.assertRaises(LedgerError):
            self.post(postings=[self.input(self.cny_account, '100', '99'), self.category('-99')])

        self.assertEqual(LedgerTransaction.objects.count(), 0)
        self.assertEqual(LedgerPosting.objects.count(), 0)
        self.assertEqual(LedgerSequence.objects.count(), 0)

    def test_rejects_invalid_category_target_currency_or_amount(self):
        invalid = [
            PostingInput(category='unknown', currency='CNY', amount=Decimal('-100'), cny_amount=Decimal('-100')),
            PostingInput(category=LedgerPosting.Category.OPENING_CAPITAL, currency='RUB', amount=Decimal('-100'), cny_amount=Decimal('-100')),
            PostingInput(category=LedgerPosting.Category.OPENING_CAPITAL, currency='CNY', amount=Decimal('-99'), cny_amount=Decimal('-100')),
            PostingInput(account=self.cny_account, category=LedgerPosting.Category.OPENING_CAPITAL, currency='CNY', amount=Decimal('100'), cny_amount=Decimal('100')),
        ]
        for posting in invalid:
            with self.subTest(posting=posting), self.assertRaises(LedgerError):
                self.post(postings=[self.input(self.cny_account, '100', '100'), posting])

        self.assertEqual(LedgerTransaction.objects.count(), 0)

    def test_rejects_unbalanced_or_single_posting_without_residue(self):
        with self.assertRaises(LedgerError):
            self.post(postings=[self.input(self.cny_account, '100', '100'), self.category('-99')])
        with self.assertRaises(LedgerError):
            self.post(postings=[self.input(self.cny_account, '100', '100')], key='single')

        self.assertEqual(LedgerTransaction.objects.count(), 0)
        self.assertEqual(LedgerPosting.objects.count(), 0)

    def test_rejects_account_currency_mismatch(self):
        wrong_currency = PostingInput(
            account=self.cny_account, currency='RUB', amount=Decimal('100'), cny_amount=Decimal('100'),
        )
        with self.assertRaises(LedgerError):
            self.post(postings=[wrong_currency, self.category('-100')])

    def test_replay_rejects_early_negative_even_when_later_deposit_covers_it(self):
        self.post(
            business_date=date(2026, 8, 12), key='later-deposit',
            postings=[self.input(self.cny_account, '100', '100'), self.category('-100')],
        )
        with self.assertRaises(LedgerError):
            self.post(
                business_date=date(2026, 8, 11), key='backdated-withdrawal',
                postings=[self.input(self.cny_account, '-100', '-100'), self.category('100')],
            )

        self.assertEqual(LedgerTransaction.objects.count(), 1)

    def test_replay_same_day_uses_effective_sequence(self):
        LedgerTransaction.objects.create(
            transaction_type=LedgerTransaction.TransactionType.OPENING_BALANCE,
            status=LedgerTransaction.Status.POSTED,
            business_date=date(2026, 8, 10),
            effective_sequence=2,
            operator=self.operator,
        )
        tx = LedgerTransaction.objects.get(effective_sequence=2)
        LedgerPosting.objects.create(
            transaction=tx, account=self.cny_account, currency='CNY',
            amount=Decimal('100'), cny_amount=Decimal('100'),
        )
        with self.assertRaises(LedgerError):
            self.post(postings=[self.input(self.cny_account, '-100', '-100'), self.category('100')])

        self.assertEqual(LedgerTransaction.objects.count(), 1)

    def test_same_idempotency_key_returns_original_and_rejects_other_type(self):
        first = self.post(key='repeat')
        duplicate = self.post(key='repeat')
        with self.assertRaises(LedgerError):
            self.post(key='repeat', transaction_type=LedgerTransaction.TransactionType.TRANSFER)

        self.assertEqual(duplicate.pk, first.pk)
        self.assertEqual(LedgerTransaction.objects.count(), 1)
        self.assertEqual(LedgerPosting.objects.count(), 2)

    def test_idempotency_return_does_not_bypass_metadata_validation(self):
        self.post(key='metadata-first')

        with self.assertRaises(LedgerError):
            self.post(key='metadata-first', business_date='2026-08-10')

        self.assertEqual(LedgerTransaction.objects.count(), 1)

    def test_non_cny_account_cannot_be_backfilled_before_existing_posting(self):
        self.post(
            business_date=date(2026, 8, 11), key='rub-later',
            postings=[self.input(self.rub_account, '100.00', '10.00'), self.category('-10')],
        )
        with self.assertRaises(LedgerError):
            self.post(
                business_date=date(2026, 8, 10), key='rub-early',
                postings=[self.input(self.rub_account, '1.00', '1.00'), self.category('-1')],
            )

    def test_snapshot_as_of_excludes_later_business_dates(self):
        self.post(key='day-one')
        self.post(
            business_date=date(2026, 8, 11), key='day-two',
            postings=[self.input(self.cny_account, '-20', '-20'), self.category('20')],
        )

        as_of = account_snapshot(self.cny_account, as_of_business_date=date(2026, 8, 10))
        current = account_snapshot(self.cny_account)
        self.assertEqual(as_of.original_balance, Decimal('100.00000000'))
        self.assertEqual(as_of.cny_book_cost, Decimal('100.00'))
        self.assertEqual(current.original_balance, Decimal('80.00000000'))
        self.assertEqual(current.cny_book_cost, Decimal('80.00'))

    def test_two_saved_operators_are_audited_on_their_transactions(self):
        first = self.post(key='operator-a', operator=self.operator)
        second = self.post(
            key='operator-b', operator=self.other_operator,
            postings=[self.input(self.rub_account, '100.00', '10.00'), self.category('-10')],
        )

        self.assertEqual(first.operator, self.operator)
        self.assertEqual(second.operator, self.other_operator)

    def test_rejects_invalid_transaction_metadata_and_non_operator(self):
        invalid_operator = User.objects.create_user('not-operator', password='pass')
        invalid_cases = [
            {'transaction_type': 'not-a-type'},
            {'business_date': datetime(2026, 8, 10, 10, 0)},
            {'business_date': '2026-08-10'},
            {'key': ''},
            {'operator': invalid_operator},
        ]
        for index, changes in enumerate(invalid_cases):
            arguments = {'key': f'invalid-{index}'}
            arguments.update(changes)
            with self.subTest(changes=changes), self.assertRaises(LedgerError):
                self.post(**arguments)

        self.assertEqual(LedgerTransaction.objects.count(), 0)

    def test_rejects_unsaved_or_missing_account_as_ledger_error(self):
        unsaved = FundAccount(name='unsaved', currency='CNY', creation_idempotency_key='unsaved')
        missing = FundAccount(id=999999, name='missing', currency='CNY', creation_idempotency_key='missing')
        for account in (unsaved, missing):
            with self.subTest(account=account), self.assertRaises(LedgerError):
                self.post(postings=[self.input(account, '100', '100'), self.category('-100')])

        self.assertEqual(LedgerTransaction.objects.count(), 0)

    def test_rejects_business_dates_before_cutover(self):
        with self.assertRaises(LedgerError):
            self.post(business_date=date(2026, 8, 9))


class LedgerIdempotencyConcurrencyTest(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.operator = User.objects.create_user('concurrent-operator', password='pass', is_staff=True)
        self.account = FundAccount.objects.create(
            name='并发 CNY', currency='CNY', creation_idempotency_key='concurrent-cny',
        )

    def test_concurrent_identical_key_creates_one_transaction_and_posting_set(self):
        barrier = threading.Barrier(2)
        errors = []
        transaction_ids = []

        def submit():
            close_old_connections()
            try:
                operator = User.objects.get(pk=self.operator.pk)
                account = FundAccount.objects.get(pk=self.account.pk)
                barrier.wait(timeout=10)
                tx = post_transaction(
                    transaction_type=LedgerTransaction.TransactionType.OPENING_BALANCE,
                    business_date=date(2026, 8, 10),
                    postings=[
                        PostingInput(account=account, currency='CNY', amount=Decimal('100'), cny_amount=Decimal('100')),
                        PostingInput(category=LedgerPosting.Category.OPENING_CAPITAL, currency='CNY', amount=Decimal('-100'), cny_amount=Decimal('-100')),
                    ],
                    operator=operator,
                    idempotency_key='concurrent-key',
                )
                transaction_ids.append(tx.pk)
            except Exception as error:  # assertions below surface real failures
                errors.append(error)
            finally:
                close_old_connections()

        threads = [threading.Thread(target=submit), threading.Thread(target=submit)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=15)

        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertEqual(errors, [])
        self.assertEqual(len(set(transaction_ids)), 1)
        self.assertEqual(LedgerTransaction.objects.filter(idempotency_key='concurrent-key').count(), 1)
        self.assertEqual(LedgerPosting.objects.count(), 2)
