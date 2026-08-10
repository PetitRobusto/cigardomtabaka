from datetime import date, datetime
from decimal import Decimal
import threading
from unittest.mock import patch

from django.db import OperationalError, close_old_connections, connection
from django.test import TestCase, TransactionTestCase

from accounting import services as ledger_services
from accounting.models import FundAccount, LedgerPosting, LedgerSequence, LedgerTransaction
from accounting.selectors import account_snapshot
from accounting.services import LedgerError, PostingInput, post_transaction
from cigars.models import User

def create_posted_fixture(operator, account, sequence, amount, cny_amount):
    """Raw fixture for legacy historical-replay tests; product ORM bypasses stay closed."""
    ledger_transaction = LedgerTransaction.objects.create(
        transaction_type=LedgerTransaction.TransactionType.TRANSFER,
        business_date=date(2026, 8, 10), effective_sequence=sequence, operator=operator,
    )
    LedgerPosting.objects.create(
        transaction=ledger_transaction, account=account, currency=account.currency,
        amount=Decimal(amount), cny_amount=Decimal(cny_amount),
    )
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE accounting_ledgertransaction SET status = %s WHERE id = %s",
            [LedgerTransaction.Status.POSTED, ledger_transaction.pk],
        )
    ledger_transaction.refresh_from_db()
    return ledger_transaction



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
             key='key-1', transaction_type=LedgerTransaction.TransactionType.TRANSFER,
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
        create_posted_fixture(self.operator, self.cny_account, 2, 100, 100)
        with self.assertRaises(LedgerError):
            self.post(postings=[self.input(self.cny_account, '-100', '-100'), self.category('100')])
        self.assertEqual(LedgerTransaction.objects.count(), 1)
    def test_same_idempotency_key_returns_original_and_rejects_other_type(self):
        first = self.post(key='repeat')
        duplicate = self.post(key='repeat')
        with self.assertRaises(LedgerError):
            self.post(key='repeat', transaction_type=LedgerTransaction.TransactionType.EXCHANGE)

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


    def test_rejects_transient_account_with_existing_primary_key(self):
        transient = FundAccount(
            id=self.cny_account.pk,
            name=self.cny_account.name,
            currency='CNY',
            creation_idempotency_key=self.cny_account.creation_idempotency_key,
        )

        self.assertTrue(transient._state.adding)
        with self.assertRaises(LedgerError):
            self.post(postings=[self.input(transient, '100', '100'), self.category('-100')])

        self.assertEqual(LedgerTransaction.objects.count(), 0)

    def test_idempotency_hit_validates_operator_and_keeps_original_audit_operator(self):
        original = self.post(key='operator-idempotency')
        unsaved_operator = User(username='unsaved-operator', is_staff=True)
        nonstaff_operator = User.objects.create_user('idempotency-nonstaff', password='pass')

        for operator in (unsaved_operator, nonstaff_operator):
            with self.subTest(operator=operator), self.assertRaises(LedgerError):
                self.post(key='operator-idempotency', operator=operator)

        persisted = LedgerTransaction.objects.get(pk=original.pk)
        self.assertEqual(persisted.operator_id, self.operator.pk)
        self.assertEqual(LedgerTransaction.objects.count(), 1)

    def test_rounds_original_and_cny_amounts_with_currency_precision(self):
        usdt_account = self.make_account('现金 USDT', 'USDT', 'cash-usdt')
        cny = self.post(
            key='round-cny',
            postings=[self.input(self.cny_account, '100.005', '100.005'), self.category('-100.005')],
        )
        rub = self.post(
            key='round-rub',
            postings=[self.input(self.rub_account, '1.005', '1.005'), self.category('-1.005')],
        )
        usdt = self.post(
            key='round-usdt',
            postings=[self.input(usdt_account, '1.000000005', '0.005'), self.category('-0.005')],
        )

        self.assertEqual(cny.postings.get(account=self.cny_account).amount, Decimal('100.01000000'))
        self.assertEqual(cny.postings.get(account=self.cny_account).cny_amount, Decimal('100.01'))
        self.assertEqual(rub.postings.get(account=self.rub_account).amount, Decimal('1.01000000'))
        self.assertEqual(rub.postings.get(account=self.rub_account).cny_amount, Decimal('1.01'))
        self.assertEqual(usdt.postings.get(account=usdt_account).amount, Decimal('1.00000001'))
        self.assertEqual(usdt.postings.get(account=usdt_account).cny_amount, Decimal('0.01'))

    def test_snapshot_ignores_draft_and_reversed_postings_and_preserves_empty_scales(self):
        for status, sequence in (
            (LedgerTransaction.Status.DRAFT, None),
            (LedgerTransaction.Status.REVERSED, 99),
        ):
            transaction = LedgerTransaction.objects.create(
                transaction_type=LedgerTransaction.TransactionType.TRANSFER,
                status=status,
                business_date=date(2026, 8, 10),
                effective_sequence=sequence,
                operator=self.operator,
            )
            LedgerPosting.objects.create(
                transaction=transaction,
                account=self.cny_account,
                currency='CNY',
                amount=Decimal('999'),
                cny_amount=Decimal('999'),
            )

        snapshot = account_snapshot(self.cny_account)
        self.assertEqual(snapshot.original_balance, Decimal('0.00000000'))
        self.assertEqual(snapshot.cny_book_cost, Decimal('0.00'))
        self.assertIsNone(snapshot.moving_average_cny)

    def test_replay_rejects_negative_cny_cost_while_original_balance_stays_positive(self):
        self.post(
            key='rub-cost-in',
            postings=[self.input(self.rub_account, '100', '100'), self.category('-100')],
        )

        with self.assertRaises(LedgerError):
            self.post(
                key='rub-cost-out',
                postings=[self.input(self.rub_account, '-1', '-101'), self.category('101')],
            )

        self.assertEqual(LedgerTransaction.objects.count(), 1)

