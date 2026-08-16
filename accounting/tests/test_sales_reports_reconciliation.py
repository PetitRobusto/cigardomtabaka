from datetime import date, datetime, timezone as dt_timezone
from decimal import Decimal
from unittest.mock import patch

from django.db import connection, transaction, models
from django.db import OperationalError
from django.db.migrations.executor import MigrationExecutor
from django.test import Client, TestCase
from django.test import TransactionTestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from django.core.exceptions import ValidationError

from accounting.models import (
    AccountReconciliation,
    Day1Initialization,
    FundAccount,
    LedgerMutationError,
    LedgerPosting,
    LedgerTransaction,
)
from accounting.services import PostingInput
from cigars.models import Brand, Cigar, PurchaseOrder, PurchaseOrderItem, Supplier, User
from accounting.mutation_scope import ledger_mutation_scope


class SalesReportsAndReconciliationTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.operator = User.objects.create_user(
            'reports-operator', password='pass', is_staff=True,
        )
        self.non_staff = User.objects.create_user('reports-customer', password='pass')
        Day1Initialization.objects.create(
            status=Day1Initialization.Status.COMPLETED,
            business_date=date(2026, 8, 10), completed_by=self.operator,
        )

    def test_account_rows_use_fixed_query_count(self):
        """账户摘要应一次聚合流水，查询数不能随账户数量线性增长。"""
        from accounting.selectors import _account_rows

        FundAccount.objects.create(
            name='查询数账户 0', currency=FundAccount.Currency.CNY,
            creation_idempotency_key='account-row-query-0',
        )
        for index in range(1, 5):
            FundAccount.objects.create(
                name=f'查询数账户 {index}', currency=FundAccount.Currency.CNY,
                creation_idempotency_key=f'account-row-query-{index}',
            )

        with CaptureQueriesContext(connection) as captured:
            rows = _account_rows(as_of=date(2026, 8, 10))

        self.assertEqual(len(rows), 5)
        self.assertEqual(len(captured), 2)


    def in_transit_order(self, **values):
        from accounting.purchase_actions import pay_purchase_order
        if not hasattr(self, 'transit_cigar'):
            brand = Brand.objects.create(english_name='Reports Brand', name='报表品牌')
            self.transit_cigar = Cigar.objects.create(
                brand=brand.english_name, english_name='Reports Cigar', name='报表雪茄',
            )
        if not hasattr(self, 'transit_account'):
            from accounting.services import record_opening_balance
            self.transit_account = FundAccount.objects.create(
                name='报表卢布账户', currency=FundAccount.Currency.RUB,
                creation_idempotency_key='reports-transit-rub',
            )
            record_opening_balance(
                self.transit_account, Decimal('1000.00'), Decimal('880.00'),
                LedgerPosting.Category.OPENING_CAPITAL, date(2026, 8, 10),
                self.operator, 'reports-transit-opening',
            )
        business_date = values.pop('business_date')
        paid_at = values.pop('paid_at')
        order = PurchaseOrder.objects.create(
            supplier=values.pop('supplier'), operator=self.operator,
            rub_total=values.pop('rub_total'),
            exchange_rate=values.pop('exchange_rate'),
            cny_total=values.pop('cny_total'),
        )
        PurchaseOrderItem.objects.create(
            purchase_order=order, cigar=self.transit_cigar,
            quantity=1, box_size=1, box_quantity=1,
            unit_price_rub_per_box=order.rub_total,
            packaging_status=PurchaseOrderItem.PackagingStatus.UNREPRESENTABLE,
        )
        expected_cost = values.pop('paid_cny_cost')
        payment = pay_purchase_order(
            purchase_order_id=order.id, rub_account_id=self.transit_account.id,
            business_date=business_date, operator=self.operator,
            idempotency_key=f'reports-payment-{order.id}',
        )
        self.assertEqual(payment.cny_cost, expected_cost)
        self.assertFalse(values)
        order.refresh_from_db()
        with transaction.atomic(), ledger_mutation_scope(
            reason='purchase_payment', model='cigars.PurchaseOrder',
            operator=self.operator, allowed_fields={'status', 'paid_cny_cost', 'paid_at'},
        ):
            order.paid_at = paid_at
            models.Model.save(order, update_fields=['paid_at'])
        return order

    def posted_transaction(self, transaction_type, business_date, postings, key):
        from accounting.services import post_transaction

        return post_transaction(
            transaction_type=transaction_type,
            business_date=business_date,
            postings=postings,
            operator=self.operator,
            idempotency_key=key,
            source_type='test',
            source_id=key,
        )

    def test_monthly_profit_uses_business_date_and_posted_only(self):
        from accounting.selectors import monthly_profit

        transport_account = FundAccount.objects.create(
            name='月报人肉费账户', currency=FundAccount.Currency.CNY,
            creation_idempotency_key='monthly-transport-account',
        )
        from accounting.services import record_opening_balance
        record_opening_balance(
            transport_account, Decimal('10.00'), Decimal('10.00'),
            LedgerPosting.Category.OPENING_CAPITAL, date(2026, 8, 10),
            self.operator, 'monthly-transport-opening',
        )
        self.posted_transaction(
            LedgerTransaction.TransactionType.SALES_SHIPMENT,
            date(2026, 8, 15),
            [
                PostingInput(category=LedgerPosting.Category.ACCOUNTS_RECEIVABLE, currency='CNY', amount=Decimal('95.00'), cny_amount=Decimal('95.00')),
                PostingInput(category=LedgerPosting.Category.SALES_REVENUE, currency='CNY', amount=Decimal('-90.00'), cny_amount=Decimal('-90.00')),
                PostingInput(category=LedgerPosting.Category.CUSTOMER_TRANSPORT_REVENUE, currency='CNY', amount=Decimal('-5.00'), cny_amount=Decimal('-5.00')),
                PostingInput(category=LedgerPosting.Category.COST_OF_GOODS_SOLD, currency='CNY', amount=Decimal('30.00'), cny_amount=Decimal('30.00')),
                PostingInput(category=LedgerPosting.Category.INVENTORY, currency='CNY', amount=Decimal('-30.00'), cny_amount=Decimal('-30.00')),
            ],
            'monthly-sales-shipment',
        )
        self.posted_transaction(
            LedgerTransaction.TransactionType.SALES_TRANSPORT_COST,
            date(2026, 8, 15),
            [
                PostingInput(category=LedgerPosting.Category.TRANSPORT_EXPENSE, currency='CNY', amount=Decimal('10.00'), cny_amount=Decimal('10.00')),
                PostingInput(account=transport_account, currency='CNY', amount=Decimal('-10.00'), cny_amount=Decimal('-10.00')),
            ],
            'monthly-transport-cost',
        )

        from accounting.selectors import monthly_profit

        monthly = monthly_profit(month=date(2026, 8, 1))
        self.assertEqual(monthly['sales_revenue_cny'], Decimal('-90.00'))
        self.assertEqual(monthly['customer_transport_revenue_cny'], Decimal('-5.00'))
        self.assertEqual(monthly['cost_of_goods_sold_cny'], Decimal('30.00'))
        self.assertEqual(monthly['transport_expense_cny'], Decimal('10.00'))
        self.assertEqual(monthly['net_profit_cny'], Decimal('55.00'))
        self.assertEqual(monthly['period_start'], date(2026, 8, 1))
        self.assertEqual(monthly['period_end'], date(2026, 8, 31))

    def test_monthly_profit_excludes_other_month_and_draft_transactions(self):
        from accounting.selectors import monthly_profit

        self.posted_transaction(
            LedgerTransaction.TransactionType.SALES_SHIPMENT,
            date(2026, 9, 1),
            [
                PostingInput(category=LedgerPosting.Category.ACCOUNTS_RECEIVABLE, currency='CNY', amount=Decimal('10.00'), cny_amount=Decimal('10.00')),
                PostingInput(category=LedgerPosting.Category.SALES_REVENUE, currency='CNY', amount=Decimal('-10.00'), cny_amount=Decimal('-10.00')),
            ],
            'monthly-outside-period',
        )
        LedgerTransaction.objects.create(
            transaction_type=LedgerTransaction.TransactionType.SALES_SHIPMENT,
            business_date=date(2026, 8, 20), operator=self.operator,
        )

        monthly = monthly_profit(month=date(2026, 8, 1))
        self.assertNotIn('draft_transaction_total', monthly)
        self.assertEqual(monthly['transaction_count'], 0)

    def test_cross_month_return_reverses_profit_in_return_month(self):
        """跨月退货保留原月利润，并在退货月记录相反利润。"""
        original = self.posted_transaction(
            LedgerTransaction.TransactionType.SALES_SHIPMENT,
            date(2026, 8, 31),
            [
                PostingInput(category=LedgerPosting.Category.ACCOUNTS_RECEIVABLE, currency='CNY', amount=Decimal('100.00'), cny_amount=Decimal('100.00')),
                PostingInput(category=LedgerPosting.Category.SALES_REVENUE, currency='CNY', amount=Decimal('-100.00'), cny_amount=Decimal('-100.00')),
                PostingInput(category=LedgerPosting.Category.COST_OF_GOODS_SOLD, currency='CNY', amount=Decimal('40.00'), cny_amount=Decimal('40.00')),
                PostingInput(category=LedgerPosting.Category.INVENTORY, currency='CNY', amount=Decimal('-40.00'), cny_amount=Decimal('-40.00')),
            ],
            'cross-month-shipment',
        )
        from accounting.services import reverse_ledger_transaction

        reverse_ledger_transaction(
            original_transaction=original,
            business_date=date(2026, 9, 1),
            operator=self.operator,
            idempotency_key='cross-month-return',
            reason='次月整单退货',
        )

        from accounting.selectors import monthly_profit

        august = monthly_profit(month=date(2026, 8, 1))
        september = monthly_profit(month=date(2026, 9, 1))
        self.assertEqual(august['net_profit_cny'], Decimal('60.00'))
        self.assertEqual(september['net_profit_cny'], Decimal('-60.00'))

    def test_monthly_profit_includes_expenses_adjustments_and_reconciliation_facts(self):
        """Monthly profit keeps expense, adjustment, and reconciliation facts."""
        categories = {
            LedgerPosting.Category.SALES_REVENUE: Decimal('-500.00'),
            LedgerPosting.Category.COST_OF_GOODS_SOLD: Decimal('0.00'),
            LedgerPosting.Category.SALARY_EXPENSE: Decimal('100.00'),
            LedgerPosting.Category.TRANSPORT_EXPENSE: Decimal('20.00'),
            LedgerPosting.Category.INVENTORY_ADJUSTMENT_GAIN: Decimal('-7.00'),
            LedgerPosting.Category.INVENTORY_ADJUSTMENT_LOSS: Decimal('3.00'),
            LedgerPosting.Category.RECONCILIATION_GAIN: Decimal('-2.00'),
            LedgerPosting.Category.RECONCILIATION_LOSS: Decimal('1.00'),
        }
        transport_amount = categories.pop(LedgerPosting.Category.TRANSPORT_EXPENSE)
        balancing_account = FundAccount.objects.create(
            name='月报分类平衡账户', currency=FundAccount.Currency.CNY,
            creation_idempotency_key='profit-category-account',
        )
        self.posted_transaction(
            LedgerTransaction.TransactionType.SALES_SHIPMENT,
            date(2026, 8, 20),
            [
                *[
                    PostingInput(category=category, currency='CNY', amount=amount, cny_amount=amount)
                    for category, amount in categories.items()
                ],
                PostingInput(account=balancing_account, currency='CNY', amount=Decimal('405.00'), cny_amount=Decimal('405.00')),
            ],
            'profit-categories',
        )
        self.posted_transaction(
            LedgerTransaction.TransactionType.SALES_TRANSPORT_COST,
            date(2026, 8, 20),
            [
                PostingInput(category=LedgerPosting.Category.TRANSPORT_EXPENSE, currency='CNY', amount=transport_amount, cny_amount=transport_amount),
                PostingInput(account=balancing_account, currency='CNY', amount=-transport_amount, cny_amount=-transport_amount),
            ],
            'profit-transport-cost',
        )

        from accounting.selectors import monthly_profit

        monthly = monthly_profit(month=date(2026, 8, 1))

        self.assertEqual(monthly['net_profit_cny'], Decimal('385.00'))
        self.assertEqual(monthly['salary_expense_cny'], Decimal('100.00'))
        self.assertEqual(monthly['inventory_adjustment_gain_cny'], Decimal('7.00'))
        self.assertEqual(monthly['inventory_adjustment_loss_cny'], Decimal('3.00'))
        self.assertEqual(monthly['reconciliation_gain_cny'], Decimal('2.00'))
        self.assertEqual(monthly['reconciliation_loss_cny'], Decimal('1.00'))

    def test_summary_as_of_includes_accounts_ar_prepayment_inventory_and_in_transit(self):
        from accounting.selectors import accounting_summary

        account = FundAccount.objects.create(
            name='摘要人民币账户', currency=FundAccount.Currency.CNY,
            creation_idempotency_key='summary-cny',
        )
        supplier = Supplier.objects.create(name='摘要供应商')
        self.in_transit_order(
            supplier=supplier, rub_total=Decimal('100.00'), exchange_rate=Decimal('12.0000'),
            cny_total=Decimal('100.00'), paid_cny_cost=Decimal('88.00'),
            business_date=date(2026, 8, 10),
            paid_at=datetime(2026, 8, 10, 20, 30, tzinfo=dt_timezone.utc),
        )
        self.in_transit_order(
            supplier=supplier, rub_total=Decimal('50.00'), exchange_rate=Decimal('12.0000'),
            cny_total=Decimal('50.00'), paid_cny_cost=Decimal('44.00'),
            business_date=date(2026, 8, 11),
            paid_at=timezone.make_aware(datetime(2026, 8, 11, 12)),
        )
        self.posted_transaction(
            LedgerTransaction.TransactionType.SALES_RECEIPT,
            date(2026, 8, 10),
            [
                PostingInput(category=LedgerPosting.Category.ACCOUNTS_RECEIVABLE, currency='CNY', amount=Decimal('50.00'), cny_amount=Decimal('50.00')),
                PostingInput(category=LedgerPosting.Category.CUSTOMER_PREPAYMENTS, currency='CNY', amount=Decimal('-50.00'), cny_amount=Decimal('-50.00')),
            ],
            'summary-receivable-prepayment',
        )
        with patch('accounting.selectors.moscow_business_date', return_value=date(2026, 8, 10)):
            summary = accounting_summary(as_of=date(2026, 8, 10))
        self.assertIn('fund_accounts', summary)
        self.assertIn('accounts_receivable_cny', summary)
        self.assertIn('customer_prepayments_cny', summary)
        self.assertIn('inventory_remaining_cost_cny', summary)
        self.assertIn('purchase_in_transit_cny', summary)
        self.assertEqual(summary['fund_accounts'][0]['account_id'], account.id)
        self.assertEqual(summary['accounts_receivable_cny'], Decimal('50.00'))
        self.assertEqual(summary['customer_prepayments_cny'], Decimal('50.00'))
        self.assertEqual(summary['purchase_in_transit_cny'], Decimal('88.00'))

    def test_summary_rejects_non_today_as_of(self):
        from accounting.selectors import accounting_summary

        with patch('accounting.selectors.moscow_business_date', return_value=date(2026, 8, 12)):
            with self.assertRaisesRegex(ValueError, 'as_of 仅支持当前日期'):
                accounting_summary(as_of=date(2026, 8, 11))

    def test_summary_api_rejects_non_today_as_of(self):
        self.client.force_login(self.operator)

        with patch('accounting.selectors.moscow_business_date', return_value=date(2026, 8, 12)):
            response = self.client.get('/api/accounting/reports/summary/?as_of=2026-08-11')

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['error'], 'as_of 仅支持当前日期')

    def test_summary_api_allows_today_current_snapshot(self):
        supplier = Supplier.objects.create(name='今日摘要供应商')
        self.in_transit_order(
            supplier=supplier, rub_total=Decimal('120.00'), exchange_rate=Decimal('12.0000'),
            cny_total=None, paid_cny_cost=Decimal('105.60'),
            business_date=date(2026, 8, 12),
            paid_at=timezone.make_aware(datetime(2026, 8, 12, 12)),
        )
        self.client.force_login(self.operator)

        with patch('accounting.selectors.moscow_business_date', return_value=date(2026, 8, 12)):
            response = self.client.get('/api/accounting/reports/summary/?as_of=2026-08-12')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['purchase_in_transit_cny'], '105.60')

    def test_reconciliation_creates_snapshot_actual_and_difference_once_per_account_date(self):
        from accounting.services import (
            confirm_reconciliation, create_reconciliation, record_opening_balance,
        )

        account = FundAccount.objects.create(
            name='对账人民币账户', currency=FundAccount.Currency.CNY,
            creation_idempotency_key='reconciliation-cny',
        )
        record_opening_balance(
            account, Decimal('100.00'), Decimal('100.00'),
            LedgerPosting.Category.OPENING_CAPITAL, date(2026, 8, 10),
            self.operator, 'reconciliation-opening',
        )
        reconciliation = create_reconciliation(
            account=account, business_date=date(2026, 8, 10),
            actual_amount=Decimal('95.00'), operator=self.operator,
            idempotency_key='reconciliation-create',
        )
        self.assertEqual(reconciliation.system_amount, Decimal('100.00'))
        self.assertEqual(reconciliation.actual_amount, Decimal('95.00'))
        self.assertEqual(reconciliation.difference, Decimal('-5.00'))
        self.assertEqual(reconciliation.status, AccountReconciliation.Status.PENDING)
        replayed = create_reconciliation(
            account=account, business_date=date(2026, 8, 10),
            actual_amount=Decimal('95.00'), operator=self.operator,
            idempotency_key='reconciliation-create',
        )
        self.assertEqual(replayed.id, reconciliation.id)
        confirmed = confirm_reconciliation(
            reconciliation_id=reconciliation.id, operator=self.operator,
            idempotency_key='reconciliation-confirm',
        )
        self.assertEqual(confirmed.status, AccountReconciliation.Status.CONFIRMED)
        replayed_confirmation = confirm_reconciliation(
            reconciliation_id=reconciliation.id, operator=self.operator,
            idempotency_key='reconciliation-confirm',
        )
        self.assertEqual(replayed_confirmation.id, confirmed.id)
        with self.assertRaises(Exception):
            confirm_reconciliation(
                reconciliation_id=reconciliation.id, operator=self.operator,
                idempotency_key='reconciliation-confirm-again',
            )
        with self.assertRaises(Exception):
            create_reconciliation(
                account=account, business_date=date(2026, 8, 10),
                actual_amount=Decimal('90.00'), operator=self.operator,
                idempotency_key='reconciliation-duplicate',
            )
        self.assertEqual(
            LedgerTransaction.objects.exclude(
                transaction_type=LedgerTransaction.TransactionType.OPENING_BALANCE,
            ).count(),
            0,
        )

    def test_reconciliation_staff_api_and_invalid_inputs_are_json(self):
        self.client.force_login(self.non_staff)
        response = self.client.post(
            '/api/accounting/reconciliations/', data={}, content_type='application/json',
            HTTP_IDEMPOTENCY_KEY='reconciliation-api-denied',
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response['Content-Type'], 'application/json')

        self.client.force_login(self.operator)
        for payload in (
            {'account_id': 999999, 'business_date': 'not-a-date', 'actual_amount': '1.00'},
            {'account_id': 999999, 'business_date': '2026-08-10', 'actual_amount': '1.001'},
        ):
            response = self.client.post(
                '/api/accounting/reconciliations/', data=payload,
                content_type='application/json',
                HTTP_IDEMPOTENCY_KEY='reconciliation-api-invalid-' + str(len(payload)),
            )
            self.assertIn(response.status_code, (400, 404, 409))
            self.assertLess(response.status_code, 500)
            self.assertEqual(response['Content-Type'], 'application/json')

    def test_reports_and_reconciliation_success_api(self):
        from accounting.services import record_opening_balance

        account = FundAccount.objects.create(
            name='API 对账人民币账户', currency=FundAccount.Currency.CNY,
            creation_idempotency_key='reconciliation-api-cny',
        )
        record_opening_balance(
            account, Decimal('100.00'), Decimal('100.00'),
            LedgerPosting.Category.OPENING_CAPITAL, date(2026, 8, 10),
            self.operator, 'reconciliation-api-opening',
        )
        self.client.force_login(self.operator)
        monthly = self.client.get('/api/accounting/reports/monthly-profit/?month=2026-08')
        self.assertEqual(monthly.status_code, 200)
        self.assertEqual(monthly.json()['period_start'], '2026-08-01')
        self.assertEqual(monthly.json()['net_profit_cny'], '0.00')
        with patch('accounting.selectors.moscow_business_date', return_value=date(2026, 8, 10)):
            summary = self.client.get('/api/accounting/reports/summary/?as_of=2026-08-10')
        self.assertEqual(summary.status_code, 200)
        self.assertEqual(summary.json()['fund_accounts'][0]['original_balance'], '100.00000000')
        created = self.client.post(
            '/api/accounting/reconciliations/',
            data={'account_id': account.id, 'business_date': '2026-08-10', 'actual_amount': '95.00'},
            content_type='application/json',
            HTTP_IDEMPOTENCY_KEY='reconciliation-api-create',
        )
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()['reconciliation']['difference'], '-5.00000000')
        reconciliation_id = created.json()['reconciliation']['id']
        confirmed = self.client.post(
            f'/api/accounting/reconciliations/{reconciliation_id}/confirm/',
            data={}, content_type='application/json',
            HTTP_IDEMPOTENCY_KEY='reconciliation-api-confirm',
        )
        self.assertEqual(confirmed.status_code, 200)
        self.assertEqual(confirmed.json()['reconciliation']['status'], 'confirmed')

    def test_reconciliation_rejects_before_cutover_and_max_original_amount(self):
        from accounting.services import LedgerError, create_reconciliation

        account = FundAccount.objects.create(
            name='对账边界账户', currency=FundAccount.Currency.CNY,
            creation_idempotency_key='reconciliation-boundary-account',
        )
        with self.assertRaises(LedgerError):
            create_reconciliation(
                account=account, business_date=date(2026, 8, 9),
                actual_amount=Decimal('1.00'), operator=self.operator,
                idempotency_key='reconciliation-before-cutover',
            )
        with self.assertRaises(LedgerError):
            create_reconciliation(
                account=account, business_date=date(2026, 8, 10),
                actual_amount=Decimal('1000000000000.00'), operator=self.operator,
                idempotency_key='reconciliation-too-large',
            )

    def test_confirmation_audits_first_confirmer_and_service_returns_replay_result(self):
        from accounting.services import confirm_reconciliation, create_reconciliation

        confirmer = User.objects.create_user(
            'reports-confirmer', password='pass', is_staff=True,
        )
        account = FundAccount.objects.create(
            name='对账审计账户', currency=FundAccount.Currency.CNY,
            creation_idempotency_key='reconciliation-audit-account',
        )
        created = create_reconciliation(
            account=account, business_date=date(2026, 8, 10),
            actual_amount=Decimal('1.00'), operator=self.operator,
            idempotency_key='reconciliation-audit-create', return_result=True,
        )
        self.assertTrue(created.created)
        replay = create_reconciliation(
            account=account, business_date=date(2026, 8, 10),
            actual_amount=Decimal('1.00'), operator=self.operator,
            idempotency_key='reconciliation-audit-create', return_result=True,
        )
        self.assertFalse(replay.created)
        confirmed = confirm_reconciliation(
            reconciliation_id=created.reconciliation.id, operator=confirmer,
            idempotency_key='reconciliation-audit-confirm', return_result=True,
        )
        self.assertTrue(confirmed.created)
        self.assertEqual(confirmed.reconciliation.confirmer_id, confirmer.id)
        replayed = confirm_reconciliation(
            reconciliation_id=created.reconciliation.id, operator=confirmer,
            idempotency_key='reconciliation-audit-confirm', return_result=True,
        )
        self.assertFalse(replayed.created)
        from accounting.services import LedgerError
        with self.assertRaises(LedgerError):
            confirm_reconciliation(
                reconciliation_id=created.reconciliation.id, operator=self.operator,
                idempotency_key='reconciliation-audit-confirm', return_result=True,
            )

    def test_reconciliation_queryset_blocks_ordinary_mutations(self):
        from accounting.services import create_reconciliation

        account = FundAccount.objects.create(
            name='对账 ORM 账户', currency=FundAccount.Currency.CNY,
            creation_idempotency_key='reconciliation-orm-account',
        )
        record = create_reconciliation(
            account=account, business_date=date(2026, 8, 10),
            actual_amount=Decimal('1.00'), operator=self.operator,
            idempotency_key='reconciliation-orm-create',
        )
        with self.assertRaises(LedgerMutationError):
            AccountReconciliation.objects.filter(pk=record.pk).update(note='bypass')
        with self.assertRaises(LedgerMutationError):
            AccountReconciliation.objects.bulk_update([record], ['note'])
        with self.assertRaises(LedgerMutationError):
            AccountReconciliation.objects.bulk_create([record])
        with self.assertRaises(LedgerMutationError):
            AccountReconciliation.objects.create(
                account=account, business_date=date(2026, 8, 11),
                system_amount=Decimal('0.00'), actual_amount=Decimal('0.00'),
                difference=Decimal('0.00'), operator=self.operator,
                creation_idempotency_key='reconciliation-forged-create',
            )
        with self.assertRaises(LedgerMutationError):
            AccountReconciliation.objects.get_or_create(
                account=account, business_date=date(2026, 8, 11),
                defaults={
                    'system_amount': Decimal('0.00'),
                    'actual_amount': Decimal('0.00'),
                    'difference': Decimal('0.00'),
                    'operator': self.operator,
                    'creation_idempotency_key': 'reconciliation-forged-get-create',
                },
            )
        with self.assertRaises(LedgerMutationError):
            AccountReconciliation.objects.filter(pk=record.pk).update_or_create(
                defaults={'note': 'bypass'}, pk=record.pk,
            )
        with self.assertRaises(LedgerMutationError):
            AccountReconciliation.objects.filter(pk=record.pk).delete()
        record.note = 'instance bypass'
        with self.assertRaises(LedgerMutationError):
            record.save(update_fields=['note'])
        with self.assertRaises(LedgerMutationError):
            record.delete()

    def test_reconciliation_api_replay_conflict_limit_and_method_statuses(self):
        self.client.force_login(self.operator)
        unsupported = self.client.put(
            '/api/accounting/reconciliations/', data='{}',
            content_type='application/json',
        )
        self.assertEqual(unsupported.status_code, 405)
        invalid_limit = self.client.get('/api/accounting/reconciliations/?limit=0')
        self.assertEqual(invalid_limit.status_code, 400)
        too_large_limit = self.client.get('/api/accounting/reconciliations/?limit=501')
        self.assertEqual(too_large_limit.status_code, 400)
        account = FundAccount.objects.create(
            name='对账 API 冲突账户', currency=FundAccount.Currency.CNY,
            creation_idempotency_key='reconciliation-api-conflict-account',
        )
        payload = {
            'account_id': account.id, 'business_date': '2026-08-10',
            'actual_amount': '1.00',
        }
        first = self.client.post(
            '/api/accounting/reconciliations/', data=payload,
            content_type='application/json', HTTP_IDEMPOTENCY_KEY='reconciliation-api-replay',
        )
        replay = self.client.post(
            '/api/accounting/reconciliations/', data=payload,
            content_type='application/json', HTTP_IDEMPOTENCY_KEY='reconciliation-api-replay',
        )
        self.assertEqual(first.status_code, 201)
        self.assertEqual(replay.status_code, 200)
        conflict = self.client.post(
            '/api/accounting/reconciliations/',
            data={**payload, 'actual_amount': '2.00'},
            content_type='application/json', HTTP_IDEMPOTENCY_KEY='reconciliation-api-replay',
        )
        self.assertEqual(conflict.status_code, 409)

    def test_reconciliation_api_returns_json_when_sqlite_lock_retries_exhaust(self):
        self.client.force_login(self.operator)
        account = FundAccount.objects.create(
            name='对账锁冲突账户', currency=FundAccount.Currency.CNY,
            creation_idempotency_key='reconciliation-api-locked-account',
        )
        with patch(
            'accounting.views.create_reconciliation',
            side_effect=OperationalError('database is locked'),
        ):
            response = self.client.post(
                '/api/accounting/reconciliations/',
                data={
                    'account_id': account.id, 'business_date': '2026-08-10',
                    'actual_amount': '1.00',
                },
                content_type='application/json',
                HTTP_IDEMPOTENCY_KEY='reconciliation-api-locked',
            )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {'error': '账务系统繁忙，请重试', 'code': 'busy', 'details': {}})


