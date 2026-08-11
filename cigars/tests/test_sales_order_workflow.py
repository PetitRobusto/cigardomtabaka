from decimal import Decimal

from django.test import TestCase

from cigars.models import (
    Brand,
    Cigar,
    PurchaseBatch,
    PurchaseOrder,
    PurchaseOrderItem,
    SalesOrder,
    StockAllocation,
    StockMovement,
    Supplier,
    User,
)
from cigars.services import AgentContext, create_sales_order_draft


class SalesOrderWorkflowTest(TestCase):
    def setUp(self):
        self.operator = User.objects.create_user('workflow-operator', password='pass', is_staff=True)
        brand = Brand.objects.create(english_name='Workflow Brand', name='流程品牌')
        self.cigar = Cigar.objects.create(
            brand=brand.english_name,
            english_name='Workflow Cigar',
            name='流程雪茄',
        )

    def context(self, command):
        return AgentContext(
            agent_name='workflow-test',
            agent_run_id='workflow-run',
            agent_request_id='workflow-request',
            command_name=command,
        )

    def batch(self, *, remaining, unit_cost='10.00', box_size=25):
        supplier = Supplier.objects.create(name=f'workflow-supplier-{PurchaseOrder.objects.count()}')
        purchase_order = PurchaseOrder.objects.create(
            supplier=supplier,
            rub_total=Decimal('1.00'),
            exchange_rate=Decimal('1.0000'),
            cny_total=Decimal(str(remaining)) * Decimal(unit_cost),
            operator=self.operator,
        )
        purchase_item = PurchaseOrderItem.objects.create(
            purchase_order=purchase_order,
            cigar=self.cigar,
            quantity=remaining,
            box_size=box_size,
            unit_price_rub=Decimal('1.00'),
            unit_price_cny=Decimal(unit_cost),
        )
        return PurchaseBatch.objects.create(
            purchase_order_item=purchase_item,
            cigar=self.cigar,
            quantity=remaining,
            remaining=remaining,
            physical_remaining=remaining,
            original_cost_cny=Decimal(str(remaining)) * Decimal(unit_cost),
            remaining_cost_cny=Decimal(str(remaining)) * Decimal(unit_cost),
            unit_cost_cny=Decimal(unit_cost),
        )

    def test_split_box_movement_type_is_available(self):
        self.assertIn('split_box', StockMovement.MovementType.values)

    def test_split_box_service_is_available(self):
        from cigars import services
        self.assertTrue(callable(getattr(services, 'split_purchase_batch_box', None)))

    def test_create_draft_snapshots_box_price_and_does_not_touch_stock(self):
        batch = self.batch(remaining=25, unit_cost='10.00', box_size=25)

        order = create_sales_order_draft(
            items=[{
                'cigar_id': self.cigar.id,
                'sale_unit': 'box',
                'sale_quantity': 2,
                'box_size': 25,
                'unit_price': '100.01',
            }],
            operator=self.operator,
            customer_name='张三',
            customer_transport_fee_cny='8.88',
            note='先建草稿',
            agent_context=self.context('create_sales_order_draft'),
        )

        item = order.items.get()
        batch.refresh_from_db()
        self.assertEqual(order.fulfillment_status, SalesOrder.FulfillmentStatus.DRAFT)
        self.assertEqual(order.payment_status, SalesOrder.PaymentStatus.UNPAID)
        self.assertEqual(order.status, 'draft')
        self.assertFalse(order.locked)
        self.assertEqual(item.quantity, 50)
        self.assertEqual(item.sale_quantity, 2)
        self.assertEqual(item.box_size, 25)
        self.assertEqual(item.unit_price, Decimal('4.00'))
        self.assertEqual(item.revenue, Decimal('200.02'))
        self.assertEqual(item.cost, Decimal('0.00'))
        self.assertEqual(item.profit, Decimal('0.00'))
        self.assertEqual(order.goods_amount_cny, Decimal('200.02'))
        self.assertEqual(order.customer_transport_fee_cny, Decimal('8.88'))
        self.assertEqual(order.amount_due_cny, Decimal('208.90'))
        self.assertEqual(order.total_revenue, Decimal('200.02'))
        self.assertEqual(order.total_cost, Decimal('0.00'))
        self.assertEqual(order.total_profit, Decimal('0.00'))
        self.assertEqual(batch.remaining, 25)
        self.assertEqual(batch.physical_remaining, 25)
        self.assertEqual(batch.remaining_cost_cny, Decimal('250.00'))
        self.assertFalse(StockAllocation.objects.exists())
        self.assertFalse(StockMovement.objects.exists())


    def test_update_draft_replaces_items_and_recalculates_amounts(self):
        from cigars.services import update_sales_order_draft
        order = create_sales_order_draft(
            items=[{"cigar_id": self.cigar.id, "sale_unit": "stick", "quantity": 1, "unit_price": "10.00"}],
            operator=self.operator, customer_name="旧客户",
            agent_context=self.context("create_sales_order_draft"),
        )

        updated = update_sales_order_draft(
            sales_order_id=order.id,
            items=[{"cigar_id": self.cigar.id, "sale_unit": "stick", "quantity": 3, "unit_price": "20.00"}],
            operator=self.operator, customer_name="新客户", customer_transport_fee_cny="2.00",
            note="已改价", agent_context=self.context("update_sales_order_draft"),
        )

        self.assertEqual(updated.items.count(), 1)
        self.assertEqual(updated.items.get().revenue, Decimal("60.00"))
        self.assertEqual(updated.items.get().cost, Decimal("0.00"))
        self.assertEqual(updated.items.get().profit, Decimal("0.00"))
        self.assertEqual(updated.total_cost, Decimal("0.00"))
        self.assertEqual(updated.total_profit, Decimal("0.00"))
        self.assertEqual(updated.customer_name, "新客户")
        self.assertEqual(updated.amount_due_cny, Decimal("62.00"))
        self.assertFalse(StockAllocation.objects.exists())


    def test_update_draft_rejects_inconsistent_box_quantity(self):
        from cigars.services import OrderServiceError, update_sales_order_draft
        order = create_sales_order_draft(
            items=[{'cigar_id': self.cigar.id, 'sale_unit': 'stick', 'quantity': 1, 'unit_price': '10.00'}],
            operator=self.operator, agent_context=self.context('create-draft'),
        )
        with self.assertRaises(OrderServiceError):
            update_sales_order_draft(
                sales_order_id=order.id,
                items=[{'cigar_id': self.cigar.id, 'sale_unit': 'box', 'sale_quantity': 2,
                        'box_size': 25, 'quantity': 49, 'unit_price': '100.00'}],
                operator=self.operator, agent_context=self.context('update-draft'),
            )
        order.refresh_from_db()
        self.assertEqual(order.items.get().quantity, 1)

    def test_confirm_stick_reserves_fifo_and_locks_without_shipping(self):
        batch = self.batch(remaining=3, unit_cost="10.00")
        order = create_sales_order_draft(
            items=[{"cigar_id": self.cigar.id, "sale_unit": "stick", "quantity": 2, "unit_price": "30.00"}],
            operator=self.operator, agent_context=self.context("create_sales_order_draft"),
        )
        from cigars.services import confirm_sales_order

        confirmed = confirm_sales_order(
            sales_order_id=order.id, operator=self.operator,
            agent_context=self.context("confirm_sales_order"),
        )

        batch.refresh_from_db(); item = confirmed.items.get()
        self.assertEqual(batch.remaining, 1)
        self.assertEqual(batch.physical_remaining, 3)
        self.assertEqual(batch.remaining_cost_cny, Decimal("30.00"))
        self.assertEqual(item.cost, Decimal("0.00"))
        self.assertEqual(item.profit, Decimal("0.00"))
        self.assertEqual(confirmed.total_cost, Decimal("0.00"))
        self.assertEqual(confirmed.fulfillment_status, SalesOrder.FulfillmentStatus.CONFIRMED)
        self.assertEqual(confirmed.status, "pending_payment")
        self.assertTrue(confirmed.locked)
        self.assertEqual(confirmed.locked_by, self.operator)
        self.assertEqual(StockAllocation.objects.get().status, StockAllocation.Status.RESERVED)
        reserve = StockMovement.objects.get(movement_type=StockMovement.MovementType.RESERVE)
        self.assertEqual(reserve.operator, self.operator)
        self.assertEqual(reserve.command_name, "confirm_sales_order")

    def test_confirm_box_reserves_complete_matching_boxes_only(self):
        first = self.batch(remaining=25, unit_cost="10.00", box_size=25)
        second = self.batch(remaining=25, unit_cost="12.00", box_size=25)
        other_size = self.batch(remaining=25, unit_cost="1.00", box_size=10)
        order = create_sales_order_draft(
            items=[{"cigar_id": self.cigar.id, "sale_unit": "box", "sale_quantity": 2, "box_size": 25, "unit_price": "100.00"}],
            operator=self.operator, agent_context=self.context("create_sales_order_draft"),
        )
        from cigars.services import confirm_sales_order

        confirm_sales_order(sales_order_id=order.id, operator=self.operator, agent_context=self.context("confirm_sales_order"))

        allocations = list(order.items.get().allocations.order_by("purchase_batch_id", "id"))
        self.assertEqual([(a.purchase_batch_id, a.quantity) for a in allocations], [(first.id, 25), (second.id, 25)])
        self.assertTrue(all(allocation.quantity % 25 == 0 for allocation in allocations))
        other_size.refresh_from_db()
        self.assertEqual(other_size.remaining, 25)

    def test_cancel_confirmed_unpaid_releases_reservation_without_shipping(self):
        batch = self.batch(remaining=2, unit_cost="10.00")
        order = create_sales_order_draft(
            items=[{"cigar_id": self.cigar.id, "sale_unit": "stick", "quantity": 1, "unit_price": "30.00"}],
            operator=self.operator, agent_context=self.context("create_sales_order_draft"),
        )
        from cigars.services import cancel_confirmed_sales_order, confirm_sales_order
        confirm_sales_order(sales_order_id=order.id, operator=self.operator, agent_context=self.context("confirm_sales_order"))

        cancelled = cancel_confirmed_sales_order(
            sales_order_id=order.id, operator=self.operator,
            agent_context=self.context("cancel_confirmed_sales_order"),
        )

        batch.refresh_from_db(); allocation = StockAllocation.objects.get()
        self.assertEqual(batch.remaining, 2)
        self.assertEqual(batch.physical_remaining, 2)
        self.assertEqual(batch.remaining_cost_cny, Decimal("20.00"))
        self.assertEqual(allocation.status, StockAllocation.Status.RELEASED)
        self.assertEqual(cancelled.fulfillment_status, SalesOrder.FulfillmentStatus.CANCELLED)
        self.assertEqual(cancelled.payment_status, SalesOrder.PaymentStatus.UNPAID)
        self.assertEqual(cancelled.status, "cancelled")
        release = StockMovement.objects.get(movement_type=StockMovement.MovementType.RELEASE_RESERVATION)
        self.assertEqual(release.operator, self.operator)
        self.assertEqual(release.command_name, "cancel_confirmed_sales_order")

    def test_cancel_confirmed_paid_marks_refund_pending(self):
        self.batch(remaining=1)
        order = create_sales_order_draft(
            items=[{"cigar_id": self.cigar.id, "sale_unit": "stick", "quantity": 1, "unit_price": "30.00"}],
            operator=self.operator, agent_context=self.context("create_sales_order_draft"),
        )
        from cigars.services import cancel_confirmed_sales_order, confirm_sales_order
        confirm_sales_order(sales_order_id=order.id, operator=self.operator, agent_context=self.context("confirm_sales_order"))
        order.payment_status = SalesOrder.PaymentStatus.PAID
        order.save(update_fields=["payment_status"])

        cancelled = cancel_confirmed_sales_order(
            sales_order_id=order.id, operator=self.operator,
            agent_context=self.context("cancel_confirmed_sales_order"),
        )

        self.assertEqual(cancelled.payment_status, SalesOrder.PaymentStatus.REFUND_PENDING)

    def test_confirm_rolls_back_all_items_when_later_item_is_insufficient(self):
        batch = self.batch(remaining=1, unit_cost="10.00")
        order = create_sales_order_draft(
            items=[
                {"cigar_id": self.cigar.id, "sale_unit": "stick", "quantity": 1, "unit_price": "30.00"},
                {"cigar_id": self.cigar.id, "sale_unit": "stick", "quantity": 1, "unit_price": "30.00"},
            ], operator=self.operator, agent_context=self.context("create_sales_order_draft"),
        )
        from cigars.services import InsufficientStockError, confirm_sales_order

        with self.assertRaises(InsufficientStockError):
            confirm_sales_order(sales_order_id=order.id, operator=self.operator, agent_context=self.context("confirm_sales_order"))

        batch.refresh_from_db(); order.refresh_from_db()
        self.assertEqual(batch.remaining, 1)
        self.assertFalse(StockAllocation.objects.filter(sales_order_item__sales_order=order).exists())
        self.assertEqual(order.fulfillment_status, SalesOrder.FulfillmentStatus.DRAFT)

    def test_confirmed_order_cannot_be_updated_or_confirmed_twice(self):
        self.batch(remaining=1)
        order = create_sales_order_draft(
            items=[{"cigar_id": self.cigar.id, "sale_unit": "stick", "quantity": 1, "unit_price": "30.00"}],
            operator=self.operator, agent_context=self.context("create_sales_order_draft"),
        )
        from cigars.services import OrderServiceError, confirm_sales_order, update_sales_order_draft
        confirm_sales_order(sales_order_id=order.id, operator=self.operator, agent_context=self.context("confirm_sales_order"))

        with self.assertRaises(OrderServiceError):
            update_sales_order_draft(
                sales_order_id=order.id, items=[{"cigar_id": self.cigar.id, "sale_unit": "stick", "quantity": 1, "unit_price": "1.00"}],
                operator=self.operator, agent_context=self.context("update_sales_order_draft"),
            )
        with self.assertRaises(OrderServiceError):
            confirm_sales_order(sales_order_id=order.id, operator=self.operator, agent_context=self.context("confirm_sales_order"))

    def test_cancel_rejects_draft_shipped_and_cancelled_orders(self):
        from cigars.services import OrderServiceError, cancel_confirmed_sales_order
        draft = create_sales_order_draft(
            items=[{"cigar_id": self.cigar.id, "sale_unit": "stick", "quantity": 1, "unit_price": "30.00"}],
            operator=self.operator, agent_context=self.context("create_sales_order_draft"),
        )
        for status in (SalesOrder.FulfillmentStatus.DRAFT, SalesOrder.FulfillmentStatus.SHIPPED, SalesOrder.FulfillmentStatus.CANCELLED):
            draft.fulfillment_status = status; draft.save(update_fields=["fulfillment_status"])
            with self.assertRaises(OrderServiceError):
                cancel_confirmed_sales_order(sales_order_id=draft.id, operator=self.operator, agent_context=self.context("cancel_confirmed_sales_order"))

    def test_box_does_not_combine_residuals_or_mismatched_packaging(self):
        first = self.batch(remaining=24, box_size=25)
        second = self.batch(remaining=24, box_size=25)
        mismatch = self.batch(remaining=25, box_size=10)
        order = create_sales_order_draft(
            items=[{"cigar_id": self.cigar.id, "sale_unit": "box", "sale_quantity": 1, "box_size": 25, "unit_price": "100.00"}],
            operator=self.operator, agent_context=self.context("create_sales_order_draft"),
        )
        from cigars.services import InsufficientStockError, confirm_sales_order
        with self.assertRaises(InsufficientStockError) as raised:
            confirm_sales_order(sales_order_id=order.id, operator=self.operator, agent_context=self.context("confirm_sales_order"))
        first.refresh_from_db(); second.refresh_from_db(); mismatch.refresh_from_db()
        self.assertEqual((first.remaining, second.remaining, mismatch.remaining), (24, 24, 25))
        self.assertEqual(raised.exception.details["available"], 0)

    def test_event_and_movement_preserve_agent_context(self):
        self.batch(remaining=1)
        order = create_sales_order_draft(
            items=[{"cigar_id": self.cigar.id, "sale_unit": "stick", "quantity": 1, "unit_price": "30.00"}],
            operator=self.operator, agent_context=self.context("draft-command"),
        )
        from cigars.services import confirm_sales_order
        confirm_sales_order(sales_order_id=order.id, operator=self.operator, agent_context=self.context("confirm-command"))
        event = order.events.order_by("id").last()
        movement = StockMovement.objects.get(movement_type=StockMovement.MovementType.RESERVE)
        self.assertEqual(event.operator, self.operator)
        self.assertEqual(event.command_name, "confirm-command")
        self.assertEqual(event.metadata["fulfillment_status"], SalesOrder.FulfillmentStatus.CONFIRMED)
        self.assertEqual(movement.operator, self.operator)
        self.assertEqual(movement.agent_name, "workflow-test")
        self.assertEqual(movement.command_name, "confirm-command")

    def test_batch_has_explicit_box_and_stick_inventory_facts(self):
        batch = self.batch(remaining=27, box_size=25)

        self.assertEqual(batch.box_size, 25)
        self.assertEqual(batch.original_box_quantity, 1)
        self.assertEqual(batch.original_stick_quantity, 2)
        self.assertEqual(batch.physical_box_quantity, 1)
        self.assertEqual(batch.available_box_quantity, 1)
        self.assertEqual(batch.physical_stick_quantity, 2)
        self.assertEqual(batch.available_stick_quantity, 2)

    def test_packaging_facts_database_constraints_reject_inconsistent_shapes(self):
        from django.db import IntegrityError, transaction
        batch = self.batch(remaining=25, box_size=25)
        with self.assertRaises(IntegrityError), transaction.atomic():
            PurchaseBatch.objects.filter(pk=batch.pk).update(available_box_quantity=2)
        with self.assertRaises(IntegrityError), transaction.atomic():
            PurchaseBatch.objects.filter(pk=batch.pk).update(physical_stick_quantity=1)

    def test_split_box_conserves_shape_aggregate_cost_and_audit_context(self):
        batch = self.batch(remaining=25, unit_cost='10.00', box_size=25)
        before_cost = batch.remaining_cost_cny
        from cigars.services import split_purchase_batch_box
        split_purchase_batch_box(batch_id=batch.id, operator=self.operator,
                                 agent_context=self.context('split-box'), note='拆盒')
        batch.refresh_from_db()
        self.assertEqual(
            (batch.physical_box_quantity, batch.available_box_quantity,
             batch.physical_stick_quantity, batch.available_stick_quantity),
            (0, 0, 25, 25),
        )
        self.assertEqual((batch.remaining, batch.physical_remaining), (25, 25))
        self.assertEqual(batch.remaining_cost_cny, before_cost)
        movement = StockMovement.objects.get(movement_type=StockMovement.MovementType.SPLIT_BOX)
        self.assertEqual(movement.quantity, 25)
        self.assertEqual(movement.operator, self.operator)
        self.assertEqual(movement.command_name, 'split-box')
        self.assertEqual(movement.agent_name, 'workflow-test')
        self.assertEqual(movement.note, '拆盒')

    def test_stick_sale_does_not_implicitly_consume_complete_box(self):
        batch = self.batch(remaining=25, box_size=25)
        order = create_sales_order_draft(
            items=[{'cigar_id': self.cigar.id, 'sale_unit': 'stick', 'quantity': 1, 'unit_price': '10.00'}],
            operator=self.operator, agent_context=self.context('create-draft'),
        )
        from cigars.services import InsufficientStockError, confirm_sales_order
        with self.assertRaises(InsufficientStockError):
            confirm_sales_order(sales_order_id=order.id, operator=self.operator,
                                agent_context=self.context('confirm-order'))
        batch.refresh_from_db()
        self.assertEqual((batch.available_box_quantity, batch.available_stick_quantity), (1, 0))
        self.assertFalse(StockAllocation.objects.exists())
