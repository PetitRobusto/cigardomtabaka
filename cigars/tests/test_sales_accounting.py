from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import connection
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.test import TestCase

from accounting.models import FundAccount, LedgerTransaction
from cigars.models import (
    Brand,
    Cigar,
    AdjustmentRecord,
    PurchaseBatch,
    PurchaseOrder,
    PurchaseOrderItem,
    SalesOrder,
    SalesOrderItem,
    SalesReceipt,
    SalesShipment,
    SalesTransportCost,
    Supplier,
    User,
)
from privnote.models import PaymentMethod


class SalesAccountingModelTest(TestCase):
    def setUp(self):
        self.operator = User.objects.create_user('sales-accounting-operator', password='pass', is_staff=True)
        self.brand = Brand.objects.create(english_name='Accounting Brand', name='账务品牌')
        self.cigar = Cigar.objects.create(
            brand=self.brand.english_name,
            english_name='Accounting Cigar',
            name='账务雪茄',
        )
        self.cny_account = FundAccount.objects.create(
            name='销售人民币账户',
            currency=FundAccount.Currency.CNY,
            creation_idempotency_key='sales-accounting-cny',
        )

    def ledger_transaction(self, kind, key):
        return LedgerTransaction.objects.create(
            transaction_type=kind,
            business_date=date(2026, 8, 11),
            idempotency_key=key,
            operator=self.operator,
        )

    def order(self, **changes):
        values = {
            'operator': self.operator,
            'goods_amount_cny': Decimal('100.00'),
            'customer_transport_fee_cny': Decimal('20.00'),
            'amount_due_cny': Decimal('120.00'),
        }
        values.update(changes)
        return SalesOrder.objects.create(**values)

    def test_display_status_is_composed_from_independent_axes(self):
        order = self.order()
        self.assertEqual(order.fulfillment_status, SalesOrder.FulfillmentStatus.DRAFT)
        self.assertEqual(order.payment_status, SalesOrder.PaymentStatus.UNPAID)
        self.assertEqual(order.display_status, '草稿')

        order.fulfillment_status = SalesOrder.FulfillmentStatus.CONFIRMED
        order.payment_status = SalesOrder.PaymentStatus.PAID
        self.assertEqual(order.display_status, '已预收，待出库')

        order.fulfillment_status = SalesOrder.FulfillmentStatus.SHIPPED
        order.payment_status = SalesOrder.PaymentStatus.UNPAID
        self.assertEqual(order.display_status, '已出库，待收款')

        order.payment_status = SalesOrder.PaymentStatus.PAID
        self.assertEqual(order.display_status, '已完成')

        order.fulfillment_status = SalesOrder.FulfillmentStatus.CONFIRMED
        order.payment_status = SalesOrder.PaymentStatus.UNPAID
        self.assertEqual(order.display_status, '待出库')

        order.fulfillment_status = SalesOrder.FulfillmentStatus.CANCELLED
        self.assertEqual(order.display_status, '已取消')
        order.payment_status = SalesOrder.PaymentStatus.REFUND_PENDING
        self.assertEqual(order.display_status, '已取消，待退款')
        order.payment_status = SalesOrder.PaymentStatus.REFUNDED
        self.assertEqual(order.display_status, '已取消，已退款')

        order.fulfillment_status = SalesOrder.FulfillmentStatus.DRAFT
        order.payment_status = SalesOrder.PaymentStatus.PAID
        self.assertEqual(order.display_status, '状态异常')

    def test_new_sales_item_keeps_actual_stick_quantity_and_sale_package_snapshot(self):
        order = self.order()
        item = SalesOrderItem.objects.create(
            sales_order=order,
            cigar=self.cigar,
            quantity=25,
            sale_unit=SalesOrderItem.SaleUnit.BOX,
            sale_quantity=1,
            box_size=25,
            unit_price=Decimal('4.00'),
            unit_cost=Decimal('2.00'),
            revenue=Decimal('100.00'),
            cost=Decimal('50.00'),
            profit=Decimal('50.00'),
        )
        self.assertEqual(item.quantity, 25)
        self.assertEqual(item.sale_unit, SalesOrderItem.SaleUnit.BOX)
        self.assertEqual(item.sale_quantity, 1)
        self.assertEqual(item.box_size, 25)

    def test_purchase_batch_has_separate_physical_and_available_stock_read_models(self):
        supplier = Supplier.objects.create(name='库存兼容供应商')
        purchase_order = PurchaseOrder.objects.create(
            supplier=supplier,
            rub_total=Decimal('1.00'),
            exchange_rate=Decimal('1.0000'),
            cny_total=Decimal('100.00'),
            operator=self.operator,
        )
        purchase_item = PurchaseOrderItem.objects.create(
            purchase_order=purchase_order,
            cigar=self.cigar,
            quantity=10,
            box_size=10,
            unit_price_rub=Decimal('1.00'),
            unit_price_cny=Decimal('10.00'),
        )
        batch = PurchaseBatch.objects.create(
            purchase_order_item=purchase_item,
            cigar=self.cigar,
            quantity=10,
            remaining=6,
            original_cost_cny=Decimal('100.00'),
            positive_adjustment_quantity=0,
            positive_adjustment_cost_cny=Decimal('0.00'),
            adjustment_cost_cny=Decimal('0.00'),
            physical_remaining=10,
            unit_cost_cny=Decimal('10.00'),
            remaining_cost_cny=Decimal('100.00'),
            sold_cost_cny=Decimal('0.00'),
        )
        self.assertEqual(batch.remaining, 6)
        self.assertEqual(batch.physical_remaining, 10)
        self.assertEqual(batch.remaining_cost_cny, Decimal('100.00'))
        self.assertEqual(batch.sold_cost_cny, Decimal('0.00'))

    def test_purchase_batch_database_constraints_reject_invalid_inventory_facts(self):
        supplier = Supplier.objects.create(name='约束供应商')
        purchase_order = PurchaseOrder.objects.create(
            supplier=supplier, rub_total=Decimal('1.00'), exchange_rate=Decimal('1.0000'),
            cny_total=Decimal('100.00'), operator=self.operator,
        )
        purchase_item = PurchaseOrderItem.objects.create(
            purchase_order=purchase_order, cigar=self.cigar, quantity=10, box_size=10,
            unit_price_rub=Decimal('1.00'), unit_price_cny=Decimal('10.00'),
        )
        batch = PurchaseBatch.objects.create(
            purchase_order_item=purchase_item, cigar=self.cigar, quantity=10, remaining=6,
            physical_remaining=8, unit_cost_cny=Decimal('10.00'),
            original_cost_cny=Decimal('100.00'),
            positive_adjustment_quantity=0,
            positive_adjustment_cost_cny=Decimal('0.00'),
            adjustment_cost_cny=Decimal('0.00'),
            remaining_cost_cny=Decimal('80.00'), sold_cost_cny=Decimal('20.00'),
        )
        for changes in (
            {'quantity': -1}, {'remaining': -1}, {'physical_remaining': -1},
            {'remaining': 9}, {'physical_remaining': 11},
            {'remaining_cost_cny': Decimal('-0.01')}, {'sold_cost_cny': Decimal('-0.01')},
            {'unit_cost_cny': Decimal('-0.01')},
        ):
            with self.subTest(changes=changes):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    PurchaseBatch.objects.filter(pk=batch.pk).update(**changes)
    def test_sales_facts_are_one_to_one_and_protect_their_accounting_references(self):
        order = self.order()
        shipment = SalesShipment.objects.create(
            sales_order=order,
            business_date=date(2026, 8, 11),
            fifo_cost_cny=Decimal('50.00'),
            ledger_transaction=self.ledger_transaction('sales_shipment', 'shipment-ledger'),
            operator=self.operator,
        )
        receipt = SalesReceipt.objects.create(
            sales_order=self.order(),
            amount_cny=Decimal('120.00'),
            fund_account=self.cny_account,
            business_date=date(2026, 8, 11),
            ledger_transaction=self.ledger_transaction('sales_receipt', 'receipt-ledger'),
            operator=self.operator,
        )
        transport = SalesTransportCost.objects.create(
            sales_order=self.order(),
            actual_cost_cny=Decimal('15.00'),
            fund_account=self.cny_account,
            business_date=date(2026, 8, 11),
            ledger_transaction=self.ledger_transaction('sales_transport_cost', 'transport-ledger'),
            operator=self.operator,
            note='人肉费',
        )
        self.assertEqual(shipment.sales_order.sales_shipment, shipment)
        self.assertEqual(receipt.sales_order.sales_receipt, receipt)
        self.assertEqual(transport.sales_order.sales_transport_cost, transport)
        with self.assertRaises(IntegrityError), transaction.atomic():
            SalesShipment.objects.create(
                sales_order=order,
                business_date=date(2026, 8, 11),
                fifo_cost_cny=Decimal('50.00'),
                ledger_transaction=self.ledger_transaction('sales_shipment', 'shipment-order-duplicate'),
                operator=self.operator,
            )

        with self.assertRaises(IntegrityError), transaction.atomic():
            SalesShipment.objects.create(
                sales_order=self.order(),
                business_date=date(2026, 8, 11),
                fifo_cost_cny=Decimal('50.00'),
                ledger_transaction=shipment.ledger_transaction,
                operator=self.operator,
            )

        with self.assertRaises(IntegrityError), transaction.atomic():
            SalesReceipt.objects.create(
                sales_order=receipt.sales_order,
                amount_cny=Decimal('120.00'),
                fund_account=self.cny_account,
                business_date=date(2026, 8, 11),
                ledger_transaction=self.ledger_transaction('sales_receipt', 'receipt-order-duplicate'),
                operator=self.operator,
            )

        with self.assertRaises(IntegrityError), transaction.atomic():
            SalesTransportCost.objects.create(
                sales_order=transport.sales_order,
                actual_cost_cny=Decimal('15.00'),
                fund_account=self.cny_account,
                business_date=date(2026, 8, 11),
                ledger_transaction=self.ledger_transaction('sales_transport_cost', 'transport-order-duplicate'),
                operator=self.operator,
            )

        with self.assertRaises(ProtectedError):
            shipment.ledger_transaction.delete()
        with self.assertRaises(ProtectedError):
            receipt.ledger_transaction.delete()
        with self.assertRaises(ProtectedError):
            transport.ledger_transaction.delete()
        with self.assertRaises(ProtectedError):
            self.cny_account.delete()

    def test_payment_method_only_accepts_a_cny_fund_account(self):
        rub_account = FundAccount.objects.create(
            name='卢布账户',
            currency=FundAccount.Currency.RUB,
            creation_idempotency_key='sales-accounting-rub',
        )
        with self.assertRaises(ValidationError):
            PaymentMethod(method_type='wechat', label='错误账户', fund_account=rub_account).full_clean()

        method = PaymentMethod(method_type='wechat', label='人民币账户', fund_account=self.cny_account)
        method.full_clean()
        unsaved_rub_account = FundAccount(
            name='未保存卢布账户',
            currency=FundAccount.Currency.RUB,
            creation_idempotency_key='unsaved-sales-accounting-rub',
        )
        with self.assertRaises(ValidationError):
            PaymentMethod(method_type='wechat', label='未保存卢布账户', fund_account=unsaved_rub_account).full_clean()
        PaymentMethod(method_type='wechat', label='未绑定账户', fund_account=None).full_clean()


