import json
import threading
from datetime import date
from decimal import Decimal

from django.db import models, transaction
from django.test import Client, TestCase, TransactionTestCase
from django.utils import timezone
from django.db import close_old_connections

from accounting.models import FundAccount, LedgerTransaction
from accounting.services import LedgerError
from accounting.mutation_scope import ledger_mutation_scope
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
    SalesShipment,
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
    cancel_confirmed_sales_order,
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
        from accounting.models import Day1Initialization
        Day1Initialization.objects.create(
            status=Day1Initialization.Status.COMPLETED,
            business_date=date(2026, 8, 10), completed_by=self.operator,
        )

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
        self.assertEqual(order.fulfillment_status, SalesOrder.FulfillmentStatus.CONFIRMED)
        self.assertEqual(order.payment_status, SalesOrder.PaymentStatus.UNPAID)
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

    def test_legacy_create_reserves_complete_box_and_prices_per_box(self):
        batch = create_batch(self.cigar, remaining=25, unit_cost='10.00', operator=self.operator)

        order = create_sales_order(
            items=[{
                'cigar_id': self.cigar.id,
                'quantity': 25,
                'sale_unit': SalesOrderItem.SaleUnit.BOX,
                'sale_quantity': 1,
                'box_size': 25,
                'unit_price': '360.00',
            }],
            operator=self.operator,
            agent_context=context(key='legacy-box-price-and-reservation'),
        )

        batch.refresh_from_db()
        item = order.items.get()
        self.assertEqual(item.revenue, Decimal('360.00'))
        self.assertEqual(item.unit_price, Decimal('360.00'))
        self.assertEqual(order.goods_amount_cny, Decimal('360.00'))
        self.assertEqual(order.amount_due_cny, Decimal('360.00'))
        self.assertEqual(order.customer_transport_fee_cny, Decimal('0.00'))
        self.assertEqual(batch.remaining, 0)
        self.assertEqual((batch.available_box_quantity, batch.available_stick_quantity), (0, 0))
        self.assertEqual(item.allocations.get().quantity, 25)

        from privnote.services import build_payment_data
        rendered = build_payment_data(order)
        self.assertEqual(rendered['items'][0]['unit_price'], 360)
        self.assertEqual(rendered['items'][0]['subtotal'], 360)
        self.assertEqual(rendered['total'], 360)
        self.assertEqual(rendered['grand_total'], 360)

    def test_legacy_create_defers_cost_and_profit_until_shipment(self):
        create_batch(self.cigar, remaining=2, unit_cost='10.00', operator=self.operator)

        order = create_sales_order(
            items=[{'cigar_id': self.cigar.id, 'quantity': 2, 'unit_price': '20.00'}],
            operator=self.operator,
            agent_context=context(key='legacy-defer-cost-profit'),
        )

        item = order.items.get()
        self.assertEqual(item.revenue, Decimal('40.00'))
        self.assertEqual(item.unit_cost, Decimal('0.00'))
        self.assertEqual(item.cost, Decimal('0.00'))
        self.assertEqual(item.profit, Decimal('0.00'))
        self.assertEqual(order.total_revenue, Decimal('40.00'))
        self.assertEqual(order.total_cost, Decimal('0.00'))
        self.assertEqual(order.total_profit, Decimal('0.00'))

    def test_confirm_payment_is_disabled_for_confirmed_order_without_side_effects(self):
        batch = create_batch(self.cigar, remaining=10, unit_cost='100.00', operator=self.operator)
        order = create_sales_order(
            items=[{'cigar_id': self.cigar.id, 'quantity': 4, 'unit_price': 180}],
            operator=self.operator,
            agent_context=context(),
        )
        batch.refresh_from_db()
        allocation = order.items.get().allocations.get()
        before_batch = (
            batch.remaining, batch.physical_remaining, batch.remaining_cost_cny,
            batch.sold_cost_cny, batch.available_box_quantity, batch.available_stick_quantity,
        )
        before_events = OrderEvent.objects.count()
        before_movements = StockMovement.objects.count()
        before_ledger = LedgerTransaction.objects.count()

        with self.assertRaisesRegex(OrderServiceError, '已停用'):
            confirm_payment(
                sales_order_id=order.id,
                operator=self.operator,
                agent_context=context(command='confirm_payment', key='pay-key'),
                note='已收款',
            )

        order.refresh_from_db()
        batch.refresh_from_db()
        allocation.refresh_from_db()
        self.assertEqual(
            (order.status, order.fulfillment_status, order.payment_status),
            ('pending_payment', SalesOrder.FulfillmentStatus.CONFIRMED, SalesOrder.PaymentStatus.UNPAID),
        )
        self.assertEqual(
            (batch.remaining, batch.physical_remaining, batch.remaining_cost_cny,
             batch.sold_cost_cny, batch.available_box_quantity, batch.available_stick_quantity),
            before_batch,
        )
        self.assertEqual(allocation.status, StockAllocation.Status.RESERVED)
        self.assertEqual(OrderEvent.objects.count(), before_events)
        self.assertEqual(StockMovement.objects.count(), before_movements)
        self.assertEqual(LedgerTransaction.objects.count(), before_ledger)

    def test_confirm_payment_is_disabled_for_draft_without_side_effects(self):
        order = SalesOrder.objects.create(operator=self.operator, status='draft')
        before_events = OrderEvent.objects.count()
        before_movements = StockMovement.objects.count()
        before_ledger = LedgerTransaction.objects.count()

        with self.assertRaisesRegex(OrderServiceError, '已停用'):
            confirm_payment(
                sales_order_id=order.id,
                operator=self.operator,
                agent_context=context(command='confirm_payment', key='draft-payment-disabled'),
            )

        order.refresh_from_db()
        self.assertEqual(
            (order.status, order.fulfillment_status, order.payment_status),
            ('draft', SalesOrder.FulfillmentStatus.DRAFT, SalesOrder.PaymentStatus.UNPAID),
        )
        self.assertEqual(OrderEvent.objects.count(), before_events)
        self.assertEqual(StockMovement.objects.count(), before_movements)
        self.assertEqual(LedgerTransaction.objects.count(), before_ledger)


    def test_cancel_rejects_legacy_fulfilled_allocation_without_side_effects(self):
        batch = create_batch(self.cigar, remaining=10, unit_cost='100.00', operator=self.operator)

        order = create_sales_order(
            items=[{'cigar_id': self.cigar.id, 'quantity': 4, 'unit_price': 180}],
            operator=self.operator,
            agent_context=context(),
        )
        allocation = order.items.get().allocations.get()
        allocation.status = StockAllocation.Status.FULFILLED
        allocation.fulfilled_at = timezone.now()
        allocation.save(update_fields=['status', 'fulfilled_at'])
        order.refresh_from_db()
        order.status = 'paid'
        order.payment_status = SalesOrder.PaymentStatus.PAID
        order.fulfillment_status = SalesOrder.FulfillmentStatus.CONFIRMED
        order.save(update_fields=['status', 'payment_status', 'fulfillment_status'])
        batch.refresh_from_db()
        before_batch = (
            batch.remaining, batch.physical_remaining, batch.remaining_cost_cny, batch.sold_cost_cny,
        )

        with self.assertRaises(OrderServiceError):
            cancel_confirmed_sales_order(
                sales_order_id=order.id,
                operator=self.operator,
                agent_context=context(command='cancel_confirmed_sales_order', key='legacy-cancel'),
            )

        order.refresh_from_db()
        batch.refresh_from_db()
        allocation.refresh_from_db()
        self.assertEqual(
            (order.status, order.fulfillment_status, order.payment_status),
            ('paid', SalesOrder.FulfillmentStatus.CONFIRMED, SalesOrder.PaymentStatus.PAID),
        )
        self.assertEqual(
            (batch.remaining, batch.physical_remaining, batch.remaining_cost_cny, batch.sold_cost_cny),
            before_batch,
        )
        self.assertEqual(allocation.status, StockAllocation.Status.FULFILLED)

    def test_cancel_rejects_confirmed_order_with_shipment_without_side_effects(self):
        batch = create_batch(self.cigar, remaining=10, unit_cost='100.00', operator=self.operator)

        order = create_sales_order(
            items=[{'cigar_id': self.cigar.id, 'quantity': 4, 'unit_price': 180}],
            operator=self.operator,
            agent_context=context(),
        )
        ledger_transaction = LedgerTransaction.objects.create(
            transaction_type=LedgerTransaction.TransactionType.SALES_SHIPMENT,
            business_date=date(2026, 8, 11),
            idempotency_key='shipment-cancel-defense',
            operator=self.operator,
        )
        SalesShipment.objects.create(
            sales_order=order,
            business_date=date(2026, 8, 11),
            fifo_cost_cny=Decimal('400.00'),
            ledger_transaction=ledger_transaction,
            operator=self.operator,
        )
        allocation = order.items.get().allocations.get()
        batch.refresh_from_db()
        before_batch = (
            batch.remaining, batch.physical_remaining, batch.remaining_cost_cny, batch.sold_cost_cny,
        )

        with self.assertRaises(OrderServiceError):
            cancel_confirmed_sales_order(
                sales_order_id=order.id,
                operator=self.operator,
                agent_context=context(command='cancel_confirmed_sales_order', key='shipment-cancel'),
            )

        order.refresh_from_db()
        batch.refresh_from_db()
        allocation.refresh_from_db()
        self.assertEqual(
            (order.status, order.fulfillment_status, order.payment_status),
            ('pending_payment', SalesOrder.FulfillmentStatus.CONFIRMED, SalesOrder.PaymentStatus.UNPAID),
        )
        self.assertEqual(
            (batch.remaining, batch.physical_remaining, batch.remaining_cost_cny, batch.sold_cost_cny),
            before_batch,
        )
        self.assertEqual(allocation.status, StockAllocation.Status.RESERVED)

    def test_legacy_confirm_payment_rejects_without_moving_locked_batches(self):
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

        before = list(PurchaseBatch.objects.filter(id__in=[first_batch.id, second_batch.id]).values_list('remaining', 'sold_cost_cny'))
        with self.assertRaisesRegex(OrderServiceError, '已停用'):
            confirm_payment(
                sales_order_id=order.id,
                operator=self.operator,
                agent_context=context(command='confirm_payment', key='batch-lock-order'),
            )
        self.assertEqual(list(PurchaseBatch.objects.filter(id__in=[first_batch.id, second_batch.id]).values_list('remaining', 'sold_cost_cny')), before)

    def test_remove_remaining_cost_assigns_last_unit_rounding_tail(self):
        from cigars.services import _remove_remaining_cost
        batch = create_batch(self.cigar, remaining=3, unit_cost='3.34', operator=self.operator)
        batch.original_cost_cny = Decimal('10.01')
        batch.remaining_cost_cny = Decimal('10.01')
        batch.physical_remaining = 3
        first = _remove_remaining_cost(batch, 1)
        batch.remaining_cost_cny -= first
        batch.physical_remaining -= 1
        second = _remove_remaining_cost(batch, 2)
        self.assertEqual(first, Decimal('3.34'))
        self.assertEqual(second, Decimal('6.67'))
        self.assertEqual(first + second, Decimal('10.01'))

    def test_negative_adjustment_preserves_active_reservation_physical_coverage(self):
        batch = create_batch(self.cigar, remaining=10, unit_cost='10.00', operator=self.operator)
        order = SalesOrder.objects.create(operator=self.operator, status='pending_payment')
        allocation = reserve_allocation(order, self.cigar, batch, 3)

        adjust_stock(
            cigar_id=self.cigar.id,
            quantity_delta=-2,
            operator=self.operator,
            reason='预留库存盘亏',
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
            reason='FIFO盘亏',
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
            reason='盘盈入账',
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
        self.assertEqual(batch.source, PurchaseBatch.Source.ADJUSTMENT)
        self.assertIsNone(batch.purchase_order_item)

    def test_positive_stock_adjustment_updates_specified_batch_inventory_facts(self):
        batch = create_batch(self.cigar, remaining=5, unit_cost='20.00', operator=self.operator)
        adjust_stock(
            cigar_id=self.cigar.id,
            quantity_delta=2,
            operator=self.operator,
            batch_id=batch.id,
            unit_cost_cny='999.99',
            reason='指定批次盘盈',
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
            reason='尾差盘亏',
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

    def test_box_adjustment_changes_only_complete_box_shape(self):
        batch = create_batch(self.cigar, remaining=25, unit_cost='10.00', operator=self.operator)

        adjust_stock(
            cigar_id=self.cigar.id,
            quantity_delta=-25,
            inventory_form='box',
            operator=self.operator,
            batch_id=batch.id,
            reason='整盒盘亏',
            agent_context=context(command='adjust_stock', key='adjust-box-loss'),
        )

        batch.refresh_from_db()
        self.assertEqual((batch.remaining, batch.physical_remaining), (0, 0))
        self.assertEqual((batch.available_box_quantity, batch.available_stick_quantity), (0, 0))
        self.assertEqual((batch.physical_box_quantity, batch.physical_stick_quantity), (0, 0))
        self.assertEqual(batch.adjustment_cost_cny, Decimal('250.00'))
        with self.assertRaises(OrderServiceError):
            adjust_stock(cigar_id=self.cigar.id, quantity_delta=-1, operator=self.operator,
                         batch_id=batch.id, reason='无散支库存', agent_context=context(key='adjust-no-stick'))

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
        self.assertEqual(
            (cancelled.fulfillment_status, cancelled.payment_status),
            (SalesOrder.FulfillmentStatus.CANCELLED, SalesOrder.PaymentStatus.UNPAID),
        )
        self.assertEqual(batch.remaining, 10)
        self.assertEqual(
            set(cancelled.items.first().allocations.values_list('status', flat=True)),
            {'released'},
        )
        self.assertEqual(StockMovement.objects.filter(movement_type='release_reservation').count(), 1)

    def test_legacy_cancel_rejects_order_with_shipment(self):
        batch = create_batch(self.cigar, remaining=10, unit_cost='100.00', operator=self.operator)
        order = create_sales_order(
            items=[{'cigar_id': self.cigar.id, 'quantity': 4, 'unit_price': 180}],
            operator=self.operator,
            agent_context=context(key='legacy-cancel-shipment'),
        )
        ledger_transaction = LedgerTransaction.objects.create(
            transaction_type=LedgerTransaction.TransactionType.SALES_SHIPMENT,
            business_date=date(2026, 8, 11),
            idempotency_key='legacy-cancel-shipment-defense',
            operator=self.operator,
        )
        SalesShipment.objects.create(
            sales_order=order,
            business_date=date(2026, 8, 11),
            fifo_cost_cny=Decimal('400.00'),
            ledger_transaction=ledger_transaction,
            operator=self.operator,
        )

        with self.assertRaises(OrderServiceError):
            cancel_sales_order(
                sales_order_id=order.id,
                operator=self.operator,
                agent_context=context(command='cancel_sales_order', key='legacy-shipment-cancel'),
            )

        order.refresh_from_db()
        batch.refresh_from_db()
        self.assertEqual(order.fulfillment_status, SalesOrder.FulfillmentStatus.CONFIRMED)
        self.assertEqual(order.payment_status, SalesOrder.PaymentStatus.UNPAID)
        self.assertEqual(batch.remaining, 6)

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

    def setUp(self):
        self.operator = create_operator()
        self.supplier = Supplier.objects.get(name='Habanos')
        self.cigar = create_cigar()
        self.purchase_seq = 0
        from accounting.day1 import confirm_day1, save_day1_draft
        payload = {
            'business_date': date(2026, 8, 14),
            'accounts': [
                {'slot': 'owner_cny', 'name': '采购测试老板人民币', 'currency': 'CNY', 'original_amount': '100.00', 'cny_book_cost': '100.00'},
                {'slot': 'partner_cny', 'name': '采购测试合伙人人民币', 'currency': 'CNY', 'original_amount': '0.00', 'cny_book_cost': '0.00'},
                {'slot': 'rub', 'name': '采购测试卢布账户', 'currency': 'RUB', 'original_amount': '0.00', 'cny_book_cost': '0.00'},
                {'slot': 'usdt', 'name': '采购测试USDT账户', 'currency': 'USDT', 'original_amount': '0.00000000', 'cny_book_cost': '0.00'},
            ],
            'inventory': [],
        }
        draft = save_day1_draft(payload=payload, expected_version=0, operator=self.operator)
        confirm_day1(expected_version=draft.version, operator=self.operator, idempotency_key='purchase-service-day1')

    def _paid_in_transit_order(self, item_updates=None):
        self.purchase_seq += 1
        order = create_purchase_order(
            supplier_id=self.supplier.id, exchange_rate='0.0800',
            operator=self.operator,
            business_date=date(2026, 8, 14), idempotency_key=f'purchase-direct-paid-{self.purchase_seq}',
            items=[{'cigar_id': self.cigar.id, 'quantity': 25, 'box_size': 25, 'unit_price_rub': '1000.00'}],
        )
        if item_updates:
            item = order.items.get()
            for name, value in item_updates.items():
                setattr(item, name, value)
            item.save(update_fields=list(item_updates))
        order.status = PurchaseOrder.Status.IN_TRANSIT
        order.paid_cny_cost = Decimal('80.00')
        order.paid_at = timezone.now()
        with transaction.atomic(), ledger_mutation_scope(
            reason='purchase_payment', model='cigars.PurchaseOrder',
            operator=self.operator, allowed_fields={'status', 'paid_cny_cost', 'paid_at'},
        ):
            order.save(update_fields=['status', 'paid_cny_cost', 'paid_at'])
        return order

    def test_receive_rejects_review_required_packaging_before_stock_loop(self):
        order = self._paid_in_transit_order({
            'packaging_status': PurchaseOrderItem.PackagingStatus.REVIEW_REQUIRED,
            'box_quantity': None, 'unit_price_rub_per_box': None,
        })
        with self.assertRaisesMessage(OrderServiceError, 'packaging_review_required'):
            receive_purchase_order(purchase_order_id=order.id, operator=self.operator)
        self.assertFalse(PurchaseBatch.objects.exists())

    def test_receive_allows_unrepresentable_packaging(self):
        order = self._paid_in_transit_order({
            'packaging_status': PurchaseOrderItem.PackagingStatus.UNREPRESENTABLE,
            'unit_price_rub': None, 'unit_price_cny': None,
        })
        batches = receive_purchase_order(
            purchase_order_id=order.id, operator=self.operator,
            agent_context=context(command='receive_purchase_order', key='po-unrepresentable'),
        )
        self.assertEqual(len(batches), 1)
        self.assertEqual(batches[0].remaining_cost_cny, Decimal('80.00'))

    def test_receive_uses_actual_payment_cost_without_legacy_snapshot(self):
        order = self._paid_in_transit_order({'unit_price_cny': None})
        batches = receive_purchase_order(
            purchase_order_id=order.id, operator=self.operator,
            agent_context=context(command='receive_purchase_order', key='po-no-legacy-cost'),
        )
        self.assertEqual(batches[0].original_cost_cny, Decimal('80.00'))

    def test_legacy_direct_create_without_key_uses_compatibility_boundary(self):
        order = create_purchase_order(
            supplier_id=self.supplier.id,
            exchange_rate='0.0800',
            operator=self.operator,
            items=[{'cigar_id': self.cigar.id, 'quantity': 25, 'box_size': 25, 'unit_price_rub': '1000.00'}],
        )
        self.assertEqual(order.status, PurchaseOrder.Status.DRAFT)
        self.assertEqual(order.items.get().quantity, 25)

    def test_create_purchase_order_is_atomic_when_later_item_fails(self):
        with self.assertRaisesMessage(OrderServiceError, "第2个采购明细雪茄不存在"):
            create_purchase_order(
                supplier_id=self.supplier.id, exchange_rate="0.0800",
                operator=self.operator,
                business_date=date(2026, 8, 14), idempotency_key='purchase-direct-atomic',
                items=[
                    {"cigar_id": self.cigar.id, "quantity": 25, "box_size": 25, "unit_price_rub": "1000.00"},
                    {"cigar_id": 999999, "quantity": 10, "box_size": 10, "unit_price_rub": "1200.00"},
                ],
            )
        self.assertFalse(PurchaseOrder.objects.exists())
        self.assertFalse(PurchaseOrderItem.objects.exists())

    def test_create_purchase_order_draft_does_not_receive_stock(self):
        order = create_purchase_order(
            supplier_id=self.supplier.id,
            exchange_rate='0.0800',
            operator=self.operator,
            business_date=date(2026, 8, 14), idempotency_key='purchase-direct-draft',
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
            business_date=date(2026, 8, 14), idempotency_key='purchase-direct-receive',
            agent_context=context(command='create_purchase_order', key='po-create'),
            items=[
                {'cigar_id': self.cigar.id, 'quantity': 25, 'box_size': 25, 'unit_price_rub': '1000.00'},
                {'cigar_id': self.cigar.id, 'quantity': 10, 'box_size': 10, 'unit_price_rub': '1200.00'},
            ],
        )

        order.status = PurchaseOrder.Status.IN_TRANSIT
        order.paid_cny_cost = Decimal('2000.00')
        order.paid_at = timezone.now()
        with transaction.atomic(), ledger_mutation_scope(
            reason='purchase_payment', model='cigars.PurchaseOrder',
            operator=self.operator, allowed_fields={'status', 'paid_cny_cost', 'paid_at'},
        ):
            order.save(update_fields=['status', 'paid_cny_cost', 'paid_at'])

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
            self.assertEqual(batch.original_cost_cny, batch.remaining_cost_cny)
            self.assertEqual(batch.positive_adjustment_quantity, 0)
            self.assertEqual(batch.positive_adjustment_cost_cny, Decimal('0.00'))
            self.assertEqual(batch.adjustment_cost_cny, Decimal('0.00'))
            self.assertGreaterEqual(batch.remaining_cost_cny, Decimal('0.00'))
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
                business_date=date(2026, 8, 14), idempotency_key='purchase-direct-missing',
                agent_context=context(command='create_purchase_order', key='po-create'),
                items=[{'cigar_id': self.cigar.id, 'quantity': 1, 'box_size': 1, 'unit_price_rub': '1000.00'}],
            )


class AgentCommandApiTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.operator = create_operator()
        self.client.login(username=self.operator.username, password='pass')
        self.cigar = create_cigar()
        self.batch = create_batch(self.cigar, remaining=10, unit_cost='100.00', operator=self.operator)
        from accounting.models import Day1Initialization
        Day1Initialization.objects.create(
            status=Day1Initialization.Status.COMPLETED,
            business_date=date(2026, 8, 10), completed_by=self.operator,
        )
        self.cny_account = FundAccount.objects.create(
            name='Agent 人民币账户', currency=FundAccount.Currency.CNY,
            custodian=self.operator, creation_idempotency_key='agent-cny-account',
        )

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
            'business_date': '2026-08-10',
            'items': [{'cigar_id': self.cigar.id, 'quantity': quantity, 'unit_price': 180}],
            'note': 'API 创建',
        }

    def _save_paid(self, order):
        with transaction.atomic(), ledger_mutation_scope(reason='purchase_payment', model='cigars.PurchaseOrder', operator=self.operator, allowed_fields={'status', 'paid_cny_cost', 'paid_at'}):
            order.save(update_fields=['status', 'paid_cny_cost', 'paid_at'])

    def post_json(self, path, body):
        return self.client.post(
            path, data=json.dumps(body), content_type='application/json',
        )

    def test_sales_command_rejects_non_object_inputs(self):
        response = self.post_json('/api/agent/orders/create/', [])
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['code'], 'order_service_error')

        body = self.body(key='invalid-agent-object')
        body['agent'] = 'codex'
        response = self.post_json('/api/agent/orders/create/', body)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['code'], 'order_service_error')

        body = self.body(key='missing-operator')
        body.pop('operator_id')
        response = self.post_json('/api/agent/orders/create/', body)
        self.assertEqual(response.status_code, 400)
        self.assertIn('operator_id', response.json()['error'])

        body = self.body(key='float-operator')
        body['operator_id'] = 1.5
        response = self.post_json('/api/agent/orders/create/', body)
        self.assertEqual(response.status_code, 400)
        self.assertIn('正整数', response.json()['error'])

    def test_sales_write_requires_business_date(self):
        body = self.body(key='missing-sales-business-date')
        body.pop('business_date')

        response = self.post_json('/api/agent/orders/create/', body)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['code'], 'order_service_error')
        self.assertFalse(SalesOrder.objects.exists())


    def test_missing_order_returns_replayable_404_json(self):
        body = {
            'idempotency_key': 'missing-sales-order',
            'operator_id': self.operator.id,
            'agent': self.body()['agent'],
            'sales_order_id': 999999,
            'business_date': '2026-08-10',
        }

        first = self.post_json('/api/agent/orders/confirm/', body)
        replay = self.post_json('/api/agent/orders/confirm/', body)

        self.assertEqual(first.status_code, 404)
        self.assertEqual(first.json()['code'], 'sales_order_not_found')
        self.assertEqual(replay.json(), first.json())
        self.assertEqual(
            IdempotencyRecord.objects.get(key='missing-sales-order').status_code,
            404,
        )

    def test_confirm_order_before_day1_returns_replayable_409_json(self):
        from accounting.models import Day1Initialization
        created = self.post_json(
            '/api/agent/orders/create/', self.body(key='agent-day1-create'),
        )
        order_id = created.json()['sales_order']['id']
        Day1Initialization.objects.update(status=Day1Initialization.Status.DRAFT)
        body = {
            'idempotency_key': 'agent-day1-confirm',
            'operator_id': self.operator.id,
            'agent': self.body()['agent'],
            'sales_order_id': order_id,
            'business_date': '2026-08-10',
        }

        first = self.post_json('/api/agent/orders/confirm/', body)
        replay = self.post_json('/api/agent/orders/confirm/', body)

        self.assertEqual(first.status_code, 409)
        self.assertEqual(first.json()['code'], 'day1_incomplete')
        self.assertEqual(replay.status_code, 409)
        self.assertEqual(replay.json(), first.json())
        self.assertEqual(
            IdempotencyRecord.objects.get(key='agent-day1-confirm').status_code,
            409,
        )

    def test_adjust_stock_blank_reason_returns_400_json(self):
        body = {
            'idempotency_key': 'agent-empty-adjust-reason',
            'operator_id': self.operator.id,
            'agent': {
                'agent_name': 'codex', 'agent_run_id': 'run-api',
                'agent_request_id': 'req-api',
            },
            'cigar_id': self.cigar.id,
            'batch_id': self.batch.id,
            'quantity_delta': -1,
            'reason': '   ',
            'business_date': '2026-08-10',
        }
        response = self.post_json('/api/agent/stock/adjust/', body)
        self.assertEqual(response.status_code, 400)
        self.assertIn('原因不能为空', response.json()['error'])
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.remaining, 10)
        self.assertFalse(StockMovement.objects.exists())

    def test_idempotent_retry_creates_one_draft_without_reserving(self):
        body = self.body()
        first = self.post_json('/api/agent/orders/create/', body)
        second = self.post_json('/api/agent/orders/create/', body)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.json(), second.json())
        self.assertEqual(first.json()['sales_order']['fulfillment_status'], 'draft')
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.remaining, 10)
        self.assertEqual(SalesOrder.objects.count(), 1)
        self.assertEqual(IdempotencyRecord.objects.count(), 1)
        self.assertFalse(StockMovement.objects.exists())

    def test_idempotency_conflict_returns_409(self):
        first = self.post_json(
            '/api/agent/orders/create/',
            self.body(key='idem-conflict', quantity=4),
        )
        second = self.post_json(
            '/api/agent/orders/create/',
            self.body(key='idem-conflict', quantity=5),
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 409)
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.remaining, 10)
        self.assertEqual(SalesOrder.objects.count(), 1)

    def test_idempotent_confirm_error_is_replayed(self):
        created = self.post_json(
            '/api/agent/orders/create/',
            self.body(key='idem-error-create', quantity=11),
        )
        order_id = created.json()['sales_order']['id']
        body = {
            'idempotency_key': 'idem-error-confirm',
            'operator_id': self.operator.id,
            'agent': self.body()['agent'],
            'sales_order_id': order_id,
            'business_date': '2026-08-10',
        }
        first = self.post_json('/api/agent/orders/confirm/', body)
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
        second = self.post_json('/api/agent/orders/confirm/', body)

        self.assertEqual(first.status_code, 400)
        self.assertEqual(first.json()['code'], 'insufficient_stock')
        self.assertEqual(second.status_code, 400)
        self.assertEqual(first.json(), second.json())
        self.assertFalse(StockAllocation.objects.exists())
        self.assertEqual(
            IdempotencyRecord.objects.get(key='idem-error-confirm').status_code,
            400,
        )



    def test_agent_can_update_confirm_cancel_and_query_order(self):
        created = self.post_json(
            '/api/agent/orders/create/',
            self.body(key='agent-flow-create', quantity=4),
        )
        order_id = created.json()['sales_order']['id']
        updated_body = self.body(key='agent-flow-update', quantity=3)
        updated_body['sales_order_id'] = order_id
        updated_body['customer_name'] = '李四'
        updated = self.post_json('/api/agent/orders/update/', updated_body)

        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()['sales_order']['customer_name'], '李四')
        self.assertEqual(updated.json()['sales_order']['items'][0]['quantity'], 3)
        self.assertEqual(self.batch.remaining, 10)

        order_number = updated.json()['sales_order']['order_number']
        listed = self.client.get(
            '/api/agent/orders/',
            {'q': order_number, 'fulfillment_status': 'draft'},
        )
        detail = self.client.get(f'/api/agent/orders/{order_id}/')
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.json()['results']), 1)
        self.assertEqual(detail.json()['sales_order']['id'], order_id)

        confirmed = self.post_json('/api/agent/orders/confirm/', {
            'idempotency_key': 'agent-flow-confirm',
            'operator_id': self.operator.id,
            'agent': self.body()['agent'],
            'sales_order_id': order_id,
            'business_date': '2026-08-10',
            'note': '确认并预留',
        })
        self.assertEqual(confirmed.status_code, 200)
        self.assertEqual(
            confirmed.json()['sales_order']['fulfillment_status'], 'confirmed',
        )
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.remaining, 7)
        reserve = StockMovement.objects.get(movement_type='reserve')
        self.assertEqual(reserve.agent_name, 'codex')
        self.assertEqual(reserve.command_name, 'confirm_sales_order')
        event = OrderEvent.objects.get(command_name='confirm_sales_order')
        self.assertEqual(event.metadata['business_date'], '2026-08-10')

        cancelled = self.post_json('/api/agent/orders/cancel/', {
            'idempotency_key': 'agent-flow-cancel',
            'operator_id': self.operator.id,
            'agent': self.body()['agent'],
            'sales_order_id': order_id,
            'business_date': '2026-08-10',
            'note': '客户取消',
        })
        self.assertEqual(cancelled.status_code, 200)
        self.assertEqual(
            cancelled.json()['sales_order']['fulfillment_status'], 'cancelled',
        )
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.remaining, 10)
        release = StockMovement.objects.get(movement_type='release_reservation')
        self.assertEqual(release.agent_name, 'codex')

    def test_agent_can_ship_receive_record_transport_and_report(self):
        created = self.post_json(
            '/api/agent/orders/create/',
            self.body(key='agent-complete-create', quantity=2),
        )
        order_id = created.json()['sales_order']['id']
        common = {
            'operator_id': self.operator.id,
            'agent': self.body()['agent'],
            'sales_order_id': order_id,
            'business_date': '2026-08-10',
        }
        self.assertEqual(self.post_json('/api/agent/orders/confirm/', {
            **common, 'idempotency_key': 'agent-complete-confirm',
        }).status_code, 200)

        missing_date = self.post_json('/api/agent/orders/ship/', {
            **common, 'idempotency_key': 'agent-ship-missing-date',
            'business_date': '',
        })
        self.assertEqual(missing_date.status_code, 400)
        self.assertEqual(missing_date.json()['code'], 'order_service_error')
        self.assertFalse(SalesShipment.objects.exists())

        shipped = self.post_json('/api/agent/orders/ship/', {
            **common, 'idempotency_key': 'agent-complete-ship',
            'business_date': '2026-08-10', 'note': '实际出库',
        })
        self.assertEqual(shipped.status_code, 200)
        self.assertEqual(
            shipped.json()['sales_order']['fulfillment_status'], 'shipped',
        )
        ship_movement = StockMovement.objects.get(movement_type='ship')
        self.assertEqual(ship_movement.agent_name, 'codex')
        self.assertEqual(ship_movement.agent_run_id, 'run-api')

        received = self.post_json('/api/agent/orders/receive/', {
            **common, 'idempotency_key': 'agent-complete-receive',
            'business_date': '2026-08-10', 'amount_cny': '360.00',
            'fund_account_id': self.cny_account.id,
        })
        self.assertEqual(received.status_code, 200)
        self.assertEqual(received.json()['sales_order']['payment_status'], 'paid')

        transport = self.post_json('/api/agent/orders/transport-cost/', {
            **common, 'idempotency_key': 'agent-complete-transport',
            'business_date': '2026-08-10', 'actual_cost_cny': '10.00',
            'fund_account_id': self.cny_account.id, 'note': '人肉支出',
        })
        self.assertEqual(transport.status_code, 200)
        self.assertEqual(
            transport.json()['sales_order']['contribution_profit'], 150,
        )

        report = self.client.get('/api/agent/reports/basic/')
        self.assertEqual(report.status_code, 200)
        payload = report.json()
        self.assertEqual(payload['orders']['fulfillment']['shipped'], 1)
        self.assertEqual(payload['orders']['payment']['paid'], 1)
        self.assertEqual(payload['sales']['shipped_amount_due_cny'], 360)
        self.assertEqual(payload['sales']['fifo_cost_cny'], 200)
        self.assertEqual(payload['sales']['contribution_profit_cny'], 150)
        self.assertEqual(payload['sales']['received_cny'], 360)
        self.assertEqual(payload['sales']['refunded_cny'], 0)
        self.assertEqual(
            payload['recent_agent_commands'][0]['agent_name'], 'codex',
        )

    def test_agent_can_refund_cancelled_prepayment_and_old_route_is_gone(self):
        self.assertEqual(
            self.post_json('/api/agent/orders/confirm-payment/', {}).status_code,
            404,
        )
        created = self.post_json(
            '/api/agent/orders/create/',
            self.body(key='agent-refund-create', quantity=1),
        )
        order_id = created.json()['sales_order']['id']
        common = {
            'operator_id': self.operator.id,
            'agent': self.body()['agent'],
            'sales_order_id': order_id,
            'business_date': '2026-08-10',
        }
        self.assertEqual(self.post_json('/api/agent/orders/confirm/', {
            **common, 'idempotency_key': 'agent-refund-confirm',
        }).status_code, 200)
        self.assertEqual(self.post_json('/api/agent/orders/receive/', {
            **common, 'idempotency_key': 'agent-refund-receive',
            'business_date': '2026-08-10', 'amount_cny': '180.00',
            'fund_account_id': self.cny_account.id,
        }).status_code, 200)
        cancelled = self.post_json('/api/agent/orders/cancel/', {
            **common, 'idempotency_key': 'agent-refund-cancel',
        })
        self.assertEqual(
            cancelled.json()['sales_order']['payment_status'], 'refund_pending',
        )

        refunded = self.post_json('/api/agent/orders/refund/', {
            **common, 'idempotency_key': 'agent-refund-fact',
            'business_date': '2026-08-10',
        })
        self.assertEqual(refunded.status_code, 200)
        self.assertEqual(
            refunded.json()['sales_order']['payment_status'], 'refunded',
        )
        report = self.client.get('/api/agent/reports/basic/').json()
        self.assertEqual(report['sales']['received_cny'], 180)
        self.assertEqual(report['sales']['refunded_cny'], 180)
        self.assertEqual(report['sales']['net_received_cny'], 0)


class AgentPurchaseReceivingApiTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.operator = create_operator()
        self.client.login(username=self.operator.username, password='pass')
        self.supplier = Supplier.objects.get(name='Habanos')
        self.cigar = create_cigar()
        from accounting.day1 import confirm_day1, save_day1_draft
        self.day1_payload = {
            'business_date': date(2026, 8, 14),
            'accounts': [
                {'slot': 'owner_cny', 'name': 'API老板人民币', 'currency': 'CNY', 'original_amount': '100.00', 'cny_book_cost': '100.00'},
                {'slot': 'partner_cny', 'name': 'API合伙人人民币', 'currency': 'CNY', 'original_amount': '0.00', 'cny_book_cost': '0.00'},
                {'slot': 'rub', 'name': 'API卢布账户', 'currency': 'RUB', 'original_amount': '0.00', 'cny_book_cost': '0.00'},
                {'slot': 'usdt', 'name': 'API USDT账户', 'currency': 'USDT', 'original_amount': '0.00000000', 'cny_book_cost': '0.00'},
            ],
            'inventory': [],
        }
        draft = save_day1_draft(payload=self.day1_payload, expected_version=0, operator=self.operator)
        confirm_day1(expected_version=draft.version, operator=self.operator, idempotency_key='agent-api-day1')

    def _save_paid(self, order):
        with transaction.atomic(), ledger_mutation_scope(reason='purchase_payment', model='cigars.PurchaseOrder', operator=self.operator, allowed_fields={'status', 'paid_cny_cost', 'paid_at'}):
            order.save(update_fields=['status', 'paid_cny_cost', 'paid_at'])

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

        purchase_order = PurchaseOrder.objects.get(id=purchase_order_id)
        purchase_order.status = PurchaseOrder.Status.IN_TRANSIT
        purchase_order.paid_cny_cost = Decimal('1000.00')
        purchase_order.paid_at = timezone.now()
        self._save_paid(purchase_order)

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
        self.assertFalse(PurchaseOrder.objects.get(id=purchase_order_id).legacy_received)
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

    def test_receive_invalid_state_returns_structured_conflict(self):
        create_response = self.post_json(
            '/api/agent/purchase-orders/create/',
            self.create_body(key='po-create-for-invalid-receive'),
        )
        purchase_order_id = create_response.json()['purchase_order']['id']

        response = self.post_json('/api/agent/purchase-orders/receive/', {
            'idempotency_key': 'po-invalid-state-receive',
            'operator_id': self.operator.id,
            'agent': self.agent('req-invalid-receive'),
            'purchase_order_id': purchase_order_id,
        })

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()['code'], 'invalid_state')

    def test_create_replay_returns_first_draft_after_cancel(self):
        first = self.post_json('/api/agent/purchase-orders/create/', self.create_body(key='po-replay-after-cancel'))
        self.assertEqual(first.status_code, 200)
        purchase_order_id = first.json()['purchase_order']['id']
        cancel = self.post_json('/api/agent/purchase-orders/cancel/', {
            'idempotency_key': 'po-cancel-after-create',
            'operator_id': self.operator.id,
            'agent': self.agent('req-cancel'),
            'purchase_order_id': purchase_order_id,
            'expected_version': first.json()['purchase_order']['version'],
            'note': '取消测试',
        })
        self.assertEqual(cancel.status_code, 200)
        self.assertEqual(cancel.json()['purchase_order']['status'], 'cancelled')

        replay = self.post_json('/api/agent/purchase-orders/create/', self.create_body(key='po-replay-after-cancel'))
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(replay.json(), first.json())
        self.assertEqual(replay.json()['purchase_order']['status'], 'draft')
        self.assertEqual(PurchaseOrder.objects.count(), 1)

    def test_canonical_mirror_replays_business_error_response(self):
        from accounting.models import Day1Initialization
        from cigars.models import IdempotencyRecord
        Day1Initialization.objects.all().update(status=Day1Initialization.Status.DRAFT)
        body = self.create_body(key='po-day1-error-replay')
        first = self.post_json('/api/agent/purchase-orders/create/', body)
        self.assertEqual(first.status_code, 409)
        self.assertEqual(first.json()['code'], 'day1_incomplete')
        Day1Initialization.objects.all().update(status=Day1Initialization.Status.COMPLETED)
        second = self.post_json('/api/agent/purchase-orders/create/', body)
        self.assertEqual(second.status_code, first.status_code)
        self.assertEqual(second.json(), first.json())
        self.assertEqual(PurchaseOrder.objects.count(), 0)
        self.assertEqual(IdempotencyRecord.objects.get(key='po-day1-error-replay').status_code, 409)

    def test_update_invalid_state_returns_409(self):
        created = self.post_json('/api/agent/purchase-orders/create/', self.create_body(key='po-update-state-create'))
        order_id = created.json()['purchase_order']['id']
        order = PurchaseOrder.objects.get(pk=order_id)
        order.status = PurchaseOrder.Status.IN_TRANSIT
        order.paid_cny_cost = Decimal('1000.00')
        order.paid_at = timezone.now()
        self._save_paid(order)
        response = self.post_json('/api/agent/purchase-orders/update/', {
            'idempotency_key': 'po-update-invalid-state',
            'operator_id': self.operator.id,
            'agent': self.agent('req-update-state'),
            'purchase_order_id': order_id,
            'expected_version': order.version,
            'items': [{
                'cigar_id': self.cigar.id, 'box_size': 25, 'box_quantity': 1,
                'unit_price_rub_per_box': '1000.00',
            }],
        })
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()['code'], 'invalid_state')

    def test_cancel_invalid_state_returns_409(self):
        created = self.post_json('/api/agent/purchase-orders/create/', self.create_body(key='po-cancel-state-create'))
        order_id = created.json()['purchase_order']['id']
        order = PurchaseOrder.objects.get(pk=order_id)
        order.status = PurchaseOrder.Status.IN_TRANSIT
        order.paid_cny_cost = Decimal('1000.00')
        order.paid_at = timezone.now()
        self._save_paid(order)
        response = self.post_json('/api/agent/purchase-orders/cancel/', {
            'idempotency_key': 'po-cancel-invalid-state',
            'operator_id': self.operator.id,
            'agent': self.agent('req-cancel-state'),
            'purchase_order_id': order_id,
            'expected_version': order.version,
        })
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()['code'], 'invalid_state')

    def test_update_invalid_purchase_order_id_returns_400(self):
        for index, value in enumerate(('abc', '999999999999999999999999999999')):
            with self.subTest(value=value):
                body = {
                    'idempotency_key': f'po-update-invalid-id-{index}',
                    'operator_id': self.operator.id,
                    'agent': self.agent(f'req-update-invalid-id-{index}'),
                    'purchase_order_id': value,
                    'expected_version': 1,
                    'items': [{
                        'cigar_id': self.cigar.id, 'box_size': 25,
                        'box_quantity': 1, 'unit_price_rub_per_box': '1000.00',
                    }],
                }
                response = self.post_json('/api/agent/purchase-orders/update/', body)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json()['code'], 'invalid_purchase_order_id')

    def test_cancel_invalid_purchase_order_id_returns_400(self):
        for index, value in enumerate(('abc', '999999999999999999999999999999')):
            with self.subTest(value=value):
                body = {
                    'idempotency_key': f'po-cancel-invalid-id-{index}',
                    'operator_id': self.operator.id,
                    'agent': self.agent(f'req-cancel-invalid-id-{index}'),
                    'purchase_order_id': value,
                    'expected_version': 1,
                }
                response = self.post_json('/api/agent/purchase-orders/cancel/', body)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json()['code'], 'invalid_purchase_order_id')

    def test_supplier_list_exposes_seeded_habanos_id(self):
        response = self.client.get('/api/agent/suppliers/?q=habanos')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['results'], [{
            'supplier_id': self.supplier.id,
            'name': 'Habanos',
        }])

    def test_receive_retry_does_not_receive_twice(self):
        purchase_order_id = self.post_json('/api/agent/purchase-orders/create/', self.create_body()).json()['purchase_order']['id']
        purchase_order = PurchaseOrder.objects.get(id=purchase_order_id)
        purchase_order.status = PurchaseOrder.Status.IN_TRANSIT
        purchase_order.paid_cny_cost = Decimal('1000.00')
        purchase_order.paid_at = timezone.now()
        self._save_paid(purchase_order)
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

    def test_missing_supplier_returns_404(self):
        body = self.create_body()
        body['idempotency_key'] = 'po-missing-supplier'
        body['supplier_id'] = 99999

        response = self.post_json('/api/agent/purchase-orders/create/', body)

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()['error'], '供应商不存在')
        self.assertFalse(PurchaseOrder.objects.exists())