class AccountReconciliationIdempotencyMigrationTest(TransactionTestCase):
    migrate_from = [('accounting', '0007_accountreconciliation')]
    migrate_to = [('accounting', '0009_accountreconciliation_confirmer')]

    def tearDown(self):
        # 迁移测试必须在 Django flush 前恢复最新 schema，避免后续并发连接看不到 Day1 表。
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def test_multiple_legacy_records_receive_distinct_nonempty_creation_keys(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        legacy_apps = MigrationExecutor(connection).loader.project_state(
            self.migrate_from,
        ).apps
        User = legacy_apps.get_model('cigars', 'User')
        FundAccount = legacy_apps.get_model('accounting', 'FundAccount')
        AccountReconciliation = legacy_apps.get_model(
            'accounting', 'AccountReconciliation',
        )
        operator = User.objects.create(username='legacy-reconciliation-operator')
        first_account = FundAccount.objects.create(
            name='旧对账账户一', currency='CNY',
            creation_idempotency_key='legacy-reconciliation-account-1',
        )
        second_account = FundAccount.objects.create(
            name='旧对账账户二', currency='RUB',
            creation_idempotency_key='legacy-reconciliation-account-2',
        )
        for account in (first_account, second_account):
            AccountReconciliation.objects.create(
                account=account, business_date=date(2026, 8, 10),
                system_amount=Decimal('10.00'), actual_amount=Decimal('10.00'),
                difference=Decimal('0.00'), operator=operator,
            )

        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_to)
        migrated_apps = MigrationExecutor(connection).loader.project_state(
            self.migrate_to,
        ).apps
        migrated_records = list(
            migrated_apps.get_model('accounting', 'AccountReconciliation')
            .objects.order_by('pk')
        )

        keys = [record.creation_idempotency_key for record in migrated_records]
        self.assertEqual(len(keys), 2)
        self.assertTrue(all(keys))
        self.assertEqual(len(set(keys)), 2)
