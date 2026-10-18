import json
import threading
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.db import models, close_old_connections
from django.test import TestCase, TransactionTestCase

from accounting.expense_actions import ExpenseActionError, record_expense, refund_expense, reverse_expense
from accounting.expense_reads import expense_period
from accounting.models import Day1Initialization, ExpenseRefund, FundAccount, LedgerMutationError, LedgerPosting, LedgerTransaction
from accounting.monthly_reports import _profit_facts, monthly_business_report
from accounting.selectors import account_snapshot, monthly_profit
from accounting.services import LedgerError, record_opening_balance, reverse_ledger_transaction
from cigars.models import User


class ExpenseRefundTests(TestCase):
    def setUp(self):
        self.operator = User.objects.create_user('refund-operator', is_staff=True)
        Day1Initialization.objects.create(singleton_key='company', status='completed', business_date=date(2026, 8, 10), completed_by=self.operator)
        self.cny = self.account('CNY', 'source', '20000', '20000')
        self.target = self.account('CNY', 'target', '0', '0')
        self.rub = self.account('RUB', 'rub', '300', '100')
        self.expense = record_expense(category='salary', subcategory='personnel_salary', amount='15000', fund_account_id=self.cny.pk, business_date=date(2026, 8, 12), operator=self.operator, idempotency_key='salary', note='合伙人工资')

    def account(self, currency, name, amount, cost):
        account = FundAccount.objects.create(name=name, currency=currency, custodian=self.operator, creation_idempotency_key=name)
        if Decimal(amount):
            record_opening_balance(account, Decimal(amount), Decimal(cost), LedgerPosting.Category.OPENING_CAPITAL, date(2026, 8, 10), self.operator, f'opening-{name}')
        return account

    def refund(self, **overrides):
        payload = dict(expense_id=self.expense.pk, amount='3000', fund_account_id=self.target.pk, business_date=date(2026, 9, 12), operator=self.operator, idempotency_key='refund', note='退还多领工资', agent_source='test:refund-run')
        return refund_expense(**{**payload, **overrides})

    def test_later_activity_cross_month_and_different_account(self):
        record_expense(category='other', amount='20', fund_account_id=self.cny.pk, business_date=date(2026, 9, 20), operator=self.operator, idempotency_key='later')
        record_expense(category='other', amount='20', fund_account_id=self.cny.pk, business_date=date(2026, 8, 20), operator=self.operator, idempotency_key='between')
        refund = self.refund()
        self.assertEqual(refund.amount_cny, Decimal('3000'))
        self.assertEqual(account_snapshot(self.target).original_balance, Decimal('3000'))
        self.assertEqual(account_snapshot(self.cny).original_balance, Decimal('4960'))
        self.expense.refresh_from_db()
        self.assertEqual(self.expense.original_amount, Decimal('15000'))
        self.assertIsNone(self.expense.ledger_transaction.reversed_by_id)
        self.assertEqual(monthly_profit(month=date(2026, 8, 1))['salary_expense_cny'], Decimal('15000'))
        self.assertEqual(monthly_profit(month=date(2026, 9, 1))['salary_expense_cny'], Decimal('-3000'))
        rows = expense_period(start=date(2026, 9, 1), end=date(2026, 10, 1), limit=1)
        self.assertEqual(rows['refunds'][0]['expense_business_date'], '2026-08-12')
        self.assertEqual(rows['summary']['net_cny'], '-2980.00')

    def test_multiple_refunds_exact_cap_replay_and_original_reversal_guard(self):
        first = self.refund()
        self.refund(amount='12000', idempotency_key='rest')
        self.assertEqual(self.refund().pk, first.pk)
        with self.assertRaises(ExpenseActionError) as ctx:
            self.refund(amount='0.01', idempotency_key='over')
        self.assertEqual(ctx.exception.code, 'refund_exceeded')
        with self.assertRaises(ExpenseActionError) as ctx:
            reverse_expense(expense_id=self.expense.pk, business_date=date(2026, 9, 20), operator=self.operator, idempotency_key='reverse', reason='录错')
        self.assertEqual(ctx.exception.code, 'expense_has_refunds')
        with self.assertRaises(LedgerError) as ctx:
            reverse_ledger_transaction(original_transaction=self.expense.ledger_transaction, business_date=date(2026, 9, 20), operator=self.operator, idempotency_key='generic-reverse', reason='录错')
        self.assertEqual(ctx.exception.code, 'expense_has_refunds')
        with self.assertRaises(LedgerError):
            reverse_ledger_transaction(original_transaction=first.ledger_transaction, business_date=date(2026, 9, 20), operator=self.operator, idempotency_key='refund-reverse', reason='录错')

    def test_invalid_requests_leave_no_facts(self):
        for change, code in [
            ({'amount': '15000.01'}, 'refund_exceeded'), ({'amount': '0'}, 'invalid_amount'),
            ({'amount': '-1'}, 'invalid_amount'), ({'amount': 'NaN'}, 'invalid_amount'),
            ({'amount': '1.001'}, 'invalid_money_precision'), ({'amount': True}, 'invalid_amount'),
            ({'business_date': date(2026, 8, 11)}, 'invalid_business_date'),
            ({'fund_account_id': self.rub.pk}, 'refund_currency_mismatch'),
            ({'fund_account_id': 999999}, 'account_not_found'),
            ({'note': ' '}, 'reason_required'), ({'agent_source': []}, 'invalid_agent_source'),
        ]:
            with self.subTest(change=change), self.assertRaises(ExpenseActionError) as ctx:
                self.refund(**change)
            self.assertEqual(ctx.exception.code, code)
        self.assertEqual(ExpenseRefund.objects.count(), 0)
        self.assertFalse(LedgerTransaction.objects.filter(source_type='expense_refund').exists())

    def test_reversed_expense_rejected(self):
        reverse_expense(expense_id=self.expense.pk, business_date=date(2026, 8, 13), operator=self.operator, idempotency_key='reverse', reason='录错')
        with self.assertRaises(ExpenseActionError) as ctx:
            self.refund()
        self.assertEqual(ctx.exception.code, 'already_reversed')

    def test_replay_conflicts_and_deactivated_account(self):
        first = self.refund()
        for override in [{'amount': '1'}, {'note': '不同'}, {'agent_source': 'other'}, {'business_date': date(2026, 9, 13)}, {'fund_account_id': self.cny.pk}]:
            with self.subTest(override=override), self.assertRaises(ExpenseActionError) as ctx:
                self.refund(**override)
            self.assertEqual(ctx.exception.code, 'idempotency_conflict')
        self.target.is_active = False
        self.target.save(update_fields=['is_active'])
        self.assertEqual(self.refund().pk, first.pk)
        with self.assertRaises(ExpenseActionError) as ctx:
            self.refund(idempotency_key='new')
        self.assertEqual(ctx.exception.code, 'account_inactive')

    def test_replay_rejects_damaged_ledger_and_shared_keys(self):
        with self.assertRaises(ExpenseActionError) as ctx:
            self.refund(idempotency_key='salary')
        self.assertEqual(ctx.exception.code, 'idempotency_conflict')
        refund = self.refund()
        models.QuerySet.update(LedgerPosting.objects.filter(transaction=refund.ledger_transaction, account=self.target), amount=Decimal('42'))
        with self.assertRaises(ExpenseActionError) as ctx:
            self.refund()
        self.assertEqual(ctx.exception.code, 'idempotency_conflict')

    def test_atomic_rollback_and_immutable_fact(self):
        count = LedgerTransaction.objects.count()
        with patch.object(ExpenseRefund, 'save', side_effect=RuntimeError('failure')):
            with self.assertRaises(RuntimeError):
                self.refund()
        self.assertEqual(LedgerTransaction.objects.count(), count)
        self.assertEqual(account_snapshot(self.target).original_balance, Decimal('0'))
        refund = self.refund()
        for action in [lambda: refund.save(), lambda: refund.delete(),
                       lambda: ExpenseRefund.objects.filter(pk=refund.pk).update(note='x'),
                       lambda: ExpenseRefund.objects.all().delete(),
                       lambda: ExpenseRefund.objects.bulk_create([refund]),
                       lambda: ExpenseRefund.objects.bulk_update([refund], ['note']),
                       lambda: ExpenseRefund.objects.get_or_create(id=refund.pk)]:
            with self.assertRaises(LedgerMutationError):
                action()

    def test_rub_uses_original_cost_with_rounding_and_historical_guard(self):
        expense = record_expense(category='rent', amount='3', fund_account_id=self.rub.pk, business_date=date(2026, 8, 12), operator=self.operator, idempotency_key='rub-rent')
        costs = [self.refund(expense_id=expense.pk, amount='1', fund_account_id=self.rub.pk, idempotency_key=f'rub-refund-{i}').amount_cny for i in range(3)]
        self.assertEqual(costs, [Decimal('.33'), Decimal('.34'), Decimal('.33')])
        self.assertEqual(account_snapshot(self.rub).cny_book_cost, Decimal('100'))
        later = record_expense(category='rent', amount='3', fund_account_id=self.rub.pk, business_date=date(2026, 9, 20), operator=self.operator, idempotency_key='rub-later')
        with self.assertRaises(ExpenseActionError) as ctx:
            self.refund(expense_id=later.pk, amount='1', fund_account_id=self.rub.pk, idempotency_key='early', business_date=date(2026, 9, 19))
        self.assertEqual(ctx.exception.code, 'invalid_business_date')
        earlier = record_expense(category='rent', amount='3', fund_account_id=self.rub.pk, business_date=date(2026, 9, 20), operator=self.operator, idempotency_key='rub-earlier')
        record_expense(category='rent', amount='3', fund_account_id=self.rub.pk, business_date=date(2026, 9, 22), operator=self.operator, idempotency_key='rub-last')
        with self.assertRaises(ExpenseActionError) as ctx:
            self.refund(expense_id=earlier.pk, amount='1', fund_account_id=self.rub.pk, idempotency_key='historical', business_date=date(2026, 9, 21))
        self.assertEqual(ctx.exception.code, 'historical_replay_required')

    def test_transport_refunds_keep_subcategory_and_human_settlement(self):
        for category, subcategory, key in [('other', 'transport_taxi', 'taxi'), ('transport', 'transport_human', 'human')]:
            expense = record_expense(category=category, subcategory=subcategory, amount='30', fund_account_id=self.cny.pk, business_date=date(2026, 8, 14), operator=self.operator, idempotency_key=key)
            self.refund(expense_id=expense.pk, amount='10', idempotency_key=f'{key}-return')
        facts = _profit_facts(start=date(2026, 9, 1), end=date(2026, 9, 30))
        self.assertEqual(facts['operating_expense_breakdown']['transport_cny'], Decimal('-10'))
        self.assertEqual(facts['operating_expense_breakdown']['other_cny'], Decimal('0'))
        self.assertEqual(facts['human_cost_cny'], Decimal('-10'))

    def test_api_permissions_cross_month_detail_and_totals_not_limited(self):
        path = f'/api/accounting/expenses/{self.expense.pk}/refund/'
        payload = {'amount': '3000', 'fund_account_id': self.target.pk, 'business_date': '2026-09-12', 'note': '退还工资'}
        self.assertEqual(self.client.post(path, json.dumps(payload), content_type='application/json', HTTP_IDEMPOTENCY_KEY='api').status_code, 403)
        self.client.force_login(self.operator)
        response = self.client.post(path, json.dumps(payload), content_type='application/json', HTTP_IDEMPOTENCY_KEY='api')
        self.assertEqual(response.status_code, 201, response.content)
        self.refund(amount='2000', idempotency_key='api-second')
        rows = self.client.get('/api/accounting/expenses/?month=2026-09&limit=1').json()
        self.assertEqual(rows['expenses'], [])
        self.assertEqual(len(rows['refunds']), 1)
        self.assertEqual(rows['summary']['refunded_cny'], '5000.00')
        self.assertEqual(rows['next_page'], 2)
        detail = self.client.get(f'/api/accounting/expenses/{self.expense.pk}/').json()['expense']
        self.assertEqual(Decimal(detail['remaining_refundable_amount']), Decimal('10000'))
        self.assertEqual(len(detail['refunds']), 2)
        aug = self.client.get('/api/accounting/expenses/?month=2026-08').json()
        self.assertEqual(aug['summary']['net_cny'], '15000.00')
        for query in ['page=0', 'page=abc', 'limit=0', 'month=bad']:
            self.assertEqual(self.client.get(f'/api/accounting/expenses/?{query}').status_code, 400)

    def test_refund_only_month_never_describes_refund_as_highest_cost(self):
        self.refund()
        with patch('accounting.monthly_reports.moscow_business_date', return_value=date(2026, 10, 18)):
            report = monthly_business_report(month=date(2026, 9, 1))
        self.assertEqual(report['profit']['operating_expenses_cny'], Decimal('-3000'))
        self.assertEqual(report['profit']['net_operating_profit_cny'], Decimal('3000'))
        self.assertNotIn('largest_cost', [item['code'] for item in report['conclusions']])

    def test_inactive_and_nonstaff_operators_rejected(self):
        for fields in [{'is_active': False}, {'is_staff': False}]:
            operator = User.objects.create_user(f'bad-{len(fields)}-{User.objects.count()}', **fields)
            with self.assertRaises(ExpenseActionError) as ctx:
                self.refund(operator=operator)
            self.assertEqual(ctx.exception.code, 'invalid_operator')


