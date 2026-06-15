import json
from decimal import Decimal

from django.test import Client, TestCase

from cigars.models import (
    Brand,
    Cigar,
    IdempotencyRecord,
    OrderEvent,
    PurchaseBatch,
    PurchaseOrder,
    PurchaseOrderItem,
    SalesOrderItem,
    StockAllocation,
    StockMovement,
    Supplier,
    User,
)
from cigars.services import (
    AgentContext,
    InsufficientStockError,
    cancel_sales_order,
    confirm_payment,
    create_sales_order,
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
        self.assertEqual(
            set(paid.items.first().allocations.values_list('status', flat=True)),
            {'fulfilled'},
        )
        ship = StockMovement.objects.get(movement_type='ship')
        self.assertEqual(ship.quantity, 4)

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
        self.batch.remaining = 20
        self.batch.save(update_fields=['remaining'])
        second = self.post_json('/api/agent/orders/create/', body)

        self.assertEqual(first.status_code, 400)
        self.assertEqual(second.status_code, 400)
        self.assertEqual(first.json(), second.json())
        self.assertFalse(StockAllocation.objects.exists())
        self.assertEqual(IdempotencyRecord.objects.get(key='idem-error').status_code, 400)