class StockAdjustmentConcurrencyTest(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.operator = create_operator('adjust-concurrency')
        self.cigar = create_cigar()
        self.batch = create_batch(self.cigar, remaining=5, unit_cost='10.00', operator=self.operator)
        from accounting.models import Day1Initialization
        Day1Initialization.objects.create(
            status=Day1Initialization.Status.COMPLETED,
            business_date=date(2026, 8, 10), completed_by=self.operator,
        )

    def _run_concurrently(self, calls):
        barrier = threading.Barrier(len(calls))
        results = [None] * len(calls)

        def worker(index, kwargs):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                results[index] = adjust_stock(**kwargs)
            except Exception as error:
                results[index] = error
            finally:
                close_old_connections()

        threads = [threading.Thread(target=worker, args=(index, kwargs)) for index, kwargs in enumerate(calls)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
        self.assertTrue(all(not thread.is_alive() for thread in threads))
        self.assertTrue(all(result is not None for result in results), results)
        return results

    def _call(self, key, *, quantity_delta=-1, reason='并发盘点'):
        return {
            'cigar_id': self.cigar.id,
            'quantity_delta': quantity_delta,
            'operator': self.operator,
            'batch_id': self.batch.id,
            'reason': reason,
            'business_date': date(2026, 8, 10),
            'agent_context': AgentContext(
                agent_name='concurrency', agent_run_id='run',
                agent_request_id='request', command_name='adjust_stock',
                idempotency_key=key,
            ),
        }

    def test_same_key_concurrent_adjustment_is_exactly_once(self):
        results = self._run_concurrently([self._call('adjust-concurrent')] * 2)
        self.assertTrue(all(not isinstance(result, Exception) for result in results), results)
        self.assertEqual(results[0].pk, results[1].pk)
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.remaining, 4)
        self.assertEqual(LedgerTransaction.objects.filter(idempotency_key='adjust-concurrent').count(), 1)
        self.assertEqual(StockMovement.objects.filter(idempotency_key='adjust-concurrent').count(), 1)

    def test_different_body_same_key_concurrent_adjustment_is_conflict(self):
        results = self._run_concurrently([
            self._call('adjust-conflict', quantity_delta=-1),
            self._call('adjust-conflict', quantity_delta=-2),
        ])
        statuses = sorted('conflict' if isinstance(result, LedgerError) else 'success' for result in results)
        self.assertEqual(statuses, ['conflict', 'success'])
        winning_delta = (-1 if not isinstance(results[0], LedgerError) else -2)
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.remaining, 5 + winning_delta)
        self.assertEqual(LedgerTransaction.objects.filter(idempotency_key='adjust-conflict').count(), 1)
        self.assertEqual(StockMovement.objects.filter(idempotency_key='adjust-conflict').count(), 1)