class PurchaseBatchInventoryMigrationFixture:
    migrate_from = [('cigars', '0023_purchasebatch_physical_remaining_and_more')]
    migrate_to = [('cigars', '0024_backfill_purchase_batch_inventory_facts')]

    def set_up_legacy_inventory(self):
        self.executor = MigrationExecutor(connection)
        self.executor.migrate(self.migrate_from)
        self.addCleanup(self.executor.migrate, self.executor.loader.graph.leaf_nodes())
        self.executor = MigrationExecutor(connection)
        self.apps = self.executor.loader.project_state(self.migrate_from).apps
        User = self.apps.get_model('cigars', 'User')
        Cigar = self.apps.get_model('cigars', 'Cigar')
        Supplier = self.apps.get_model('cigars', 'Supplier')
        PurchaseOrder = self.apps.get_model('cigars', 'PurchaseOrder')
        PurchaseOrderItem = self.apps.get_model('cigars', 'PurchaseOrderItem')
        PurchaseBatch = self.apps.get_model('cigars', 'PurchaseBatch')
        SalesOrder = self.apps.get_model('cigars', 'SalesOrder')
        SalesOrderItem = self.apps.get_model('cigars', 'SalesOrderItem')
        StockAllocation = self.apps.get_model('cigars', 'StockAllocation')
        StockMovement = self.apps.get_model('cigars', 'StockMovement')
        self.operator = User.objects.create(username='migration-operator', is_staff=True)
        self.cigar = Cigar.objects.create(
            brand='Migration Brand',
            english_name='Migration Cigar',
            name='迁移雪茄',
        )
        supplier = Supplier.objects.create(name='迁移供应商')
        purchase_order = PurchaseOrder.objects.create(
            supplier=supplier,
            rub_total=Decimal('10.00'),
            exchange_rate=Decimal('1.0000'),
            cny_total=Decimal('100.00'),
            operator=self.operator,
        )
        purchase_item = PurchaseOrderItem.objects.create(
            purchase_order=purchase_order,
            cigar=self.cigar,
            quantity=10,
            box_size=10,
            unit_price_rub=Decimal('1.00'),
            unit_price_cny=Decimal('10.00'),
        )
        batch = PurchaseBatch.objects.create(
            purchase_order_item=purchase_item,
            cigar=self.cigar,
            quantity=10,
            remaining=6,
            unit_cost_cny=Decimal('10.00'),
        )
        StockMovement.objects.create(
            movement_type='receive',
            cigar=self.cigar,
            purchase_batch=batch,
            quantity=10,
            operator=self.operator,
            command_name='legacy-receive',
        )
        order = SalesOrder.objects.create(operator=self.operator)
        item = SalesOrderItem.objects.create(
            sales_order=order,
            cigar=self.cigar,
            quantity=4,
            unit_price=Decimal('20.00'),
            unit_cost=Decimal('10.00'),
            revenue=Decimal('80.00'),
            cost=Decimal('40.00'),
            profit=Decimal('40.00'),
        )
        StockAllocation.objects.create(
            sales_order_item=item,
            purchase_batch=batch,
            quantity=4,
            status='reserved',
        )
        self.batch_id = batch.pk