class LedgerIdempotencyConcurrencyTest(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.operator = User.objects.create_user('concurrent-operator', password='pass', is_staff=True)
        self.account = FundAccount.objects.create(
            name='并发 CNY', currency='CNY', creation_idempotency_key='concurrent-cny',
        )
        self.cny_account = self.account
        self.rub_account = FundAccount.objects.create(
            name='并发 RUB', currency='RUB', creation_idempotency_key='concurrent-rub',
        )

    def make_account(self, name, currency, key):
        return FundAccount.objects.create(
            name=name,
            currency=currency,
            creation_idempotency_key=key,
        )

    def input(self, account, amount, cny_amount):
        return PostingInput(
            account=account,
            currency=account.currency,
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

    def post(self, *, key, postings=None):
        return post_transaction(
            transaction_type=LedgerTransaction.TransactionType.TRANSFER,
            business_date=date(2026, 8, 10),
            postings=postings or [self.input(self.cny_account, '100', '100'), self.category('-100')],
            operator=self.operator,
            idempotency_key=key,
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
                    transaction_type=LedgerTransaction.TransactionType.TRANSFER,
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

    def test_concurrent_different_keys_receive_distinct_global_sequences(self):
        barrier = threading.Barrier(2)
        errors = []
        sequences = []

        def submit(idempotency_key):
            close_old_connections()
            try:
                operator = User.objects.get(pk=self.operator.pk)
                account = FundAccount.objects.get(pk=self.account.pk)
                barrier.wait(timeout=10)
                tx = post_transaction(
                    transaction_type=LedgerTransaction.TransactionType.TRANSFER,
                    business_date=date(2026, 8, 10),
                    postings=[
                        PostingInput(account=account, currency='CNY', amount=Decimal('100'), cny_amount=Decimal('100')),
                        PostingInput(category=LedgerPosting.Category.OPENING_CAPITAL, currency='CNY', amount=Decimal('-100'), cny_amount=Decimal('-100')),
                    ],
                    operator=operator,
                    idempotency_key=idempotency_key,
                )
                sequences.append(tx.effective_sequence)
            except Exception as error:  # assertions below surface real failures
                errors.append(error)
            finally:
                close_old_connections()

        threads = [
            threading.Thread(target=submit, args=('concurrent-key-a',)),
            threading.Thread(target=submit, args=('concurrent-key-b',)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=15)

        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertEqual(errors, [])
        self.assertEqual(set(sequences), {1, 2})
        self.assertEqual(LedgerTransaction.objects.count(), 2)
        self.assertEqual(LedgerPosting.objects.count(), 4)

    def test_retries_one_shot_generator_after_locked_error(self):
        def postings():
            yield self.input(self.cny_account, '100', '100')
            yield self.category('-100')

        original_validate = ledger_services._validate_historical_balances
        attempts = 0

        def lock_once(*args):
            nonlocal attempts
            original_validate(*args)
            attempts += 1
            if attempts == 1:
                raise OperationalError('database is locked')

        with patch.object(ledger_services, '_validate_historical_balances', side_effect=lock_once):
            transaction = self.post(key='generator-retry', postings=postings())

        self.assertEqual(attempts, 2)
        self.assertEqual(transaction.postings.count(), 2)
        self.assertEqual(LedgerTransaction.objects.count(), 1)

    def test_direct_posted_history_without_sequence_is_rejected(self):
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            LedgerTransaction.objects.create(
                transaction_type=LedgerTransaction.TransactionType.TRANSFER,
                status=LedgerTransaction.Status.POSTED, business_date=date(2026, 8, 10),
                operator=self.operator,
            )

    def test_validates_decimal_field_boundaries_before_writing(self):
        original_bound = Decimal('999999999999.99')
        accepted = self.post(
            key='original-bound',
            postings=[self.input(self.cny_account, original_bound, original_bound), self.category(-original_bound)],
        )
        self.assertEqual(accepted.postings.get(account=self.cny_account).amount, original_bound)

        with self.assertRaisesRegex(LedgerError, '原币金额超出范围'):
            self.post(
                key='original-overflow',
                postings=[self.input(self.cny_account, '1000000000000', '1000000000000'), self.category('-1000000000000')],
            )

        reserve = self.make_account('人民币账面边界准备金', 'RUB', 'rub-cny-bound')
        seed = create_posted_fixture(
            self.operator, reserve, 2, 1, 999999999999999999.99,
        )
        LedgerSequence.objects.filter(name='global').update(next_value=3)
        cny_bound = self.post(
            key='cny-bound',
            postings=[
                self.input(self.rub_account, '1', '999999999999999999.99'),
                self.input(reserve, '-1', '-999999999999999999.99'),
            ],
        )
        self.assertIsNotNone(cny_bound.pk)

        with self.assertRaisesRegex(LedgerError, '人民币账面金额超出范围'):
            self.post(
                key='cny-overflow',
                postings=[
                    self.input(self.rub_account, '1', '1000000000000000000'),
                    self.input(reserve, '-1', '-1000000000000000000'),
                ],
            )

        self.assertEqual(LedgerTransaction.objects.count(), 3)
        self.assertEqual(LedgerPosting.objects.count(), 5)

    def test_public_post_rejects_non_finite_amounts_without_residue(self):
        usdt_account = self.make_account('非有限 USDT', 'USDT', 'non-finite-usdt')
        accounts = {'CNY': self.cny_account, 'RUB': self.rub_account, 'USDT': usdt_account}

        for bad_value in (Decimal('NaN'), Decimal('Infinity')):
            for currency, account in accounts.items():
                for field_name in ('amount', 'cny_amount'):
                    values = {'amount': Decimal('100'), 'cny_amount': Decimal('100')}
                    values[field_name] = bad_value
                    with self.subTest(value=bad_value, currency=currency, field=field_name), self.assertRaises(LedgerError):
                        self.post(
                            key=f'non-finite-{bad_value}-{currency}-{field_name}',
                            postings=[
                                PostingInput(account=account, currency=currency, **values),
                                self.category('-100'),
                            ],
                        )
                    self.assertEqual(LedgerTransaction.objects.count(), 0)
                    self.assertEqual(LedgerPosting.objects.count(), 0)
                    self.assertEqual(LedgerSequence.objects.count(), 0)
