import json
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from decimal import Decimal
from threading import Barrier
from unittest.mock import patch

from django.db import close_old_connections, models
from django.test import TestCase, TransactionTestCase

from accounting.business_time import moscow_business_date
from accounting.fund_receipts import record_fund_receipt
from accounting.guards import Day1IncompleteError
from accounting.models import Day1Initialization, FundAccount, FundReceipt, LedgerMutationError, LedgerPosting, LedgerTransaction
from accounting.purchase_actions import pay_purchase_order, receive_paid_purchase_order
from accounting.selectors import account_snapshot, monthly_profit, retained_earnings
from accounting.services import LedgerError, exchange_to_rub, reverse_ledger_transaction
from cigars.models import Cigar, PurchaseOrder, PurchaseOrderItem, Supplier, User


class ReceiptFixture:
    def setUp(self):
        self.operator = User.objects.create_user('receipt-operator', is_staff=True)
        self.contributor = User.objects.create_user('partner', first_name='投入人')
        self.day1 = Day1Initialization.objects.create(singleton_key='company', status='completed', business_date=date(2026, 8, 10), completed_by=self.operator)
        self.cny = FundAccount.objects.create(name='人民币', currency='CNY', custodian=self.operator, creation_idempotency_key='cny')
        self.rub = FundAccount.objects.create(name='卢布', currency='RUB', custodian=self.operator, creation_idempotency_key='rub')

    def receipt(self, **overrides):
        return record_fund_receipt(**{
            'contributor_id': self.contributor.pk, 'fund_account_id': self.cny.pk,
            'amount_cny': '30000.00', 'business_date': date(2026, 8, 12),
            'operator': self.operator, 'idempotency_key': 'receipt', 'note': '买货资金',
            'agent_source': 'test:receipt', **overrides,
        })