class SalesAccountingConstraintTest(SalesAccountingModelTest):
    def test_sales_database_constraints_reject_invalid_row_local_facts(self):
        def assert_rejected(model, pk, changes):
            with self.subTest(model=model.__name__, changes=changes):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    model.objects.filter(pk=pk).update(**changes)

        order = self.order()
        for changes in (
            {'goods_amount_cny': Decimal('-0.01')},
            {'customer_transport_fee_cny': Decimal('-0.01')},
            {'amount_due_cny': Decimal('-0.01')},
            {'fifo_cost_cny': Decimal('-0.01')},
            {'actual_transport_cost_cny': Decimal('-0.01')},
        ):
            assert_rejected(SalesOrder, order.pk, changes)
        SalesOrder.objects.filter(pk=order.pk).update(contribution_profit_cny=Decimal('-0.01'))

        item = SalesOrderItem.objects.create(
            sales_order=self.order(), cigar=self.cigar, quantity=1,
            unit_price=Decimal('1.00'), unit_cost=Decimal('1.00'), revenue=Decimal('1.00'),
            cost=Decimal('1.00'), profit=Decimal('0.00'),
        )
        self.assertEqual(item.sale_unit, '')
        self.assertIsNone(item.sale_quantity)
        self.assertIsNone(item.box_size)
        for changes in ({'quantity': 0}, {'sale_quantity': 0}, {'box_size': 0}):
            assert_rejected(SalesOrderItem, item.pk, changes)

        shipment = SalesShipment.objects.create(
            sales_order=self.order(), business_date=date(2026, 8, 11), fifo_cost_cny=Decimal('1.00'),
            ledger_transaction=self.ledger_transaction('sales_shipment', 'constraint-shipment'), operator=self.operator,
        )
        assert_rejected(SalesShipment, shipment.pk, {'fifo_cost_cny': Decimal('-0.01')})

        receipt = SalesReceipt.objects.create(
            sales_order=self.order(), amount_cny=Decimal('1.00'), fund_account=self.cny_account,
            business_date=date(2026, 8, 11),
            ledger_transaction=self.ledger_transaction('sales_receipt', 'constraint-receipt'), operator=self.operator,
        )
        assert_rejected(SalesReceipt, receipt.pk, {'amount_cny': Decimal('0.00')})

        transport = SalesTransportCost.objects.create(
            sales_order=self.order(), actual_cost_cny=Decimal('1.00'), fund_account=self.cny_account,
            business_date=date(2026, 8, 11),
            ledger_transaction=self.ledger_transaction('sales_transport_cost', 'constraint-transport'), operator=self.operator,
        )
        assert_rejected(SalesTransportCost, transport.pk, {'actual_cost_cny': Decimal('-0.01')})

class PurchaseBatchCostPoolCapacityMigrationTest(
    PurchaseBatchInventoryMigrationFixture, TransactionTestCase
):
    def setUp(self):
        super().setUp()
        self.set_up_legacy_inventory()

    def test_legacy_cost_pool_fields_hold_maximum_quantity_backfill(self):
        PurchaseBatch = self.apps.get_model('cigars', 'PurchaseBatch')
        unit_cost = Decimal('9999999999.99')
        # Exceeds the former 14-digit field while retaining exact cents on SQLite.
        # SQLite NUMERIC affinity cannot round-trip the theoretical 22-digit limit.
        quantity = 1000
        expected_cost = Decimal(quantity) * unit_cost
        self.assertGreater(expected_cost, Decimal('999999999999.99'))
        PurchaseBatch.objects.filter(pk=self.batch_id).update(
            quantity=quantity,
            remaining=quantity - 4,
            unit_cost_cny=unit_cost,
        )

        self.executor.migrate(self.migrate_to)
        apps = self.executor.loader.project_state(self.migrate_to).apps
        migrated_batch = apps.get_model('cigars', 'PurchaseBatch').objects.get(pk=self.batch_id)
        self.assertEqual(migrated_batch.remaining_cost_cny, expected_cost)
        self.assertEqual(migrated_batch.sold_cost_cny, Decimal('0.00'))

class PurchaseBatchInventoryMigrationTest(
    PurchaseBatchInventoryMigrationFixture, TransactionTestCase
):
    def setUp(self):
        super().setUp()
        self.set_up_legacy_inventory()

    def test_reserved_legacy_stock_backfills_physical_and_cost_pools(self):
        self.executor.migrate(self.migrate_to)
        apps = self.executor.loader.project_state(self.migrate_to).apps
        PurchaseBatch = apps.get_model('cigars', 'PurchaseBatch')
        batch = PurchaseBatch.objects.get(pk=self.batch_id)
        self.assertEqual(batch.remaining, 6)
        self.assertEqual(batch.physical_remaining, 10)
        self.assertEqual(batch.remaining_cost_cny, Decimal('100.00'))
        self.assertEqual(batch.sold_cost_cny, Decimal('0.00'))

    def tearDown(self):
        self.executor.migrate(self.executor.loader.graph.leaf_nodes())
        super().tearDown()


