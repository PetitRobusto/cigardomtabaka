import json
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.db import models
from django.test import TestCase, TransactionTestCase

from accounting.dividend_round_actions import record_paid_dividend, record_dividend_payout
from accounting.dividend_actions import DividendActionError
from accounting.models import DividendRound, DividendPayout, LedgerPosting, LedgerTransaction, FundAccount
from accounting.selectors import account_snapshot, retained_earnings, monthly_profit
from accounting.services import LedgerError, PostingInput, post_transaction
from accounting.tests.test_dividend_round_actions import DividendRoundTests, DividendRoundConcurrencyTests
from cigars.models import User


class PaidDividendTests(TestCase):
    day = DividendRoundTests.day
    setUp = DividendRoundTests.setUp

    def record(self, key='paid', **changes):
        return record_paid_dividend(operator=self.operator, idempotency_key=key,
                                    **{**self.body, 'fund_account_id': self.account.pk, **changes})

    def acknowledge(self, key='paid', **changes):
        with self.assertRaises(DividendActionError) as failure:
            self.record(key, **changes)
        self.assertEqual(failure.exception.code, 'warning_required')
        payload = {**changes, 'warning_ack': True,
                   'warning_fingerprint': failure.exception.details['warning_fingerprint']}
        return self.record(key, **payload), payload

    def add_profit(self):
        post_transaction(transaction_type='sales_shipment', business_date=self.day,
                         postings=[PostingInput(category='sales_revenue', currency='CNY', amount=Decimal('-200'), cny_amount=Decimal('-200')),
                                   PostingInput(category='accounts_receivable', currency='CNY', amount=Decimal('200'), cny_amount=Decimal('200'))],
                         operator=self.operator, idempotency_key='profit')

    def test_one_save_cash_retained_payable_and_profit(self):
        self.add_profit()
        before = account_snapshot(self.account)
        retained = retained_earnings(as_of=self.day)
        profit = monthly_profit(month=self.day)
        count = LedgerTransaction.objects.count()
        result = self.record()
        self.assertEqual(result.payouts.count(), 2)
        self.assertEqual(list(result.payouts.values_list('amount_cny', flat=True)), [Decimal('50.01')] * 2)
        self.assertEqual(account_snapshot(self.account).original_balance, before.original_balance - Decimal('100.02'))
        self.assertEqual(retained_earnings(as_of=self.day), retained - Decimal('100.02'))
        after_profit = monthly_profit(month=self.day)
        # 月报另含流水笔数；分红增加三笔流水，但不改变任何利润金额。
        self.assertEqual({k: v for k, v in after_profit.items() if k != 'transaction_count'},
                         {k: v for k, v in profit.items() if k != 'transaction_count'})
        self.assertEqual(sum(LedgerPosting.objects.filter(category='dividend_payable').values_list('cny_amount', flat=True)), 0)
        self.assertEqual(LedgerTransaction.objects.count(), count + 3)

    def test_warning_read_only_stale_and_request_binding(self):
        count = LedgerTransaction.objects.count()
        with self.assertRaises(DividendActionError) as failure:
            self.record()
        fingerprint = failure.exception.details['warning_fingerprint']
        self.assertEqual(LedgerTransaction.objects.count(), count)
        self.assertFalse(DividendRound.objects.exists())
        for change in [{'note': 'changed'}, {'business_date': date(2026, 9, 15)}, {'partner_a_id': self.b.pk, 'partner_b_id': self.a.pk}]:
            with self.subTest(change=change), self.assertRaisesRegex(DividendActionError, 'warning_stale'):
                self.record(warning_ack=True, warning_fingerprint=fingerprint, **change)
        self.add_profit()
        with self.assertRaisesRegex(DividendActionError, 'warning_stale'):
            self.record(warning_ack=True, warning_fingerprint=fingerprint)
        self.record()  # 利润足够后正常一次保存。

    def test_warning_bound_to_account_and_operator(self):
        other_account = FundAccount.objects.create(name='另一个人民币账户', currency='CNY', creation_idempotency_key='second')
        post_transaction(transaction_type='sales_receipt', business_date=self.day,
                         postings=[PostingInput(account=other_account, currency='CNY', amount=Decimal('200'), cny_amount=Decimal('200')),
                                   PostingInput(category='customer_prepayments', currency='CNY', amount=Decimal('-200'), cny_amount=Decimal('-200'))],
                         operator=self.operator, idempotency_key='fund-second')
        with self.assertRaises(DividendActionError) as failure:
            self.record()
        fingerprint = failure.exception.details['warning_fingerprint']
        with self.assertRaisesRegex(DividendActionError, 'warning_stale'):
            self.record(fund_account_id=other_account.pk, warning_ack=True, warning_fingerprint=fingerprint)
        other = User.objects.create_user(username='other-staff', is_staff=True)
        with self.assertRaisesRegex(DividendActionError, 'warning_stale'):
            record_paid_dividend(operator=other, idempotency_key='other-op', fund_account_id=self.account.pk,
                                 warning_ack=True, warning_fingerprint=fingerprint, **self.body)

    def test_legacy_command_root_key_conflict(self):
        DividendRoundTests.confirm(self, key='paid')
        with self.assertRaisesRegex(DividendActionError, 'idempotency_conflict'):
            self.record()
        self.assertFalse(DividendPayout.objects.exists())

    def test_second_payout_failure_rolls_everything_back(self):
        self.add_profit()
        count = LedgerTransaction.objects.count()
        before = account_snapshot(self.account)
        def fail_second(**kwargs):
            if kwargs['recipient_id'] == self.b.pk:
                raise LedgerError('second payout failed')
            return record_dividend_payout(**kwargs)
        with patch('accounting.dividend_round_actions.record_dividend_payout', side_effect=fail_second):
            with self.assertRaisesRegex(LedgerError, 'second payout'):
                self.record()
        self.assertFalse(DividendRound.objects.exists())
        self.assertFalse(DividendPayout.objects.exists())
        self.assertEqual(LedgerTransaction.objects.count(), count)
        self.assertEqual(account_snapshot(self.account), before)
        self.record()  # 回滚后原键可以正常重试。

    def test_invalid_inputs_and_insufficient_total_leave_no_facts(self):
        foreign = FundAccount.objects.create(name='卢布', currency='RUB', creation_idempotency_key='foreign')
        inactive = FundAccount.objects.create(name='停用', currency='CNY', is_active=False, creation_idempotency_key='inactive')
        cases = [({'total_cny': '100.01'}, 'uneven_split'), ({'total_cny': '1.001'}, 'invalid_money_precision'),
                 ({'total_cny': '0'}, 'invalid_amount'), ({'partner_a_id': self.b.pk}, 'recipient_same'),
                 ({'partner_a_id': 99999}, 'invalid_recipient'), ({'fund_account_id': 99999}, 'account_not_found'),
                 ({'fund_account_id': foreign.pk}, 'currency_rule'), ({'fund_account_id': inactive.pk}, 'account_inactive'),
                 ({'total_cny': '1500.00'}, 'insufficient_balance'), ({'warning_ack': 'true'}, 'warning_required')]
        for change, code in cases:
            with self.subTest(code=code), self.assertRaisesRegex(DividendActionError, code):
                self.record(**change)
        self.assertFalse(DividendRound.objects.exists())
        self.assertFalse(DividendPayout.objects.exists())

    def test_historical_second_outflow_insufficient_rolls_back(self):
        post_transaction(transaction_type='sales_receipt', business_date=date(2026, 9, 16),
                         postings=[PostingInput(account=self.account, currency='CNY', amount=Decimal('1000'), cny_amount=Decimal('1000')),
                                   PostingInput(category='customer_prepayments', currency='CNY', amount=Decimal('-1000'), cny_amount=Decimal('-1000'))],
                         operator=self.operator, idempotency_key='later-cash')
        with self.assertRaises(DividendActionError) as failure:
            self.record(total_cny='1500.00')
        count = LedgerTransaction.objects.count()
        with self.assertRaisesRegex(LedgerError, '历史余额'):
            self.record(total_cny='1500.00', warning_ack=True, warning_fingerprint=failure.exception.details['warning_fingerprint'])
        self.assertFalse(DividendRound.objects.exists())
        self.assertFalse(DividendPayout.objects.exists())
        self.assertEqual(LedgerTransaction.objects.count(), count)

    def test_exact_replay_after_disabled_entities_and_conflicts(self):
        result, payload = self.acknowledge()
        count = LedgerTransaction.objects.count()
        self.account.is_active = False
        self.account.save(update_fields=['is_active'])
        User.objects.filter(pk__in=[self.a.pk, self.b.pk, self.operator.pk]).update(is_active=False)
        self.assertEqual(self.record(**payload).pk, result.pk)
        self.assertEqual(LedgerTransaction.objects.count(), count)
        for change in [{'fund_account_id': 99999}, {'total_cny': '100.00'}, {'note': 'changed'}, {'warning_ack': False}]:
            with self.subTest(change=change), self.assertRaisesRegex(DividendActionError, 'idempotency_conflict'):
                self.record(**{**payload, **change})

    def test_missing_or_tampered_child_refused_without_repair(self):
        result, payload = self.acknowledge()
        child = result.payouts.first()
        models.QuerySet.update(DividendPayout.objects.filter(pk=child.pk), amount_cny=Decimal('1.00'))
        with self.assertRaisesRegex(DividendActionError, 'idempotency_conflict'):
            self.record(**payload)
        models.QuerySet.delete(DividendPayout.objects.filter(pk=child.pk))
        with self.assertRaisesRegex(DividendActionError, 'idempotency_conflict'):
            self.record(**payload)
        self.assertEqual(result.payouts.count(), 1)

    def test_api_permissions_record_month_filter_and_defaults(self):
        url = '/api/accounting/dividend-rounds/'
        body = {**self.body, 'business_date': self.day.isoformat(), 'fund_account_id': self.account.pk}
        def submit(key='api-paid', **changes):
            return self.client.post(url + 'record/', json.dumps({**body, **changes}), content_type='application/json', HTTP_IDEMPOTENCY_KEY=key)
        self.assertEqual(submit().status_code, 403)
        self.client.force_login(self.a)
        self.assertEqual(submit().status_code, 403)
        self.client.force_login(self.operator)
        self.assertEqual(self.client.get(url + 'record/').status_code, 405)
        warning = submit()
        self.assertEqual(warning.status_code, 409)
        response = submit(warning_ack=True, warning_fingerprint=warning.json()['details']['warning_fingerprint'])
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()['round']['pending_cny'], '0.00')
        listing = self.client.get(url, {'month': '2026-09'}).json()
        self.assertEqual(listing['count'], 1)
        self.assertEqual(listing['defaults'], {'partner_a_id': self.a.pk, 'partner_b_id': self.b.pk, 'fund_account_id': self.account.pk})
        self.assertEqual(self.client.get(url, {'month': '2026-10'}).json()['count'], 0)
        self.assertEqual(self.client.get(url, {'month': '2026-13'}).status_code, 400)
        self.assertEqual(self.client.get(url, {'month': '2026-9'}).status_code, 400)
        legacy_round = DividendRoundTests.confirm(self, key='september', total_cny='10.00')
        record_dividend_payout(round_id=legacy_round.pk, recipient_id=self.a.pk, fund_account_id=self.account.pk,
                              amount_cny='5.00', business_date=date(2026, 10, 1), operator=self.operator, idempotency_key='october')
        october = self.client.get(url, {'month': '2026-10'}).json()
        self.assertEqual([r['id'] for r in october['rounds']], [legacy_round.pk])


