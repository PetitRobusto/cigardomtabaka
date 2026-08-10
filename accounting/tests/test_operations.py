from datetime import date
from decimal import Decimal
import inspect
import threading

from unittest.mock import patch
from django.db import OperationalError, close_old_connections
from django.test import TestCase, TransactionTestCase

from accounting import services
from accounting.models import FundAccount, LedgerPosting, LedgerSequence, LedgerTransaction
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

    def test_opening_must_precede_all_normal_cutover_business(self):
        first = self.opening(self.cny, '100', '100', 'cutover-first-opening')
        exchange_to_rub(
            self.cny, self.rub, '100', '1200', self.business_date, self.operator, 'cutover-normal-business',
        )
        duplicate = self.opening(self.cny, '0', '0', 'cutover-first-opening')
        unused = self.account('late opening account', 'USDT', 'late-opening-account')
        transaction_count = LedgerTransaction.objects.count()
        posting_count = LedgerPosting.objects.count()
        sequence = LedgerSequence.objects.get(name='global')
        next_value = sequence.next_value

        self.assertEqual(duplicate.pk, first.pk)
        with self.assertRaises(LedgerError):
            self.opening(unused, '1', '1', 'late-opening')

        sequence.refresh_from_db()
        self.assertEqual(LedgerTransaction.objects.count(), transaction_count)
        self.assertEqual(LedgerPosting.objects.count(), posting_count)
        self.assertEqual(sequence.next_value, next_value)

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

    def test_usdt_exchange_partial_and_final_outflow_move_rounded_then_remaining_cost(self):
        self.opening(self.usdt, '3', '10', 'usdt-exchange-opening')
        first = exchange_to_rub(
            self.usdt, self.rub, '1', '100', self.business_date, self.operator, 'usdt-exchange-first',
        )
        second = exchange_to_rub(
            self.usdt, self.rub, '2', '200', self.business_date, self.operator, 'usdt-exchange-final',
        )

        self.assertEqual(first.postings.get(account=self.rub).cny_amount, Decimal('3.33'))
        self.assertEqual(second.postings.get(account=self.rub).cny_amount, Decimal('6.67'))
        self.assertEqual(
            (self.snapshot(self.usdt).original_balance, self.snapshot(self.usdt).cny_book_cost),
            (Decimal('0.00000000'), Decimal('0.00')),
        )
        self.assertEqual(
            (self.snapshot(self.rub).original_balance, self.snapshot(self.rub).cny_book_cost),
            (Decimal('300.00000000'), Decimal('10.00')),
        )

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

    def test_exchange_rejects_negative_rub_amount_without_residue(self):
        with self.assertRaises(LedgerError):
            exchange_to_rub(
                self.cny, self.rub, '1', '-1', self.business_date, self.operator, 'negative-rub-amount',
            )
        self.assert_no_ledger_residue()

    def test_exchange_and_transfer_reject_missing_account_rows_without_residue(self):
        missing_id = 999999
        stale = FundAccount(
            id=missing_id,
            name='missing account',
            currency='CNY',
            creation_idempotency_key='missing-account',
        )
        stale._state.adding = False

        with self.assertRaises(LedgerError):
            exchange_to_rub(stale, self.rub, '1', '1', self.business_date, self.operator, 'missing-exchange')
        with self.assertRaises(LedgerError):
            transfer_same_currency(stale, self.cny, '1', self.business_date, self.operator, 'missing-transfer')

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


    def test_operation_retries_locked_single_transaction_attempt_five_times(self):
        self.opening(self.cny, '100', '100', 'retry-boundary-opening')

        with patch(
            'accounting.services._post_transaction_once',
            side_effect=OperationalError('database is locked'),
        ) as post_once, patch('accounting.services.time.sleep'):
            with self.assertRaises(OperationalError):
                exchange_to_rub(
                    self.cny, self.rub, '100', '1200', self.business_date,
                    self.operator, 'retry-boundary-exchange',
                )

        self.assertEqual(post_once.call_count, 5)

    def test_operation_lock_retry_uses_jitter_to_break_symmetric_backoff(self):
        self.opening(self.cny, '100', '100', 'retry-jitter-opening')

        with patch(
            'accounting.services._post_transaction_once',
            side_effect=OperationalError('database is locked'),
        ), patch('accounting.services.time.sleep') as sleep, patch.object(
            services, 'random', create=True,
        ) as random_module:
            random_module.uniform.return_value = 0.037
            with self.assertRaises(OperationalError):
                exchange_to_rub(
                    self.cny, self.rub, '100', '1200', self.business_date,
                    self.operator, 'retry-jitter-exchange',
                )

        self.assertEqual(sleep.call_count, 4)
        for actual, expected in zip(
            (entry.args[0] for entry in sleep.call_args_list),
            (0.137, 0.237, 0.337, 0.437),
        ):
            self.assertAlmostEqual(actual, expected)
        self.assertEqual(random_module.uniform.call_count, 4)

    def test_retry_decorator_preserves_public_operation_signatures(self):
        expected_parameters = {
            'record_opening_balance': (
                'account', 'original_amount', 'cny_book_cost', 'equity_category',
                'business_date', 'operator', 'idempotency_key',
            ),
            'exchange_to_rub': (
                'source_account', 'rub_account', 'source_amount', 'rub_amount',
                'business_date', 'operator', 'idempotency_key', 'description',
            ),
            'transfer_same_currency': (
                'source_account', 'target_account', 'amount', 'business_date',
                'operator', 'idempotency_key', 'description',
            ),
        }
        operations = {
            'record_opening_balance': record_opening_balance,
            'exchange_to_rub': exchange_to_rub,
            'transfer_same_currency': transfer_same_currency,
        }

        for name, operation in operations.items():
            with self.subTest(operation=name):
                self.assertEqual(operation.__name__, name)
                self.assertTrue(hasattr(operation, '__wrapped__'))
                self.assertEqual(tuple(inspect.signature(operation).parameters), expected_parameters[name])

