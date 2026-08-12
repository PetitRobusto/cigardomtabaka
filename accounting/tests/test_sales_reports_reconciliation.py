from datetime import date
from decimal import Decimal

from django.test import Client, TestCase

from accounting.models import (
    AccountReconciliation,
    FundAccount,
    LedgerPosting,
    LedgerTransaction,
)
from cigars.models import PurchaseOrder, Supplier, User


class SalesReportsAndReconciliationTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.operator = User.objects.create_user(
            'reports-operator', password='pass', is_staff=True,
        )
        self.non_staff = User.objects.create_user('reports-customer', password='pass')

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

        monthly = monthly_profit(month=date(2026, 8, 1))
        self.assertNotIn('draft_transaction_total', monthly)
        self.assertEqual(monthly['transaction_count'], 0)

    def test_summary_as_of_includes_accounts_ar_prepayment_inventory_and_in_transit(self):
        from accounting.selectors import accounting_summary

        account = FundAccount.objects.create(
            name='摘要人民币账户', currency=FundAccount.Currency.CNY,
            creation_idempotency_key='summary-cny',
        )
        supplier = Supplier.objects.create(name='摘要供应商')
        PurchaseOrder.objects.create(
            supplier=supplier, status='draft', rub_total=Decimal('100.00'),
            exchange_rate=Decimal('12.0000'), cny_total=Decimal('100.00'),
            operator=self.operator,
        )
        summary = accounting_summary(as_of=date(2026, 8, 10))
        self.assertIn('fund_accounts', summary)
        self.assertIn('accounts_receivable_cny', summary)
        self.assertIn('customer_prepayments_cny', summary)
        self.assertIn('inventory_remaining_cost_cny', summary)
        self.assertIn('purchase_in_transit_cny', summary)
        self.assertEqual(summary['fund_accounts'][0]['account_id'], account.id)

    def test_reconciliation_creates_snapshot_actual_and_difference_once_per_account_date(self):
        from accounting.services import confirm_reconciliation, create_reconciliation

        account = FundAccount.objects.create(
            name='对账人民币账户', currency=FundAccount.Currency.CNY,
            creation_idempotency_key='reconciliation-cny',
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
        confirmed = confirm_reconciliation(
            reconciliation_id=reconciliation.id, operator=self.operator,
            idempotency_key='reconciliation-confirm',
        )
        self.assertEqual(confirmed.status, AccountReconciliation.Status.CONFIRMED)
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
        self.assertEqual(LedgerTransaction.objects.count(), 0)

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
