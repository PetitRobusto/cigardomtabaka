from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import Client, TestCase, TransactionTestCase
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from unittest.mock import patch
from importlib import import_module

from accounting.models import Day1Initialization, Day1DraftAccount, Day1DraftInventory
from cigars.models import Cigar, PurchaseBatch, PurchaseOrder, PurchaseOrderItem, Supplier, User


class Day1ModelTest(TestCase):
    def test_only_one_shared_company_initialization_can_exist(self):
        first = Day1Initialization.objects.create()

        with self.assertRaises(IntegrityError), transaction.atomic():
            Day1Initialization.objects.create()

        self.assertEqual(first.singleton_key, 'company')
        self.assertEqual(Day1Initialization.objects.count(), 1)

    def test_opening_purchase_batch_does_not_require_historical_order_item(self):
        cigar = Cigar.objects.create(
            brand='Day 1 Brand',
            english_name='Day 1 Cigar',
            name='期初雪茄',
        )

        batch = PurchaseBatch.objects.create(
            purchase_order_item=None,
            source=PurchaseBatch.Source.OPENING,
            cigar=cigar,
            quantity=10,
            remaining=10,
            physical_remaining=10,
            box_size=10,
            original_box_quantity=1,
            original_stick_quantity=0,
            physical_box_quantity=1,
            available_box_quantity=1,
            physical_stick_quantity=0,
            available_stick_quantity=0,
            original_cost_cny=Decimal('100.00'),
            remaining_cost_cny=Decimal('100.00'),
            unit_cost_cny=Decimal('10.00'),
        )

        self.assertIsNone(batch.purchase_order_item)
        self.assertEqual(batch.source, PurchaseBatch.Source.OPENING)

    def test_purchase_source_requires_purchase_order_item(self):
        cigar = Cigar.objects.create(
            brand='Day 1 Brand', english_name='Purchase Source Cigar', name='采购来源雪茄',
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            PurchaseBatch.objects.create(
                purchase_order_item=None,
                source=PurchaseBatch.Source.PURCHASE,
                cigar=cigar,
                quantity=1,
                remaining=1,
                physical_remaining=1,
                original_cost_cny=Decimal('10.00'),
                remaining_cost_cny=Decimal('10.00'),
                unit_cost_cny=Decimal('10.00'),
            )

    def test_opening_source_rejects_purchase_order_item(self):
        user = User.objects.create_user('day1-source-user')
        supplier = Supplier.objects.create(name='Day 1 Source Supplier')
        cigar = Cigar.objects.create(
            brand='Day 1 Brand', english_name='Opening Source Cigar', name='期初来源雪茄',
        )
        order = PurchaseOrder.objects.create(
            supplier=supplier, rub_total=Decimal('1.00'), exchange_rate=Decimal('1.0000'),
            cny_total=Decimal('10.00'), operator=user,
        )
        item = PurchaseOrderItem.objects.create(
            purchase_order=order, cigar=cigar, quantity=1, box_size=None,
            unit_price_rub=Decimal('1.00'), unit_price_cny=Decimal('10.00'),
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            PurchaseBatch.objects.create(
                purchase_order_item=item,
                source=PurchaseBatch.Source.OPENING,
                cigar=cigar,
                quantity=1,
                remaining=1,
                physical_remaining=1,
                original_cost_cny=Decimal('10.00'),
                remaining_cost_cny=Decimal('10.00'),
                unit_cost_cny=Decimal('10.00'),
            )

    def test_draft_account_slot_currency_pairing_is_database_constrained(self):
        initialization = Day1Initialization.objects.create()
        invalid_rows = (
            (Day1DraftAccount.Slot.OWNER_CNY, 'RUB'),
            (Day1DraftAccount.Slot.PARTNER_CNY, 'USDT'),
            (Day1DraftAccount.Slot.RUB, 'CNY'),
            (Day1DraftAccount.Slot.USDT, 'RUB'),
        )
        for slot, currency in invalid_rows:
            with self.subTest(slot=slot, currency=currency):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    Day1DraftAccount.objects.create(
                        initialization=initialization,
                        slot=slot,
                        account_name=f'{slot}-{currency}',
                        currency=currency,
                        original_amount=Decimal('1.00'),
                        cny_book_cost=Decimal('1.00'),
                    )

    def test_opening_batch_is_safe_through_receive_endpoint_representation(self):
        operator = User.objects.create_user('day1-agent-user', password='pass', is_staff=True)
        cigar = Cigar.objects.create(
            brand='Day 1 Brand', english_name='Agent Opening Cigar', name='代理期初雪茄',
        )
        batch = PurchaseBatch.objects.create(
            purchase_order_item=None,
            source=PurchaseBatch.Source.OPENING,
            cigar=cigar,
            quantity=1,
            remaining=1,
            physical_remaining=1,
            original_cost_cny=Decimal('10.00'),
            remaining_cost_cny=Decimal('10.00'),
            unit_cost_cny=Decimal('10.00'),
        )
        client = Client()
        client.force_login(operator)
        with patch('cigars.agent_api.receive_purchase_order', return_value=[batch]):
            response = client.post(
                '/api/agent/purchase-orders/receive/',
                data='{"idempotency_key":"day1-opening-receive","agent":{"agent_name":"test"}}',
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()['purchase_order'])
        self.assertEqual(response.json()['batch_source'], 'opening')


class Day1MigrationTest(TransactionTestCase):
    reset_sequences = True

    migrate_from = [
        ('accounting', '0010_day1_initialization'),
        ('cigars', '0033_guideconfiguration_userguideprogress'),
    ]
    migrate_to = [
        ('accounting', '0010_day1_initialization'),
        ('cigars', '0034_purchase_batch_source'),
    ]

    def tearDown(self):
        MigrationExecutor(connection).migrate(MigrationExecutor(connection).loader.graph.leaf_nodes())
        super().tearDown()

    def _make_legacy_batch(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        apps = MigrationExecutor(connection).loader.project_state(self.migrate_from).apps
        UserModel = apps.get_model('cigars', 'User')
        CigarModel = apps.get_model('cigars', 'Cigar')
        SupplierModel = apps.get_model('cigars', 'Supplier')
        PurchaseOrderModel = apps.get_model('cigars', 'PurchaseOrder')
        PurchaseOrderItemModel = apps.get_model('cigars', 'PurchaseOrderItem')
        PurchaseBatchModel = apps.get_model('cigars', 'PurchaseBatch')
        operator = UserModel.objects.create(username='day1-migration-user', is_staff=True)
        cigar = CigarModel.objects.create(brand='Migration Brand', english_name='Migration Cigar', name='迁移雪茄')
        supplier = SupplierModel.objects.create(name='Day 1 Migration Supplier')
        order = PurchaseOrderModel.objects.create(
            supplier=supplier, rub_total=Decimal('1.00'), exchange_rate=Decimal('1.0000'),
            cny_total=Decimal('10.00'), operator=operator,
        )
        item = PurchaseOrderItemModel.objects.create(
            purchase_order=order, cigar=cigar, quantity=1, box_size=None,
            unit_price_rub=Decimal('1.00'), unit_price_cny=Decimal('10.00'),
        )
        return executor, PurchaseBatchModel.objects.create(
            purchase_order_item=item, cigar=cigar, quantity=1, remaining=1,
            physical_remaining=1, original_cost_cny=Decimal('10.00'),
            remaining_cost_cny=Decimal('10.00'), unit_cost_cny=Decimal('10.00'),
        )

    def test_legacy_batch_gets_purchase_source_on_0034(self):
        executor, batch = self._make_legacy_batch()
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_to)
        migrated = executor.loader.project_state(self.migrate_to).apps.get_model('cigars', 'PurchaseBatch').objects.get(pk=batch.pk)
        self.assertEqual(migrated.source, 'purchase')
        self.assertIsNotNone(migrated.purchase_order_item_id)

    def test_rollback_refuses_opening_batches_with_clear_error(self):
        executor, batch = self._make_legacy_batch()
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_to)
        PurchaseBatchModel = executor.loader.project_state(self.migrate_to).apps.get_model('cigars', 'PurchaseBatch')
        PurchaseBatchModel.objects.filter(pk=batch.pk).update(source='opening', purchase_order_item=None)

        migration = import_module('cigars.migrations.0034_purchase_batch_source')
        with connection.schema_editor() as schema_editor:
            with self.assertRaisesRegex(RuntimeError, 'opening batches'):
                migration.refuse_opening_batches_on_reverse(
                    executor.loader.project_state(self.migrate_to).apps,
                    schema_editor,
                )

    def test_draft_account_slot_is_unique_per_initialization(self):
        initialization = Day1Initialization.objects.create()
        Day1DraftAccount.objects.create(
            initialization=initialization,
            slot=Day1DraftAccount.Slot.OWNER_CNY,
            account_name='老板人民币',
            currency='CNY',
            original_amount=Decimal('100.00'),
            cny_book_cost=Decimal('100.00'),
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            Day1DraftAccount.objects.create(
                initialization=initialization,
                slot=Day1DraftAccount.Slot.OWNER_CNY,
                account_name='重复账户',
                currency='CNY',
                original_amount=Decimal('1.00'),
                cny_book_cost=Decimal('1.00'),
            )

    def test_draft_inventory_is_unique_by_cigar_and_box_size(self):
        initialization = Day1Initialization.objects.create()
        cigar = Cigar.objects.create(
            brand='Day 1 Brand',
            english_name='Inventory Cigar',
            name='库存雪茄',
        )
        Day1DraftInventory.objects.create(
            initialization=initialization,
            cigar=cigar,
            box_size=25,
            box_quantity=1,
            loose_sticks=2,
            unit_cost_cny=Decimal('12.50'),
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            Day1DraftInventory.objects.create(
                initialization=initialization,
                cigar=cigar,
                box_size=25,
                box_quantity=2,
                loose_sticks=0,
                unit_cost_cny=Decimal('12.50'),
            )
