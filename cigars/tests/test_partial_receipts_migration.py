from datetime import date
from decimal import Decimal

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase, tag


@tag('migration', 'migration-other')
class PartialReceiptsMigrationTest(TransactionTestCase):
    def test_existing_receipt_refund_and_ledger_survive_and_more_receipts_are_allowed(self):
        before = [('cigars', '0043_alter_salesreceipt_options_and_more'), ('privnote', '0011_access_events')]
        after = [('cigars', '0044_sales_partial_receipts'), ('privnote', '0012_sales_partial_receipts')]
        executor = MigrationExecutor(connection)
        leaves = executor.loader.graph.leaf_nodes()
        self.addCleanup(lambda: MigrationExecutor(connection).migrate(leaves))
        executor.migrate(before)
        apps = MigrationExecutor(connection).loader.project_state(before).apps
        user = apps.get_model('cigars', 'User').objects.create(username='partial-migration')
        account = apps.get_model('accounting', 'FundAccount').objects.create(name='历史账户', currency='CNY', creation_idempotency_key='migration-account')
        order = apps.get_model('cigars', 'SalesOrder').objects.create(operator_id=user.pk, amount_due_cny=100, fulfillment_status='cancelled', payment_status='refunded')
        tx_model = apps.get_model('accounting', 'LedgerTransaction')
        receipt_tx = tx_model.objects.create(transaction_type='sales_receipt', status='posted', business_date=date(2026, 9, 11), operator_id=user.pk, source_type='sales_order', source_id=str(order.pk), idempotency_key='migration-receipt', effective_sequence=1)
        refund_tx = tx_model.objects.create(transaction_type='sales_refund', status='posted', business_date=date(2026, 9, 12), operator_id=user.pk, source_type='sales_order', source_id=str(order.pk), idempotency_key='migration-refund', effective_sequence=2)
        apps.get_model('cigars', 'SalesReceipt').objects.create(sales_order_id=order.pk, amount_cny=100, fund_account_id=account.pk, ledger_transaction_id=receipt_tx.pk, operator_id=user.pk, business_date=date(2026, 9, 11))
        apps.get_model('cigars', 'SalesRefund').objects.create(sales_order_id=order.pk, amount_cny=100, fund_account_id=account.pk, ledger_transaction_id=refund_tx.pk, operator_id=user.pk, business_date=date(2026, 9, 12))
        snapshots = {name: list(apps.get_model(app, name).objects.values()) for app, name in [('cigars', 'SalesReceipt'), ('cigars', 'SalesRefund'), ('accounting', 'LedgerTransaction')]}
        MigrationExecutor(connection).migrate(after)
        apps = MigrationExecutor(connection).loader.project_state(after).apps
        for app, name in [('cigars', 'SalesReceipt'), ('cigars', 'SalesRefund'), ('accounting', 'LedgerTransaction')]:
            self.assertEqual(list(apps.get_model(app, name).objects.values()), snapshots[name])
        with connection.cursor() as cursor:
            constraints = connection.introspection.get_constraints(cursor, 'cigars_salesreceipt')
            self.assertNotIn('sales_receipt_one_active_per_order', constraints)
            constraints = connection.introspection.get_constraints(cursor, 'privnote_paymentsubmission')
            self.assertNotIn('payment_submission_one_accepted_per_order', constraints)
        self.assertTrue(apps.get_model('cigars', 'SalesRefund')._meta.get_field('fund_account').null)
        self.assertEqual(apps.get_model('cigars', 'SalesReceipt').objects.get().amount_cny, Decimal('100'))
