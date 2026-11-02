import json
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from decimal import Decimal
from threading import Barrier
from unittest.mock import patch

from django.db import close_old_connections, connection, models
from django.test import TestCase, TransactionTestCase

from accounting.business_time import moscow_business_date
from accounting.expense_actions import record_expense
from accounting.guards import Day1IncompleteError
from accounting.models import (
    Day1Initialization, FundAccount, LedgerMutationError, LedgerPosting,
    LedgerTransaction, OtherIncome, OtherIncomeReversal,
)
from accounting.monthly_reports import monthly_business_report
from accounting.other_income import record_other_income, reverse_other_income
from accounting.other_income_reads import income_period
from accounting.income_categories import CATALOG, SUBCATEGORIES
from accounting.selectors import account_snapshot, monthly_profit, retained_earnings
from accounting.services import (
    LedgerError, confirm_reconciliation, create_reconciliation, record_opening_balance,
    reverse_ledger_transaction,
)
from cigars.models import User


class IncomeFixture:
    def setUp(self):
        self.operator = User.objects.create_user('income-operator', is_staff=True)
        self.outsider = User.objects.create_user('income-outsider')
        self.day1 = Day1Initialization.objects.create(status='completed', business_date=date(2026, 8, 10), completed_by=self.operator)
        self.cny = FundAccount.objects.create(name='人民币', currency='CNY', creation_idempotency_key='income-cny')
        self.rub = FundAccount.objects.create(name='卢布', currency='RUB', creation_idempotency_key='income-rub')

    def income(self, **overrides):
        category = overrides.get('category', 'interest')
        subcategory = {'interest': 'bank_interest', 'used_item': 'used_item_sale', 'other': 'other_gain'}.get(category, '') if isinstance(category, str) else ''
        return record_other_income(**{
            'category': 'interest', 'fund_account_id': self.rub.pk, 'amount': '11000.00',
            'subcategory': subcategory, 'recognition_confirmed': category == 'other',
            'exchange_rate': '11', 'rate_source': '业务日银行报价', 'business_date': date(2026, 8, 12),
            'operator': self.operator, 'idempotency_key': 'income', 'note': '公司存款利息',
            'agent_source': 'test:income', **overrides,
        })

    def cny_income(self, **overrides):
        return self.income(**{'fund_account_id': self.cny.pk, 'exchange_rate': None, 'rate_source': '', **overrides})

    def reverse(self, income, **overrides):
        return reverse_other_income(**{
            'income_id': income.pk, 'business_date': date(2026, 9, 2), 'operator': self.operator,
            'idempotency_key': 'reverse-income', 'note': '录错，冲正', 'agent_source': 'test:reverse', **overrides,
        })

    def reconcile(self, account, business_date):
        reconciliation = create_reconciliation(
            account=account, business_date=business_date,
            actual_amount=account_snapshot(account, business_date).original_balance,
            operator=self.operator, idempotency_key='reconcile',
        )
        confirm_reconciliation(reconciliation_id=reconciliation.pk, operator=self.operator, idempotency_key='confirm-reconcile')


