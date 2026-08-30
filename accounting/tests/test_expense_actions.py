from datetime import date
from decimal import Decimal

from django.db import OperationalError, models
from django.test import TestCase
from unittest.mock import patch

from accounting.models import (
    Day1Initialization,
    Expense,
    FundAccount,
    LedgerPosting,
    LedgerTransaction,
)
from accounting.services import exchange_to_rub, record_opening_balance
from accounting.selectors import account_snapshot
from accounting.selectors import monthly_profit
from cigars.models import User


class ExpenseActionTest(TestCase):
    business_date = date(2026, 8, 14)

    def setUp(self):
        self.operator = User.objects.create_user(
            username='expense-operator', is_staff=True,
        )
        Day1Initialization.objects.create(
            singleton_key='company',
            status=Day1Initialization.Status.COMPLETED,
            business_date=date(2026, 8, 10),
            completed_by=self.operator,
        )
        self.cny = FundAccount.objects.create(
            name='费用人民币账户', currency=FundAccount.Currency.CNY,
            creation_idempotency_key='expense-cny', custodian=self.operator,
        )
        record_opening_balance(
            self.cny, Decimal('1000.00'), Decimal('1000.00'),
            LedgerPosting.Category.OPENING_CAPITAL, date(2026, 8, 10),
            self.operator, 'expense-opening-cny',
        )
        self.rub = FundAccount.objects.create(
            name='费用卢布账户', currency=FundAccount.Currency.RUB,
            creation_idempotency_key='expense-rub', custodian=self.operator,
        )
        record_opening_balance(
            self.rub, Decimal('1200.00'), Decimal('100.00'),
            LedgerPosting.Category.OPENING_CAPITAL, date(2026, 8, 10),
            self.operator, 'expense-opening-rub',
        )

    def test_salary_uses_cny_account_and_salary_category(self):
        from accounting.expense_actions import record_expense

        expense = record_expense(
            category=Expense.Category.SALARY,
            amount='100.00',
            fund_account_id=self.cny.pk,
            business_date=self.business_date,
            operator=self.operator,
            idempotency_key='expense-salary-1',
        )

        self.assertEqual(expense.category, Expense.Category.SALARY)
        self.assertEqual(expense.original_amount, Decimal('100.00'))
        self.assertEqual(expense.amount_cny, Decimal('100.00'))
        transaction = expense.ledger_transaction
        self.assertEqual(transaction.transaction_type, LedgerTransaction.TransactionType.EXPENSE)
        self.assertEqual(
            set(transaction.postings.values_list('category', flat=True)),
            {'', LedgerPosting.Category.SALARY_EXPENSE},
        )

    def test_rent_uses_rub_moving_average_and_rent_category(self):
        from accounting.expense_actions import record_expense

        expense = record_expense(
            category=Expense.Category.RENT,
            amount='120.00',
            fund_account_id=self.rub.pk,
            business_date=self.business_date,
            operator=self.operator,
            idempotency_key='expense-rent-1',
        )

        self.assertEqual(expense.amount_cny, Decimal('10.00'))
        posting = expense.ledger_transaction.postings.get(account=self.rub)
        self.assertEqual(posting.cny_amount, Decimal('-10.00'))
        self.assertEqual(
            expense.ledger_transaction.postings.get(account__isnull=True).category,
            LedgerPosting.Category.RENT_EXPENSE,
        )

    def test_operating_categories_use_rub_accounts(self):
        from accounting.expense_actions import record_expense

        for category, posting_category in (
            (Expense.Category.UTILITIES, LedgerPosting.Category.UTILITIES_EXPENSE),
            (Expense.Category.PROFESSIONAL, LedgerPosting.Category.PROFESSIONAL_EXPENSE),
            (Expense.Category.INTEREST, LedgerPosting.Category.INTEREST_EXPENSE),
            (Expense.Category.OTHER, LedgerPosting.Category.OTHER_EXPENSE),
        ):
            with self.subTest(category=category):
                expense = record_expense(
                    category=category,
                    amount='12.00',
                    fund_account_id=self.rub.pk,
                    business_date=self.business_date,
                    operator=self.operator,
                    idempotency_key=f'expense-{category}-1',
                )
                self.assertEqual(
                    expense.ledger_transaction.postings.get(
                        account__isnull=True,
                    ).category,
                    posting_category,
                )
        monthly = monthly_profit(month=self.business_date)
        self.assertEqual(monthly['professional_expense_cny'], Decimal('1.00'))
        self.assertEqual(monthly['interest_expense_cny'], Decimal('1.00'))

    def test_subcategory_is_recorded_and_keeps_existing_accounting_category(self):
        from accounting.expense_actions import record_expense

        expense = record_expense(
            category=Expense.Category.OTHER,
            subcategory=Expense.Subcategory.TRANSPORT_TAXI,
            amount='25.00',
            fund_account_id=self.cny.pk,
            business_date=self.business_date,
            operator=self.operator,
            idempotency_key='expense-taxi-subcategory-1',
        )

        self.assertEqual(expense.subcategory, Expense.Subcategory.TRANSPORT_TAXI)
        self.assertEqual(
            expense.ledger_transaction.postings.get(account__isnull=True).category,
            LedgerPosting.Category.OTHER_EXPENSE,
        )

    def test_subcategory_must_match_its_parent_accounting_category(self):
        from accounting.expense_actions import ExpenseActionError, record_expense

        with self.assertRaises(ExpenseActionError) as raised:
            record_expense(
                category=Expense.Category.SALARY,
                subcategory=Expense.Subcategory.TRANSPORT_TAXI,
                amount='25.00',
                fund_account_id=self.cny.pk,
                business_date=self.business_date,
                operator=self.operator,
                idempotency_key='expense-subcategory-mismatch-1',
            )

        self.assertEqual(raised.exception.code, 'category_subcategory_mismatch')

    def test_invalid_amounts_have_stable_codes(self):
        from accounting.expense_actions import ExpenseActionError, record_expense

        for amount, code in (
            ('-1.00', 'invalid_amount'),
            ('0.00', 'invalid_amount'),
            ('1.001', 'invalid_money_precision'),
            ('1000000000000.00', 'invalid_money_precision'),
        ):
            with self.subTest(amount=amount):
                with self.assertRaises(ExpenseActionError) as raised:
                    record_expense(
                        category=Expense.Category.SALARY,
                        amount=amount,
                        fund_account_id=self.cny.pk,
                        business_date=self.business_date,
                        operator=self.operator,
                        idempotency_key=f'expense-invalid-{amount}',
                    )
                self.assertEqual(raised.exception.code, code)

    def test_account_state_and_balance_have_stable_codes(self):
        from accounting.expense_actions import ExpenseActionError, record_expense

        inactive = FundAccount.objects.create(
            name='停用费用账户', currency=FundAccount.Currency.CNY,
            creation_idempotency_key='expense-inactive', is_active=False,
        )
        cases = (
            (
                Expense.Category.SALARY, inactive.pk, 'account_inactive',
                'expense-inactive-case',
            ),
            (
                Expense.Category.RENT, self.rub.pk, 'insufficient_balance',
                'expense-balance-case',
            ),
        )
        for category, account_id, code, key in cases:
            with self.subTest(code=code):
                with self.assertRaises(ExpenseActionError) as raised:
                    record_expense(
                        category=category,
                        amount='999999.00' if code == 'insufficient_balance' else '10.00',
                        fund_account_id=account_id,
                        business_date=self.business_date,
                        operator=self.operator,
                        idempotency_key=key,
                    )
                self.assertEqual(raised.exception.code, code)

    def test_replay_returns_same_expense_and_parameter_conflict_is_stable(self):
        from accounting.expense_actions import ExpenseActionError, record_expense

        kwargs = {
            'category': Expense.Category.SALARY,
            'amount': '10.00',
            'fund_account_id': self.cny.pk,
            'business_date': self.business_date,
            'operator': self.operator,
            'idempotency_key': 'expense-replay-1',
        }
        first = record_expense(**kwargs)
        replay = record_expense(**kwargs)
        self.assertEqual(replay.pk, first.pk)
        self.assertEqual(Expense.objects.count(), 1)
        with self.assertRaises(ExpenseActionError) as raised:
            record_expense(**{**kwargs, 'amount': '11.00'})
        self.assertEqual(raised.exception.code, 'idempotency_conflict')

    def test_replay_rejects_changed_note(self):
        from accounting.expense_actions import ExpenseActionError, record_expense

        kwargs = {
            'category': Expense.Category.SALARY,
            'amount': '10.00',
            'fund_account_id': self.cny.pk,
            'business_date': self.business_date,
            'operator': self.operator,
            'idempotency_key': 'expense-note-replay',
            'note': '八月工资',
        }
        first = record_expense(**kwargs)
        self.assertEqual(record_expense(**kwargs).pk, first.pk)
        with self.assertRaises(ExpenseActionError) as raised:
            record_expense(**{**kwargs, 'note': '九月工资'})
        self.assertEqual(raised.exception.code, 'idempotency_conflict')

    def test_day1_gate_allows_replay_but_blocks_new_expense(self):
        from accounting.expense_actions import ExpenseActionError, record_expense

        kwargs = {
            'category': Expense.Category.SALARY,
            'amount': '10.00',
            'fund_account_id': self.cny.pk,
            'business_date': date(2026, 9, 1),
            'operator': self.operator,
            'idempotency_key': 'expense-day1-gate-1',
        }
        first = record_expense(**kwargs)
        Day1Initialization.objects.all().delete()
        self.assertEqual(record_expense(**kwargs).pk, first.pk)
        with self.assertRaises(ExpenseActionError) as raised:
            record_expense(**{**kwargs, 'idempotency_key': 'expense-day1-gate-2'})
        self.assertEqual(raised.exception.code, 'day1_incomplete')

    def test_writer_gate_lock_retries_once_and_creates_one_fact(self):
        from accounting import expense_actions
        from accounting.expense_actions import record_expense

        original_gate = expense_actions._acquire_sqlite_writer_gate
        calls = {'count': 0}

        def lock_once():
            calls['count'] += 1
            if calls['count'] == 1:
                raise OperationalError('database is locked')
            return original_gate()

        before_expenses = Expense.objects.count()
        before_ledgers = LedgerTransaction.objects.count()
        with patch.object(expense_actions, '_acquire_sqlite_writer_gate', side_effect=lock_once):
            expense = record_expense(
                category=Expense.Category.SALARY,
                amount='10.00',
                fund_account_id=self.cny.pk,
                business_date=self.business_date,
                operator=self.operator,
                idempotency_key='expense-lock-retry-1',
            )

        self.assertGreaterEqual(calls['count'], 2)
        self.assertEqual(Expense.objects.count(), before_expenses + 1)
        self.assertEqual(LedgerTransaction.objects.count(), before_ledgers + 1)
        self.assertEqual(
            Expense.objects.get(pk=expense.pk).ledger_transaction.postings.count(),
            2,
        )

    def test_posting_failure_rolls_back_expense_ledger_and_account_fact(self):
        from accounting import expense_actions
        from accounting.expense_actions import record_expense

        before_expenses = Expense.objects.count()
        before_ledgers = LedgerTransaction.objects.count()
        before_snapshot = account_snapshot(self.cny)
        with patch.object(
            expense_actions,
            '_post_transaction_once',
            side_effect=RuntimeError('injected posting failure'),
        ):
            with self.assertRaises(RuntimeError):
                record_expense(
                    category=Expense.Category.SALARY,
                    amount='10.00',
                    fund_account_id=self.cny.pk,
                    business_date=self.business_date,
                    operator=self.operator,
                    idempotency_key='expense-atomic-failure-1',
                )

        self.assertEqual(Expense.objects.count(), before_expenses)
        self.assertEqual(LedgerTransaction.objects.count(), before_ledgers)
        self.assertEqual(account_snapshot(self.cny), before_snapshot)

    def test_expense_creation_failure_rolls_back_posting(self):
        from accounting import expense_actions
        from accounting.expense_actions import record_expense

        before_expenses = Expense.objects.count()
        before_ledgers = LedgerTransaction.objects.count()
        before_snapshot = account_snapshot(self.cny)
        with patch.object(
            expense_actions,
            'ledger_mutation_scope',
            side_effect=RuntimeError('injected expense failure'),
        ):
            with self.assertRaises(RuntimeError):
                record_expense(
                    category=Expense.Category.SALARY,
                    amount='10.00',
                    fund_account_id=self.cny.pk,
                    business_date=self.business_date,
                    operator=self.operator,
                    idempotency_key='expense-atomic-expense-failure-1',
                )

        self.assertEqual(Expense.objects.count(), before_expenses)
        self.assertEqual(LedgerTransaction.objects.count(), before_ledgers)
        self.assertEqual(account_snapshot(self.cny), before_snapshot)

    def test_input_validation_has_stable_codes_and_account_id_replay(self):
        from accounting.expense_actions import ExpenseActionError, record_expense

        common = {
            'category': Expense.Category.SALARY,
            'amount': '10.00',
            'fund_account_id': self.cny.pk,
            'business_date': self.business_date,
            'operator': self.operator,
        }
        for field, value, code in (
            ('idempotency_key', '', 'invalid_idempotency_key'),
            ('idempotency_key', 'x' * 129, 'invalid_idempotency_key'),
            ('business_date', '2026-08-14', 'invalid_business_date'),
            ('fund_account_id', 999999, 'account_not_found'),
        ):
            with self.subTest(field=field, value=value):
                payload = {
                    **common,
                    'idempotency_key': f'expense-invalid-{field}-{code}',
                    field: value,
                }
                with self.assertRaises(ExpenseActionError) as raised:
                    record_expense(**payload)
                self.assertEqual(raised.exception.code, code)

        invalid_operator_payload = {
            **common,
            'operator': User(username='not-an-operator'),
            'idempotency_key': 'expense-invalid-operator',
        }
        with self.assertRaises(ExpenseActionError) as raised:
            record_expense(
                **invalid_operator_payload,
            )
        self.assertEqual(raised.exception.code, 'invalid_operator')

        first = record_expense(**{
            **common,
            'fund_account_id': str(self.cny.pk),
            'idempotency_key': 'expense-string-account-id',
        })
        replay = record_expense(**{
            **common,
            'idempotency_key': 'expense-string-account-id',
        })
        self.assertEqual(replay.pk, first.pk)

    def test_replay_survives_day1_operator_and_account_state_changes(self):
        from accounting.expense_actions import record_expense

        kwargs = {
            'category': Expense.Category.SALARY,
            'amount': '10.00',
            'fund_account_id': self.cny.pk,
            'business_date': date(2026, 9, 1),
            'operator': self.operator,
            'idempotency_key': 'expense-replay-state-changes',
        }
        first = record_expense(**kwargs)
        self.operator.is_active = False
        self.operator.save(update_fields=['is_active'])
        self.cny.is_active = False
        self.cny.save(update_fields=['is_active'])
        Day1Initialization.objects.all().delete()

        replay = record_expense(**kwargs)
        self.assertEqual(replay.pk, first.pk)
        self.assertEqual(replay.business_date, date(2026, 9, 1))

    def test_new_write_rejects_inactive_and_non_operator_users(self):
        from accounting.expense_actions import ExpenseActionError, record_expense

        inactive = User.objects.create_user(
            username='inactive-expense-operator', is_staff=True, is_active=False,
        )
        non_operator = User.objects.create_user(
            username='non-operator-expense-user', is_staff=False,
        )
        for operator, key in (
            (inactive, 'expense-inactive-operator'),
            (non_operator, 'expense-non-operator'),
        ):
            with self.subTest(operator=operator.username):
                with self.assertRaises(ExpenseActionError) as raised:
                    record_expense(
                        category=Expense.Category.SALARY,
                        amount='10.00',
                        fund_account_id=self.cny.pk,
                        business_date=self.business_date,
                        operator=operator,
                        idempotency_key=key,
                    )
                self.assertEqual(raised.exception.code, 'invalid_operator')

    def test_expense_postings_never_use_transport_expense(self):
        from accounting.expense_actions import record_expense

        for index, (category, account) in enumerate((
            (Expense.Category.SALARY, self.cny),
            (Expense.Category.RENT, self.rub),
            (Expense.Category.UTILITIES, self.rub),
            (Expense.Category.OTHER, self.rub),
        )):
            with self.subTest(category=category):
                expense = record_expense(
                    category=category,
                    amount='1.00',
                    fund_account_id=account.pk,
                    business_date=self.business_date,
                    operator=self.operator,
                    idempotency_key=f'expense-transport-isolation-{index}',
                )
                self.assertNotIn(
                    LedgerPosting.Category.TRANSPORT_EXPENSE,
                    expense.ledger_transaction.postings.values_list(
                        'category', flat=True,
                    ),
                )

    def test_transport_human_expense_posts_separate_transport_settlement(self):
        from accounting.expense_actions import record_expense

        expense = record_expense(
            category=Expense.Category.TRANSPORT,
            subcategory=Expense.Subcategory.TRANSPORT_HUMAN,
            amount='120.00',
            fund_account_id=self.cny.pk,
            business_date=self.business_date,
            operator=self.operator,
            idempotency_key='expense-transport-human-1',
        )

        self.assertEqual(expense.subcategory, Expense.Subcategory.TRANSPORT_HUMAN)
        self.assertEqual(
            expense.ledger_transaction.postings.get(account__isnull=True).category,
            LedgerPosting.Category.TRANSPORT_SETTLEMENT_EXPENSE,
        )
        self.assertEqual(
            monthly_profit(month=self.business_date)['transport_settlement_expense_cny'],
            Decimal('120.00'),
        )

    def test_expense_reversal_posts_opposite_fact_and_is_idempotent(self):
        from accounting.expense_actions import reverse_expense, record_expense

        expense = record_expense(
            category=Expense.Category.SALARY,
            amount='10.00',
            fund_account_id=self.cny.pk,
            business_date=self.business_date,
            operator=self.operator,
            idempotency_key='expense-reversal-original',
        )
        reversal = reverse_expense(
            expense_id=expense.pk,
            business_date=date(2026, 8, 15),
            operator=self.operator,
            idempotency_key='expense-reversal-action',
            reason='重复录入',
        )
        expense.refresh_from_db()
        original = expense.ledger_transaction
        self.assertIsNotNone(original.reversed_by_id)
        self.assertEqual(reversal.pk, expense.pk)
        reversal_tx = LedgerTransaction.objects.get(pk=original.reversed_by_id)
        self.assertEqual(reversal_tx.status, LedgerTransaction.Status.POSTED)
        self.assertEqual(
            list(reversal_tx.postings.order_by('id').values_list('amount', 'cny_amount')),
            [(Decimal('10.00'), Decimal('10.00')), (Decimal('-10.00'), Decimal('-10.00'))],
        )
        reverse_expense(
            expense_id=expense.pk,
            business_date=date(2026, 8, 15),
            operator=self.operator,
            idempotency_key='expense-reversal-action',
            reason='重复录入',
        )
        self.assertEqual(
            LedgerTransaction.objects.filter(source_type='ledger_reversal').count(), 1,
        )

    def test_expense_reversal_rejects_second_reversal_and_missing_reason(self):
        from accounting.expense_actions import ExpenseActionError, reverse_expense, record_expense

        expense = record_expense(
            category=Expense.Category.SALARY,
            amount='10.00',
            fund_account_id=self.cny.pk,
            business_date=self.business_date,
            operator=self.operator,
            idempotency_key='expense-reversal-guard-original',
        )
        with self.assertRaises(ExpenseActionError) as missing:
            reverse_expense(
                expense_id=expense.pk, business_date=self.business_date,
                operator=self.operator, idempotency_key='expense-reversal-no-reason',
            )
        self.assertEqual(missing.exception.code, 'reason_required')
        reverse_expense(
            expense_id=expense.pk, business_date=self.business_date,
            operator=self.operator, idempotency_key='expense-reversal-guard-action',
            reason='录入错误',
        )
        with self.assertRaises(ExpenseActionError) as duplicate:
            reverse_expense(
                expense_id=expense.pk, business_date=self.business_date,
                operator=self.operator, idempotency_key='expense-reversal-other-action',
                reason='再次撤回',
            )
        self.assertEqual(duplicate.exception.code, 'already_reversed')

    def test_rub_historical_backfill_requires_replay(self):
        from accounting.expense_actions import ExpenseActionError, record_expense

        exchange_to_rub(
            self.cny,
            self.rub,
            '100.00',
            '1200.00',
            date(2026, 8, 14),
            self.operator,
            'expense-historical-later-exchange',
        )
        with self.assertRaises(ExpenseActionError) as raised:
            record_expense(
                category=Expense.Category.RENT,
                amount='10.00',
                fund_account_id=self.rub.pk,
                business_date=date(2026, 8, 11),
                operator=self.operator,
                idempotency_key='expense-historical-backfill',
            )
        self.assertEqual(raised.exception.code, 'historical_replay_required')
        self.assertFalse(
            Expense.objects.filter(
                idempotency_key='expense-historical-backfill',
            ).exists()
        )
        self.assertFalse(
            LedgerTransaction.objects.filter(
                idempotency_key='expense-historical-backfill',
            ).exists()
        )

    def test_replay_rejects_tampered_linked_ledger_metadata(self):
        from accounting.expense_actions import ExpenseActionError, record_expense

        kwargs = {
            'category': Expense.Category.SALARY,
            'amount': '10.00',
            'fund_account_id': self.cny.pk,
            'business_date': self.business_date,
            'operator': self.operator,
            'idempotency_key': 'expense-replay-tampered-ledger',
        }
        expense = record_expense(**kwargs)
        ledger = expense.ledger_transaction
        ledger.source_type = 'tampered'
        models.Model.save(ledger, update_fields=['source_type'])

        with self.assertRaises(ExpenseActionError) as raised:
            record_expense(**kwargs)
        self.assertEqual(raised.exception.code, 'idempotency_conflict')