class FundReceiptTests(ReceiptFixture, TestCase):
    def test_receipt_exchange_purchase_receiving_preserves_cost_and_profit(self):
        before = monthly_profit(month=date(2026, 8, 1))
        receipt, created = self.receipt()
        self.assertTrue(created)
        self.assertEqual(receipt.contributor_name, '投入人')
        self.assertEqual(account_snapshot(self.cny).original_balance, Decimal('30000'))
        self.assertEqual(LedgerPosting.objects.get(category='contributed_capital').cny_amount, Decimal('-30000'))
        self.assertFalse(LedgerPosting.objects.filter(category='opening_capital').exists())
        exchange_to_rub(self.cny, self.rub, Decimal('10000'), Decimal('115000'), date(2026, 8, 13), self.operator, 'exchange')
        supplier = Supplier.objects.create(name='供货商')
        cigar = Cigar.objects.create(brand='Test', english_name='Receipt Cigar', name='测试雪茄')
        order = PurchaseOrder.objects.create(supplier=supplier, rub_total=Decimal('57500'), operator=self.operator, draft_business_date=date(2026, 8, 14))
        PurchaseOrderItem.objects.create(purchase_order=order, cigar=cigar, quantity=25, box_size=25, box_quantity=1,
                                        unit_price_rub_per_box=Decimal('57500'), packaging_status='normalized')
        pay_purchase_order(purchase_order_id=order.pk, rub_account_id=self.rub.pk, business_date=date(2026, 8, 14), operator=self.operator, idempotency_key='pay')
        order.refresh_from_db()
        self.assertEqual(order.paid_cny_cost, Decimal('5000'))
        receive_paid_purchase_order(purchase_order_id=order.pk, business_date=date(2026, 8, 15), operator=self.operator, idempotency_key='receive')
        self.assertEqual(account_snapshot(self.cny).cny_book_cost, Decimal('20000'))
        self.assertEqual(account_snapshot(self.rub).cny_book_cost, Decimal('5000'))
        self.assertEqual(LedgerPosting.objects.get(category='inventory').cny_amount, Decimal('5000'))
        after = monthly_profit(month=date(2026, 8, 1))
        self.assertEqual({key: value for key, value in after.items() if key != 'transaction_count'},
                         {key: value for key, value in before.items() if key != 'transaction_count'})
        self.assertEqual(retained_earnings(as_of=date(2026, 8, 31)), Decimal('0'))
        # 已有换汇/采购以后，允许按真实日期补录人民币资金；不改外币历史成本。
        self.receipt(idempotency_key='backfill', amount_cny='100', business_date=date(2026, 8, 11))
        self.assertEqual(account_snapshot(self.cny).original_balance, Decimal('20100'))
        self.assertEqual(account_snapshot(self.rub).cny_book_cost, Decimal('5000'))

    def test_replay_after_rename_or_deactivation_and_all_request_conflicts(self):
        receipt, _ = self.receipt()
        self.contributor.first_name = '改名'; self.contributor.is_active = False
        self.contributor.save(update_fields=['first_name', 'is_active'])
        self.cny.is_active = False; self.cny.save(update_fields=['is_active'])
        replay, created = self.receipt()
        self.assertFalse(created); self.assertEqual(replay.pk, receipt.pk)
        self.assertEqual(replay.contributor_name, '投入人')
        for changes in [{'amount_cny': '1'}, {'contributor_id': self.operator.pk}, {'fund_account_id': self.rub.pk},
                        {'business_date': date(2026, 8, 13)}, {'note': 'changed'}, {'agent_source': 'other'}, {'operator': self.contributor}]:
            with self.subTest(changes=changes), self.assertRaises(LedgerError) as caught:
                self.receipt(**changes)
            self.assertEqual(caught.exception.code, 'idempotency_conflict')
        with self.assertRaises(LedgerError):
            self.receipt(idempotency_key='new')
        self.assertEqual(FundReceipt.objects.count(), 1)

    def test_invalid_input_and_guards_do_not_post(self):
        cases = [{'amount_cny': value} for value in ['0', '-1', 'NaN', 'Infinity', '0.001', '1000000000000', True]]
        cases += [{'business_date': date(2026, 8, 9)}, {'business_date': moscow_business_date() + timedelta(days=1)},
                  {'fund_account_id': self.rub.pk}, {'fund_account_id': True}, {'fund_account_id': 999999},
                  {'contributor_id': 999999}, {'contributor_id': 1.0}, {'agent_source': []}, {'note': {}},
                  {'note': 'x' * 2001}, {'idempotency_key': ' '}, {'operator': self.contributor}]
        for change in cases:
            with self.subTest(change=change), self.assertRaises(LedgerError):
                self.receipt(**change)
        self.contributor.is_active = False; self.contributor.save(update_fields=['is_active'])
        with self.assertRaises(LedgerError):
            self.receipt()
        self.day1.delete()
        with self.assertRaises(Day1IncompleteError):
            self.receipt()
        self.assertEqual(FundReceipt.objects.count(), 0)
        self.assertEqual(LedgerTransaction.objects.count(), 0)

    def test_rollback_immutability_and_no_generic_reversal(self):
        with patch.object(FundReceipt, 'save', side_effect=RuntimeError('fail')):
            with self.assertRaises(RuntimeError):
                self.receipt()
        self.assertEqual(LedgerTransaction.objects.count(), 0)
        receipt, _ = self.receipt()
        for action in [lambda: receipt.save(), lambda: receipt.delete(), lambda: FundReceipt.objects.all().delete(),
                       lambda: FundReceipt.objects.filter(pk=receipt.pk).update(note='x'),
                       lambda: FundReceipt.objects.bulk_create([receipt]), lambda: FundReceipt.objects.bulk_update([receipt], ['note']),
                       lambda: FundReceipt.objects.get_or_create(id=receipt.pk)]:
            with self.assertRaises(LedgerMutationError):
                action()
        with self.assertRaises(LedgerError):
            reverse_ledger_transaction(original_transaction=receipt.ledger_transaction, business_date=date(2026, 8, 13), operator=self.operator, idempotency_key='reverse', reason='test')
        self.assertEqual(account_snapshot(self.cny).original_balance, Decimal('30000'))

    def test_replay_checks_ledger_and_shared_key(self):
        receipt, _ = self.receipt()
        models.QuerySet.update(LedgerPosting.objects.filter(transaction=receipt.ledger_transaction, account=self.cny), amount=Decimal('1'))
        with self.assertRaises(LedgerError) as caught:
            self.receipt()
        self.assertEqual(caught.exception.code, 'idempotency_conflict')

    def test_api_permissions_decimal_contract_and_pagination(self):
        path = '/api/accounting/fund-receipts/'
        payload = {'contributor_id': self.contributor.pk, 'fund_account_id': self.cny.pk,
                   'amount_cny': '30000.00', 'business_date': '2026-08-12', 'note': '到账'}
        def post(data=payload, key='api'):
            return self.client.post(path, json.dumps(data), content_type='application/json', HTTP_IDEMPOTENCY_KEY=key)
        self.assertEqual(post().status_code, 403)
        self.client.force_login(self.contributor)
        self.assertEqual(post().status_code, 403)
        self.client.force_login(self.operator)
        response = post(); self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(post().status_code, 200)
        self.assertEqual(post({**payload, 'amount_cny': '1'}).status_code, 409)
        self.assertEqual(post({**payload, 'amount_cny': 12}, 'numeric').status_code, 400)
        self.assertEqual(post(key='').status_code, 400)
        self.assertEqual(self.client.patch(path).status_code, 405)
        self.assertEqual(self.client.get(path, {'page': '0'}).status_code, 400)
        for index in range(20):
            self.receipt(idempotency_key=f'page-{index}', amount_cny='1')
        first = self.client.get(path).json()
        second = self.client.get(path, {'page': 2}).json()
        self.assertEqual(len(first['receipts']), 20); self.assertEqual(first['next_page'], 2)
        self.assertEqual(len(second['receipts']), 1); self.assertIsNone(second['next_page'])
        self.assertEqual(second['receipts'][0]['amount_cny'], '30000.00')
        self.assertIn({'id': self.contributor.pk, 'name': '投入人'}, first['contributors'])


class FundReceiptConcurrencyTests(ReceiptFixture, TransactionTestCase):
    def test_same_key_posts_once_and_different_keys_add(self):
        def run(keys):
            barrier = Barrier(2)
            def worker(key):
                close_old_connections()
                try:
                    barrier.wait(timeout=10)
                    return self.receipt(idempotency_key=key)[0].pk
                finally:
                    close_old_connections()
            with ThreadPoolExecutor(max_workers=2) as pool:
                return list(pool.map(worker, keys))
        ids = run(['shared', 'shared'])
        self.assertEqual(ids[0], ids[1])
        self.assertEqual(FundReceipt.objects.count(), 1)
        run(['new-a', 'new-b'])
        self.assertEqual(FundReceipt.objects.count(), 3)
        self.assertEqual(account_snapshot(self.cny).original_balance, Decimal('90000'))
