from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase

from accounting.models import FundAccount, LedgerPosting, LedgerTransaction
from accounting.services import LedgerError
from cigars.models import SalesOrder, SalesReceipt
from cigars.sales_accounting import (
    receive_sales_order_payment, ship_sales_order, return_sales_order,
    refund_sales_order_payment, withdraw_sales_order_payment,
)
from cigars.sales_reports import pending_collection_summary
from cigars.services import OrderServiceError, cancel_confirmed_sales_order, serialize_sales_order
from cigars.tests import test_sales_refund_transport as fixtures


class PartialReceiptsTest(TestCase):
    business_date = fixtures.SalesRefundAndTransportTest.business_date
    setUp = fixtures.SalesRefundAndTransportTest.setUp
    batch = fixtures.SalesRefundAndTransportTest.batch
    context = fixtures.SalesRefundAndTransportTest.context
    confirmed_order = fixtures.SalesRefundAndTransportTest.confirmed_order

    def prepare(self):
        self.batch()
        self.order = self.confirmed_order()  # 95 CNY, cost 30
        self.a = FundAccount.objects.create(name='A', currency='CNY', creation_idempotency_key='partial-a')
        self.b = FundAccount.objects.create(name='B', currency='CNY', creation_idempotency_key='partial-b')

    def receive(self, amount, key, account=None, day=None):
        return receive_sales_order_payment(order_id=self.order.pk, amount_cny=amount,
            fund_account=account or self.a, business_date=day or self.business_date,
            operator=self.operator, idempotency_key=key)

    def action(self, function, key, **kwargs):
        return function(order_id=self.order.pk, business_date=self.business_date,
                        operator=self.operator, idempotency_key=key, **kwargs)

    def category_total(self, category):
        return sum((p.cny_amount for p in LedgerPosting.objects.filter(category=category)), Decimal('0'))

    def test_partial_prepaid_shipment_tail_receipt_and_replay(self):
        self.prepare()
        first = self.receive('30', 'first')
        self.assertEqual(self.receive('30', 'first').pk, first.pk)
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, 'partial')
        self.assertEqual(pending_collection_summary()['amount_cny'], Decimal('65'))
        payload = serialize_sales_order(self.order)
        self.assertEqual(payload['received_amount_cny'], 30)
        self.assertEqual(payload['remaining_amount_cny'], 65)
        self.assertIn('receive', payload['available_actions'])
        self.action(ship_sales_order, 'ship')
        self.assertEqual(self.category_total('customer_prepayments'), 0)
        self.assertEqual(self.category_total('accounts_receivable'), 65)
        self.receive('65', 'tail', self.b)
        self.action(ship_sales_order, 'ship')
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, 'paid')
        self.assertEqual(self.category_total('accounts_receivable'), 0)
        self.assertEqual(pending_collection_summary()['order_count'], 0)

    def test_partial_tail_return_and_original_account_refund_clear_balances(self):
        self.prepare()
        self.receive('30', 'first')
        self.action(ship_sales_order, 'ship')
        self.receive('20', 'tail', self.b)
        self.action(return_sales_order, 'return', reason='整单退货')
        refund = self.action(refund_sales_order_payment, 'refund')
        self.assertEqual(refund.amount_cny, 50)
        self.assertIsNone(refund.fund_account_id)
        self.assertEqual(self.action(refund_sales_order_payment, 'refund').pk, refund.pk)
        self.assertEqual(self.category_total('customer_prepayments'), 0)
        self.assertEqual(self.category_total('accounts_receivable'), 0)
        self.assertEqual(self.category_total('sales_revenue'), 0)
        self.order.refresh_from_db()
        self.assertEqual(serialize_sales_order(self.order)['remaining_amount_cny'], 0)
        for account in (self.a, self.b):
            self.assertEqual(sum(p.amount for p in LedgerPosting.objects.filter(account=account)), 0)

    def test_partial_cancel_refunds_only_received(self):
        self.prepare()
        self.receive('30', 'first')
        cancel_confirmed_sales_order(sales_order_id=self.order.pk, operator=self.operator)
        self.assertEqual(self.action(refund_sales_order_payment, 'refund').amount_cny, 30)
        self.assertEqual(self.category_total('customer_prepayments'), 0)

    def test_pending_summary_subtracts_all_receipts_without_duplicating_order_total(self):
        self.prepare()
        self.receive('20', 'first')
        self.receive('10', 'second', self.b)
        self.batch()
        self.confirmed_order()
        self.assertEqual(pending_collection_summary(), {'order_count': 2, 'amount_cny': Decimal('160.00')})

    def test_multi_account_refund_failure_rolls_back_all_accounts(self):
        self.prepare()
        self.receive('30', 'first')
        self.receive('20', 'second', self.b)
        cancel_confirmed_sales_order(sales_order_id=self.order.pk, operator=self.operator)
        before = LedgerPosting.objects.count()
        self.b.is_active = False
        self.b.save(update_fields=['is_active'])
        with self.assertRaises(LedgerError):
            self.action(refund_sales_order_payment, 'refund')
        self.assertEqual(LedgerPosting.objects.count(), before)
        self.b.is_active = True
        self.b.save(update_fields=['is_active'])
        with patch('cigars.sales_accounting.SalesRefund.objects.create', side_effect=RuntimeError('after ledger')):
            with self.assertRaises(RuntimeError):
                self.action(refund_sales_order_payment, 'refund')
        self.assertEqual(LedgerPosting.objects.count(), before)
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, 'refund_pending')
        self.assertEqual(self.action(refund_sales_order_payment, 'refund').amount_cny, 50)

    def test_withdraw_cannot_target_a_different_or_stale_receipt(self):
        self.prepare()
        first = self.receive('30', 'first')
        last = self.receive('20', 'last')
        with self.assertRaises(OrderServiceError):
            self.action(withdraw_sales_order_payment, 'withdraw', reason='错误', sales_receipt_id=first.pk)
        self.action(withdraw_sales_order_payment, 'withdraw', reason='错误', sales_receipt_id=last.pk)
        with self.assertRaises(OrderServiceError):
            self.action(withdraw_sales_order_payment, 'withdraw', reason='错误', sales_receipt_id=first.pk)

    def test_overpayment_precision_and_changed_replay_are_rejected(self):
        self.prepare()
        self.receive('30', 'first')
        before = LedgerTransaction.objects.count()
        for amount, key in [('65.01', 'over'), ('0', 'zero'), ('-1', 'negative'), ('1.001', 'precision'), ('31', 'first')]:
            with self.subTest(amount=amount), self.assertRaises((OrderServiceError, LedgerError)):
                self.receive(amount, key)
        self.assertEqual(LedgerTransaction.objects.count(), before)
        self.assertEqual(SalesReceipt.objects.count(), 1)

    def test_withdraw_latest_restores_partial_and_replays(self):
        self.prepare()
        self.receive('30', 'first')
        last = self.receive('65', 'tail', self.b)
        withdrawn = self.action(withdraw_sales_order_payment, 'withdraw', reason='账户错误')
        self.assertEqual(withdrawn.pk, last.pk)
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, 'partial')
        self.assertEqual(self.action(withdraw_sales_order_payment, 'withdraw', reason='账户错误').pk, last.pk)

    def test_business_dates_preserve_prepayment_and_receivable_classification(self):
        self.prepare()
        self.receive('30', 'first', day=self.business_date + timedelta(days=1))
        with self.assertRaisesMessage(OrderServiceError, '出库日期不能早于'):
            self.action(ship_sales_order, 'too-early')
        ship_sales_order(order_id=self.order.pk, business_date=self.business_date + timedelta(days=1),
                         operator=self.operator, idempotency_key='ship')
        with self.assertRaisesMessage(OrderServiceError, '不能早于出库'):
            self.receive('20', 'backdated')
