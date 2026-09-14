import json
import threading
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.db import models, close_old_connections
from django.test import TestCase, TransactionTestCase

from accounting.dividend_actions import DividendActionError
from accounting.dividend_round_actions import (
    confirm_dividend_round, preview_dividend_round, record_dividend_payout,
)
from accounting.models import (
    Day1Initialization, DividendRound, DividendPayout, FundAccount,
    LedgerMutationError, LedgerPosting, LedgerTransaction,
)
from accounting.mutation_scope import ledger_mutation_scope
from accounting.selectors import account_snapshot, monthly_profit, retained_earnings
from accounting.services import LedgerError, PostingInput, post_transaction, record_opening_balance
from cigars.models import User


class DividendRoundTests(TestCase):
    day = date(2026, 9, 14)

    def setUp(self):
        self.operator = User.objects.create_user(username='round-op', is_staff=True)
        self.a = User.objects.create_user(username='round-a')
        self.b = User.objects.create_user(username='round-b')
        Day1Initialization.objects.create(singleton_key='company', status='completed',
                                         business_date=date(2026, 9, 1), completed_by=self.operator)
        self.account = FundAccount.objects.create(name='公司人民币', currency='CNY', creation_idempotency_key='round-account')
        record_opening_balance(self.account, Decimal('1000.00'), Decimal('1000.00'),
                               LedgerPosting.Category.OPENING_CAPITAL, date(2026, 8, 10), self.operator, 'round-opening')
        self.body = dict(total_cny='100.02', partner_a_id=self.a.pk, partner_b_id=self.b.pk,
                         business_date=self.day, note='分配', agent_source='test:round')

    def confirm(self, key='round-confirm', **changes):
        body = {**self.body, **changes}
        preview = preview_dividend_round(operator=self.operator, **body)
        return confirm_dividend_round(operator=self.operator, idempotency_key=key,
                                      warning_fingerprint=preview['warning_fingerprint'], warning_ack=True, **body)

    def payout(self, round, key='round-payout', **changes):
        body = dict(round_id=round.pk, recipient_id=self.a.pk, fund_account_id=self.account.pk,
                    amount_cny='10.00', business_date=self.day, note='领取', agent_source='test:payout')
        return record_dividend_payout(operator=self.operator, idempotency_key=key, **{**body, **changes})

    def test_preview_read_only_precision_and_recipients(self):
        count = LedgerTransaction.objects.count()
        preview_dividend_round(operator=self.operator, **self.body)
        self.assertEqual(LedgerTransaction.objects.count(), count)
        self.assertFalse(DividendRound.objects.exists())
        for changes, code in [({'total_cny': '100.01'}, 'uneven_split'),
                              ({'total_cny': '1.001'}, 'invalid_money_precision'),
                              ({'total_cny': '0'}, 'invalid_amount'),
                              ({'total_cny': float('nan')}, 'invalid_amount'),
                              ({'partner_b_id': self.a.pk}, 'recipient_same'),
                              ({'partner_b_id': 99999}, 'invalid_recipient')]:
            with self.subTest(changes=changes), self.assertRaisesRegex(DividendActionError, code):
                preview_dividend_round(operator=self.operator, **{**self.body, **changes})
        self.b.is_active = False
        self.b.save(update_fields=['is_active'])
        with self.assertRaisesRegex(DividendActionError, 'invalid_recipient'):
            self.confirm()

    def test_distribution_cash_and_profit_then_installments_same_account(self):
        before = account_snapshot(self.account)
        profit = monthly_profit(month=self.day)['net_profit_cny']
        retained = retained_earnings(as_of=self.day)
        round = self.confirm()
        self.assertEqual(account_snapshot(self.account), before)
        self.assertEqual(monthly_profit(month=self.day)['net_profit_cny'], profit)
        self.assertEqual(retained_earnings(as_of=self.day), retained - Decimal('100.02'))
        self.assertEqual(set(round.ledger_transaction.postings.values_list('category', flat=True)),
                         {'dividend_distribution', 'dividend_payable'})
        self.payout(round, amount_cny='20.01')
        self.payout(round, key='payout-a2', amount_cny='30.00', business_date=date(2026, 9, 15))
        self.payout(round, key='payout-b1', recipient_id=self.b.pk, amount_cny='50.01', business_date=date(2026, 9, 16))
        self.assertEqual(retained_earnings(as_of=date(2026, 9, 16)), retained - Decimal('100.02'))
        self.assertEqual(monthly_profit(month=self.day)['net_profit_cny'], profit)
        from accounting.action_serializers import serialize_dividend_round
        output = serialize_dividend_round(round)
        self.assertEqual(output['pending_cny'], '0.00')
        self.assertEqual([p['paid_cny'] for p in output['partners']], ['50.01', '50.01'])

    def test_payout_validation_no_partial_writes(self):
        round = self.confirm()
        cases = [({'amount_cny': '50.02'}, 'payout_exceeded'),
                 ({'business_date': date(2026, 9, 13)}, 'invalid_business_date'),
                 ({'recipient_id': self.operator.pk}, 'invalid_recipient'),
                 ({'amount_cny': '0'}, 'invalid_amount'),
                 ({'amount_cny': '1.001'}, 'invalid_money_precision'),
                 ({'fund_account_id': 99999}, 'account_not_found')]
        count = LedgerTransaction.objects.count()
        for changes, code in cases:
            with self.subTest(code=code), self.assertRaisesRegex(DividendActionError, code):
                self.payout(round, **changes)
        self.assertEqual(LedgerTransaction.objects.count(), count)
        self.assertFalse(DividendPayout.objects.exists())
        self.payout(round, amount_cny='40.00')
        with self.assertRaisesRegex(DividendActionError, 'payout_exceeded'):
            self.payout(round, key='over-installment', amount_cny='10.02')
        self.account.is_active = False
        self.account.save(update_fields=['is_active'])
        with self.assertRaisesRegex(DividendActionError, 'account_inactive'):
            self.payout(round, key='inactive', amount_cny='1.00')

    def test_insufficient_and_foreign_account(self):
        round = self.confirm(total_cny='4000.00')
        with self.assertRaisesRegex(DividendActionError, 'insufficient_balance'):
            self.payout(round, amount_cny='1000.01')
        foreign = FundAccount.objects.create(name='卢布公司', currency='RUB', creation_idempotency_key='round-rub')
        with self.assertRaisesRegex(DividendActionError, 'currency_rule'):
            self.payout(round, fund_account_id=foreign.pk)

    def test_backdated_cash_and_pending_never_go_negative(self):
        round = self.confirm(total_cny='3000.00')
        post_transaction(transaction_type='sales_receipt', business_date=date(2026, 9, 16),
                         postings=[PostingInput(account=self.account, currency='CNY', amount=Decimal('1000.00'), cny_amount=Decimal('1000.00')),
                                   PostingInput(category='customer_prepayments', currency='CNY', amount=Decimal('-1000.00'), cny_amount=Decimal('-1000.00'))],
                         operator=self.operator, idempotency_key='later-cash')
        before = account_snapshot(self.account)
        with self.assertRaisesRegex(LedgerError, '历史余额'):
            self.payout(round, amount_cny='1100.00')
        self.assertEqual(account_snapshot(self.account), before)
        self.payout(round, amount_cny='400.00', business_date=date(2026, 9, 17))
        self.payout(round, key='backdated-valid', amount_cny='900.00', business_date=self.day)
        with self.assertRaisesRegex(DividendActionError, 'payout_exceeded'):
            self.payout(round, key='backdated-over', amount_cny='200.01', business_date=self.day)
        self.assertEqual(retained_earnings(as_of=self.day), Decimal('-3000.00'))

    def test_warning_ack_stale_and_operator_binding(self):
        preview = preview_dividend_round(operator=self.operator, **self.body)
        args = dict(operator=self.operator, idempotency_key='warning-round', warning_fingerprint=preview['warning_fingerprint'])
        with self.assertRaisesRegex(DividendActionError, 'warning_required'):
            confirm_dividend_round(**args, warning_ack=False, **self.body)
        other = User.objects.create_user(username='other-op', is_staff=True)
        with self.assertRaisesRegex(DividendActionError, 'warning_stale'):
            confirm_dividend_round(**{**args, 'operator': other}, warning_ack=True, **self.body)
        self.confirm(key='other-round', total_cny='2.00')
        with self.assertRaisesRegex(DividendActionError, 'warning_stale'):
            confirm_dividend_round(**args, warning_ack=True, **self.body)

    def test_no_warning_can_confirm_without_ack(self):
        post_transaction(transaction_type='sales_shipment', business_date=self.day,
                         postings=[PostingInput(category='sales_revenue', currency='CNY', amount=Decimal('-200'), cny_amount=Decimal('-200')),
                                   PostingInput(category='accounts_receivable', currency='CNY', amount=Decimal('200'), cny_amount=Decimal('200'))],
                         operator=self.operator, idempotency_key='round-profit')
        preview = preview_dividend_round(operator=self.operator, **self.body)
        self.assertIsNone(preview['warning'])
        round = confirm_dividend_round(operator=self.operator, idempotency_key='no-warning',
                                       warning_fingerprint=preview['warning_fingerprint'], warning_ack=False, **self.body)
        self.assertEqual(round.total_cny, Decimal('100.02'))

    def test_exact_replay_after_disabled_entities_and_changed_profit(self):
        preview = preview_dividend_round(operator=self.operator, **self.body)
        args = dict(operator=self.operator, idempotency_key='round-confirm',
                    warning_fingerprint=preview['warning_fingerprint'], warning_ack=True, **self.body)
        round = confirm_dividend_round(**args)
        payout = self.payout(round)
        self.account.is_active = False
        self.account.save(update_fields=['is_active'])
        User.objects.filter(pk__in=[self.a.pk, self.b.pk, self.operator.pk]).update(is_active=False)
        count = LedgerTransaction.objects.count()
        self.assertEqual(confirm_dividend_round(**args).pk, round.pk)
        self.assertEqual(self.payout(round).pk, payout.pk)
        self.assertEqual(LedgerTransaction.objects.count(), count)
        with self.assertRaisesRegex(DividendActionError, 'idempotency_conflict'):
            confirm_dividend_round(**{**args, 'note': 'changed'})
        with self.assertRaisesRegex(DividendActionError, 'idempotency_conflict'):
            self.payout(round, amount_cny='11.00')

    def test_tamper_snapshot_pointer_and_ledger_rejected(self):
        preview = preview_dividend_round(operator=self.operator, **self.body)
        args = dict(operator=self.operator, idempotency_key='round-confirm',
                    warning_fingerprint=preview['warning_fingerprint'], warning_ack=True, **self.body)
        round = confirm_dividend_round(**args)
        for field, value in [('partner_a_name', '伪造'), ('ledger_transaction_id', 99999), ('warning_retained_earnings_cny', Decimal('1.00'))]:
            original = getattr(round, field)
            models.QuerySet.update(DividendRound.objects.filter(pk=round.pk), **{field: value})
            with self.assertRaisesRegex(DividendActionError, 'idempotency_conflict'):
                confirm_dividend_round(**args)
            models.QuerySet.update(DividendRound.objects.filter(pk=round.pk), **{field: original})
        payout = self.payout(round)
        models.QuerySet.update(DividendPayout.objects.filter(pk=payout.pk), recipient_name='伪造')
        with self.assertRaisesRegex(DividendActionError, 'idempotency_conflict'):
            self.payout(round)
        models.QuerySet.update(LedgerPosting.objects.filter(transaction=round.ledger_transaction, category='dividend_payable'), amount=Decimal('-99.00'))
        with self.assertRaises(LedgerError):
            confirm_dividend_round(**args)

    def test_orm_guards_and_failed_save_rolls_back(self):
        round = self.confirm()
        payout = self.payout(round)
        for fact in (round, payout):
            manager = type(fact).objects
            for operation in [lambda: fact.save(), lambda: fact.delete(),
                              lambda: manager.filter(pk=fact.pk).update(note='overwrite'),
                              lambda: manager.filter(pk=fact.pk).delete(),
                              lambda: manager.bulk_create([fact]),
                              lambda: manager.bulk_update([fact], ['note']),
                              lambda: manager.get_or_create(pk=fact.pk),
                              lambda: manager.update_or_create(pk=fact.pk)]:
                with self.assertRaises(LedgerMutationError):
                    operation()
            clone = type(fact)(**{f.attname: getattr(fact, f.attname) for f in fact._meta.concrete_fields})
            with ledger_mutation_scope(reason=fact.mutation_reason, model=f'accounting.{type(fact).__name__}',
                                       operator=self.operator, allowed_fields={f.name for f in fact._meta.concrete_fields}):
                with self.assertRaises(LedgerMutationError):
                    clone.save()
        count = LedgerTransaction.objects.count()
        with patch.object(DividendPayout, 'save', side_effect=RuntimeError('save failed')):
            with self.assertRaisesRegex(RuntimeError, 'save failed'):
                self.payout(round, key='rollback')
        self.assertEqual(LedgerTransaction.objects.count(), count)
        with patch.object(DividendRound, 'save', side_effect=RuntimeError('round failed')):
            with self.assertRaises(RuntimeError):
                self.confirm(key='rollback-round')
        self.assertEqual(LedgerTransaction.objects.count(), count)

    def test_api_auth_methods_envelopes_and_pagination(self):
        url = '/api/accounting/dividend-rounds/'
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.a)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.operator)
        self.assertEqual(self.client.post(url).status_code, 405)
        self.assertEqual(self.client.get(url + 'preview/').status_code, 405)
        self.assertEqual(self.client.get(url, {'page': '0'}).status_code, 400)
        body = {**self.body, 'business_date': self.day.isoformat()}
        response = self.client.post(url + 'preview/', json.dumps(body), content_type='application/json')
        self.assertEqual(response.status_code, 200, response.content)
        confirm = self.client.post(url + 'confirm/', json.dumps({**body, 'warning_fingerprint': response.json()['preview']['warning_fingerprint'], 'warning_ack': True}),
                                   content_type='application/json', HTTP_IDEMPOTENCY_KEY='api-round')
        self.assertEqual(confirm.status_code, 201, confirm.content)
        round_id = confirm.json()['round']['id']
        payout = self.client.post(url + f'{round_id}/payouts/', json.dumps({'recipient_id': self.a.pk, 'fund_account_id': self.account.pk,
                                                                         'amount_cny': '1.00', 'business_date': self.day.isoformat()}),
                                  content_type='application/json', HTTP_IDEMPOTENCY_KEY='api-payout')
        self.assertEqual(payout.status_code, 201, payout.content)
        self.assertEqual(payout.json()['payout']['recipient_name'], self.a.username)
        for i in range(20):
            self.confirm(key=f'page-round-{i}', total_cny='0.02')
        listing = self.client.get(url).json()
        self.assertEqual(listing['count'], 21)
        self.assertEqual(listing['next_page'], 2)
        self.assertEqual(len(listing['rounds']), 20)
        self.assertEqual(len(self.client.get(url, {'page': 2}).json()['rounds']), 1)
        self.assertIn('legacy_dividends', listing)
        self.assertEqual(self.client.post(url + 'confirm/', '{}', content_type='application/json').status_code, 400)


