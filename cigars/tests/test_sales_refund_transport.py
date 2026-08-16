from datetime import date
from decimal import Decimal

from unittest.mock import patch
from django.test import TestCase
from django.db import connection, models

from accounting.models import Day1Initialization, FundAccount, LedgerPosting, LedgerTransaction
from accounting.guards import Day1IncompleteError
from accounting.selectors import account_snapshot
from accounting.services import LedgerError, record_opening_balance
from cigars.models import (
    Brand, Cigar, PurchaseBatch, PurchaseOrder, PurchaseOrderItem,
    SalesOrder, SalesReceipt, SalesRefund, SalesShipment, SalesTransportCost,
    StockAllocation, StockMovement, Supplier, User,
)
from cigars.tests.inventory_fixtures import create_purchase_batch
from cigars.services import (
    AgentContext, OrderServiceError, cancel_confirmed_sales_order,
    confirm_sales_order, create_sales_order_draft,
)


class SalesRefundAndTransportTest(TestCase):
    business_date = date(2026, 8, 10)

    def setUp(self):
        self.operator = User.objects.create_user(
            'refund-transport-operator', password='pass', is_staff=True,
        )
        Day1Initialization.objects.create(
            singleton_key='company', status=Day1Initialization.Status.COMPLETED,
            business_date=self.business_date, completed_by=self.operator,
        )
        brand = Brand.objects.create(english_name='Refund Transport Brand', name='退款人肉品牌')
        self.cigar = Cigar.objects.create(
            brand=brand.english_name, english_name='Refund Transport Cigar', name='退款人肉雪茄',
        )

    def context(self, command, key=''):
        return AgentContext(
            agent_name='refund-transport-test', agent_run_id='run-1',
            agent_request_id='request-1', command_name=command, idempotency_key=key,
        )

    def batch(self, quantity=3, unit_cost='10.00'):
        supplier = Supplier.objects.create(name=f'refund-transport-supplier-{PurchaseOrder.objects.count()}')
        purchase_order = PurchaseOrder.objects.create(
            supplier=supplier, rub_total=Decimal('1.00'),
            exchange_rate=Decimal('1.0000'),
            cny_total=Decimal(str(quantity)) * Decimal(str(unit_cost)),
            operator=self.operator,
        )
        item = PurchaseOrderItem.objects.create(
            purchase_order=purchase_order, cigar=self.cigar, quantity=quantity,
            unit_price_rub=Decimal('1.00'), unit_price_cny=Decimal(str(unit_cost)),
        )
        return create_purchase_batch(
            operator=self.operator,
            purchase_order_item=item, cigar=self.cigar, quantity=quantity,
            remaining=quantity, physical_remaining=quantity,
            original_cost_cny=Decimal(str(quantity)) * Decimal(str(unit_cost)),
            remaining_cost_cny=Decimal(str(quantity)) * Decimal(str(unit_cost)),
            unit_cost_cny=Decimal(str(unit_cost)),
            original_stick_quantity=quantity, physical_stick_quantity=quantity,
            available_stick_quantity=quantity,
        )

    def confirmed_order(self, quantity=3, unit_price='30.00'):
        order = create_sales_order_draft(
            items=[{
                'cigar_id': self.cigar.id, 'sale_unit': 'stick',
                'quantity': quantity, 'unit_price': unit_price,
            }],
            operator=self.operator, customer_name='退款人肉测试客户',
            customer_transport_fee_cny='5.00',
            agent_context=self.context('create_sales_order_draft'),
        )
        return confirm_sales_order(
            sales_order_id=order.id, operator=self.operator,
            agent_context=self.context('confirm_sales_order'),
        )

    def prepaid_confirmed_order(self):
        account = FundAccount.objects.create(
            name='退款原收款账户', currency=FundAccount.Currency.CNY,
            custodian=self.operator, creation_idempotency_key='refund-original-account',
        )
        self.batch()
        order = self.confirmed_order()
        from cigars.sales_accounting import receive_sales_order_payment
        receive_sales_order_payment(
            order_id=order.id, amount_cny=Decimal('95.00'),
            fund_account=account, business_date=self.business_date,
            operator=self.operator, idempotency_key='refund-original-receipt',
        )
        cancel_confirmed_sales_order(
            sales_order_id=order.id, operator=self.operator,
            agent_context=self.context('cancel_confirmed_sales_order'),
        )
        return order, account

    def shipped_order(self):
        account = FundAccount.objects.create(
            name='人肉成本账户', currency=FundAccount.Currency.CNY,
            custodian=self.operator, creation_idempotency_key='transport-cost-account',
        )
        record_opening_balance(
            account, '10.00', '10.00', LedgerPosting.Category.OPENING_CAPITAL,
            self.business_date, self.operator, 'transport-cost-opening',
        )
        batch = self.batch()
        order = self.confirmed_order()
        from cigars.sales_accounting import ship_sales_order
        shipped = ship_sales_order(
            order_id=order.id, business_date=self.business_date,
            operator=self.operator, idempotency_key='transport-ship',
        )
        return shipped, account, batch

    def test_refund_prepaid_cancelled_order_reverses_receipt(self):
        order, account = self.prepaid_confirmed_order()
        from cigars.sales_accounting import refund_sales_order_payment
        refunded = refund_sales_order_payment(
            order_id=order.id, business_date=self.business_date,
            operator=self.operator, idempotency_key='refund-1',
        )
        from cigars.models import SalesRefund
        ledger = refunded.ledger_transaction
        account.refresh_from_db(); order.refresh_from_db()
        self.assertEqual(account_snapshot(account).original_balance, Decimal('0E-8'))
        self.assertEqual(list(ledger.postings.order_by('id').values_list('category', 'amount', 'cny_amount')), [
            (LedgerPosting.Category.FUND_ACCOUNT, Decimal('-95.00'), Decimal('-95.00')),
            (LedgerPosting.Category.CUSTOMER_PREPAYMENTS, Decimal('95.00'), Decimal('95.00')),
        ])
        self.assertEqual(SalesRefund.objects.get(sales_order=order).id, refunded.id)
        self.assertEqual(order.payment_status, SalesOrder.PaymentStatus.REFUNDED)
        self.assertEqual(order.fulfillment_status, SalesOrder.FulfillmentStatus.CANCELLED)

    def test_returned_order_refund_uses_original_receivable_category(self):
        """先出库后收款的退货退款必须冲回原应收科目。"""
        shipped, _transport_account, _batch = self.shipped_order()
        receipt_account = FundAccount.objects.create(
            name='退货收款账户',
            currency=FundAccount.Currency.CNY,
            custodian=self.operator,
            creation_idempotency_key='return-refund-account',
        )
        from cigars.sales_accounting import (
            receive_sales_order_payment,
            refund_sales_order_payment,
            return_sales_order,
        )

        receive_sales_order_payment(
            order_id=shipped.id,
            amount_cny=Decimal('95.00'),
            fund_account=receipt_account,
            business_date=self.business_date,
            operator=self.operator,
            idempotency_key='receipt-after-shipment-for-return',
        )
        return_sales_order(
            order_id=shipped.id,
            business_date=date(2026, 8, 11),
            operator=self.operator,
            idempotency_key='return-before-refund',
            reason='客户退货',
        )
        refund = refund_sales_order_payment(
            order_id=shipped.id,
            business_date=date(2026, 8, 11),
            operator=self.operator,
            idempotency_key='refund-returned-order',
        )

        self.assertEqual(
            list(refund.ledger_transaction.postings.order_by('id').values_list(
                'category', 'amount', 'cny_amount',
            )),
            [
                (LedgerPosting.Category.FUND_ACCOUNT, Decimal('-95.00'), Decimal('-95.00')),
                (LedgerPosting.Category.ACCOUNTS_RECEIVABLE, Decimal('95.00'), Decimal('95.00')),
            ],
        )
        shipped.refresh_from_db()
        self.assertEqual(shipped.fulfillment_status, SalesOrder.FulfillmentStatus.RETURNED)
        self.assertEqual(shipped.payment_status, SalesOrder.PaymentStatus.REFUNDED)

    def test_sales_services_require_day1_before_formal_facts(self):
        """All direct sales accounting actions share the Day 1 service gate."""
        Day1Initialization.objects.all().delete()
        from cigars.sales_accounting import (
            receive_sales_order_payment, refund_sales_order_payment,
            record_sales_transport_cost, ship_sales_order,
        )
        account = FundAccount.objects.create(
            name='Day1 guard sales account', currency=FundAccount.Currency.CNY,
            custodian=self.operator, creation_idempotency_key='day1-guard-sales-account',
        )
        confirmed = SalesOrder.objects.create(
            fulfillment_status=SalesOrder.FulfillmentStatus.CONFIRMED,
            payment_status=SalesOrder.PaymentStatus.UNPAID,
            amount_due_cny=Decimal('10.00'), operator=self.operator,
        )
        cancelled = SalesOrder.objects.create(
            fulfillment_status=SalesOrder.FulfillmentStatus.CANCELLED,
            payment_status=SalesOrder.PaymentStatus.REFUND_PENDING,
            amount_due_cny=Decimal('10.00'), operator=self.operator,
        )
        shipped = SalesOrder.objects.create(
            fulfillment_status=SalesOrder.FulfillmentStatus.SHIPPED,
            payment_status=SalesOrder.PaymentStatus.UNPAID,
            amount_due_cny=Decimal('10.00'), operator=self.operator,
        )
        calls = (
            lambda: ship_sales_order(order_id=confirmed.id, business_date=self.business_date,
                                     operator=self.operator, idempotency_key='day1-guard-ship'),
            lambda: receive_sales_order_payment(order_id=confirmed.id, amount_cny=Decimal('10.00'),
                                                fund_account=account, business_date=self.business_date,
                                                operator=self.operator, idempotency_key='day1-guard-receive'),
            lambda: refund_sales_order_payment(order_id=cancelled.id, business_date=self.business_date,
                                               operator=self.operator, idempotency_key='day1-guard-refund'),
            lambda: record_sales_transport_cost(order_id=shipped.id, actual_cost_cny=Decimal('1.00'),
                                                fund_account=account, business_date=self.business_date,
                                                operator=self.operator, idempotency_key='day1-guard-transport'),
        )
        for action in calls:
            with self.subTest(action=action):
                with self.assertRaises(Day1IncompleteError) as raised:
                    action()
                self.assertEqual(raised.exception.code, 'day1_incomplete')
        self.assertEqual(LedgerTransaction.objects.count(), 0)

    def test_refund_same_key_replays_and_different_key_rejects(self):
        order, account = self.prepaid_confirmed_order()
        from cigars.sales_accounting import refund_sales_order_payment
        first = refund_sales_order_payment(order_id=order.id, business_date=self.business_date, operator=self.operator, idempotency_key='refund-idempotent')
        second = refund_sales_order_payment(order_id=order.id, business_date=self.business_date, operator=self.operator, idempotency_key='refund-idempotent')
        self.assertEqual(second.id, first.id)
        with self.assertRaises((LedgerError, OrderServiceError)):
            refund_sales_order_payment(order_id=order.id, business_date=self.business_date, operator=self.operator, idempotency_key='refund-other')
        self.assertEqual(SalesReceipt.objects.count(), 1)
        self.assertEqual(LedgerTransaction.objects.filter(transaction_type=LedgerTransaction.TransactionType.SALES_RECEIPT).count(), 1)


    def test_refund_same_key_replays_after_original_operator_loses_permission(self):
        """退款完成后，原操作员降权不应破坏同参数幂等重放。"""
        order, _account = self.prepaid_confirmed_order()
        from cigars.sales_accounting import refund_sales_order_payment

        first = refund_sales_order_payment(
            order_id=order.id, business_date=self.business_date,
            operator=self.operator, idempotency_key='refund-replay-revoked',
        )
        self.operator.is_staff = False
        replay = refund_sales_order_payment(
            order_id=order.id, business_date=self.business_date,
            operator=self.operator, idempotency_key='refund-replay-revoked',
        )

        self.assertEqual(replay.pk, first.pk)
    def test_refund_ledger_failure_rolls_back_and_rejects_invalid_source(self):
        order, account = self.prepaid_confirmed_order()
        from cigars.sales_accounting import refund_sales_order_payment
        with patch('cigars.sales_accounting._post_transaction_once', side_effect=LedgerError('ledger failed')):
            with self.assertRaises(LedgerError):
                refund_sales_order_payment(order_id=order.id, business_date=self.business_date, operator=self.operator, idempotency_key='refund-rollback')
        order.refresh_from_db(); account.refresh_from_db()
        self.assertEqual(order.payment_status, SalesOrder.PaymentStatus.REFUND_PENDING)
        self.assertEqual(account_snapshot(account).original_balance, Decimal('95.00000000'))
        retried = refund_sales_order_payment(
            order_id=order.id, business_date=self.business_date,
            operator=self.operator, idempotency_key='refund-retry',
        )
        order.refresh_from_db(); account.refresh_from_db()
        self.assertEqual(retried.sales_order_id, order.id)
        self.assertEqual(order.payment_status, SalesOrder.PaymentStatus.REFUNDED)
        self.assertEqual(account_snapshot(account).original_balance, Decimal('0E-8'))
        self.assertEqual(SalesRefund.objects.filter(sales_order=order).count(), 1)

    def test_transport_cost_after_shipment_posts_expense_and_updates_profit(self):
        order, account, batch = self.shipped_order()
        from cigars.sales_accounting import record_sales_transport_cost
        recorded = record_sales_transport_cost(
            order_id=order.id, actual_cost_cny=Decimal('10.00'),
            fund_account=account, business_date=self.business_date,
            operator=self.operator, idempotency_key='transport-cost-1',
        )
        ledger = recorded.ledger_transaction
        order.refresh_from_db(); account.refresh_from_db()
        self.assertEqual(list(ledger.postings.order_by('id').values_list('category', 'amount', 'cny_amount')), [
            (LedgerPosting.Category.TRANSPORT_EXPENSE, Decimal('10.00'), Decimal('10.00')),
            (LedgerPosting.Category.FUND_ACCOUNT, Decimal('-10.00'), Decimal('-10.00')),
        ])
        self.assertEqual(recorded.actual_cost_cny, Decimal('10.00'))
        self.assertEqual(order.actual_transport_cost_cny, Decimal('10.00'))
        self.assertEqual(order.contribution_profit_cny, Decimal('55.00'))
        self.assertEqual(SalesTransportCost.objects.get(sales_order=order).id, recorded.id)
        self.assertEqual(account_snapshot(account).original_balance, Decimal('0E-8'))

    def test_transport_cost_same_key_replays_and_different_key_rejects(self):
        order, account, batch = self.shipped_order()
        from cigars.sales_accounting import record_sales_transport_cost
        first = record_sales_transport_cost(order_id=order.id, actual_cost_cny=Decimal('10.00'), fund_account=account, business_date=self.business_date, operator=self.operator, idempotency_key='transport-idempotent', note='莫斯科配送')
        second = record_sales_transport_cost(order_id=order.id, actual_cost_cny=Decimal('10.00'), fund_account=account, business_date=self.business_date, operator=self.operator, idempotency_key='transport-idempotent', note='莫斯科配送')
        self.assertEqual(second.id, first.id)
        FundAccount.objects.filter(pk=account.pk).update(is_active=False)
        SalesOrder.objects.filter(pk=order.pk).update(
            fulfillment_status=SalesOrder.FulfillmentStatus.CANCELLED,
        )
        replay_after_state_change = record_sales_transport_cost(
            order_id=order.id, actual_cost_cny=Decimal('10.00'),
            fund_account=account, business_date=self.business_date,
            operator=self.operator, idempotency_key='transport-idempotent',
            note='莫斯科配送',
        )
        self.assertEqual(replay_after_state_change.pk, first.pk)
        with self.assertRaises((LedgerError, OrderServiceError)):
            record_sales_transport_cost(order_id=order.id, actual_cost_cny=Decimal('10.00'), fund_account=account, business_date=self.business_date, operator=self.operator, idempotency_key='transport-idempotent', note='备注被修改')
        with self.assertRaises((LedgerError, OrderServiceError)):
            record_sales_transport_cost(order_id=order.id, actual_cost_cny=Decimal('10.00'), fund_account=account, business_date=self.business_date, operator=self.operator, idempotency_key='transport-other')

    def test_transport_replay_rejects_corrupted_posting(self):
        """人肉费 replay 必须拒绝账户或费用金额被篡改的流水。"""
        order, account, _batch = self.shipped_order()
        from cigars.sales_accounting import record_sales_transport_cost

        cost = record_sales_transport_cost(
            order_id=order.id, actual_cost_cny=Decimal('10.00'),
            fund_account=account, business_date=self.business_date,
            operator=self.operator, idempotency_key='transport-posting-replay',
        )
        posting = cost.ledger_transaction.postings.get(
            category=LedgerPosting.Category.TRANSPORT_EXPENSE,
        )
        posting.cny_amount += Decimal('1.00')
        models.Model.save(posting, update_fields=['cny_amount'])

        with self.assertRaises(OrderServiceError):
            record_sales_transport_cost(
                order_id=order.id, actual_cost_cny=Decimal('10.00'),
                fund_account=account, business_date=self.business_date,
                operator=self.operator, idempotency_key='transport-posting-replay',
            )

    def test_transport_cost_rejects_invalid_status_amount_and_account(self):
        from cigars.sales_accounting import record_sales_transport_cost
        for status in (SalesOrder.FulfillmentStatus.DRAFT, SalesOrder.FulfillmentStatus.CONFIRMED, SalesOrder.FulfillmentStatus.CANCELLED):
            order = SalesOrder.objects.create(
                fulfillment_status=status, payment_status=SalesOrder.PaymentStatus.UNPAID,
                amount_due_cny=Decimal('95.00'), operator=self.operator,
            )
            account = FundAccount.objects.create(name=f'transport-invalid-{status}', currency=FundAccount.Currency.CNY, custodian=self.operator, creation_idempotency_key=f'transport-invalid-{status}')
            with self.assertRaises((LedgerError, OrderServiceError)):
                record_sales_transport_cost(order_id=order.id, actual_cost_cny=Decimal('10.00'), fund_account=account, business_date=self.business_date, operator=self.operator, idempotency_key=f'transport-invalid-{status}')
        order, account, batch = self.shipped_order()
        inactive = FundAccount.objects.create(name='transport-inactive', currency=FundAccount.Currency.CNY, custodian=self.operator, is_active=False, creation_idempotency_key='transport-inactive')
        rub = FundAccount.objects.create(name='transport-rub', currency=FundAccount.Currency.RUB, custodian=self.operator, creation_idempotency_key='transport-rub')
        for index, (amount, fund) in enumerate(((Decimal('10.001'), account), (Decimal('10.00'), inactive), (Decimal('10.00'), rub))):
            with self.assertRaises((LedgerError, OrderServiceError)):
                record_sales_transport_cost(order_id=order.id, actual_cost_cny=amount, fund_account=fund, business_date=self.business_date, operator=self.operator, idempotency_key=f'transport-invalid-account-{index}')

    def test_transport_cost_ledger_failure_rolls_back(self):
        order, account, batch = self.shipped_order()
        from cigars.sales_accounting import record_sales_transport_cost
        with patch('cigars.sales_accounting._post_transaction_once', side_effect=LedgerError('ledger failed')):
            with self.assertRaises(LedgerError):
                record_sales_transport_cost(order_id=order.id, actual_cost_cny=Decimal('10.00'), fund_account=account, business_date=self.business_date, operator=self.operator, idempotency_key='transport-rollback')
        order.refresh_from_db(); account.refresh_from_db()
        self.assertEqual(order.actual_transport_cost_cny, Decimal('0.00'))
        self.assertEqual(SalesTransportCost.objects.count(), 0)
        self.assertEqual(account_snapshot(account).original_balance, Decimal('10.00000000'))


    def test_refund_replay_requires_date_and_operator_and_cross_order_key_is_rejected(self):
        order, account = self.prepaid_confirmed_order()
        second_account = FundAccount.objects.create(
            name='退款第二账户', currency=FundAccount.Currency.CNY,
            custodian=self.operator, creation_idempotency_key='refund-second-account',
        )
        from cigars.sales_accounting import refund_sales_order_payment
        first = refund_sales_order_payment(order_id=order.id, business_date=self.business_date, operator=self.operator, idempotency_key='refund-strict')
        another = User.objects.create_user('refund-other-operator', password='pass', is_staff=True)
        for kwargs in (
            {'business_date': date(2026, 8, 11), 'operator': self.operator},
            {'business_date': self.business_date, 'operator': another},
        ):
            with self.assertRaises(OrderServiceError):
                refund_sales_order_payment(order_id=order.id, idempotency_key='refund-strict', **kwargs)
        self.assertEqual(first.id, SalesRefund.objects.get(sales_order=order).id)

    def test_refund_rejects_cross_order_key(self):
        first_order, first_account = self.prepaid_confirmed_order()
        second_account = FundAccount.objects.create(name='退款跨单账户', currency=FundAccount.Currency.CNY, custodian=self.operator, creation_idempotency_key='refund-cross-account')
        self.batch()
        second_order = self.confirmed_order()
        from cigars.sales_accounting import refund_sales_order_payment
        refund_sales_order_payment(order_id=first_order.id, business_date=self.business_date, operator=self.operator, idempotency_key='refund-cross-key')
        with self.assertRaises(OrderServiceError):
            refund_sales_order_payment(order_id=second_order.id, business_date=self.business_date, operator=self.operator, idempotency_key='refund-cross-key')

    def test_refund_rejects_malformed_receipt_ledger(self):
        order, account = self.prepaid_confirmed_order()
        receipt = SalesReceipt.objects.get(sales_order=order)
        posting = receipt.ledger_transaction.postings.get(category=LedgerPosting.Category.CUSTOMER_PREPAYMENTS)
        posting.amount = Decimal('-1.00')
        posting.cny_amount = Decimal('-1.00')
        models.Model.save(posting, update_fields=['amount', 'cny_amount'])
        from cigars.sales_accounting import refund_sales_order_payment
        with self.assertRaises(OrderServiceError):
            refund_sales_order_payment(order_id=order.id, business_date=self.business_date, operator=self.operator, idempotency_key='refund-malformed')


    def _swap_posting_targets(self, transaction):
        postings = list(transaction.postings.order_by('id'))
        account_posting, category_posting = postings
        with connection.cursor() as cursor:
            cursor.execute('UPDATE accounting_ledgerposting SET id = -id WHERE id IN (%s, %s)', [account_posting.id, category_posting.id])
            cursor.execute('UPDATE accounting_ledgerposting SET id = %s WHERE id = %s', [category_posting.id, -account_posting.id])
            cursor.execute('UPDATE accounting_ledgerposting SET id = %s WHERE id = %s', [account_posting.id, -category_posting.id])

    def test_refund_replay_accepts_semantically_valid_reverse_posting_order(self):
        order, account = self.prepaid_confirmed_order()
        from cigars.sales_accounting import refund_sales_order_payment
        first = refund_sales_order_payment(order_id=order.id, business_date=self.business_date, operator=self.operator, idempotency_key='refund-reverse')
        self._swap_posting_targets(first.ledger_transaction)
        replay = refund_sales_order_payment(order_id=order.id, business_date=self.business_date, operator=self.operator, idempotency_key='refund-reverse')
        self.assertEqual(replay.id, first.id)

    def test_refund_rejects_non_cny_receipt_posting(self):
        order, account = self.prepaid_confirmed_order()
        receipt = SalesReceipt.objects.get(sales_order=order)
        posting = receipt.ledger_transaction.postings.get(category=LedgerPosting.Category.CUSTOMER_PREPAYMENTS)
        posting.currency = 'RUB'
        models.Model.save(posting, update_fields=['currency'])
        from cigars.sales_accounting import refund_sales_order_payment
        with self.assertRaises(OrderServiceError):
            refund_sales_order_payment(order_id=order.id, business_date=self.business_date, operator=self.operator, idempotency_key='refund-rub-posting')

    def test_refund_rejects_category_posting_with_fund_account(self):
        order, account = self.prepaid_confirmed_order()
        receipt = SalesReceipt.objects.get(sales_order=order)
        posting = receipt.ledger_transaction.postings.get(category=LedgerPosting.Category.CUSTOMER_PREPAYMENTS)
        with connection.cursor() as cursor:
            cursor.execute('PRAGMA ignore_check_constraints = ON')
            cursor.execute('UPDATE accounting_ledgerposting SET account_id = %s WHERE id = %s', [account.id, posting.id])
            cursor.execute('PRAGMA ignore_check_constraints = OFF')
        from cigars.sales_accounting import refund_sales_order_payment
        with self.assertRaises((OrderServiceError, LedgerError)):
            refund_sales_order_payment(order_id=order.id, business_date=self.business_date, operator=self.operator, idempotency_key='refund-account-category')
