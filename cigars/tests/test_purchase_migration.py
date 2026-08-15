from datetime import datetime, timezone
from decimal import Decimal
from importlib import import_module
from unittest.mock import patch

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class PurchaseMigrationTest(TransactionTestCase):
    migrate_from = [("cigars", "0035_sales_order_transport_payer")]
    migrate_to = [("cigars", "0036_purchase_payment_state")]

    def migrate_back_to_latest(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())

    def test_0036_preserves_real_received_quote_and_marks_legacy(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        executor = MigrationExecutor(connection)
        self.addCleanup(self.migrate_back_to_latest)
        apps = executor.loader.project_state(self.migrate_from).apps
        User = apps.get_model("cigars", "User")
        Supplier = apps.get_model("cigars", "Supplier")
        Cigar = apps.get_model("cigars", "Cigar")
        PurchaseOrder = apps.get_model("cigars", "PurchaseOrder")
        PurchaseOrderItem = apps.get_model("cigars", "PurchaseOrderItem")

        operator = User.objects.create(username="migration-operator")
        supplier = Supplier.objects.create(name="迁移供应商")
        cigar = Cigar.objects.create(
            english_name="Migration Cigar", name="迁移雪茄", brand="Migration"
        )
        row = PurchaseOrder.objects.create(
            supplier_id=supplier.pk,
            operator_id=operator.pk,
            status="received",
            rub_total="25000.00",
            exchange_rate="12.0000",
            cny_total="2083.33",
        )
        PurchaseOrderItem.objects.create(
            purchase_order_id=row.pk,
            cigar_id=cigar.pk,
            quantity=25,
            box_size=25,
            unit_price_rub="1000.00",
            unit_price_cny="83.33",
        )

        executor.migrate(self.migrate_to)
        executor = MigrationExecutor(connection)
        apps = executor.loader.project_state(self.migrate_to).apps
        NewOrder = apps.get_model("cigars", "PurchaseOrder")
        NewItem = apps.get_model("cigars", "PurchaseOrderItem")
        migrated = NewOrder.objects.get(pk=row.pk)
        item = NewItem.objects.get(purchase_order_id=row.pk)

        self.assertTrue(migrated.legacy_received)
        self.assertEqual(migrated.exchange_rate, Decimal("12.0000"))
        self.assertEqual(migrated.cny_total, Decimal("2083.33"))
        self.assertEqual(migrated.paid_cny_cost, Decimal("0.00"))
        self.assertIsNone(migrated.paid_at)
        self.assertEqual(item.box_quantity, 1)
        self.assertEqual(item.unit_price_rub_per_box, Decimal("25000.00"))
        self.assertEqual(item.unit_price_rub, Decimal("1000.00"))
        self.assertEqual(item.unit_price_cny, Decimal("83.33"))
        self.assertEqual(item.quantity, item.box_size * item.box_quantity)
        self.assertEqual(item.packaging_status, "normalized")

    def test_0036_marks_non_divisible_and_unboxed_rows_for_review(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        executor = MigrationExecutor(connection)
        self.addCleanup(self.migrate_back_to_latest)
        apps = executor.loader.project_state(self.migrate_from).apps
        User = apps.get_model("cigars", "User")
        Supplier = apps.get_model("cigars", "Supplier")
        Cigar = apps.get_model("cigars", "Cigar")
        PurchaseOrder = apps.get_model("cigars", "PurchaseOrder")
        PurchaseOrderItem = apps.get_model("cigars", "PurchaseOrderItem")

        operator = User.objects.create(username="review-migration-operator")
        supplier = Supplier.objects.create(name="复核迁移供应商")
        cigar = Cigar.objects.create(
            english_name="Review Cigar", name="复核雪茄", brand="Review"
        )
        order = PurchaseOrder.objects.create(
            supplier_id=supplier.pk,
            operator_id=operator.pk,
            rub_total="3000.00",
            exchange_rate="12.0000",
            cny_total="250.00",
        )
        PurchaseOrderItem.objects.create(
            purchase_order_id=order.pk,
            cigar_id=cigar.pk,
            quantity=26,
            box_size=25,
            unit_price_rub="100.00",
            unit_price_cny="8.00",
        )
        PurchaseOrderItem.objects.create(
            purchase_order_id=order.pk,
            cigar_id=cigar.pk,
            quantity=10,
            box_size=None,
            unit_price_rub="100.00",
            unit_price_cny="8.00",
        )

        executor.migrate(self.migrate_to)
        executor = MigrationExecutor(connection)
        apps = executor.loader.project_state(self.migrate_to).apps
        NewItem = apps.get_model("cigars", "PurchaseOrderItem")
        statuses = list(
            NewItem.objects.filter(purchase_order_id=order.pk)
            .order_by("id")
            .values_list("packaging_status", "box_quantity", "unit_price_rub_per_box")
        )
        self.assertEqual(
            statuses,
            [("review_required", None, None), ("review_required", None, None)],
        )



    def test_0036_can_reverse_normalized_legacy_row_safely(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        executor = MigrationExecutor(connection)
        self.addCleanup(self.migrate_back_to_latest)
        apps = executor.loader.project_state(self.migrate_from).apps
        User = apps.get_model("cigars", "User")
        Supplier = apps.get_model("cigars", "Supplier")
        Cigar = apps.get_model("cigars", "Cigar")
        PurchaseOrder = apps.get_model("cigars", "PurchaseOrder")
        PurchaseOrderItem = apps.get_model("cigars", "PurchaseOrderItem")
        operator = User.objects.create(username="reverse-operator")
        order = PurchaseOrder.objects.create(
            supplier=Supplier.objects.create(name="可回退供应商"), operator=operator,
            status="draft", rub_total="2500.00", exchange_rate="12.0000", cny_total="208.33",
        )
        cigar = Cigar.objects.create(
            english_name="Reverse Cigar", name="回退雪茄", brand="Reverse"
        )
        PurchaseOrderItem.objects.create(
            purchase_order=order, cigar=cigar, quantity=25, box_size=25,
            unit_price_rub="100.00", unit_price_cny="8.00",
        )
        executor.migrate(self.migrate_to)
        executor = MigrationExecutor(connection)
        self.assertEqual(
            executor.loader.project_state(self.migrate_to).apps.get_model(
                "cigars", "PurchaseOrderItem"
            ).objects.get(purchase_order_id=order.pk).packaging_status,
            "normalized",
        )
        executor.migrate(self.migrate_from)
        apps = MigrationExecutor(connection).loader.project_state(self.migrate_from).apps
        OldItem = apps.get_model("cigars", "PurchaseOrderItem")
        restored = OldItem.objects.get(purchase_order_id=order.pk)
        self.assertEqual(restored.unit_price_rub, Decimal("100.00"))
        self.assertEqual(restored.unit_price_cny, Decimal("8.00"))

    def test_0036_refuses_reverse_for_new_paid_received_fact(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        executor = MigrationExecutor(connection)
        self.addCleanup(self.migrate_back_to_latest)
        apps = executor.loader.project_state(self.migrate_from).apps
        User = apps.get_model("cigars", "User")
        Supplier = apps.get_model("cigars", "Supplier")
        operator = User.objects.create(username="new-received-operator")
        supplier = Supplier.objects.create(name="新付款供应商")

        executor.migrate(self.migrate_to)
        executor = MigrationExecutor(connection)
        NewOrder = executor.loader.project_state(self.migrate_to).apps.get_model("cigars", "PurchaseOrder")
        NewOrder.objects.create(
            supplier_id=supplier.pk, operator_id=operator.pk, status="received",
            rub_total="1200.00", exchange_rate="12.0000", cny_total="100.00",
            paid_cny_cost="100.00",
            paid_at=datetime(2026, 8, 10, 12, tzinfo=timezone.utc),
            legacy_received=False,
        )

        with self.assertRaisesRegex(RuntimeError, "new received facts"):
            executor.migrate(self.migrate_from)

    def test_0036_marks_nonpositive_quantity_for_review(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        executor = MigrationExecutor(connection)
        self.addCleanup(self.migrate_back_to_latest)
        apps = executor.loader.project_state(self.migrate_from).apps
        User = apps.get_model("cigars", "User")
        Supplier = apps.get_model("cigars", "Supplier")
        Cigar = apps.get_model("cigars", "Cigar")
        PurchaseOrder = apps.get_model("cigars", "PurchaseOrder")
        PurchaseOrderItem = apps.get_model("cigars", "PurchaseOrderItem")
        operator = User.objects.create(username="negative-quantity-operator")
        order = PurchaseOrder.objects.create(
            supplier=Supplier.objects.create(name="负数量迁移供应商"), operator=operator,
            rub_total="0.00", exchange_rate="12.0000", cny_total="0.00",
        )
        cigar = Cigar.objects.create(
            english_name="Negative Quantity Cigar", name="负数量雪茄", brand="Review"
        )
        PurchaseOrderItem.objects.create(
            purchase_order=order, cigar=cigar, quantity=-25, box_size=25,
            unit_price_rub="100.00", unit_price_cny="8.00",
        )
        executor.migrate(self.migrate_to)
        executor = MigrationExecutor(connection)
        item = executor.loader.project_state(self.migrate_to).apps.get_model(
            "cigars", "PurchaseOrderItem"
        ).objects.get(purchase_order_id=order.pk)
        self.assertEqual(item.packaging_status, "review_required")
        self.assertIsNone(item.box_quantity)
        self.assertIsNone(item.unit_price_rub_per_box)

    def test_0036_keeps_canonical_when_legacy_snapshot_is_unrepresentable(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        executor = MigrationExecutor(connection)
        self.addCleanup(self.migrate_back_to_latest)
        apps = executor.loader.project_state(self.migrate_from).apps
        User = apps.get_model("cigars", "User")
        Supplier = apps.get_model("cigars", "Supplier")
        Cigar = apps.get_model("cigars", "Cigar")
        PurchaseOrder = apps.get_model("cigars", "PurchaseOrder")
        PurchaseOrderItem = apps.get_model("cigars", "PurchaseOrderItem")
        operator = User.objects.create(username="snapshot-review-operator")
        order = PurchaseOrder.objects.create(
            supplier=Supplier.objects.create(name="快照复核供应商"), operator=operator,
            rub_total="2500.00", exchange_rate="12.0000", cny_total="208.33",
        )
        cigar = Cigar.objects.create(
            english_name="Snapshot Cigar", name="快照雪茄", brand="Review"
        )
        PurchaseOrderItem.objects.create(
            purchase_order=order, cigar=cigar, quantity=25, box_size=25,
            unit_price_rub="100.00", unit_price_cny="8.00",
        )
        migration_module = import_module("cigars.migrations.0036_purchase_payment_state")
        # 旧快照不可无损的分支由迁移 helper 明确判定；canonical 仍必须保留。
        with patch.object(migration_module, "_fits_legacy_price", side_effect=[True, False]):
            executor.migrate(self.migrate_to)
        executor = MigrationExecutor(connection)
        item = executor.loader.project_state(self.migrate_to).apps.get_model(
            "cigars", "PurchaseOrderItem"
        ).objects.get(purchase_order_id=order.pk)
        self.assertEqual(item.box_quantity, 1)
        self.assertEqual(item.unit_price_rub_per_box, Decimal("2500.00"))
        self.assertEqual(item.packaging_status, "unrepresentable")
        self.assertEqual(item.legacy_snapshot_status, "unrepresentable")
        self.assertIsNone(item.unit_price_rub)
        self.assertIsNone(item.unit_price_cny)

    def test_0036_clears_positive_rub_and_negative_cny_legacy_snapshot(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        executor = MigrationExecutor(connection)
        self.addCleanup(self.migrate_back_to_latest)
        apps = executor.loader.project_state(self.migrate_from).apps
        User = apps.get_model('cigars', 'User')
        Supplier = apps.get_model('cigars', 'Supplier')
        Cigar = apps.get_model('cigars', 'Cigar')
        PurchaseOrder = apps.get_model('cigars', 'PurchaseOrder')
        PurchaseOrderItem = apps.get_model('cigars', 'PurchaseOrderItem')
        operator = User.objects.create(username='negative-cny-operator')
        order = PurchaseOrder.objects.create(
            supplier=Supplier.objects.create(name='负人民币快照供应商'), operator=operator,
            rub_total='2500.00', exchange_rate='12.0000', cny_total='-16.67',
        )
        cigar = Cigar.objects.create(
            english_name='Negative CNY Snapshot Cigar', name='负人民币快照雪茄', brand='Review'
        )
        PurchaseOrderItem.objects.create(
            purchase_order=order, cigar=cigar, quantity=25, box_size=25,
            unit_price_rub='100.00', unit_price_cny='-8.00',
        )

        executor.migrate(self.migrate_to)
        executor = MigrationExecutor(connection)
        item = executor.loader.project_state(self.migrate_to).apps.get_model(
            'cigars', 'PurchaseOrderItem'
        ).objects.get(purchase_order_id=order.pk)
        self.assertEqual(item.box_quantity, 1)
        self.assertEqual(item.unit_price_rub_per_box, Decimal('2500.00'))
        self.assertEqual(item.packaging_status, 'unrepresentable')
        self.assertEqual(item.legacy_snapshot_status, 'unrepresentable')
        self.assertIsNone(item.unit_price_rub)
        self.assertIsNone(item.unit_price_cny)

    def test_0036_handles_nonfinite_legacy_prices_without_crashing(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        executor = MigrationExecutor(connection)
        self.addCleanup(self.migrate_back_to_latest)
        apps = executor.loader.project_state(self.migrate_from).apps
        User = apps.get_model("cigars", "User")
        Supplier = apps.get_model("cigars", "Supplier")
        Cigar = apps.get_model("cigars", "Cigar")
        PurchaseOrder = apps.get_model("cigars", "PurchaseOrder")
        PurchaseOrderItem = apps.get_model("cigars", "PurchaseOrderItem")
        operator = User.objects.create(username="nonfinite-price-operator")
        order = PurchaseOrder.objects.create(
            supplier=Supplier.objects.create(name="非有限价格供应商"), operator=operator,
            rub_total="10000.00", exchange_rate="12.0000", cny_total="800.00",
        )
        rows = [
            ("RUB NaN", "NaN", "8.00"),
            ("RUB Infinity", "Infinity", "8.00"),
            ("CNY NaN", "100.00", "NaN"),
            ("CNY Infinity", "100.00", "Infinity"),
        ]
        for name, rub, cny in rows:
            cigar = Cigar.objects.create(
                english_name=name, name=name, brand="Review",
            )
            item = PurchaseOrderItem.objects.create(
                purchase_order=order, cigar=cigar, quantity=25, box_size=25,
                unit_price_rub="100.00", unit_price_cny="8.00",
            )
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE cigars_purchaseorderitem SET unit_price_rub = %s, unit_price_cny = %s WHERE id = %s",
                            [rub, cny, item.pk],
                )

        migration_module = import_module("cigars.migrations.0036_purchase_payment_state")
        self.assertFalse(migration_module._fits_legacy_price(Decimal("NaN")))
        self.assertFalse(migration_module._fits_legacy_price(Decimal("Infinity")))
        self.assertFalse(migration_module._fits_canonical_box_price(Decimal("NaN")))

        executor.migrate(self.migrate_to)
        executor = MigrationExecutor(connection)
        NewItem = executor.loader.project_state(self.migrate_to).apps.get_model(
            "cigars", "PurchaseOrderItem"
        )
        migrated = list(NewItem.objects.filter(purchase_order_id=order.pk).order_by("id"))
        self.assertEqual(
            [(item.packaging_status, item.box_quantity, item.unit_price_rub_per_box) for item in migrated[:2]],
            [("review_required", None, None), ("review_required", None, None)],
        )
        for item in migrated[2:]:
            self.assertEqual(item.packaging_status, "unrepresentable")
            self.assertEqual(item.legacy_snapshot_status, "unrepresentable")
            self.assertEqual(item.box_quantity, 1)
            self.assertEqual(item.unit_price_rub_per_box, Decimal("2500.00"))
            self.assertIsNone(item.unit_price_rub)
            self.assertIsNone(item.unit_price_cny)

    def test_0036_does_not_normalize_negative_legacy_price(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        executor = MigrationExecutor(connection)
        self.addCleanup(self.migrate_back_to_latest)
        apps = executor.loader.project_state(self.migrate_from).apps
        User = apps.get_model("cigars", "User")
        Supplier = apps.get_model("cigars", "Supplier")
        Cigar = apps.get_model("cigars", "Cigar")
        PurchaseOrder = apps.get_model("cigars", "PurchaseOrder")
        PurchaseOrderItem = apps.get_model("cigars", "PurchaseOrderItem")
        operator = User.objects.create(username="negative-price-operator")
        order = PurchaseOrder.objects.create(
            supplier=Supplier.objects.create(name="负价迁移供应商"),
            operator=operator, rub_total="-2500.00",
            exchange_rate="12.0000", cny_total="-208.33",
        )
        cigar = Cigar.objects.create(
            english_name="Negative Price Cigar", name="负价雪茄", brand="Review"
        )
        PurchaseOrderItem.objects.create(
            purchase_order=order, cigar=cigar, quantity=25, box_size=25,
            unit_price_rub="-100.00", unit_price_cny="-8.00",
        )
        executor.migrate(self.migrate_to)
        executor = MigrationExecutor(connection)
        item = executor.loader.project_state(self.migrate_to).apps.get_model(
            "cigars", "PurchaseOrderItem"
        ).objects.get(purchase_order_id=order.pk)
        self.assertEqual(item.packaging_status, "review_required")
        self.assertIsNone(item.box_quantity)
        self.assertIsNone(item.unit_price_rub_per_box)