class InconsistentReservedAllocationMigrationTest(
    PurchaseBatchInventoryMigrationFixture, TransactionTestCase
):
    def setUp(self):
        super().setUp()
        self.set_up_legacy_inventory()
        SalesOrder = self.apps.get_model('cigars', 'SalesOrder')
        SalesOrderItem = self.apps.get_model('cigars', 'SalesOrderItem')
        StockAllocation = self.apps.get_model('cigars', 'StockAllocation')
        PurchaseBatch = self.apps.get_model('cigars', 'PurchaseBatch')
        order = SalesOrder.objects.create(operator=self.operator)
        item = SalesOrderItem.objects.create(
            sales_order=order,
            cigar=self.cigar,
            quantity=1,
            unit_price=Decimal('20.00'),
            unit_cost=Decimal('10.00'),
            revenue=Decimal('20.00'),
            cost=Decimal('10.00'),
            profit=Decimal('10.00'),
        )
        self.invalid_allocation = StockAllocation.objects.create(
            sales_order_item=item,
            purchase_batch=PurchaseBatch.objects.get(pk=self.batch_id),
            quantity=1,
            status='reserved',
        )

    def test_migration_rejects_reserved_quantity_beyond_batch_quantity(self):
        with self.assertRaises(RuntimeError):
            self.executor.migrate(self.migrate_to)

    def tearDown(self):
        self.apps.get_model('cigars', 'StockAllocation').objects.filter(
            pk=self.invalid_allocation.pk
        ).delete()
        self.executor.migrate(self.executor.loader.graph.leaf_nodes())
        super().tearDown()


class OffsetNegativeReservedAllocationMigrationTest(
    PurchaseBatchInventoryMigrationFixture, TransactionTestCase
):
    def setUp(self):
        super().setUp()
        self.set_up_legacy_inventory()
        SalesOrder = self.apps.get_model('cigars', 'SalesOrder')
        SalesOrderItem = self.apps.get_model('cigars', 'SalesOrderItem')
        StockAllocation = self.apps.get_model('cigars', 'StockAllocation')
        PurchaseBatch = self.apps.get_model('cigars', 'PurchaseBatch')
        purchase_batch = PurchaseBatch.objects.get(pk=self.batch_id)
        order = SalesOrder.objects.create(operator=self.operator)
        self.offset_allocations = []
        for quantity in (-1, 1):
            item = SalesOrderItem.objects.create(
                sales_order=order,
                cigar=self.cigar,
                quantity=1,
                unit_price=Decimal('20.00'),
                unit_cost=Decimal('10.00'),
                revenue=Decimal('20.00'),
                cost=Decimal('10.00'),
                profit=Decimal('10.00'),
            )
            self.offset_allocations.append(StockAllocation.objects.create(
                sales_order_item=item,
                purchase_batch=purchase_batch,
                quantity=quantity,
                status='reserved',
            ))

    def test_migration_rejects_negative_allocation_hidden_by_positive_reserved_sum(self):
        quantities = self.apps.get_model('cigars', 'StockAllocation').objects.filter(
            purchase_batch_id=self.batch_id,
            status='reserved',
        ).values_list('quantity', flat=True)
        self.assertEqual(sum(quantities), 4)
        with self.assertRaises(RuntimeError):
            self.executor.migrate(self.migrate_to)

    def tearDown(self):
        self.apps.get_model('cigars', 'StockAllocation').objects.filter(
            pk__in=[allocation.pk for allocation in self.offset_allocations]
        ).delete()
        self.executor.migrate(self.executor.loader.graph.leaf_nodes())
        super().tearDown()


class NegativeLegacyStockMigrationTest(
    PurchaseBatchInventoryMigrationFixture, TransactionTestCase
):
    def setUp(self):
        super().setUp()
        self.set_up_legacy_inventory()
        PurchaseBatch = self.apps.get_model('cigars', 'PurchaseBatch')
        PurchaseBatch.objects.filter(pk=self.batch_id).update(remaining=-1)

    def test_migration_rejects_negative_remaining_quantity(self):
        with self.assertRaises(RuntimeError):
            self.executor.migrate(self.migrate_to)

    def tearDown(self):
        PurchaseBatch = self.apps.get_model('cigars', 'PurchaseBatch')
        PurchaseBatch.objects.filter(pk=self.batch_id).update(remaining=6)
        self.executor.migrate(self.executor.loader.graph.leaf_nodes())
        super().tearDown()


