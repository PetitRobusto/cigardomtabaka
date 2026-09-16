from datetime import date
from decimal import Decimal

from django.db import transaction
from django.test import TestCase
from unittest.mock import patch

from accounting.models import (
    Day1Initialization,
    FundAccount,
    LedgerPosting,
    LedgerTransaction,
)
from accounting.mutation_scope import ledger_mutation_scope
from accounting.services import (
    PostingInput,
    post_transaction,
    record_opening_balance,
    reverse_ledger_transaction,
)
from cigars.models import (
    Cigar,
    Customer,
    SalesOrder,
    SalesOrderItem,
    SalesReceipt,
    SalesReturn,
    SalesShipment,
    SalesTransportCost,
    User,
)


class MonthlyBusinessReportTest(TestCase):
    def setUp(self):
        self.operator = User.objects.create_user(
            'monthly-report-operator', password='pass', is_staff=True,
        )
        Day1Initialization.objects.create(
            status=Day1Initialization.Status.COMPLETED,
            business_date=date(2026, 8, 10),
            completed_by=self.operator,
        )
        self.account = FundAccount.objects.create(
            name='月报人民币账户',
            currency=FundAccount.Currency.CNY,
            creation_idempotency_key='monthly-report-account',
        )
        record_opening_balance(
            self.account,
            Decimal('1000.00'),
            Decimal('1000.00'),
            LedgerPosting.Category.OPENING_CAPITAL,
            date(2026, 8, 10),
            self.operator,
            'monthly-report-account-opening',
        )
        self.cigar = Cigar.objects.create(
            brand='Cohiba', english_name='Robustos', name='罗布图',
        )

    def post(self, transaction_type, business_date, postings, key):
        return post_transaction(
            transaction_type=transaction_type,
            business_date=business_date,
            postings=postings,
            operator=self.operator,
            idempotency_key=key,
            source_type='monthly_report_test',
            source_id=key,
        )

    def shipment(self, *, business_date, goods, cost, key, customer=None,
                 transport_fee=Decimal('0.00'), company_pays=False):
        amount_due = goods + transport_fee
        order = SalesOrder.objects.create(
            customer=customer,
            customer_name='' if customer else f'散客-{key}',
            goods_amount_cny=goods,
            customer_transport_fee_cny=transport_fee,
            transport_payer=(
                SalesOrder.TransportPayer.COMPANY
                if company_pays else SalesOrder.TransportPayer.CUSTOMER
            ),
            amount_due_cny=amount_due,
            fifo_cost_cny=cost,
            actual_transport_cost_cny=Decimal('0.00'),
            contribution_profit_cny=amount_due - cost,
            total_revenue=amount_due,
            total_cost=cost,
            total_profit=amount_due - cost,
            fulfillment_status=SalesOrder.FulfillmentStatus.SHIPPED,
            payment_status=SalesOrder.PaymentStatus.UNPAID,
            status='shipped',
            operator=self.operator,
        )
        item = SalesOrderItem.objects.create(
            sales_order=order,
            cigar=self.cigar,
            quantity=1,
            unit_price=goods,
            unit_cost=cost,
            revenue=goods,
            cost=cost,
            profit=goods - cost,
        )
        ledger = self.post(
            LedgerTransaction.TransactionType.SALES_SHIPMENT,
            business_date,
            [
                PostingInput(
                    category=LedgerPosting.Category.ACCOUNTS_RECEIVABLE,
                    currency='CNY', amount=amount_due, cny_amount=amount_due,
                ),
                PostingInput(
                    category=LedgerPosting.Category.SALES_REVENUE,
                    currency='CNY', amount=-goods, cny_amount=-goods,
                ),
                PostingInput(
                    category=LedgerPosting.Category.CUSTOMER_TRANSPORT_REVENUE,
                    currency='CNY', amount=-transport_fee, cny_amount=-transport_fee,
                ),
                PostingInput(
                    category=LedgerPosting.Category.COST_OF_GOODS_SOLD,
                    currency='CNY', amount=cost, cny_amount=cost,
                ),
                PostingInput(
                    category=LedgerPosting.Category.INVENTORY,
                    currency='CNY', amount=-cost, cny_amount=-cost,
                ),
            ],
            f'{key}-shipment-ledger',
        )
        shipment = SalesShipment.objects.create(
            sales_order=order,
            business_date=business_date,
            fifo_cost_cny=cost,
            ledger_transaction=ledger,
            operator=self.operator,
        )
        return order, item, shipment

    def transport_cost(self, order, *, business_date, amount, key):
        ledger = self.post(
            LedgerTransaction.TransactionType.SALES_TRANSPORT_COST,
            business_date,
            [
                PostingInput(
                    category=LedgerPosting.Category.TRANSPORT_EXPENSE,
                    currency='CNY', amount=amount, cny_amount=amount,
                ),
                PostingInput(
                    account=self.account,
                    currency='CNY', amount=-amount, cny_amount=-amount,
                ),
            ],
            f'{key}-transport-ledger',
        )
        return SalesTransportCost.objects.create(
            sales_order=order,
            actual_cost_cny=amount,
            fund_account=self.account,
            business_date=business_date,
            ledger_transaction=ledger,
            operator=self.operator,
        )

    def test_sales_income_cost_structure_and_zero_base_comparison(self):
        customer = Customer.objects.create(name='月报客户')
        company_order, _item, _shipment = self.shipment(
            business_date=date(2026, 8, 15),
            goods=Decimal('100.00'), cost=Decimal('40.00'),
            key='company-paid', customer=customer, company_pays=True,
        )
        self.transport_cost(
            company_order,
            business_date=date(2026, 8, 15),
            amount=Decimal('20.00'), key='company-paid',
        )
        self.shipment(
            business_date=date(2026, 8, 18),
            goods=Decimal('80.00'), cost=Decimal('30.00'),
            transport_fee=Decimal('10.00'),
            key='customer-paid', customer=customer,
        )

        from accounting.monthly_reports import monthly_business_report

        with patch('accounting.monthly_reports.moscow_business_date', return_value=date(2026, 9, 16)):
            report = monthly_business_report(month=date(2026, 8, 1))

        self.assertEqual(report['profit']['sales_revenue_cny'], Decimal('190.00'))
        self.assertEqual(report['profit']['product_cost_cny'], Decimal('70.00'))
        self.assertEqual(report['profit']['human_cost_cny'], Decimal('20.00'))
        self.assertEqual(report['profit']['sales_profit_cny'], Decimal('100.00'))
        self.assertEqual(report['profit']['core_operating_profit_cny'], Decimal('100.00'))
        self.assertEqual(report['profit']['net_operating_profit_cny'], Decimal('100.00'))
        self.assertEqual(report['sales']['fulfillment_order_count'], 2)
        self.assertEqual(report['sales']['net_sales_revenue_cny'], Decimal('190.00'))
        self.assertEqual(
            report['comparison']['metrics']['sales_revenue_cny']['status'], 'new',
        )
        self.assertIsNone(
            report['comparison']['metrics']['sales_revenue_cny']['change_rate'],
        )
        brand = report['rankings']['brands'][0]
        self.assertEqual(brand['net_sales_revenue_cny'], Decimal('190.00'))
        self.assertEqual(brand['human_cost_cny'], Decimal('20.00'))
        self.assertEqual(report['customers']['new_customer_count'], 1)
        self.assertEqual(report['customers']['repeat_customer_count'], 1)

    def test_fulfillment_receipt_and_return_follow_their_own_business_months(self):
        customer = Customer.objects.create(name='跨月客户')
        order, _item, shipment = self.shipment(
            business_date=date(2026, 8, 31),
            goods=Decimal('100.00'), cost=Decimal('40.00'),
            transport_fee=Decimal('10.00'), key='cross-month', customer=customer,
        )
        self.transport_cost(
            order,
            business_date=date(2026, 9, 1),
            amount=Decimal('20.00'), key='cross-month',
        )
        receipt_ledger = self.post(
            LedgerTransaction.TransactionType.SALES_RECEIPT,
            date(2026, 9, 1),
            [
                PostingInput(
                    account=self.account,
                    currency='CNY', amount=Decimal('110.00'), cny_amount=Decimal('110.00'),
                ),
                PostingInput(
                    category=LedgerPosting.Category.ACCOUNTS_RECEIVABLE,
                    currency='CNY', amount=Decimal('-110.00'), cny_amount=Decimal('-110.00'),
                ),
            ],
            'cross-month-receipt-ledger',
        )
        SalesReceipt.objects.create(
            sales_order=order,
            amount_cny=Decimal('110.00'),
            fund_account=self.account,
            business_date=date(2026, 9, 1),
            ledger_transaction=receipt_ledger,
            operator=self.operator,
        )
        reversal = reverse_ledger_transaction(
            original_transaction=shipment.ledger_transaction,
            business_date=date(2026, 9, 2),
            operator=self.operator,
            idempotency_key='cross-month-return-ledger',
            reason='次月退货',
        )
        with transaction.atomic(), ledger_mutation_scope(
            reason='sales_return_fact',
            model='cigars.SalesReturn',
            operator=self.operator,
        ):
            SalesReturn.objects.create(
                sales_order=order,
                sales_shipment=shipment,
                amount_cny=Decimal('110.00'),
                fifo_cost_cny=Decimal('40.00'),
                ledger_transaction=reversal,
                business_date=date(2026, 9, 2),
                operator=self.operator,
                reason='次月退货',
            )

        from accounting.monthly_reports import monthly_business_report

        with patch('accounting.monthly_reports.moscow_business_date', return_value=date(2026, 9, 16)):
            august = monthly_business_report(month=date(2026, 8, 1))
            september = monthly_business_report(month=date(2026, 9, 1))

        self.assertEqual(august['profit']['sales_revenue_cny'], Decimal('110.00'))
        self.assertEqual(august['profit']['human_cost_cny'], Decimal('0.00'))
        self.assertEqual(august['rankings']['brands'][0]['human_cost_cny'], Decimal('20.00'))
        self.assertEqual(august['rankings']['products'][0]['human_cost_cny'], Decimal('20.00'))
        self.assertEqual(august['rankings']['customers'][0]['human_cost_cny'], Decimal('20.00'))
        self.assertEqual(
            august['rankings']['unallocated_human_cost_cny'], Decimal('-20.00'),
        )
        self.assertEqual(august['cash']['sales_receipts_cny'], Decimal('0.00'))
        self.assertEqual(september['cash']['sales_receipts_cny'], Decimal('110.00'))
        self.assertEqual(september['sales']['fulfillment_order_count'], 0)
        self.assertEqual(september['sales']['return_order_count'], 1)
        self.assertEqual(september['profit']['sales_revenue_cny'], Decimal('-110.00'))
        self.assertEqual(september['profit']['product_cost_cny'], Decimal('-40.00'))
        self.assertEqual(september['profit']['human_cost_cny'], Decimal('20.00'))
        self.assertEqual(september['profit']['sales_profit_cny'], Decimal('-90.00'))
        self.assertEqual(september['rankings']['brands'][0]['human_cost_cny'], Decimal('0.00'))
        self.assertEqual(september['rankings']['products'][0]['human_cost_cny'], Decimal('0.00'))
        self.assertEqual(september['rankings']['customers'][0]['human_cost_cny'], Decimal('0.00'))
        self.assertEqual(
            september['rankings']['unallocated_human_cost_cny'], Decimal('20.00'),
        )

    def test_current_month_compares_the_same_elapsed_days(self):
        from accounting.monthly_reports import monthly_business_report

        with patch('accounting.monthly_reports.moscow_business_date', return_value=date(2026, 9, 16)):
            report = monthly_business_report(month=date(2026, 9, 1))

        self.assertTrue(report['period']['is_current_month'])
        self.assertEqual(report['period']['period_end'], date(2026, 9, 16))
        self.assertEqual(report['comparison']['mode'], 'same_days_previous_month')
        self.assertEqual(report['comparison']['previous_period_start'], date(2026, 8, 1))
        self.assertEqual(report['comparison']['previous_period_end'], date(2026, 8, 16))

    def test_transport_settlement_stays_unallocated_from_rankings(self):
        order, _item, _shipment = self.shipment(
            business_date=date(2026, 8, 18),
            goods=Decimal('100.00'), cost=Decimal('40.00'),
            key='settlement-unallocated', company_pays=True,
        )
        self.transport_cost(
            order,
            business_date=date(2026, 8, 18),
            amount=Decimal('20.00'), key='settlement-unallocated',
        )
        self.post(
            LedgerTransaction.TransactionType.EXPENSE,
            date(2026, 8, 19),
            [
                PostingInput(
                    category=LedgerPosting.Category.TRANSPORT_SETTLEMENT_EXPENSE,
                    currency='CNY', amount=Decimal('15.00'), cny_amount=Decimal('15.00'),
                ),
                PostingInput(
                    account=self.account,
                    currency='CNY', amount=Decimal('-15.00'), cny_amount=Decimal('-15.00'),
                ),
            ],
            'settlement-unallocated-ledger',
        )

        from accounting.monthly_reports import monthly_business_report

        with patch('accounting.monthly_reports.moscow_business_date', return_value=date(2026, 9, 16)):
            report = monthly_business_report(month=date(2026, 8, 1))

        self.assertEqual(report['profit']['human_cost_cny'], Decimal('35.00'))
        self.assertEqual(report['rankings']['brands'][0]['human_cost_cny'], Decimal('20.00'))
        self.assertEqual(
            report['rankings']['unallocated_human_cost_cny'], Decimal('15.00'),
        )

    def test_historical_inventory_uses_ledger_and_customer_identity_excludes_guests(self):
        self.post(
            LedgerTransaction.TransactionType.INVENTORY_ADJUSTMENT,
            date(2026, 8, 10),
            [
                PostingInput(
                    category=LedgerPosting.Category.INVENTORY,
                    currency='CNY', amount=Decimal('100.00'), cny_amount=Decimal('100.00'),
                ),
                PostingInput(
                    category=LedgerPosting.Category.INVENTORY_ADJUSTMENT_GAIN,
                    currency='CNY', amount=Decimal('-100.00'), cny_amount=Decimal('-100.00'),
                ),
            ],
            'inventory-opening',
        )
        self.post(
            LedgerTransaction.TransactionType.PURCHASE_RECEIPT,
            date(2026, 9, 2),
            [
                PostingInput(
                    category=LedgerPosting.Category.INVENTORY,
                    currency='CNY', amount=Decimal('50.00'), cny_amount=Decimal('50.00'),
                ),
                PostingInput(
                    category=LedgerPosting.Category.PURCHASE_IN_TRANSIT,
                    currency='CNY', amount=Decimal('-50.00'), cny_amount=Decimal('-50.00'),
                ),
            ],
            'inventory-receipt',
        )
        self.post(
            LedgerTransaction.TransactionType.INVENTORY_ADJUSTMENT,
            date(2026, 9, 20),
            [
                PostingInput(
                    category=LedgerPosting.Category.INVENTORY,
                    currency='CNY', amount=Decimal('-10.00'), cny_amount=Decimal('-10.00'),
                ),
                PostingInput(
                    category=LedgerPosting.Category.INVENTORY_ADJUSTMENT_LOSS,
                    currency='CNY', amount=Decimal('10.00'), cny_amount=Decimal('10.00'),
                ),
            ],
            'inventory-adjustment',
        )
        new_customer = Customer.objects.create(name='八月新客')
        existing_customer = Customer.objects.create(name='历史客户')
        self.shipment(
            business_date=date(2026, 8, 20), goods=Decimal('10.00'),
            cost=Decimal('0.00'), key='existing-august', customer=existing_customer,
            company_pays=True,
        )
        self.shipment(
            business_date=date(2026, 9, 10), goods=Decimal('30.00'),
            cost=Decimal('20.00'), key='new-first', customer=new_customer,
            company_pays=True,
        )
        self.shipment(
            business_date=date(2026, 9, 12), goods=Decimal('20.00'),
            cost=Decimal('0.00'), key='new-repeat', customer=new_customer,
            company_pays=True,
        )
        self.shipment(
            business_date=date(2026, 9, 14), goods=Decimal('20.00'),
            cost=Decimal('0.00'), key='existing-september', customer=existing_customer,
            company_pays=True,
        )
        self.shipment(
            business_date=date(2026, 9, 16), goods=Decimal('20.00'),
            cost=Decimal('0.00'), key='guest', company_pays=True,
        )

        from accounting.monthly_reports import monthly_business_report

        with patch('accounting.monthly_reports.moscow_business_date', return_value=date(2026, 10, 16)):
            report = monthly_business_report(month=date(2026, 9, 1))

        self.assertEqual(report['inventory']['opening_cost_cny'], Decimal('100.00'))
        self.assertEqual(report['inventory']['received_cost_cny'], Decimal('50.00'))
        self.assertEqual(report['inventory']['product_cost_consumed_cny'], Decimal('20.00'))
        self.assertEqual(report['inventory']['adjustment_net_cny'], Decimal('-10.00'))
        self.assertEqual(report['inventory']['closing_cost_cny'], Decimal('120.00'))
        self.assertEqual(report['inventory']['average_cost_cny'], Decimal('110.00'))
        self.assertEqual(report['customers']['fulfilled_customer_count'], 2)
        self.assertEqual(report['customers']['new_customer_count'], 1)
        self.assertEqual(report['customers']['repeat_customer_count'], 2)
        self.assertTrue(report['customers']['guest_orders_excluded'])
        self.assertEqual(report['inventory']['warnings']['status'], 'unavailable')

    def test_api_validation_and_legacy_monthly_profit_compatibility(self):
        self.client.force_login(self.operator)

        invalid = self.client.get('/api/accounting/reports/monthly-business/?month=bad')
        legacy = self.client.get('/api/accounting/reports/monthly-profit/?month=2026-08')
        with patch('accounting.monthly_reports.moscow_business_date', return_value=date(2026, 9, 16)):
            valid = self.client.get('/api/accounting/reports/monthly-business/?month=2026-08')

        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(invalid.json()['error'], 'month 必须是 YYYY-MM')
        self.assertEqual(legacy.status_code, 200)
        self.assertEqual(valid.status_code, 200)
        self.assertEqual(valid.json()['period']['month'], '2026-08')
        self.assertIn('profit', valid.json())