class PaidDividendConcurrencyTests(TransactionTestCase):
    day = DividendRoundTests.day
    setUp = DividendRoundTests.setUp
    parallel = DividendRoundConcurrencyTests.parallel

    def test_same_key_posts_once(self):
        body = {**self.body, 'fund_account_id': self.account.pk}
        with self.assertRaises(DividendActionError) as failure:
            record_paid_dividend(operator=self.operator, idempotency_key='parallel-paid', **body)
        results, errors = self.parallel(lambda index, operator: record_paid_dividend(
            operator=operator, idempotency_key='parallel-paid', warning_ack=True,
            warning_fingerprint=failure.exception.details['warning_fingerprint'], **body))
        self.assertEqual(errors, [])
        self.assertEqual(len(set(results)), 1)
        self.assertEqual(DividendRound.objects.count(), 1)
        self.assertEqual(DividendPayout.objects.count(), 2)

    def test_different_keys_cannot_overdraw_account(self):
        body = {**self.body, 'total_cny': '600.00', 'fund_account_id': self.account.pk}
        with self.assertRaises(DividendActionError) as failure:
            record_paid_dividend(operator=self.operator, idempotency_key='warning', **body)
        results, errors = self.parallel(lambda index, operator: record_paid_dividend(
            operator=operator, idempotency_key=f'paid-{index}', warning_ack=True,
            warning_fingerprint=failure.exception.details['warning_fingerprint'], **body))
        self.assertEqual(len(results), 1)
        self.assertEqual([getattr(e, 'code', None) for e in errors], ['insufficient_balance'])
        self.assertEqual(DividendRound.objects.count(), 1)
        self.assertEqual(DividendPayout.objects.count(), 2)
        self.assertEqual(account_snapshot(self.account).original_balance, Decimal('400.00'))
