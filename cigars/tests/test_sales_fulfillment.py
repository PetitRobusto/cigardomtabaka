from datetime import date
from decimal import Decimal

from django.test import TestCase

from accounting.models import LedgerPosting, LedgerTransaction
from cigars.models import (
    Brand,
    Cigar,
    PurchaseBatch,
    PurchaseOrder,
    PurchaseOrderItem,
    SalesOrder,
    SalesShipment,
    StockAllocation,
    StockMovement,
    Supplier,
    User,
)
from cigars.services import AgentContext, confirm_sales_order, create_sales_order_draft


class SalesFulfillmentServiceTest(TestCase):
    business_date = date(2026, 8, 10)

    def setUp(self):
        self.operator = User.objects.create_user(
            'fulfillment-operator', password='pass', is_staff=True,
        )
        brand = Brand.objects.create(english_name='Fulfillment Brand', name='出库品牌')
        self.cigar = Cigar.objects.create(
            brand=brand.english_name, english_name='Fulfillment Cigar', name='出库雪茄',
        )

    def context(self, command, key=''):
        return AgentContext(
            agent_name='fulfillment-test', agent_run_id='run-1',
            agent_request_id='request-1', command_name=command,
            idempotency_key=key,
        )

    def batch(self, *, quantity, unit_cost, box_size=None):
        supplier = Supplier.objects.create(name=f'fulfillment-supplier-{PurchaseOrder.objects.count()}')
        purchase_order = PurchaseOrder.objects.create(
            supplier=supplier, rub_total=Decimal('1.00'), exchange_rate=Decimal('1.0000'),
            cny_total=Decimal(str(quantity)) * Decimal(str(unit_cost)), operator=self.operator,
        )
        purchase_item = PurchaseOrderItem.objects.create(
            purchase_order=purchase_order, cigar=self.cigar, quantity=quantity,
            box_size=box_size, unit_price_rub=Decimal('1.00'),
            unit_price_cny=Decimal(str(unit_cost)),
        )
        if box_size:
            boxes, sticks = divmod(quantity, box_size)
        else:
            boxes, sticks = 0, quantity
        return PurchaseBatch.objects.create(
            purchase_order_item=purchase_item, cigar=self.cigar, quantity=quantity,
            remaining=quantity, physical_remaining=quantity,
            original_cost_cny=Decimal(str(quantity)) * Decimal(str(unit_cost)),
            remaining_cost_cny=Decimal(str(quantity)) * Decimal(str(unit_cost)),
            unit_cost_cny=Decimal(str(unit_cost)), box_size=box_size,
            original_box_quantity=boxes, original_stick_quantity=sticks,
            physical_box_quantity=boxes, available_box_quantity=boxes,
            physical_stick_quantity=sticks, available_stick_quantity=sticks,
        )

    def confirmed_order(self, *, quantity=3, unit_price='30.00', box_size=None):
        item = {
            'cigar_id': self.cigar.id,
            'sale_unit': 'stick',
            'quantity': quantity,
            'unit_price': unit_price,
        }
        if box_size:
            item.update(sale_unit='box', sale_quantity=quantity, box_size=box_size)
            item['quantity'] = quantity * box_size
        order = create_sales_order_draft(
            items=[item], operator=self.operator, customer_name='测试客户',
            customer_transport_fee_cny='5.00',
            agent_context=self.context('create_sales_order_draft'),
        )
        return confirm_sales_order(
            sales_order_id=order.id, operator=self.operator,
            agent_context=self.context('confirm_sales_order'),
        )

    def test_ship_unpaid_order_posts_ar_and_fifo_cost(self):
        first = self.batch(quantity=2, unit_cost='10.00')
        second = self.batch(quantity=2, unit_cost='12.00')
        order = self.confirmed_order(quantity=3, unit_price='30.00')

        from cigars.sales_accounting import ship_sales_order

        shipped = ship_sales_order(
            order_id=order.id, business_date=self.business_date,
            operator=self.operator, idempotency_key='ship-unpaid-1', note='出库',
        )

        shipped.refresh_from_db()
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(shipped.fulfillment_status, SalesOrder.FulfillmentStatus.SHIPPED)
        self.assertEqual(shipped.status, 'shipped')
        self.assertEqual(shipped.amount_due_cny, Decimal('95.00'))
        self.assertEqual(shipped.fifo_cost_cny, Decimal('32.00'))
        self.assertEqual(shipped.total_cost, Decimal('32.00'))
        self.assertEqual(shipped.contribution_profit_cny, Decimal('63.00'))
        self.assertEqual(shipped.total_profit, Decimal('63.00'))
        self.assertEqual(first.physical_remaining, 0)
        self.assertEqual(second.physical_remaining, 1)
        self.assertEqual(first.remaining_cost_cny, Decimal('0.00'))
        self.assertEqual(second.remaining_cost_cny, Decimal('12.00'))
        self.assertEqual(first.sold_cost_cny, Decimal('20.00'))
        self.assertEqual(second.sold_cost_cny, Decimal('12.00'))
        self.assertEqual(StockAllocation.objects.filter(status=StockAllocation.Status.FULFILLED).count(), 2)
        self.assertEqual(StockMovement.objects.filter(movement_type=StockMovement.MovementType.SHIP).count(), 2)
        shipment = SalesShipment.objects.get(sales_order=shipped)
        self.assertEqual(shipment.fifo_cost_cny, Decimal('32.00'))
        ledger = shipment.ledger_transaction
        self.assertEqual(ledger.transaction_type, LedgerTransaction.TransactionType.SALES_SHIPMENT)
        postings = list(ledger.postings.order_by('id').values_list('category', 'amount', 'cny_amount'))
        self.assertEqual(
            postings,
            [
                (LedgerPosting.Category.ACCOUNTS_RECEIVABLE, Decimal('95.00'), Decimal('95.00')),
                (LedgerPosting.Category.SALES_REVENUE, Decimal('-90.00'), Decimal('-90.00')),
                (LedgerPosting.Category.CUSTOMER_TRANSPORT_REVENUE, Decimal('-5.00'), Decimal('-5.00')),
                (LedgerPosting.Category.COST_OF_GOODS_SOLD, Decimal('32.00'), Decimal('32.00')),
                (LedgerPosting.Category.INVENTORY, Decimal('-32.00'), Decimal('-32.00')),
            ],
        )
        self.assertEqual(sum(row[2] for row in ledger.postings.values_list("category", "amount", "cny_amount")), Decimal("0.00"))