class PurchaseBatchCostFactsMigrationTest(TransactionTestCase):
    migrate_from = [('cigars', '0026_purchase_batch_unit_cost_gte_zero')]
    migrate_to = [('cigars', '0027_purchase_batch_cost_facts')]

    def setUp(self):
        super().setUp()
        self.executor = MigrationExecutor(connection)
        self.executor.migrate(self.migrate_from)
        self.addCleanup(self.executor.migrate, self.executor.loader.graph.leaf_nodes())
        self.executor = MigrationExecutor(connection)
        self.apps = self.executor.loader.project_state(self.migrate_from).apps

        User = self.apps.get_model('cigars', 'User')
        Cigar = self.apps.get_model('cigars', 'Cigar')
        Supplier = self.apps.get_model('cigars', 'Supplier')
        PurchaseOrder = self.apps.get_model('cigars', 'PurchaseOrder')
        PurchaseOrderItem = self.apps.get_model('cigars', 'PurchaseOrderItem')
        PurchaseBatch = self.apps.get_model('cigars', 'PurchaseBatch')
        StockMovement = self.apps.get_model('cigars', 'StockMovement')
        AdjustmentRecord = self.apps.get_model('cigars', 'AdjustmentRecord')

        operator = User.objects.create(username='cost-facts-migration-operator', is_staff=True)
        cigar = Cigar.objects.create(
            brand='Cost Facts Brand', english_name='Cost Facts Cigar', name='成本事实雪茄',
        )
        supplier = Supplier.objects.create(name='成本事实供应商')
        purchase_order = PurchaseOrder.objects.create(
            supplier=supplier,
            rub_total=Decimal('10.00'),
            exchange_rate=Decimal('1.0000'),
            cny_total=Decimal('100.00'),
            operator=operator,
        )
        purchase_item = PurchaseOrderItem.objects.create(
            purchase_order=purchase_order,
            cigar=cigar,
            quantity=10,
            box_size=10,
            unit_price_rub=Decimal('1.00'),
            unit_price_cny=Decimal('10.00'),
        )
        batch = PurchaseBatch.objects.create(
            purchase_order_item=purchase_item,
            cigar=cigar,
            quantity=12,
            remaining=12,
            physical_remaining=12,
            unit_cost_cny=Decimal('10.00'),
            remaining_cost_cny=Decimal('120.00'),
            sold_cost_cny=Decimal('0.00'),
        )
        StockMovement.objects.create(
            movement_type='receive',
            cigar=cigar,
            purchase_batch=batch,
            quantity=10,
            operator=operator,
            command_name='legacy-receive',
        )
        StockMovement.objects.create(
            movement_type='adjustment',
            cigar=cigar,
            purchase_batch=batch,
            quantity=4,
            operator=operator,
            command_name='legacy-positive-adjustment',
        )
        StockMovement.objects.create(
            movement_type='adjustment',
            cigar=cigar,
            purchase_batch=batch,
            quantity=-2,
            operator=operator,
            command_name='legacy-negative-adjustment',
        )
        self.adjustment_id = AdjustmentRecord.objects.create(
            cigar=cigar,
            batch=batch,
            type='LOSS',
            quantity=2,
            unit_cost_cny=Decimal('10.00'),
            operator=operator,
            reason='历史损耗',
        ).pk
        self.batch_id = batch.pk

    def test_migration_restores_original_quantity_and_cost_facts_exactly(self):
        self.executor.migrate(self.migrate_to)
        apps = self.executor.loader.project_state(self.migrate_to).apps
        PurchaseBatch = apps.get_model('cigars', 'PurchaseBatch')
        AdjustmentRecord = apps.get_model('cigars', 'AdjustmentRecord')

        batch = PurchaseBatch.objects.get(pk=self.batch_id)
        adjustment = AdjustmentRecord.objects.get(pk=self.adjustment_id)

        self.assertEqual(batch.quantity, 10)
        self.assertEqual(batch.positive_adjustment_quantity, 4)
        self.assertEqual(batch.original_cost_cny, Decimal('100.00'))
        self.assertEqual(batch.positive_adjustment_cost_cny, Decimal('40.00'))
        self.assertEqual(batch.adjustment_cost_cny, Decimal('20.00'))
        self.assertEqual(adjustment.cost_cny, Decimal('20.00'))
        self.assertEqual(
            batch.original_cost_cny + batch.positive_adjustment_cost_cny,
            batch.remaining_cost_cny + batch.sold_cost_cny + batch.adjustment_cost_cny,
        )

    def test_migration_uses_opening_balance_as_physical_baseline_not_original_purchase(self):
        StockMovement = self.apps.get_model('cigars', 'StockMovement')
        AdjustmentRecord = self.apps.get_model('cigars', 'AdjustmentRecord')
        PurchaseBatch = self.apps.get_model('cigars', 'PurchaseBatch')
        PurchaseOrderItem = self.apps.get_model('cigars', 'PurchaseOrderItem')

        StockMovement.objects.filter(purchase_batch_id=self.batch_id).delete()
        AdjustmentRecord.objects.filter(batch_id=self.batch_id).delete()
        PurchaseOrderItem.objects.filter(
            pk=PurchaseBatch.objects.get(pk=self.batch_id).purchase_order_item_id,
        ).update(quantity=25)
        PurchaseBatch.objects.filter(pk=self.batch_id).update(
            quantity=25,
            remaining=10,
            physical_remaining=10,
            remaining_cost_cny=Decimal('100.00'),
            sold_cost_cny=Decimal('150.00'),
        )
        batch = PurchaseBatch.objects.get(pk=self.batch_id)
        StockMovement.objects.create(
            movement_type='receive',
            cigar_id=batch.cigar_id,
            purchase_batch=batch,
            quantity=10,
            operator_id=batch.purchase_order_item.purchase_order.operator_id,
            command_name='migration_stock_opening_balance',
        )

        self.executor.migrate(self.migrate_to)
        apps = self.executor.loader.project_state(self.migrate_to).apps
        migrated_batch = apps.get_model('cigars', 'PurchaseBatch').objects.get(pk=self.batch_id)

        self.assertEqual(migrated_batch.quantity, 25)
        self.assertEqual(migrated_batch.original_cost_cny, Decimal('250.00'))
        self.assertEqual(migrated_batch.sold_cost_cny, Decimal('150.00'))

    def test_migration_allows_fully_sold_legacy_batch_without_movements(self):
        StockMovement = self.apps.get_model('cigars', 'StockMovement')
        AdjustmentRecord = self.apps.get_model('cigars', 'AdjustmentRecord')
        PurchaseBatch = self.apps.get_model('cigars', 'PurchaseBatch')
        PurchaseOrderItem = self.apps.get_model('cigars', 'PurchaseOrderItem')

        StockMovement.objects.filter(purchase_batch_id=self.batch_id).delete()
        AdjustmentRecord.objects.filter(batch_id=self.batch_id).delete()
        PurchaseOrderItem.objects.filter(
            pk=PurchaseBatch.objects.get(pk=self.batch_id).purchase_order_item_id,
        ).update(quantity=25)
        PurchaseBatch.objects.filter(pk=self.batch_id).update(
            quantity=25, remaining=0, physical_remaining=0,
            remaining_cost_cny=Decimal('0.00'), sold_cost_cny=Decimal('250.00'),
        )

        self.executor.migrate(self.migrate_to)
        apps = self.executor.loader.project_state(self.migrate_to).apps
        batch = apps.get_model('cigars', 'PurchaseBatch').objects.get(pk=self.batch_id)
        self.assertEqual(batch.quantity, 25)
        self.assertEqual(batch.sold_cost_cny, Decimal('250.00'))

    def test_migration_rejects_normal_receive_not_matching_purchase_quantity(self):
        StockMovement = self.apps.get_model('cigars', 'StockMovement')
        AdjustmentRecord = self.apps.get_model('cigars', 'AdjustmentRecord')
        PurchaseBatch = self.apps.get_model('cigars', 'PurchaseBatch')
        PurchaseOrderItem = self.apps.get_model('cigars', 'PurchaseOrderItem')

        StockMovement.objects.filter(purchase_batch_id=self.batch_id).delete()
        AdjustmentRecord.objects.filter(batch_id=self.batch_id).delete()
        PurchaseOrderItem.objects.filter(
            pk=PurchaseBatch.objects.get(pk=self.batch_id).purchase_order_item_id,
        ).update(quantity=25)
        PurchaseBatch.objects.filter(pk=self.batch_id).update(
            quantity=24, remaining=24, physical_remaining=24,
            remaining_cost_cny=Decimal('240.00'), sold_cost_cny=Decimal('10.00'),
        )
        batch = PurchaseBatch.objects.get(pk=self.batch_id)
        StockMovement.objects.create(
            movement_type='receive', cigar_id=batch.cigar_id, purchase_batch=batch, quantity=24,
            operator_id=batch.purchase_order_item.purchase_order.operator_id, command_name='legacy-receive',
        )
        self.addCleanup(PurchaseBatch.objects.filter(pk=self.batch_id).delete)
        self.addCleanup(StockMovement.objects.filter(purchase_batch_id=self.batch_id).delete)

        with self.assertRaisesRegex(RuntimeError, r'采购批次 \d+.*正常入库流水数量'):
            self.executor.migrate(self.migrate_to)

    def test_migration_backfills_batchless_adjustment_and_ignores_released_allocation(self):
        AdjustmentRecord = self.apps.get_model('cigars', 'AdjustmentRecord')
        PurchaseBatch = self.apps.get_model('cigars', 'PurchaseBatch')
        SalesOrder = self.apps.get_model('cigars', 'SalesOrder')
        SalesOrderItem = self.apps.get_model('cigars', 'SalesOrderItem')
        StockAllocation = self.apps.get_model('cigars', 'StockAllocation')
        batch = PurchaseBatch.objects.get(pk=self.batch_id)
        operator = batch.purchase_order_item.purchase_order.operator
        batchless_adjustment = AdjustmentRecord.objects.create(
            cigar=batch.cigar, batch=None, type='LOSS', quantity=1,
            unit_cost_cny=Decimal('10.00'), operator=operator, reason='无批次历史损耗',
        )
        order = SalesOrder.objects.create(operator=operator)
        item = SalesOrderItem.objects.create(
            sales_order=order, cigar=batch.cigar, quantity=1, unit_price=Decimal('20.00'),
            unit_cost=Decimal('10.00'), revenue=Decimal('20.00'), cost=Decimal('10.00'), profit=Decimal('10.00'),
        )
        StockAllocation.objects.create(
            sales_order_item=item, purchase_batch=batch, quantity=1, status='released',
        )

        self.executor.migrate(self.migrate_to)
        apps = self.executor.loader.project_state(self.migrate_to).apps
        adjustment = apps.get_model('cigars', 'AdjustmentRecord').objects.get(pk=batchless_adjustment.pk)
        self.assertEqual(adjustment.cost_cny, Decimal('10.00'))

    def test_migration_rejects_movement_cigar_not_matching_batch(self):
        StockMovement = self.apps.get_model('cigars', 'StockMovement')
        Cigar = self.apps.get_model('cigars', 'Cigar')
        other_cigar = Cigar.objects.create(
            brand='Mismatch Brand', english_name='Mismatch Cigar', name='不一致雪茄',
        )
        movement = StockMovement.objects.get(
            purchase_batch_id=self.batch_id, movement_type='receive',
        )
        StockMovement.objects.filter(pk=movement.pk).update(cigar_id=other_cigar.pk)
        self.addCleanup(StockMovement.objects.filter(pk=movement.pk).update, cigar_id=movement.cigar_id)

        with self.assertRaisesRegex(RuntimeError, rf'采购批次 {self.batch_id}.*库存流水 {movement.pk}.*雪茄与批次不一致'):
            self.executor.migrate(self.migrate_to)

    def test_migration_rejects_unmatched_negative_adjustment_movement(self):
        StockMovement = self.apps.get_model('cigars', 'StockMovement')
        movement = StockMovement.objects.get(
            purchase_batch_id=self.batch_id, movement_type='adjustment', quantity=-2,
        )
        self.addCleanup(StockMovement.objects.filter(pk=movement.pk).update, quantity=-2)
        StockMovement.objects.filter(pk=movement.pk).update(quantity=-3)

        with self.assertRaisesRegex(RuntimeError, r'采购批次 \d+'):
            self.executor.migrate(self.migrate_to)
    def test_migration_rejects_duplicate_normal_receives_even_when_total_matches_purchase(self):
        StockMovement = self.apps.get_model('cigars', 'StockMovement')
        batch = self.apps.get_model('cigars', 'PurchaseBatch').objects.get(pk=self.batch_id)
        operator = batch.purchase_order_item.purchase_order.operator

        StockMovement.objects.filter(purchase_batch_id=self.batch_id, movement_type='receive').delete()
        for quantity in (5, 5):
            StockMovement.objects.create(
                movement_type='receive', cigar=batch.cigar, purchase_batch=batch, quantity=quantity,
                operator=operator, command_name='legacy-receive',
            )
        self.addCleanup(
            StockMovement.objects.create,
            movement_type='receive', cigar=batch.cigar, purchase_batch=batch, quantity=10,
            operator=operator, command_name='legacy-receive',
        )
        self.addCleanup(StockMovement.objects.filter(
            purchase_batch_id=self.batch_id, movement_type='receive',
        ).delete)

        with self.assertRaisesRegex(RuntimeError, rf'采购批次 {self.batch_id}.*正常入库流水.*条数'):
            self.executor.migrate(self.migrate_to)

    def test_migration_rejects_duplicate_opening_receives(self):
        StockMovement = self.apps.get_model('cigars', 'StockMovement')
        AdjustmentRecord = self.apps.get_model('cigars', 'AdjustmentRecord')
        PurchaseBatch = self.apps.get_model('cigars', 'PurchaseBatch')
        PurchaseOrderItem = self.apps.get_model('cigars', 'PurchaseOrderItem')

        StockMovement.objects.filter(purchase_batch_id=self.batch_id).delete()
        AdjustmentRecord.objects.filter(batch_id=self.batch_id).delete()
        PurchaseOrderItem.objects.filter(
            pk=PurchaseBatch.objects.get(pk=self.batch_id).purchase_order_item_id,
        ).update(quantity=25)
        PurchaseBatch.objects.filter(pk=self.batch_id).update(
            quantity=25, remaining=10, physical_remaining=10,
            remaining_cost_cny=Decimal('100.00'), sold_cost_cny=Decimal('150.00'),
        )
        batch = PurchaseBatch.objects.get(pk=self.batch_id)
        for quantity in (5, 5):
            StockMovement.objects.create(
                movement_type='receive', cigar=batch.cigar, purchase_batch=batch, quantity=quantity,
                operator_id=batch.purchase_order_item.purchase_order.operator_id,
                command_name='migration_stock_opening_balance',
            )
        self.addCleanup(PurchaseBatch.objects.filter(pk=self.batch_id).delete)
        self.addCleanup(StockMovement.objects.filter(purchase_batch_id=self.batch_id).delete)

        with self.assertRaisesRegex(RuntimeError, rf'采购批次 {self.batch_id}.*opening balance.*条数'):
            self.executor.migrate(self.migrate_to)

    def test_migration_rejects_adjustment_cigar_not_matching_batch(self):
        AdjustmentRecord = self.apps.get_model('cigars', 'AdjustmentRecord')
        Cigar = self.apps.get_model('cigars', 'Cigar')
        batch = self.apps.get_model('cigars', 'PurchaseBatch').objects.get(pk=self.batch_id)
        other_cigar = Cigar.objects.create(
            brand='Adjustment Mismatch Brand', english_name='Adjustment Mismatch Cigar', name='损耗不一致雪茄',
        )
        adjustment = AdjustmentRecord.objects.create(
            cigar=other_cigar, batch=batch, type='LOSS', quantity=1,
            unit_cost_cny=Decimal('10.00'), operator=batch.purchase_order_item.purchase_order.operator,
        )
        self.addCleanup(AdjustmentRecord.objects.filter(pk=adjustment.pk).delete)

        with self.assertRaisesRegex(RuntimeError, rf'采购批次 {self.batch_id}.*损耗记录 {adjustment.pk}.*雪茄与批次不一致'):
            self.executor.migrate(self.migrate_to)

    def test_migration_rejects_allocation_cigar_not_matching_batch(self):
        Cigar = self.apps.get_model('cigars', 'Cigar')
        SalesOrder = self.apps.get_model('cigars', 'SalesOrder')
        SalesOrderItem = self.apps.get_model('cigars', 'SalesOrderItem')
        StockAllocation = self.apps.get_model('cigars', 'StockAllocation')
        batch = self.apps.get_model('cigars', 'PurchaseBatch').objects.get(pk=self.batch_id)
        other_cigar = Cigar.objects.create(
            brand='Allocation Mismatch Brand', english_name='Allocation Mismatch Cigar', name='分配不一致雪茄',
        )
        order = SalesOrder.objects.create(operator=batch.purchase_order_item.purchase_order.operator)
        item = SalesOrderItem.objects.create(
            sales_order=order, cigar=other_cigar, quantity=1, unit_price=Decimal('20.00'),
            unit_cost=Decimal('10.00'), revenue=Decimal('20.00'), cost=Decimal('10.00'), profit=Decimal('10.00'),
        )
        allocation = StockAllocation.objects.create(
            sales_order_item=item, purchase_batch=batch, quantity=1, status='released',
        )
        self.addCleanup(StockAllocation.objects.filter(pk=allocation.pk).delete)

        with self.assertRaisesRegex(RuntimeError, rf'采购批次 {self.batch_id}.*库存分配 {allocation.pk}.*雪茄与批次不一致'):
            self.executor.migrate(self.migrate_to)

    def test_migration_describes_invalid_batchless_adjustment_without_none_batch(self):
        AdjustmentRecord = self.apps.get_model('cigars', 'AdjustmentRecord')
        batch = self.apps.get_model('cigars', 'PurchaseBatch').objects.get(pk=self.batch_id)
        adjustment = AdjustmentRecord.objects.create(
            cigar=batch.cigar, batch=None, type='LOSS', quantity=-1,
            unit_cost_cny=Decimal('10.00'), operator=batch.purchase_order_item.purchase_order.operator,
        )
        self.addCleanup(AdjustmentRecord.objects.filter(pk=adjustment.pk).delete)

        with self.assertRaisesRegex(RuntimeError, rf'无关联批次的损耗记录 {adjustment.pk}.*负成本'):
            self.executor.migrate(self.migrate_to)


    def test_migration_rejects_ship_and_physical_quantity_mismatch(self):
        PurchaseBatch = self.apps.get_model('cigars', 'PurchaseBatch')
        SalesOrder = self.apps.get_model('cigars', 'SalesOrder')
        SalesOrderItem = self.apps.get_model('cigars', 'SalesOrderItem')
        StockAllocation = self.apps.get_model('cigars', 'StockAllocation')
        StockMovement = self.apps.get_model('cigars', 'StockMovement')
        batch = PurchaseBatch.objects.get(pk=self.batch_id)
        operator = batch.purchase_order_item.purchase_order.operator
        order = SalesOrder.objects.create(operator=operator)
        item = SalesOrderItem.objects.create(
            sales_order=order,
            cigar=batch.cigar,
            quantity=1,
            unit_price=Decimal('20.00'),
            unit_cost=Decimal('10.00'),
            revenue=Decimal('20.00'),
            cost=Decimal('10.00'),
            profit=Decimal('10.00'),
        )
        allocation = StockAllocation.objects.create(
            sales_order_item=item,
            purchase_batch=batch,
            quantity=1,
            status='fulfilled',
        )
        movement = StockMovement.objects.create(
            movement_type='ship',
            cigar=batch.cigar,
            purchase_batch=batch,
            sales_order=order,
            sales_order_item=item,
            quantity=1,
            operator=operator,
            command_name='legacy-ship',
        )
        self.addCleanup(StockAllocation.objects.filter(pk=allocation.pk).delete)
        self.addCleanup(StockMovement.objects.filter(pk=movement.pk).delete)

        with self.assertRaisesRegex(RuntimeError, r'采购批次 \d+'):
            self.executor.migrate(self.migrate_to)

    def test_migration_rejects_reserved_and_remaining_quantity_mismatch(self):
        PurchaseBatch = self.apps.get_model('cigars', 'PurchaseBatch')
        SalesOrder = self.apps.get_model('cigars', 'SalesOrder')
        SalesOrderItem = self.apps.get_model('cigars', 'SalesOrderItem')
        StockAllocation = self.apps.get_model('cigars', 'StockAllocation')
        batch = PurchaseBatch.objects.get(pk=self.batch_id)
        operator = batch.purchase_order_item.purchase_order.operator
        order = SalesOrder.objects.create(operator=operator)
        item = SalesOrderItem.objects.create(
            sales_order=order,
            cigar=batch.cigar,
            quantity=1,
            unit_price=Decimal('20.00'),
            unit_cost=Decimal('10.00'),
            revenue=Decimal('20.00'),
            cost=Decimal('10.00'),
            profit=Decimal('10.00'),
        )
        allocation = StockAllocation.objects.create(
            sales_order_item=item,
            purchase_batch=batch,
            quantity=1,
            status='reserved',
        )
        self.addCleanup(StockAllocation.objects.filter(pk=allocation.pk).delete)

        with self.assertRaisesRegex(RuntimeError, r'采购批次 \d+'):
            self.executor.migrate(self.migrate_to)

