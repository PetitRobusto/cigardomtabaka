import json
from decimal import Decimal

from django.test import Client, TestCase

from cigars.models import (
    Brand,
    AdjustmentRecord,
    Cigar,
    IdempotencyRecord,
    OrderEvent,
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
from cigars.services import (
    AgentContext,
    InsufficientStockError,
    OrderServiceError,
    adjust_stock,
    cancel_sales_order,
    confirm_payment,
    create_purchase_order,
    create_sales_order,
    receive_purchase_order,
)


def create_operator(username='operator'):
    return User.objects.create_user(username, password='pass', is_staff=True)


def create_cigar():
    brand = Brand.objects.create(english_name='TestBrand', name='测试品牌')
    return Cigar.objects.create(
        brand=brand.english_name,
        english_name='Test Cigar',
        name='测试雪茄',
        vitola='Robusto',
    )


def create_batch(cigar, *, remaining, unit_cost, operator=None):
    operator = operator or User.objects.first() or create_operator('po_operator')
    supplier = Supplier.objects.create(name=f'Supplier-{remaining}-{unit_cost}')
    po = PurchaseOrder.objects.create(
        supplier=supplier,
        rub_total=Decimal('1000.00'),
        exchange_rate=Decimal('1.0000'),
        cny_total=Decimal(str(remaining)) * Decimal(str(unit_cost)),
        operator=operator,
    )
    item = PurchaseOrderItem.objects.create(
        purchase_order=po,
        cigar=cigar,
        quantity=remaining,
        box_size=25,
        unit_price_rub=Decimal('10.00'),
        unit_price_cny=Decimal(str(unit_cost)),
    )
    return PurchaseBatch.objects.create(
        purchase_order_item=item,
        cigar=cigar,
        quantity=remaining,
        remaining=remaining,
        physical_remaining=remaining,
        original_cost_cny=Decimal(str(remaining)) * Decimal(str(unit_cost)),
        positive_adjustment_quantity=0,
        positive_adjustment_cost_cny=Decimal('0.00'),
        adjustment_cost_cny=Decimal('0.00'),
        remaining_cost_cny=Decimal(str(remaining)) * Decimal(str(unit_cost)),
        sold_cost_cny=Decimal('0.00'),
        unit_cost_cny=Decimal(str(unit_cost)),
    )


def context(command='create_sales_order', key='test-key'):
    return AgentContext(
        agent_name='codex',
        agent_run_id='run-1',
        agent_request_id='req-1',
        command_name=command,
        idempotency_key=key,
    )


def reserve_allocation(order, cigar, batch, quantity):
    item = SalesOrderItem.objects.create(
        sales_order=order,
        cigar=cigar,
        quantity=quantity,
        unit_price=Decimal('20.00'),
        unit_cost=batch.unit_cost_cny,
        revenue=Decimal('20.00') * quantity,
        cost=batch.unit_cost_cny * quantity,
        profit=(Decimal('20.00') - batch.unit_cost_cny) * quantity,
    )
    allocation = StockAllocation.objects.create(
        sales_order_item=item,
        purchase_batch=batch,
        quantity=quantity,
        status=StockAllocation.Status.RESERVED,
    )
    batch.remaining -= quantity
    batch.available_stick_quantity -= quantity
    batch.save(update_fields=['remaining', 'available_stick_quantity'])
    return allocation


class OrderInventoryServiceTest(TestCase):
    def setUp(self):
        self.operator = create_operator()
        self.cigar = create_cigar()

    def test_in_stock_create_reserves_stock(self):
        batch = create_batch(self.cigar, remaining=10, unit_cost='100.00', operator=self.operator)

        order = create_sales_order(
            items=[{'cigar_id': self.cigar.id, 'quantity': 4, 'unit_price': 180}],
            operator=self.operator,
            customer_name='张三',
            agent_context=context(),
            note='客户等付款',
        )

        batch.refresh_from_db()
        self.assertEqual(order.status, 'pending_payment')
        self.assertEqual(batch.remaining, 6)
        self.assertEqual(order.items.first().allocations.count(), 1)
        reserve = StockMovement.objects.get(movement_type='reserve')
        self.assertEqual(reserve.quantity, 4)


    def test_sales_order_defaults_to_stick_snapshot(self):
        create_batch(self.cigar, remaining=10, unit_cost='100.00', operator=self.operator)
        order = create_sales_order(
            items=[{'cigar_id': self.cigar.id, 'quantity': 4, 'unit_price': 180}],
            operator=self.operator,
            agent_context=context(),
        )
        item = order.items.get()
        self.assertEqual(item.sale_unit, SalesOrderItem.SaleUnit.STICK)
        self.assertEqual(item.sale_quantity, 4)
        self.assertIsNone(item.box_size)

    def test_box_snapshot_requires_consistent_positive_values(self):
        create_batch(self.cigar, remaining=10, unit_cost='100.00', operator=self.operator)
        invalid_items = [
            {'cigar_id': self.cigar.id, 'quantity': 4, 'unit_price': 180, 'sale_unit': 'box', 'sale_quantity': 0, 'box_size': 4},
            {'cigar_id': self.cigar.id, 'quantity': 4, 'unit_price': 180, 'sale_unit': 'box', 'sale_quantity': 1, 'box_size': 5},
        ]
        for raw_item in invalid_items:
            with self.assertRaises(OrderServiceError):
                create_sales_order(items=[raw_item], operator=self.operator, agent_context=context())


    def test_confirm_payment_ships_reserved_stock(self):
        batch = create_batch(self.cigar, remaining=10, unit_cost='100.00', operator=self.operator)
        order = create_sales_order(
            items=[{'cigar_id': self.cigar.id, 'quantity': 4, 'unit_price': 180}],
            operator=self.operator,
            agent_context=context(),
        )

        paid = confirm_payment(
            sales_order_id=order.id,
            operator=self.operator,
            agent_context=context(command='confirm_payment', key='pay-key'),
            note='已收款',
        )

        batch.refresh_from_db()
        self.assertEqual(paid.status, 'paid')
        self.assertEqual(batch.remaining, 6)
        self.assertEqual(batch.physical_remaining, 6)
        self.assertEqual(batch.remaining_cost_cny, Decimal('600.00'))
        self.assertEqual(batch.sold_cost_cny, Decimal('400.00'))
        self.assertEqual(
            set(paid.items.first().allocations.values_list('status', flat=True)),
            {'fulfilled'},
        )
        ship = StockMovement.objects.get(movement_type='ship')
        self.assertEqual(ship.quantity, 4)

    def test_confirm_payment_locks_allocations_by_batch_then_allocation_id(self):
        first_batch = create_batch(self.cigar, remaining=1, unit_cost='10.00', operator=self.operator)
        second_batch = create_batch(self.cigar, remaining=1, unit_cost='11.00', operator=self.operator)
        order = SalesOrder.objects.create(operator=self.operator, status='pending_payment')

        for batch in (second_batch, first_batch):
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
            StockAllocation.objects.create(
                sales_order_item=item,
                purchase_batch=batch,
                quantity=1,
                status=StockAllocation.Status.RESERVED,
            )
            batch.remaining = 0
            batch.available_stick_quantity = 0
            batch.save(update_fields=['remaining', 'available_stick_quantity'])

        confirm_payment(
            sales_order_id=order.id,
            operator=self.operator,
            agent_context=context(command='confirm_payment', key='batch-lock-order'),
        )

        shipment_batch_ids = list(
            StockMovement.objects.filter(movement_type='ship').order_by('id')
            .values_list('purchase_batch_id', flat=True)
        )
        self.assertEqual(shipment_batch_ids, [first_batch.id, second_batch.id])

    def test_confirm_payment_moves_cost_for_multiple_allocations_and_last_unit_tail(self):
        batch = create_batch(self.cigar, remaining=3, unit_cost='3.34', operator=self.operator)
        batch.original_cost_cny = Decimal('10.01')
        batch.remaining_cost_cny = Decimal('10.01')
        batch.save(update_fields=['original_cost_cny', 'remaining_cost_cny'])
        order = SalesOrder.objects.create(operator=self.operator, status='pending_payment')
        reserve_allocation(order, self.cigar, batch, 1)
        reserve_allocation(order, self.cigar, batch, 2)

        confirm_payment(
            sales_order_id=order.id,
            operator=self.operator,
            agent_context=context(command='confirm_payment', key='tail-cost'),
        )

        batch.refresh_from_db()
        self.assertEqual(batch.quantity, 3)
        self.assertEqual(batch.original_cost_cny, Decimal('10.01'))
        self.assertEqual(batch.positive_adjustment_quantity, 0)
        self.assertEqual(batch.positive_adjustment_cost_cny, Decimal('0.00'))
        self.assertEqual(batch.adjustment_cost_cny, Decimal('0.00'))
        self.assertEqual(
            batch.original_cost_cny + batch.positive_adjustment_cost_cny,
            batch.remaining_cost_cny + batch.sold_cost_cny + batch.adjustment_cost_cny,
        )
        self.assertEqual(batch.remaining, 0)
        self.assertEqual(batch.physical_remaining, 0)
        self.assertEqual(batch.remaining_cost_cny, Decimal('0.00'))
        self.assertEqual(batch.sold_cost_cny, Decimal('10.01'))
        self.assertEqual(
            list(StockMovement.objects.filter(movement_type='ship').order_by('id').values_list('quantity', flat=True)),
            [1, 2],
        )

    def test_negative_adjustment_preserves_active_reservation_physical_coverage(self):
        batch = create_batch(self.cigar, remaining=10, unit_cost='10.00', operator=self.operator)
        order = SalesOrder.objects.create(operator=self.operator, status='pending_payment')
        allocation = reserve_allocation(order, self.cigar, batch, 3)

        adjust_stock(
            cigar_id=self.cigar.id,
            quantity_delta=-2,
            operator=self.operator,
            agent_context=context(command='adjust_stock', key='loss-with-reservation'),
        )

        batch.refresh_from_db()
        allocation.refresh_from_db()
        self.assertEqual(batch.quantity, 10)
        self.assertEqual(batch.original_cost_cny, Decimal('100.00'))
        self.assertEqual(batch.positive_adjustment_quantity, 0)
        self.assertEqual(batch.positive_adjustment_cost_cny, Decimal('0.00'))
        self.assertEqual(batch.adjustment_cost_cny, Decimal('20.00'))
        self.assertEqual(AdjustmentRecord.objects.get(batch=batch).cost_cny, Decimal('20.00'))
        self.assertEqual(
            batch.original_cost_cny + batch.positive_adjustment_cost_cny,
            batch.remaining_cost_cny + batch.sold_cost_cny + batch.adjustment_cost_cny,
        )
        self.assertEqual(batch.remaining, 5)
        self.assertEqual(batch.physical_remaining, 8)
        self.assertEqual(batch.remaining_cost_cny, Decimal('80.00'))
        self.assertEqual(batch.sold_cost_cny, Decimal('0.00'))
        self.assertEqual(allocation.status, StockAllocation.Status.RESERVED)
        self.assertLessEqual(batch.remaining + allocation.quantity, batch.physical_remaining)

    def test_negative_adjustment_consumes_batches_fifo_with_each_cost_pool(self):
        first_batch = create_batch(self.cigar, remaining=2, unit_cost='10.00', operator=self.operator)
        second_batch = create_batch(self.cigar, remaining=3, unit_cost='20.00', operator=self.operator)

        adjust_stock(
            cigar_id=self.cigar.id,
            quantity_delta=-4,
            operator=self.operator,
            agent_context=context(command='adjust_stock', key='loss-fifo'),
        )

        first_batch.refresh_from_db()
        second_batch.refresh_from_db()
        self.assertEqual(
            (first_batch.quantity, first_batch.remaining, first_batch.physical_remaining),
            (2, 0, 0),
        )
        self.assertEqual(first_batch.remaining_cost_cny, Decimal('0.00'))
        self.assertEqual(first_batch.sold_cost_cny, Decimal('0.00'))
        self.assertEqual(first_batch.original_cost_cny, Decimal('20.00'))
        self.assertEqual(first_batch.adjustment_cost_cny, Decimal('20.00'))
        self.assertEqual(AdjustmentRecord.objects.get(batch=first_batch).cost_cny, Decimal('20.00'))
        self.assertEqual(
            first_batch.original_cost_cny + first_batch.positive_adjustment_cost_cny,
            first_batch.remaining_cost_cny + first_batch.sold_cost_cny + first_batch.adjustment_cost_cny,
        )
        self.assertEqual(
            (second_batch.quantity, second_batch.remaining, second_batch.physical_remaining),
            (3, 1, 1),
        )
        self.assertEqual(second_batch.remaining_cost_cny, Decimal('20.00'))
        self.assertEqual(second_batch.sold_cost_cny, Decimal('0.00'))
        self.assertEqual(second_batch.original_cost_cny, Decimal('60.00'))
        self.assertEqual(second_batch.adjustment_cost_cny, Decimal('40.00'))
        self.assertEqual(AdjustmentRecord.objects.get(batch=second_batch).cost_cny, Decimal('40.00'))
        self.assertEqual(
            second_batch.original_cost_cny + second_batch.positive_adjustment_cost_cny,
            second_batch.remaining_cost_cny + second_batch.sold_cost_cny + second_batch.adjustment_cost_cny,
        )

    def test_positive_stock_adjustment_creates_batch_with_inventory_facts(self):
        batch = adjust_stock(
            cigar_id=self.cigar.id,
            quantity_delta=3,
            operator=self.operator,
            unit_cost_cny='12.34',
            agent_context=context(command='adjust_stock', key='adjust-positive-new'),
        )

        batch.refresh_from_db()
        self.assertEqual(batch.quantity, 0)
        self.assertEqual(batch.original_cost_cny, Decimal('0.00'))
        self.assertEqual(batch.positive_adjustment_quantity, 3)
        self.assertEqual(batch.positive_adjustment_cost_cny, Decimal('37.02'))
        self.assertEqual(batch.adjustment_cost_cny, Decimal('0.00'))
        self.assertEqual(
            batch.original_cost_cny + batch.positive_adjustment_cost_cny,
            batch.remaining_cost_cny + batch.sold_cost_cny + batch.adjustment_cost_cny,
        )
        self.assertEqual(batch.remaining, 3)
        self.assertEqual(batch.physical_remaining, 3)
        self.assertEqual(batch.unit_cost_cny, Decimal('12.34'))
        self.assertEqual(batch.remaining_cost_cny, Decimal('37.02'))
        self.assertEqual(batch.sold_cost_cny, Decimal('0.00'))

    def test_positive_stock_adjustment_updates_specified_batch_inventory_facts(self):
        batch = create_batch(self.cigar, remaining=5, unit_cost='20.00', operator=self.operator)
        adjust_stock(
            cigar_id=self.cigar.id,
            quantity_delta=2,
            operator=self.operator,
            batch_id=batch.id,
            unit_cost_cny='999.99',
            agent_context=context(command='adjust_stock', key='adjust-positive-existing'),
        )

        batch.refresh_from_db()
        self.assertEqual(batch.quantity, 5)
        self.assertEqual(batch.original_cost_cny, Decimal('100.00'))
        self.assertEqual(batch.positive_adjustment_quantity, 2)
        self.assertEqual(batch.positive_adjustment_cost_cny, Decimal('40.00'))
        self.assertEqual(batch.adjustment_cost_cny, Decimal('0.00'))
        self.assertEqual(
            batch.original_cost_cny + batch.positive_adjustment_cost_cny,
            batch.remaining_cost_cny + batch.sold_cost_cny + batch.adjustment_cost_cny,
        )
        self.assertEqual(batch.remaining, 7)
        self.assertEqual(batch.physical_remaining, 7)
        self.assertEqual(batch.unit_cost_cny, Decimal('20.00'))
        self.assertEqual(batch.remaining_cost_cny, Decimal('140.00'))
        self.assertEqual(batch.sold_cost_cny, Decimal('0.00'))

    def test_negative_stock_adjustment_reduces_physical_stock_and_remaining_cost_only(self):
        batch = create_batch(self.cigar, remaining=10, unit_cost='10.00', operator=self.operator)

        adjust_stock(
            cigar_id=self.cigar.id,
            quantity_delta=-3,
            operator=self.operator,
            reason='盘点损耗',
            agent_context=context(command='adjust_stock', key='adjust-negative'),
        )

        batch.refresh_from_db()
        self.assertEqual(batch.quantity, 10)
        self.assertEqual(batch.original_cost_cny, Decimal('100.00'))
        self.assertEqual(batch.positive_adjustment_quantity, 0)
        self.assertEqual(batch.positive_adjustment_cost_cny, Decimal('0.00'))
        self.assertEqual(batch.adjustment_cost_cny, Decimal('30.00'))
        self.assertEqual(AdjustmentRecord.objects.get(batch=batch).cost_cny, Decimal('30.00'))
        self.assertEqual(
            batch.original_cost_cny + batch.positive_adjustment_cost_cny,
            batch.remaining_cost_cny + batch.sold_cost_cny + batch.adjustment_cost_cny,
        )
        self.assertEqual(batch.remaining, 7)
        self.assertEqual(batch.physical_remaining, 7)
        self.assertEqual(batch.remaining_cost_cny, Decimal('70.00'))
        self.assertEqual(batch.sold_cost_cny, Decimal('0.00'))

    def test_negative_adjustment_assigns_cost_pool_rounding_residue_to_loss(self):
        batch = create_batch(self.cigar, remaining=3, unit_cost='3.34', operator=self.operator)
        batch.original_cost_cny = Decimal('10.01')
        batch.remaining_cost_cny = Decimal('10.01')
        batch.save(update_fields=['original_cost_cny', 'remaining_cost_cny'])

        adjust_stock(
            cigar_id=self.cigar.id,
            quantity_delta=-3,
            operator=self.operator,
            agent_context=context(command='adjust_stock', key='loss-tail-cost'),
        )

        batch.refresh_from_db()
        record = AdjustmentRecord.objects.get(batch=batch)
        self.assertEqual(batch.quantity, 3)
        self.assertEqual(batch.remaining, 0)
        self.assertEqual(batch.physical_remaining, 0)
        self.assertEqual(batch.remaining_cost_cny, Decimal('0.00'))
        self.assertEqual(batch.adjustment_cost_cny, Decimal('10.01'))
        self.assertEqual(record.unit_cost_cny, Decimal('3.34'))
        self.assertEqual(record.cost_cny, Decimal('10.01'))
        self.assertEqual(
            batch.original_cost_cny + batch.positive_adjustment_cost_cny,
            batch.remaining_cost_cny + batch.sold_cost_cny + batch.adjustment_cost_cny,
        )

    def test_cancel_releases_reserved_stock(self):
        batch = create_batch(self.cigar, remaining=10, unit_cost='100.00', operator=self.operator)
        order = create_sales_order(
            items=[{'cigar_id': self.cigar.id, 'quantity': 4, 'unit_price': 180}],
            operator=self.operator,
            agent_context=context(),
        )

        cancelled = cancel_sales_order(
            sales_order_id=order.id,
            operator=self.operator,
            agent_context=context(command='cancel_sales_order', key='cancel-key'),
            note='客户取消',
        )

        batch.refresh_from_db()
        self.assertEqual(cancelled.status, 'cancelled')
        self.assertEqual(batch.remaining, 10)
        self.assertEqual(
            set(cancelled.items.first().allocations.values_list('status', flat=True)),
            {'released'},
        )
        self.assertEqual(StockMovement.objects.filter(movement_type='release_reservation').count(), 1)

    def test_fifo_allocation_can_span_batches(self):
        old_batch = create_batch(self.cigar, remaining=3, unit_cost='100.00', operator=self.operator)
        new_batch = create_batch(self.cigar, remaining=20, unit_cost='120.00', operator=self.operator)

        order = create_sales_order(
            items=[{'cigar_id': self.cigar.id, 'quantity': 10, 'unit_price': 200}],
            operator=self.operator,
            agent_context=context(),
        )

        allocations = list(order.items.first().allocations.order_by('id'))
        self.assertEqual([(a.purchase_batch_id, a.quantity) for a in allocations], [
            (old_batch.id, 3),
            (new_batch.id, 7),
        ])
        old_batch.refresh_from_db()
        new_batch.refresh_from_db()
        self.assertEqual(old_batch.remaining, 0)
        self.assertEqual(new_batch.remaining, 13)

    def test_preorder_does_not_allocate_stock(self):
        batch = create_batch(self.cigar, remaining=3, unit_cost='100.00', operator=self.operator)

        order = create_sales_order(
            items=[{
                'cigar_id': self.cigar.id,
                'quantity': 10,
                'unit_price': 200,
                'fulfillment_type': SalesOrderItem.FulfillmentType.PREORDER,
            }],
            operator=self.operator,
            agent_context=context(),
        )

        batch.refresh_from_db()
        self.assertEqual(batch.remaining, 3)
        self.assertEqual(order.items.first().allocations.count(), 0)
        self.assertFalse(StockMovement.objects.exists())

    def test_in_stock_create_fails_when_stock_is_insufficient(self):
        batch = create_batch(self.cigar, remaining=3, unit_cost='100.00', operator=self.operator)

        with self.assertRaises(InsufficientStockError):
            create_sales_order(
                items=[{'cigar_id': self.cigar.id, 'quantity': 4, 'unit_price': 180}],
                operator=self.operator,
                agent_context=context(),
            )

        batch.refresh_from_db()
        self.assertEqual(batch.remaining, 3)
        self.assertFalse(StockAllocation.objects.exists())

    def test_order_event_records_note_operator_and_agent(self):
        create_batch(self.cigar, remaining=10, unit_cost='100.00', operator=self.operator)

        order = create_sales_order(
            items=[{'cigar_id': self.cigar.id, 'quantity': 1, 'unit_price': 180}],
            operator=self.operator,
            agent_context=context(),
            note='客户要代取',
        )

        event = OrderEvent.objects.get(sales_order=order)
        self.assertEqual(event.note, '客户要代取')
        self.assertEqual(event.operator, self.operator)
        self.assertEqual(event.agent_name, 'codex')
        self.assertEqual(event.command_name, 'create_sales_order')


class PurchaseReceivingServiceTest(TestCase):

    def test_box_adjustment_changes_only_complete_box_shape(self):
        batch = create_batch(self.cigar, remaining=25, unit_cost='10.00', operator=self.operator)

        adjust_stock(
            cigar_id=self.cigar.id, quantity_delta=-25, inventory_form='box',
            operator=self.operator, batch_id=batch.id,
            agent_context=context(command='adjust_stock', key='adjust-box-loss'),
        )

        batch.refresh_from_db()
        self.assertEqual((batch.remaining, batch.physical_remaining), (0, 0))
        self.assertEqual((batch.available_box_quantity, batch.available_stick_quantity), (0, 0))
        self.assertEqual((batch.physical_box_quantity, batch.physical_stick_quantity), (0, 0))
        self.assertEqual(batch.adjustment_cost_cny, Decimal('250.00'))
        with self.assertRaises(OrderServiceError):
            adjust_stock(cigar_id=self.cigar.id, quantity_delta=-1, operator=self.operator,
                         batch_id=batch.id, agent_context=context(key='adjust-no-stick'))
    def setUp(self):
        self.operator = create_operator()
        self.supplier = Supplier.objects.get(name='Habanos')
        self.cigar = create_cigar()

    def test_create_purchase_order_draft_does_not_receive_stock(self):
        order = create_purchase_order(
            supplier_id=self.supplier.id,
            exchange_rate='0.0800',
            operator=self.operator,
            agent_context=context(command='create_purchase_order', key='po-create'),
            note='待二次确认',
            items=[{
                'cigar_id': self.cigar.id,
                'quantity': 25,
                'box_size': 25,
                'unit_price_rub': '1000.00',
            }],
        )

        self.assertEqual(order.status, PurchaseOrder.Status.DRAFT)
        self.assertEqual(order.supplier, self.supplier)
        self.assertEqual(order.items.count(), 1)
        self.assertEqual(order.rub_total, Decimal('25000.00'))
        self.assertEqual(order.cny_total, Decimal('2000.00'))
        self.assertFalse(PurchaseBatch.objects.exists())
        self.assertFalse(StockMovement.objects.filter(movement_type='receive').exists())

    def test_receive_purchase_order_creates_batches_and_movements(self):
        order = create_purchase_order(
            supplier_id=self.supplier.id,
            exchange_rate='0.0800',
            operator=self.operator,
            agent_context=context(command='create_purchase_order', key='po-create'),
            items=[
                {'cigar_id': self.cigar.id, 'quantity': 25, 'box_size': 25, 'unit_price_rub': '1000.00'},
                {'cigar_id': self.cigar.id, 'quantity': 10, 'box_size': 10, 'unit_price_rub': '1200.00'},
            ],
        )

        batches = receive_purchase_order(
            purchase_order_id=order.id,
            operator=self.operator,
            agent_context=context(command='receive_purchase_order', key='po-receive'),
            note='确认到货',
        )

        order.refresh_from_db()
        self.assertEqual(order.status, PurchaseOrder.Status.RECEIVED)
        self.assertEqual(len(batches), 2)
        self.assertEqual(
            list(PurchaseBatch.objects.order_by('id').values_list('quantity', 'remaining')),
            [(25, 25), (10, 10)],
        )
        for batch in batches:
            self.assertEqual(batch.remaining, batch.quantity)
            self.assertEqual(batch.physical_remaining, batch.quantity)
            self.assertEqual(batch.original_cost_cny, batch.quantity * batch.unit_cost_cny)
            self.assertEqual(batch.positive_adjustment_quantity, 0)
            self.assertEqual(batch.positive_adjustment_cost_cny, Decimal('0.00'))
            self.assertEqual(batch.adjustment_cost_cny, Decimal('0.00'))
            self.assertEqual(batch.remaining_cost_cny, batch.quantity * batch.unit_cost_cny)
            self.assertEqual(batch.sold_cost_cny, Decimal('0.00'))
        self.assertEqual(StockMovement.objects.filter(movement_type='receive').count(), 2)
        movement = StockMovement.objects.filter(movement_type='receive').first()
        self.assertEqual(movement.operator, self.operator)
        self.assertEqual(movement.agent_name, 'codex')
        self.assertEqual(movement.command_name, 'receive_purchase_order')
        self.assertEqual(movement.idempotency_key, 'po-receive')

    def test_missing_supplier_is_rejected(self):
        with self.assertRaisesMessage(OrderServiceError, '供应商不存在'):
            create_purchase_order(
                supplier_id=99999,
                exchange_rate='0.0800',
                operator=self.operator,
                agent_context=context(command='create_purchase_order', key='po-create'),
                items=[{'cigar_id': self.cigar.id, 'quantity': 1, 'unit_price_rub': '1000.00'}],
            )


class AgentCommandApiTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.operator = create_operator()
        self.client.login(username=self.operator.username, password='pass')
        self.cigar = create_cigar()
        self.batch = create_batch(self.cigar, remaining=10, unit_cost='100.00', operator=self.operator)

    def body(self, key='idem-1', quantity=4):
        return {
            'idempotency_key': key,
            'operator_id': self.operator.id,
            'agent': {
                'agent_name': 'codex',
                'agent_run_id': 'run-api',
                'agent_request_id': 'req-api',
            },
            'customer_name': '张三',
            'items': [{'cigar_id': self.cigar.id, 'quantity': quantity, 'unit_price': 180}],
            'note': 'API 创建',
        }

    def post_json(self, path, body):
        return self.client.post(path, data=json.dumps(body), content_type='application/json')

    def test_idempotent_retry_does_not_reserve_twice(self):
        body = self.body()
        first = self.post_json('/api/agent/orders/create/', body)
        second = self.post_json('/api/agent/orders/create/', body)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.json(), second.json())
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.remaining, 6)
        self.assertEqual(IdempotencyRecord.objects.count(), 1)
        self.assertEqual(StockMovement.objects.filter(movement_type='reserve').count(), 1)

    def test_idempotency_conflict_returns_409(self):
        first = self.post_json('/api/agent/orders/create/', self.body(key='idem-conflict', quantity=4))
        second = self.post_json('/api/agent/orders/create/', self.body(key='idem-conflict', quantity=5))

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 409)
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.remaining, 6)

    def test_idempotent_business_error_is_replayed(self):
        body = self.body(key='idem-error', quantity=11)
        first = self.post_json('/api/agent/orders/create/', body)
        self.batch.positive_adjustment_quantity = 10
        self.batch.positive_adjustment_cost_cny = Decimal('1000.00')
        self.batch.remaining = 20
        self.batch.physical_remaining = 20
        self.batch.available_box_quantity = 0
        self.batch.available_stick_quantity = 20
        self.batch.physical_box_quantity = 0
        self.batch.physical_stick_quantity = 20
        self.batch.remaining_cost_cny = Decimal('2000.00')
        self.batch.save(update_fields=[
            'positive_adjustment_quantity', 'positive_adjustment_cost_cny',
            'remaining', 'physical_remaining', 'remaining_cost_cny',
            'available_box_quantity', 'available_stick_quantity',
            'physical_box_quantity', 'physical_stick_quantity',
        ])
        second = self.post_json('/api/agent/orders/create/', body)

        self.assertEqual(first.status_code, 400)
        self.assertEqual(second.status_code, 400)
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.quantity, 10)
        self.assertEqual(self.batch.positive_adjustment_quantity, 10)
        self.assertEqual(self.batch.positive_adjustment_cost_cny, Decimal('1000.00'))
        self.assertEqual(self.batch.physical_remaining, 20)
        self.assertEqual(self.batch.remaining, 20)
        self.assertEqual(self.batch.remaining_cost_cny, Decimal('2000.00'))
        self.assertEqual(first.json(), second.json())
        self.assertFalse(StockAllocation.objects.exists())
        self.assertEqual(IdempotencyRecord.objects.get(key='idem-error').status_code, 400)


class AgentPurchaseReceivingApiTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.operator = create_operator()
        self.client.login(username=self.operator.username, password='pass')
        self.supplier = Supplier.objects.get(name='Habanos')
        self.cigar = create_cigar()

    def post_json(self, path, body):
        return self.client.post(path, data=json.dumps(body), content_type='application/json')

    def agent(self, request_id='req-po'):
        return {
            'agent_name': 'codex',
            'agent_run_id': 'run-po',
            'agent_request_id': request_id,
        }

    def create_body(self, key='po-create-api', quantity=25):
        return {
            'idempotency_key': key,
            'operator_id': self.operator.id,
            'agent': self.agent('req-create'),
            'supplier_id': self.supplier.id,
            'exchange_rate': '0.0800',
            'note': 'Habanos 到货草稿',
            'items': [{
                'cigar_id': self.cigar.id,
                'quantity': quantity,
                'box_size': 25,
                'unit_price_rub': '1000.00',
            }],
        }

    def test_create_and_receive_purchase_order_via_agent_api(self):
        create_response = self.post_json('/api/agent/purchase-orders/create/', self.create_body())
        self.assertEqual(create_response.status_code, 200)
        purchase_order_id = create_response.json()['purchase_order']['id']

        self.assertEqual(PurchaseOrder.objects.get(id=purchase_order_id).status, PurchaseOrder.Status.DRAFT)
        self.assertFalse(PurchaseBatch.objects.exists())

        receive_body = {
            'idempotency_key': 'po-receive-api',
            'operator_id': self.operator.id,
            'agent': self.agent('req-receive'),
            'purchase_order_id': purchase_order_id,
            'note': '二次确认后正式入库',
        }
        receive_response = self.post_json('/api/agent/purchase-orders/receive/', receive_body)

        self.assertEqual(receive_response.status_code, 200)
        payload = receive_response.json()['purchase_order']
        self.assertEqual(payload['status'], 'received')
        self.assertEqual(payload['supplier_name'], 'Habanos')
        self.assertEqual(len(payload['items'][0]['batches']), 1)
        batch = PurchaseBatch.objects.get()
        self.assertEqual(batch.quantity, 25)
        self.assertEqual(batch.remaining, 25)
        movement = StockMovement.objects.get(movement_type='receive')
        self.assertEqual(movement.quantity, 25)
        self.assertEqual(movement.operator, self.operator)
        self.assertEqual(movement.agent_name, 'codex')
        self.assertEqual(movement.agent_request_id, 'req-receive')
        create_record = IdempotencyRecord.objects.get(command_name='create_purchase_order')
        receive_record = IdempotencyRecord.objects.get(command_name='receive_purchase_order')
        self.assertEqual(create_record.operator, self.operator)
        self.assertEqual(create_record.agent_name, 'codex')
        self.assertEqual(receive_record.operator, self.operator)
        self.assertEqual(receive_record.agent_name, 'codex')

    def test_supplier_list_exposes_seeded_habanos_id(self):
        response = self.client.get('/api/agent/suppliers/?q=habanos')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['results'], [{
            'supplier_id': self.supplier.id,
            'name': 'Habanos',
        }])

    def test_receive_retry_does_not_receive_twice(self):
        purchase_order_id = self.post_json('/api/agent/purchase-orders/create/', self.create_body()).json()['purchase_order']['id']
        body = {
            'idempotency_key': 'po-receive-retry',
            'operator_id': self.operator.id,
            'agent': self.agent('req-receive'),
            'purchase_order_id': purchase_order_id,
            'note': '确认到货',
        }

        first = self.post_json('/api/agent/purchase-orders/receive/', body)
        second = self.post_json('/api/agent/purchase-orders/receive/', body)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.json(), second.json())
        self.assertEqual(PurchaseBatch.objects.count(), 1)
        self.assertEqual(StockMovement.objects.filter(movement_type='receive').count(), 1)

    def test_same_idempotency_key_different_body_returns_409(self):
        first = self.post_json('/api/agent/purchase-orders/create/', self.create_body(key='po-conflict', quantity=25))
        second = self.post_json('/api/agent/purchase-orders/create/', self.create_body(key='po-conflict', quantity=10))

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 409)
        self.assertEqual(PurchaseOrder.objects.count(), 1)
        self.assertFalse(PurchaseBatch.objects.exists())

    def test_missing_supplier_returns_400(self):
        body = self.create_body()
        body['idempotency_key'] = 'po-missing-supplier'
        body['supplier_id'] = 99999

        response = self.post_json('/api/agent/purchase-orders/create/', body)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['error'], '供应商不存在')
        self.assertFalse(PurchaseOrder.objects.exists())