class DividendRoundConcurrencyTests(TransactionTestCase):
    day = DividendRoundTests.day
    setUp = DividendRoundTests.setUp
    confirm = DividendRoundTests.confirm

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

        threads = [threading.Thread(target=worker, args=(index,)) for index in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=20)
        self.assertFalse(any(thread.is_alive() for thread in threads))
        return results, errors

    def test_concurrent_round_replay_posts_once(self):
        preview = preview_dividend_round(operator=self.operator, **self.body)
        results, errors = self.parallel(lambda index, operator: confirm_dividend_round(
            operator=operator, idempotency_key='parallel-round', warning_fingerprint=preview['warning_fingerprint'],
            warning_ack=True, **self.body))
        self.assertEqual(errors, [])
        self.assertEqual(len(set(results)), 1)
        self.assertEqual(DividendRound.objects.count(), 1)
        self.assertEqual(LedgerTransaction.objects.filter(idempotency_key='parallel-round').count(), 1)

    def test_concurrent_installments_cannot_overpay(self):
        round = self.confirm()
        results, errors = self.parallel(lambda index, operator: record_dividend_payout(
            round_id=round.pk, recipient_id=self.a.pk, fund_account_id=self.account.pk,
            amount_cny='40.00', business_date=self.day, operator=operator, idempotency_key=f'parallel-payout-{index}'))
        self.assertEqual(len(results), 1)
        self.assertEqual(len(errors), 1)
        self.assertEqual(getattr(errors[0], 'code', None), 'payout_exceeded')
        self.assertEqual(DividendPayout.objects.count(), 1)