class PurchaseBatchCostFactsModelTest(TestCase):
    def setUp(self):
        super().setUp()
        self.operator = User.objects.create_user('cost-facts-operator', password='pass', is_staff=True)
        self.cigar = Cigar.objects.create(
            brand='Cost Facts Brand',
            english_name='Cost Facts Cigar',
            name='成本事实雪茄',
        )

    def test_purchase_batch_cost_fact_constraints_and_adjustment_capacity(self):
        supplier = Supplier.objects.create(name='成本事实约束供应商')
        purchase_order = PurchaseOrder.objects.create(
            supplier=supplier,
            rub_total=Decimal('1.00'),
            exchange_rate=Decimal('1.0000'),
            cny_total=Decimal('100.00'),
            operator=self.operator,
        )
        purchase_item = PurchaseOrderItem.objects.create(
            purchase_order=purchase_order,
            cigar=self.cigar,
            quantity=10,
            box_size=10,
            unit_price_rub=Decimal('1.00'),
            unit_price_cny=Decimal('10.00'),
        )
        batch = PurchaseBatch.objects.create(
            purchase_order_item=purchase_item,
            cigar=self.cigar,
            quantity=10,
            remaining=6,
            physical_remaining=8,
            original_cost_cny=Decimal('100.00'),
            positive_adjustment_quantity=0,
            positive_adjustment_cost_cny=Decimal('0.00'),
            adjustment_cost_cny=Decimal('0.00'),
            unit_cost_cny=Decimal('10.00'),
            remaining_cost_cny=Decimal('80.00'),
            sold_cost_cny=Decimal('20.00'),
        )
        adjustment = AdjustmentRecord.objects.create(
            cigar=self.cigar,
            batch=batch,
            type=AdjustmentRecord.AdjustType.LOSS,
            quantity=1,
            unit_cost_cny=Decimal('10.00'),
            operator=self.operator,
        )

        def assert_rejected(model, pk, changes):
            with self.subTest(model=model.__name__, changes=changes):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    model.objects.filter(pk=pk).update(**changes)

        assert_rejected(PurchaseBatch, batch.pk, {'positive_adjustment_quantity': -1})
        for field in (
            'original_cost_cny',
            'positive_adjustment_cost_cny',
            'adjustment_cost_cny',
        ):
            assert_rejected(PurchaseBatch, batch.pk, {field: Decimal('-0.01')})
        assert_rejected(AdjustmentRecord, adjustment.pk, {'cost_cny': Decimal('-0.01')})
        assert_rejected(PurchaseBatch, batch.pk, {'physical_remaining': 11})

        PurchaseBatch.objects.filter(pk=batch.pk).update(
            positive_adjustment_quantity=4,
            physical_remaining=14,
        )
        self.assertEqual(PurchaseBatch.objects.get(pk=batch.pk).physical_remaining, 14)

    def test_purchase_batch_and_adjustment_cost_fields_store_cents_at_22_digits(self):
        for model, field_names in (
            (PurchaseBatch, (
                'original_cost_cny',
                'positive_adjustment_cost_cny',
                'adjustment_cost_cny',
            )),
            (AdjustmentRecord, ('cost_cny',)),
        ):
            for field_name in field_names:
                with self.subTest(model=model.__name__, field=field_name):
                    field = model._meta.get_field(field_name)
                    self.assertEqual(field.max_digits, 22)
                    self.assertEqual(field.decimal_places, 2)