class OtherIncomeTests(IncomeFixture, TestCase):
    def test_every_enabled_subcategory_posts_and_reverses_with_two_level_labels(self):
        enabled = [item for group in CATALOG for item in group['items'] if item['manual_entry_enabled']]
        self.assertEqual(len(SUBCATEGORIES), sum(len(group['items']) for group in CATALOG))
        for item in enabled:
            with self.subTest(subcategory=item['value']):
                income, _ = self.cny_income(category=item['category'], subcategory=item['value'],
                    recognition_confirmed=item['requires_recognition'], zero_book_value_confirmed=item['category'] == 'used_item',
                    idempotency_key=item['value'], amount='10')
                row = next(row for row in income_period()['incomes'] if row['id'] == income.id)
                self.assertEqual(row['subcategory_label'], item['label'])
                self.assertEqual(row['income_group'], SUBCATEGORIES[item['value']][0]['value'])
                self.reverse(income, idempotency_key=f'reverse-{item["value"]}')
                reversed_row = income_period(start=date(2026, 9, 1))['reversals'][0]
                self.assertEqual(reversed_row['subcategory_label'], item['label'])
        self.assertEqual(retained_earnings(as_of=date(2026, 9, 30)), 0)

    def test_invalid_blocked_or_unconfirmed_classification_never_posts(self):
        cases = [dict(subcategory=value) for value in ['', 'unknown', None, [], 'commission']]
        cases += [dict(category='other', subcategory=item['value'], recognition_confirmed=True)
                  for _, item in SUBCATEGORIES.values() if not item['manual_entry_enabled']]
        cases += [dict(category='other', subcategory='commission', recognition_confirmed=value)
                  for value in [False, 'true', 1]]
        cases += [dict(category='used_item', subcategory=code, zero_book_value_confirmed=False)
                  for code in ['scrap_sale', 'packaging_sale']]
        for index, changes in enumerate(cases):
            with self.subTest(changes=changes), self.assertRaises(LedgerError):
                self.cny_income(**changes, idempotency_key=f'invalid-{index}')
        self.assertEqual(OtherIncome.objects.count(), 0)
        self.assertEqual(LedgerTransaction.objects.count(), 0)

    def test_subcategory_and_recognition_are_part_of_replay_identity(self):
        income, _ = self.cny_income(category='other', subcategory='commission', recognition_confirmed=True)
        again, created = self.cny_income(category='other', subcategory='commission', recognition_confirmed=True)
        self.assertEqual(income.id, again.id)
        self.assertFalse(created)
        for changes in [dict(subcategory='promotion'), dict(recognition_confirmed=False)]:
            with self.assertRaises(LedgerError):
                self.cny_income(category='other', **{'subcategory': 'commission', 'recognition_confirmed': True, **changes})
        facts = monthly_profit(month=date(2026, 8, 1))
        self.assertEqual(facts['other_income_breakdown']['other_cny'], Decimal('11000'))
        self.assertEqual(facts['other_income_breakdown']['interest_cny'], 0)

    def test_investment_interest_is_not_bank_interest_and_classification_is_immutable(self):
        income, _ = self.cny_income(category='other', subcategory='investment_interest', recognition_confirmed=True)
        facts = monthly_profit(month=date(2026, 8, 1))
        self.assertEqual(facts['other_income_breakdown']['interest_cny'], 0)
        self.assertEqual(facts['other_income_breakdown']['other_cny'], Decimal('11000'))
        for changes in [dict(subcategory='investment_dividend'), dict(recognition_confirmed=False)]:
            with self.assertRaises(LedgerMutationError):
                OtherIncome.objects.filter(pk=income.pk).update(**changes)

    def test_legacy_committed_request_replays_without_reclassifying_but_new_legacy_rejected(self):
        income, _ = self.cny_income()
        # Simulate an immutable fact created under migration 0022, before this field existed.
        with connection.cursor() as cursor:
            cursor.execute('UPDATE accounting_otherincome SET subcategory = %s WHERE id = %s', ['', income.pk])
        again, created = self.cny_income(subcategory='')
        self.assertFalse(created)
        self.assertEqual(again.id, income.id)
        self.assertEqual(again.subcategory, '')
        self.assertIn('历史未细分', income_period()['incomes'][0]['subcategory_label'])
        with self.assertRaises(LedgerError):
            self.cny_income(subcategory='', idempotency_key='uncommitted-legacy')
        self.reverse(again)
        self.assertEqual(OtherIncomeReversal.objects.count(), 1)

    def test_reversal_date_and_key_conflicts_leave_income_unchanged(self):
        income, _ = self.income()
        for changes in [
            {'business_date': date(2026, 8, 11)},
            {'business_date': moscow_business_date() + timedelta(days=1)},
            {'note': ' '}, {'idempotency_key': income.idempotency_key},
        ]:
            with self.subTest(changes=changes), self.assertRaises(LedgerError):
                self.reverse(income, **changes)
        self.assertEqual(OtherIncomeReversal.objects.count(), 0)
        self.assertEqual(account_snapshot(self.rub).original_balance, 11000)

    def test_period_totals_include_all_pages_and_cross_month_reversals(self):
        for index in range(3):
            self.cny_income(amount='10.00', idempotency_key=f'income-{index}')
        last = OtherIncome.objects.first()
        self.reverse(last)
        august = income_period(start=date(2026, 8, 1), end=date(2026, 9, 1), limit=2)
        self.assertEqual(len(august['incomes']), 2)
        self.assertEqual(august['next_page'], 2)
        self.assertEqual(august['summary']['net_cny'], '30.00')
        september = income_period(start=date(2026, 9, 1), end=date(2026, 10, 1), limit=2)
        self.assertEqual(september['count'], 0)
        self.assertEqual(september['reversal_count'], 1)
        self.assertEqual(september['summary']['net_cny'], '-10.00')

    def test_rub_income_revalues_average_cost_and_next_expense_uses_it(self):
        record_opening_balance(self.rub, Decimal('10000'), Decimal('1000'), 'opening_capital', date(2026, 8, 10), self.operator, 'opening')
        income, created = self.income()
        self.assertTrue(created)
        self.assertEqual(income.amount_cny, Decimal('1000'))
        snapshot = account_snapshot(self.rub)
        self.assertEqual((snapshot.original_balance, snapshot.cny_book_cost), (Decimal('21000'), Decimal('2000')))
        self.assertEqual(account_snapshot(self.cny).original_balance, 0)
        self.assertFalse(LedgerTransaction.objects.filter(transaction_type='exchange').exists())
        expense = record_expense(category='rent', amount='10500', fund_account_id=self.rub.pk,
                                 business_date=date(2026, 8, 13), operator=self.operator, idempotency_key='rent')
        self.assertEqual(expense.amount_cny, Decimal('1000'))
        self.assertEqual(account_snapshot(self.rub).cny_book_cost, Decimal('1000'))
        report = monthly_business_report(month=date(2026, 8, 1))
        self.assertEqual(report['profit']['sales_revenue_cny'], 0)
        self.assertEqual(report['profit']['sales_profit_cny'], 0)
        self.assertEqual(report['profit']['core_operating_profit_cny'], -1000)
        self.assertEqual(report['profit']['other_income_cny'], 1000)
        self.assertEqual(report['profit']['other_income_breakdown']['interest_cny'], 1000)
        self.assertEqual(report['profit']['net_operating_profit_cny'], 0)
        self.assertEqual(monthly_profit(month=date(2026, 8, 1))['net_profit_cny'], 0)
        self.assertEqual(retained_earnings(as_of=date(2026, 8, 31)), 0)

    def test_cny_categories_and_old_item_confirmation(self):
        for category in ['interest', 'used_item', 'other']:
            self.cny_income(category=category, idempotency_key=category, amount='100.01',
                            zero_book_value_confirmed=category == 'used_item')
        facts = monthly_profit(month=date(2026, 8, 1))
        self.assertEqual(facts['net_profit_cny'], Decimal('300.03'))
        self.assertEqual(facts['interest_expense_cny'], 0)
        self.assertEqual(facts['other_income_breakdown'], dict(interest_cny=Decimal('100.01'), used_item_cny=Decimal('100.01'), other_cny=Decimal('100.01')))
        self.assertEqual(retained_earnings(as_of=date(2026, 8, 31)), Decimal('300.03'))

    def test_half_up_rounding_and_empty_rub_account(self):
        income, _ = self.income(amount='1', exchange_rate='8')
        self.assertEqual(income.amount_cny, Decimal('0.13'))
        self.assertEqual(account_snapshot(self.rub).cny_book_cost, Decimal('0.13'))

    def test_cross_month_reversal_uses_original_cost_and_preserves_history(self):
        income, _ = self.income()
        reversal, created = self.reverse(income)
        self.assertTrue(created)
        self.assertEqual(self.reverse(income)[0].pk, reversal.pk)
        self.assertFalse(self.reverse(income)[1])
        self.assertEqual(account_snapshot(self.rub).original_balance, 0)
        self.assertEqual(account_snapshot(self.rub).cny_book_cost, 0)
        self.assertEqual(monthly_profit(month=date(2026, 8, 1))['net_profit_cny'], 1000)
        self.assertEqual(monthly_profit(month=date(2026, 9, 1))['net_profit_cny'], -1000)
        self.assertEqual(monthly_business_report(month=date(2026, 9, 1))['profit']['net_operating_profit_cny'], -1000)
        self.assertEqual(retained_earnings(as_of=date(2026, 9, 30)), 0)
        august = income_period(start=date(2026, 8, 1), end=date(2026, 9, 1))
        september = income_period(start=date(2026, 9, 1), end=date(2026, 10, 1))
        self.assertEqual(august['summary']['net_cny'], '1000.00')
        self.assertEqual(august['incomes'][0]['status'], 'reversed')
        self.assertEqual(september['summary']['net_cny'], '-1000.00')
        self.assertEqual(september['reversals'][0]['agent_source'], 'test:reverse')
        with self.assertRaises(LedgerError):
            self.income()
        for changes in [{'idempotency_key': 'new'}, {'note': 'new'}, {'business_date': date(2026, 9, 3)},
                        {'agent_source': 'new'}, {'operator': self.outsider}]:
            with self.subTest(changes=changes), self.assertRaises(LedgerError):
                self.reverse(income, **changes)

    def test_replay_compares_all_fields_and_survives_account_deactivation(self):
        income, _ = self.income()
        self.rub.is_active = False
        self.rub.save(update_fields=['is_active'])
        self.assertEqual(self.income()[0].pk, income.pk)
        self.assertFalse(self.income()[1])
        for changes in [{'amount': '1'}, {'exchange_rate': '12'}, {'rate_source': 'different'},
                        {'reference': 'different'}, {'note': 'different'}, {'category': 'other'},
                        {'business_date': date(2026, 8, 13)}, {'operator': self.outsider}, {'agent_source': 'different'}]:
            with self.subTest(changes=changes), self.assertRaises(LedgerError) as caught:
                self.income(**changes)
            self.assertEqual(caught.exception.code, 'idempotency_conflict')
        with self.assertRaises(LedgerError):
            self.income(idempotency_key='new')
        self.reverse(income)  # 误记收入在账户停用后仍能安全冲正。

    def test_invalid_requests_leave_no_postings(self):
        usdt = FundAccount.objects.create(name='USDT', currency='USDT', creation_idempotency_key='usdt')
        cases = [{'amount': value} for value in ['0', '-1', 'NaN', 'Infinity', '0.001', '1000000000000', True, {}, '1e9999']]
        cases += [{'exchange_rate': value} for value in [None, '0', '-1', 'NaN', 'Infinity', '1.000000001', '10000000000', True]]
        cases += [{'amount': '0.01', 'exchange_rate': '100'}, {'amount': '999999999999', 'exchange_rate': '0.00000001'},
                  {'category': 'used_item'}, {'zero_book_value_confirmed': 'true'}, {'zero_book_value_confirmed': True},
                  {'category': []}, {'category': 'sales'}, {'rate_source': ''}, {'rate_source': ' '},
                  {'fund_account_id': usdt.pk}, {'fund_account_id': True}, {'fund_account_id': 999999},
                  {'business_date': date(2026, 8, 9)}, {'business_date': moscow_business_date() + timedelta(days=1)},
                  {'reference': []}, {'agent_source': []}, {'note': ' '}, {'note': 'x' * 2001},
                  {'operator': self.outsider}, {'idempotency_key': ' '}]
        for changes in cases:
            with self.subTest(changes=changes), self.assertRaises(LedgerError):
                self.income(**changes)
        with self.assertRaises(LedgerError):
            self.cny_income(exchange_rate='11')
        self.day1.delete()
        with self.assertRaises(Day1IncompleteError):
            self.income()
        self.assertEqual(OtherIncome.objects.count(), 0)
        self.assertEqual(LedgerTransaction.objects.count(), 0)

    def test_historical_rub_block_cny_backfill_and_later_activity_reversal_block(self):
        income, _ = self.income()
        self.income(idempotency_key='later', business_date=date(2026, 8, 14))
        with self.assertRaises(LedgerError) as caught:
            self.income(idempotency_key='backfill', business_date=date(2026, 8, 13))
        self.assertEqual(caught.exception.code, 'historical_replay_required')
        with self.assertRaises(LedgerError) as caught:
            self.reverse(income)
        self.assertEqual(caught.exception.code, 'income_has_later_activity')
        self.cny_income(idempotency_key='cny-later', business_date=date(2026, 8, 14))
        self.cny_income(idempotency_key='cny-backfill', business_date=date(2026, 8, 13))
        self.assertEqual(account_snapshot(self.cny).original_balance, 22000)

    def test_reconciled_period_blocks_new_income_and_later_dated_reversal(self):
        income, _ = self.income()
        self.reconcile(self.rub, date(2026, 8, 13))
        with self.assertRaises(LedgerError) as caught:
            self.income(idempotency_key='backfill')
        self.assertEqual(caught.exception.code, 'income_reconciled_period')
        with self.assertRaises(LedgerError) as caught:
            self.reverse(income)
        self.assertEqual(caught.exception.code, 'income_reconciled_period')
        self.assertEqual(self.income()[0].pk, income.pk)
        self.income(idempotency_key='after-reconcile', business_date=date(2026, 8, 14))

    def test_atomic_rollback_model_immutability_and_generic_reversal_block(self):
        with patch.object(OtherIncome, 'save', side_effect=RuntimeError('fail')):
            with self.assertRaises(RuntimeError):
                self.income()
        self.assertEqual(LedgerTransaction.objects.count(), 0)
        income, _ = self.income()
        with patch.object(OtherIncomeReversal, 'save', side_effect=RuntimeError('fail')):
            with self.assertRaises(RuntimeError):
                self.reverse(income)
        income.ledger_transaction.refresh_from_db()
        self.assertIsNone(income.ledger_transaction.reversed_by_id)
        self.assertEqual(LedgerTransaction.objects.count(), 1)
        with self.assertRaises(LedgerError):
            reverse_ledger_transaction(original_transaction=income.ledger_transaction, business_date=date(2026, 9, 2),
                                       operator=self.operator, idempotency_key='generic', reason='错误')
        reversal, _ = self.reverse(income)
        for fact in [income, reversal]:
            model = type(fact)
            for operation in [lambda: fact.save(), lambda: fact.delete(), lambda: model.objects.all().delete(),
                              lambda: model.objects.filter(pk=fact.pk).update(note='bad'),
                              lambda: model.objects.bulk_update([fact], ['note']),
                              lambda: model.objects.bulk_create([fact]),
                              lambda: model.objects.get_or_create(pk=fact.pk)]:
                with self.subTest(model=model, operation=operation), self.assertRaises(LedgerMutationError):
                    operation()

    def test_damaged_ledger_replay_and_reversal_are_rejected(self):
        income, _ = self.income()
        models.QuerySet.update(LedgerPosting.objects.filter(transaction=income.ledger_transaction, account=self.rub), amount=Decimal('1'))
        with self.assertRaises(LedgerError):
            self.income()
        with self.assertRaises(LedgerError):
            self.reverse(income)
        self.assertEqual(OtherIncomeReversal.objects.count(), 0)

    def test_api_permissions_decimal_contract_details_and_pagination(self):
        path = '/api/accounting/other-incomes/'
        payload = dict(category='interest', subcategory='bank_interest', fund_account_id=self.rub.pk, amount='11000', exchange_rate='11',
                       rate_source='银行报价', business_date='2026-08-12', note='到账')
        def post(data=None, key='api'):
            return self.client.post(path, json.dumps(payload if data is None else data), content_type='application/json', HTTP_IDEMPOTENCY_KEY=key)
        self.assertEqual(post().status_code, 403)
        self.client.force_login(self.outsider)
        self.assertEqual(post().status_code, 403)
        self.client.force_login(self.operator)
        response = post()
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()['income']['amount_cny'], '1000.00')
        income_id = response.json()['income']['id']
        self.assertEqual(post().status_code, 200)
        self.assertEqual(post({**payload, 'amount': '1'}).status_code, 409)
        for change in [{'amount': 12}, {'exchange_rate': 11}, {'amount': None}]:
            self.assertEqual(post({**payload, **change}, key='numeric').status_code, 400)
        self.assertEqual(post(key='').status_code, 400)
        self.assertEqual(self.client.patch(path).status_code, 405)
        self.assertEqual(self.client.get(path, {'page': '0'}).status_code, 400)
        self.assertEqual(self.client.get(path, {'month': 'bad'}).status_code, 400)
        self.assertEqual(self.client.get(f'{path}{income_id}/').status_code, 200)
        self.assertEqual(self.client.get(f'{path}999999/').status_code, 404)
        for index in range(20):
            self.cny_income(idempotency_key=f'page-{index}', amount='1')
        first = self.client.get(path, {'month': '2026-08'}).json()
        second = self.client.get(path, {'month': '2026-08', 'page': '2'}).json()
        self.assertEqual(len(first['incomes']), 20)
        self.assertEqual(len(second['incomes']), 1)
        self.assertEqual(first['summary'], second['summary'])
        self.assertEqual(first['summary']['net_cny'], '1020.00')
        reversal_payload = dict(business_date='2026-09-02', note='冲正', agent_source='api:test')
        response = self.client.post(f'{path}{income_id}/reverse/', json.dumps(reversal_payload), content_type='application/json', HTTP_IDEMPOTENCY_KEY='api-reverse')
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()['income']['status'], 'reversed')
        self.assertEqual(self.client.get(path, {'month': '2026-09'}).json()['summary']['net_cny'], '-1000.00')