class ExpenseRefundConcurrencyTests(TransactionTestCase):
    setUp = ExpenseRefundTests.setUp
    account = ExpenseRefundTests.account
    refund = ExpenseRefundTests.refund

    def parallel(self, operation):
        barrier = threading.Barrier(2)
        results, errors = [], []
        def worker(index):
            close_old_connections()
            try:
                operator = User.objects.get(pk=self.operator.pk)
                barrier.wait(timeout=10)
                results.append(operation(index, operator).pk)
            except Exception as error:
                errors.append(error)
            finally:
                close_old_connections()
        threads = [threading.Thread(target=worker, args=(i,)) for i in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=20)
        self.assertFalse(any(thread.is_alive() for thread in threads))
        return results, errors

    def test_concurrent_refunds_cannot_exceed_original(self):
        results, errors = self.parallel(lambda index, operator: self.refund(amount='10000', idempotency_key=f'parallel-{index}', operator=operator))
        self.assertEqual(len(results), 1)
        self.assertEqual([getattr(error, 'code', None) for error in errors], ['refund_exceeded'])
        self.assertEqual(account_snapshot(self.target).original_balance, Decimal('10000'))

    def test_concurrent_replay_posts_once(self):
        results, errors = self.parallel(lambda index, operator: self.refund(operator=operator))
        self.assertEqual(errors, [])
        self.assertEqual(len(set(results)), 1)
        self.assertEqual(ExpenseRefund.objects.count(), 1)

    def test_refund_and_generic_reversal_are_mutually_exclusive(self):
        def operation(index, operator):
            if index == 0:
                return self.refund(operator=operator)
            return reverse_ledger_transaction(original_transaction=self.expense.ledger_transaction, business_date=date(2026, 9, 12), operator=operator, idempotency_key='parallel-reverse', reason='录错')
        results, errors = self.parallel(operation)
        self.assertEqual(len(results), 1)
        self.assertEqual(len(errors), 1)
        self.assertIn(getattr(errors[0], 'code', None), ['already_reversed', 'expense_has_refunds'])
        self.expense.refresh_from_db()
        self.assertNotEqual(bool(self.expense.ledger_transaction.reversed_by_id), ExpenseRefund.objects.exists())