class PurchaseBatchPackagingModelTest(TestCase):
    def setUp(self):
        self.operator = User.objects.create_user('packaging-model-operator', password='pass', is_staff=True)
        self.cigar = Cigar.objects.create(brand='Packaging Model Brand', english_name='Packaging Model Cigar', name='包装模型雪茄')

    def test_create_initializes_null_packaging_as_sticks(self):
        supplier = Supplier.objects.create(name='包装模型供应商')
        order = PurchaseOrder.objects.create(
            supplier=supplier, rub_total=Decimal('1.00'), exchange_rate=Decimal('1.0000'),
            cny_total=Decimal('1000.00'), operator=self.operator,
        )
        item = PurchaseOrderItem.objects.create(
            purchase_order=order, cigar=self.cigar, quantity=5, box_size=None,
            unit_price_rub=Decimal('1.00'), unit_price_cny=Decimal('10.00'),
        )
        batch = PurchaseBatch.objects.create(
            purchase_order_item=item, cigar=self.cigar, quantity=5, remaining=3, physical_remaining=4,
            original_cost_cny=Decimal('50.00'), remaining_cost_cny=Decimal('30.00'),
            sold_cost_cny=Decimal('20.00'), unit_cost_cny=Decimal('10.00'),
        )

        self.assertEqual(
            (
                batch.original_box_quantity, batch.original_stick_quantity,
                batch.physical_box_quantity, batch.physical_stick_quantity,
                batch.available_box_quantity, batch.available_stick_quantity,
            ),
            (0, 5, 0, 4, 0, 3),
        )