class OtherIncomeConcurrencyTests(IncomeFixture, TransactionTestCase):
    def test_simultaneous_reversals_create_one_fact(self):
        income, _ = self.income()
        barrier = Barrier(2)
        def worker(_):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return self.reverse(income)[0].pk
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            ids = list(pool.map(worker, range(2)))
        self.assertEqual(ids[0], ids[1])
        self.assertEqual(OtherIncomeReversal.objects.count(), 1)
        self.assertEqual(account_snapshot(self.rub).original_balance, 0)

    def test_simultaneous_duplicate_and_distinct_receipts(self):
        def run(keys):
            barrier = Barrier(2)
            def worker(key):
                close_old_connections()
                try:
                    barrier.wait(timeout=10)
                    return self.income(idempotency_key=key)[0].pk
                finally:
                    close_old_connections()
            with ThreadPoolExecutor(max_workers=2) as pool:
                return list(pool.map(worker, keys))
        ids = run(['shared', 'shared'])
        self.assertEqual(ids[0], ids[1])
        run(['a', 'b'])
        self.assertEqual(OtherIncome.objects.count(), 3)
        self.assertEqual(account_snapshot(self.rub).original_balance, 33000)
        self.assertEqual(account_snapshot(self.rub).cny_book_cost, 3000)
