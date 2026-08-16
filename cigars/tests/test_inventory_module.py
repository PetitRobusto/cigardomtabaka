from decimal import Decimal
from unittest.mock import patch

from django.db import OperationalError
from django.test import TestCase

from cigars.audit import AgentContext
from cigars.inventory import (
    InventoryError,
    InventoryInsufficientError,
    adjust_stock,
    open_stock,
    receive_stock,
    release_order,
    reserve_order_item,
    ship_order,
    split_box,
)
from cigars.models import (
    AdjustmentRecord,
    Cigar,
    PurchaseBatch,
    PurchaseOrder,
    PurchaseOrderItem,
    SalesOrder,
    SalesOrderItem,
    StockAllocation,
    StockMovement,
    Supplier,
    User,
)


class InventoryModuleTest(TestCase):
    """七类库存动作共同维护数量、包装和成本事实。"""

    def setUp(self):
        self.operator = User.objects.create_user(
            'inventory-module-operator', is_staff=True,
        )
        self.cigar = Cigar.objects.create(
            brand='Inventory Module Brand',
            english_name='Inventory Module Cigar',
            name='库存模块雪茄',
        )
        self.context = AgentContext(
            agent_name='inventory-module-test',
            agent_run_id='run-1',
            agent_request_id='request-1',
            command_name='inventory_module',
            idempotency_key='inventory-module-key',
        )

    def opening(self, *, quantity, total_cost, box_size=None, boxes=0, loose=None):
        if loose is None:
            loose = quantity - ((box_size or 0) * boxes)
        return open_stock(
            cigar_id=self.cigar.pk,
            quantity=quantity,
            box_size=box_size,
            box_quantity=boxes,
            loose_sticks=loose,
            total_cost_cny=Decimal(total_cost),
            unit_cost_cny=(Decimal(total_cost) / quantity),
            operator=self.operator,
            context=self.context,
        )

    def order_item(self, *, quantity, sale_unit='stick', sale_quantity=None, box_size=None):
        order = SalesOrder.objects.create(
            customer_name='库存模块客户', operator=self.operator,
        )
        if sale_quantity is None:
            sale_quantity = quantity
        item = SalesOrderItem.objects.create(
            sales_order=order,
            cigar=self.cigar,
            quantity=quantity,
            unit_price=Decimal('100.00'),
            unit_cost=Decimal('0.00'),
            revenue=Decimal('100.00') * sale_quantity,
            cost=Decimal('0.00'),
            profit=Decimal('0.00'),
            fulfillment_type=SalesOrderItem.FulfillmentType.IN_STOCK,
            sale_unit=sale_unit,
            sale_quantity=sale_quantity,
            box_size=box_size,
        )
        return order, item

    def assert_cost_conserved(self, batch):
        batch.refresh_from_db()
        self.assertEqual(
            batch.original_cost_cny + batch.positive_adjustment_cost_cny,
            batch.remaining_cost_cny + batch.sold_cost_cny + batch.adjustment_cost_cny,
        )

    def test_opening_stock_creates_batch_shape_cost_and_receive_movement(self):
        batch = self.opening(
            quantity=7, total_cost='70.00', box_size=5, boxes=1, loose=2,
        )

        self.assertEqual(batch.source, PurchaseBatch.Source.OPENING)
        self.assertEqual(batch.remaining, 7)
        self.assertEqual(batch.physical_remaining, 7)
        self.assertEqual(batch.available_box_quantity, 1)
        self.assertEqual(batch.available_stick_quantity, 2)
        self.assertEqual(batch.remaining_cost_cny, Decimal('70.00'))
        movement = StockMovement.objects.get(purchase_batch=batch)
        self.assertEqual(movement.movement_type, StockMovement.MovementType.RECEIVE)
        self.assertEqual(movement.quantity, 7)
        self.assertEqual(movement.operator, self.operator)
        self.assertEqual(movement.agent_name, 'inventory-module-test')

    def test_opening_rejects_cost_unit_that_does_not_match_cost_pool(self):
        with self.assertRaises(InventoryError):
            open_stock(
                cigar_id=self.cigar.pk,
                quantity=3,
                box_size=None,
                box_quantity=0,
                loose_sticks=3,
                total_cost_cny=Decimal('100.00'),
                unit_cost_cny=Decimal('1.00'),
                operator=self.operator,
                context=self.context,
            )
        self.assertFalse(PurchaseBatch.objects.filter(cigar=self.cigar).exists())

    def test_purchase_receipt_creates_canonical_box_batch(self):
        supplier = Supplier.objects.create(name='库存模块供应商')
        order = PurchaseOrder.objects.create(
            supplier=supplier,
            rub_total=Decimal('500.00'),
            exchange_rate=Decimal('0.2000'),
            cny_total=Decimal('100.00'),
            operator=self.operator,
        )
        item = PurchaseOrderItem.objects.create(
            purchase_order=order,
            cigar=self.cigar,
            quantity=10,
            box_size=5,
            box_quantity=2,
            unit_price_rub=Decimal('50.00'),
            unit_price_cny=Decimal('10.00'),
            unit_price_rub_per_box=Decimal('250.00'),
            packaging_status=PurchaseOrderItem.PackagingStatus.NORMALIZED,
            actual_cost_cny=Decimal('100.00'),
        )

        batch = receive_stock(
            purchase_order_item=item,
            quantity=10,
            total_cost_cny=Decimal('100.00'),
            unit_cost_cny=Decimal('10.00'),
            operator=self.operator,
            context=self.context,
        )

        self.assertEqual(batch.source, PurchaseBatch.Source.PURCHASE)
        self.assertEqual(batch.original_box_quantity, 2)
        self.assertEqual(batch.available_box_quantity, 2)
        self.assertEqual(batch.available_stick_quantity, 0)
        self.assertTrue(StockMovement.objects.filter(
            purchase_batch=batch,
            movement_type=StockMovement.MovementType.RECEIVE,
            quantity=10,
        ).exists())

    def test_stick_reservation_uses_fifo_without_reducing_physical_stock(self):
        first = self.opening(quantity=2, total_cost='20.00')
        second = self.opening(quantity=3, total_cost='60.00')
        order, item = self.order_item(quantity=4)

        estimated_cost = reserve_order_item(
            order=order,
            item=item,
            operator=self.operator,
            context=self.context,
        )

        allocations = list(StockAllocation.objects.filter(
            sales_order_item=item,
        ).order_by('id'))
        self.assertEqual(
            [(row.purchase_batch_id, row.quantity) for row in allocations],
            [(first.pk, 2), (second.pk, 2)],
        )
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual((first.remaining, second.remaining), (0, 1))
        self.assertEqual((first.physical_remaining, second.physical_remaining), (2, 3))
        self.assertEqual(estimated_cost, Decimal('60.00'))

    def test_preorder_item_cannot_reserve_stock_through_module(self):
        self.opening(quantity=2, total_cost='20.00')
        order, item = self.order_item(quantity=1)
        item.fulfillment_type = SalesOrderItem.FulfillmentType.PREORDER
        item.save(update_fields=['fulfillment_type'])

        with self.assertRaises(InventoryError):
            reserve_order_item(
                order=order, item=item, operator=self.operator, context=self.context,
            )

        self.assertFalse(StockAllocation.objects.filter(sales_order_item=item).exists())

    def test_reservation_retries_sqlite_writer_lock_as_one_transaction(self):
        batch = self.opening(quantity=2, total_cost='20.00')
        order, item = self.order_item(quantity=1)
        lock = OperationalError('database is locked')

        with patch(
            'cigars.inventory._acquire_sqlite_writer_gate',
            side_effect=[lock, None],
        ) as writer_gate:
            reserve_order_item(
                order=order, item=item, operator=self.operator, context=self.context,
            )

        batch.refresh_from_db()
        self.assertEqual(writer_gate.call_count, 2)
        self.assertEqual(batch.remaining, 1)
        self.assertEqual(StockAllocation.objects.filter(sales_order_item=item).count(), 1)

    def test_failed_reservation_rolls_back_all_partial_fifo_writes(self):
        batch = self.opening(quantity=2, total_cost='20.00')
        order, item = self.order_item(quantity=3)

        with self.assertRaises(InventoryInsufficientError):
            reserve_order_item(
                order=order,
                item=item,
                operator=self.operator,
                context=self.context,
            )

        batch.refresh_from_db()
        self.assertEqual(batch.remaining, 2)
        self.assertEqual(StockAllocation.objects.filter(sales_order_item=item).count(), 0)
        self.assertEqual(StockMovement.objects.filter(
            sales_order_item=item,
            movement_type=StockMovement.MovementType.RESERVE,
        ).count(), 0)

    def test_box_reservation_and_release_do_not_consume_loose_sticks(self):
        batch = self.opening(
            quantity=7, total_cost='70.00', box_size=5, boxes=1, loose=2,
        )
        order, item = self.order_item(
            quantity=5,
            sale_unit=SalesOrderItem.SaleUnit.BOX,
            sale_quantity=1,
            box_size=5,
        )
        reserve_order_item(
            order=order,
            item=item,
            operator=self.operator,
            context=self.context,
        )
        batch.refresh_from_db()
        self.assertEqual(batch.remaining, 2)
        self.assertEqual(batch.available_box_quantity, 0)
        self.assertEqual(batch.available_stick_quantity, 2)
        self.assertEqual(batch.physical_remaining, 7)

        release_order(
            order=order,
            operator=self.operator,
            context=self.context,
        )
        batch.refresh_from_db()
        allocation = StockAllocation.objects.get(sales_order_item=item)
        self.assertEqual(batch.remaining, 7)
        self.assertEqual(batch.available_box_quantity, 1)
        self.assertEqual(batch.available_stick_quantity, 2)
        self.assertEqual(allocation.status, StockAllocation.Status.RELEASED)

    def test_shipping_fulfils_allocations_and_conserves_fifo_cost(self):
        first = self.opening(quantity=2, total_cost='20.00')
        second = self.opening(quantity=3, total_cost='60.00')
        order, item = self.order_item(quantity=4)
        reserve_order_item(
            order=order,
            item=item,
            operator=self.operator,
            context=self.context,
        )

        result = ship_order(
            order=order,
            operator=self.operator,
            context=self.context,
        )

        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(result.item_costs[item.pk], Decimal('60.00'))
        self.assertEqual(result.total_cost_cny, Decimal('60.00'))
        self.assertEqual((first.physical_remaining, second.physical_remaining), (0, 1))
        self.assertEqual((first.remaining_cost_cny, second.remaining_cost_cny),
                         (Decimal('0.00'), Decimal('20.00')))
        self.assertEqual(StockAllocation.objects.filter(
            sales_order_item=item,
            status=StockAllocation.Status.FULFILLED,
        ).count(), 2)
        self.assert_cost_conserved(first)
        self.assert_cost_conserved(second)

    def test_split_box_changes_shape_without_changing_aggregate_stock_or_cost(self):
        batch = self.opening(
            quantity=10, total_cost='100.00', box_size=5, boxes=2, loose=0,
        )

        split_box(
            batch_id=batch.pk,
            operator=self.operator,
            context=self.context,
        )

        batch.refresh_from_db()
        self.assertEqual(batch.remaining, 10)
        self.assertEqual(batch.physical_remaining, 10)
        self.assertEqual(batch.available_box_quantity, 1)
        self.assertEqual(batch.physical_box_quantity, 1)
        self.assertEqual(batch.available_stick_quantity, 5)
        self.assertEqual(batch.physical_stick_quantity, 5)
        self.assertEqual(batch.remaining_cost_cny, Decimal('100.00'))
        self.assertTrue(StockMovement.objects.filter(
            purchase_batch=batch,
            movement_type=StockMovement.MovementType.SPLIT_BOX,
            quantity=5,
        ).exists())

    def test_positive_adjustment_creates_costed_adjustment_batch(self):
        result = adjust_stock(
            cigar=self.cigar,
            quantity_delta=3,
            inventory_form='stick',
            unit_cost_cny=Decimal('4.00'),
            operator=self.operator,
            context=self.context,
            reason='盘盈',
        )

        batch = result.batch
        self.assertEqual(batch.source, PurchaseBatch.Source.ADJUSTMENT)
        self.assertEqual(batch.quantity, 0)
        self.assertEqual(batch.positive_adjustment_quantity, 3)
        self.assertEqual(batch.remaining, 3)
        self.assertEqual(batch.physical_remaining, 3)
        self.assertEqual(batch.remaining_cost_cny, Decimal('12.00'))
        self.assertEqual(result.cost_cny, Decimal('12.00'))
        self.assert_cost_conserved(batch)

    def test_negative_adjustment_uses_fifo_and_records_loss_cost(self):
        first = self.opening(quantity=2, total_cost='20.00')
        second = self.opening(quantity=3, total_cost='60.00')

        result = adjust_stock(
            cigar=self.cigar,
            quantity_delta=-4,
            inventory_form='stick',
            operator=self.operator,
            context=self.context,
            reason='盘亏',
            adjustment_type=AdjustmentRecord.AdjustType.LOSS,
        )

        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(result.cost_cny, Decimal('60.00'))
        self.assertEqual((first.remaining, second.remaining), (0, 1))
        self.assertEqual((first.adjustment_cost_cny, second.adjustment_cost_cny),
                         (Decimal('20.00'), Decimal('40.00')))
        self.assertEqual(AdjustmentRecord.objects.filter(
            cigar=self.cigar,
            type=AdjustmentRecord.AdjustType.LOSS,
        ).count(), 2)
        self.assert_cost_conserved(first)
        self.assert_cost_conserved(second)