class PurchaseBatchPackagingMigrationTest(TransactionTestCase):
    def test_migration_backfills_available_first_box_and_stick_facts(self):
        executor = MigrationExecutor(connection)
        migrate_from = [('cigars', '0027_purchase_batch_cost_facts')]
        migrate_to = [('cigars', '0029_purchase_batch_packaging_constraints')]
        executor.migrate(migrate_from)
        self.addCleanup(executor.migrate, executor.loader.graph.leaf_nodes())
        executor = MigrationExecutor(connection)
        apps = MigrationExecutor(connection).loader.project_state(migrate_from).apps
        User = apps.get_model('cigars', 'User')
        Cigar = apps.get_model('cigars', 'Cigar')
        Supplier = apps.get_model('cigars', 'Supplier')
        PurchaseOrder = apps.get_model('cigars', 'PurchaseOrder')
        PurchaseOrderItem = apps.get_model('cigars', 'PurchaseOrderItem')
        PurchaseBatch = apps.get_model('cigars', 'PurchaseBatch')
        operator = User.objects.create(username='packaging-migration-operator', is_staff=True)
        cigar = Cigar.objects.create(brand='Packaging Migration Brand', english_name='Packaging Migration Cigar', name='包装迁移雪茄')
        order = PurchaseOrder.objects.create(supplier=Supplier.objects.create(name='包装迁移供应商'), rub_total=Decimal('1.00'), exchange_rate=Decimal('1.0000'), cny_total=Decimal('250.00'), operator=operator)
        item = PurchaseOrderItem.objects.create(purchase_order=order, cigar=cigar, quantity=25, box_size=25, unit_price_rub=Decimal('1.00'), unit_price_cny=Decimal('10.00'))
        batch = PurchaseBatch.objects.create(purchase_order_item=item, cigar=cigar, quantity=25, remaining=24, physical_remaining=25, original_cost_cny=Decimal('250.00'), remaining_cost_cny=Decimal('240.00'), sold_cost_cny=Decimal('10.00'), unit_cost_cny=Decimal('10.00'))

        executor.migrate(migrate_to)
        executor = MigrationExecutor(connection)
        migrated = executor.loader.project_state(migrate_to).apps.get_model('cigars', 'PurchaseBatch').objects.get(pk=batch.pk)
        self.assertEqual((migrated.original_box_quantity, migrated.original_stick_quantity, migrated.physical_box_quantity, migrated.physical_stick_quantity, migrated.available_box_quantity, migrated.available_stick_quantity), (1, 0, 0, 25, 0, 24))