class CanonicalPurchaseMirrorConcurrencyTest(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.operator = create_operator('mirror-concurrency')
        self.operator.telegram_id = 'mirror-concurrency-telegram'
        self.operator.save(update_fields=['telegram_id'])
        self.supplier = Supplier.objects.create(name='Mirror concurrency supplier')
        self.cigar = create_cigar()
        from accounting.models import Day1Initialization
        Day1Initialization.objects.create(
            status=Day1Initialization.Status.COMPLETED,
            updated_by=self.operator, completed_by=self.operator,
        )

    def _body(self, key='mirror-concurrent', quantity=25):
        return {
            'idempotency_key': key,
            'operator_id': self.operator.id,
            'agent': {
                'agent_name': 'codex', 'agent_run_id': 'mirror-run',
                'agent_request_id': 'mirror-request',
            },
            'supplier_id': self.supplier.id,
            'exchange_rate': '0.0800',
            'items': [{
                'cigar_id': self.cigar.id, 'quantity': quantity,
                'box_size': 25, 'unit_price_rub': '1000.00',
            }],
        }

    def _concurrent_posts(self, bodies, path='/api/agent/purchase-orders/create/'):
        barrier = threading.Barrier(len(bodies))
        results = [None] * len(bodies)

        def worker(index, body):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                client = Client()
                response = client.post(
                    path, data=json.dumps(body), content_type='application/json',
                    HTTP_X_TELEGRAM_ID='mirror-concurrency-telegram',
                )
                results[index] = (response.status_code, response.json())
            except Exception as error:
                results[index] = error
            finally:
                close_old_connections()

        threads = [threading.Thread(target=worker, args=(i, body)) for i, body in enumerate(bodies)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
        self.assertTrue(all(not thread.is_alive() for thread in threads))
        self.assertTrue(all(not isinstance(result, Exception) for result in results), results)
        return results

    def _sales_body(self):
        return {
            'idempotency_key': 'sales-mirror-concurrent',
            'operator_id': self.operator.id,
            'agent': {
                'agent_name': 'codex', 'agent_run_id': 'sales-mirror-run',
                'agent_request_id': 'sales-mirror-request',
            },
            'business_date': '2026-08-10',
            'customer_name': '并发客户',
            'items': [{
                'cigar_id': self.cigar.id, 'quantity': 1, 'unit_price': '100.00',
            }],
        }

    def test_same_key_concurrent_create_is_one_success_and_one_replay(self):
        results = self._concurrent_posts([self._body(), self._body()])
        self.assertEqual([status for status, _ in results], [200, 200])
        self.assertEqual(results[0][1], results[1][1])
        self.assertEqual(PurchaseOrder.objects.count(), 1)
        self.assertEqual(IdempotencyRecord.objects.filter(key='mirror-concurrent').count(), 1)

    def test_same_key_concurrent_sales_draft_is_created_once(self):
        body = self._sales_body()
        results = self._concurrent_posts(
            [body, body], path='/api/agent/orders/create/',
        )
        self.assertEqual([status for status, _ in results], [200, 200])
        self.assertEqual(results[0][1], results[1][1])
        self.assertEqual(SalesOrder.objects.count(), 1)
        self.assertEqual(
            IdempotencyRecord.objects.filter(
                key='sales-mirror-concurrent',
            ).count(),
            1,
        )

    def test_different_body_same_key_concurrent_create_is_stable_conflict(self):
        results = self._concurrent_posts([self._body(quantity=25), self._body(quantity=50)])
        self.assertEqual(sorted(status for status, _ in results), [200, 409])
        self.assertEqual(PurchaseOrder.objects.count(), 1)
        self.assertEqual(IdempotencyRecord.objects.filter(key='mirror-concurrent').count(), 1)