class OpeningSequenceConcurrencyTest(TransactionTestCase):
    reset_sequences = True
    business_date = date(2026, 8, 10)

    def setUp(self):
        self.operator = User.objects.create_user('opening-sequence-operator', password='pass', is_staff=True)

    def _exercise_concurrent_opening_and_exchange(self):
        for attempt in range(1):
            with self.subTest(attempt=attempt):
                cny = FundAccount.objects.create(
                    name=f'concurrent CNY {attempt}', currency='CNY',
                    creation_idempotency_key=f'concurrent-cny-{attempt}',
                )
                rub = FundAccount.objects.create(
                    name=f'concurrent RUB {attempt}', currency='RUB',
                    creation_idempotency_key=f'concurrent-rub-{attempt}',
                )
                opening = FundAccount.objects.create(
                    name=f'concurrent opening {attempt}', currency='USDT',
                    creation_idempotency_key=f'concurrent-opening-{attempt}',
                )
                record_opening_balance(
                    cny, '100', '100', LedgerPosting.Category.OPENING_CAPITAL,
                    self.business_date, self.operator, f'concurrent-seed-{attempt}',
                )
                barrier = threading.Barrier(2)
                transactions = {}
                errors = {}

                def submit(name, operation):
                    close_old_connections()
                    try:
                        barrier.wait(timeout=10)
                        transactions[name] = operation()
                    except Exception as error:  # assertions below surface all unexpected database errors
                        errors[name] = error
                    finally:
                        close_old_connections()

                def submit_opening():
                    return record_opening_balance(
                        FundAccount.objects.get(pk=opening.pk), '1', '1',
                        LedgerPosting.Category.OPENING_CAPITAL, self.business_date,
                        User.objects.get(pk=self.operator.pk), f'concurrent-opening-tx-{attempt}',
                    )

                def submit_exchange():
                    return exchange_to_rub(
                        FundAccount.objects.get(pk=cny.pk), FundAccount.objects.get(pk=rub.pk),
                        '100', '1200', self.business_date, User.objects.get(pk=self.operator.pk),
                        f'concurrent-exchange-tx-{attempt}',
                    )

                threads = [
                    threading.Thread(target=submit, args=('opening', submit_opening)),
                    threading.Thread(target=submit, args=('exchange', submit_exchange)),
                ]
                for thread in threads:
                    thread.start()
                for thread in threads:
                    thread.join(timeout=15)

                self.assertFalse(any(thread.is_alive() for thread in threads))
                self.assertNotIn('exchange', errors)
                self.assertIn('exchange', transactions)
                self.assertTrue(
                    'opening' in transactions or isinstance(errors.get('opening'), LedgerError),
                    errors,
                )
                if 'opening' in transactions:
                    self.assertLess(
                        transactions['opening'].effective_sequence,
                        transactions['exchange'].effective_sequence,
                    )
    def test_concurrent_opening_and_exchange_attempt_1(self):
        self._exercise_concurrent_opening_and_exchange()

    def test_concurrent_opening_and_exchange_attempt_2(self):
        self._exercise_concurrent_opening_and_exchange()

    def test_concurrent_opening_and_exchange_attempt_3(self):
        self._exercise_concurrent_opening_and_exchange()

    def test_concurrent_opening_and_exchange_attempt_4(self):
        self._exercise_concurrent_opening_and_exchange()

    def test_concurrent_opening_and_exchange_attempt_5(self):
        self._exercise_concurrent_opening_and_exchange()

    def test_concurrent_opening_and_exchange_attempt_6(self):
        self._exercise_concurrent_opening_and_exchange()

    def test_concurrent_opening_and_exchange_attempt_7(self):
        self._exercise_concurrent_opening_and_exchange()

    def test_concurrent_opening_and_exchange_attempt_8(self):
        self._exercise_concurrent_opening_and_exchange()
