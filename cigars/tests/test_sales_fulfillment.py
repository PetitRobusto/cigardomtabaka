from datetime import date
from decimal import Decimal

from unittest.mock import patch
from django.db import models
from django.test import TestCase

from accounting.models import Day1Initialization, FundAccount, LedgerMutationError, LedgerPosting, LedgerTransaction
from accounting.selectors import account_snapshot
from accounting.services import LedgerError
from cigars.models import (
    Brand,
    Cigar,
    PurchaseBatch,
    PurchaseOrder,
    PurchaseOrderItem,
    SalesOrder,
    SalesReceipt,
    SalesReturn,
    SalesShipment,
    StockAllocation,
    StockMovement,
    Supplier,
    User,
)
from cigars.tests.inventory_fixtures import (
    create_purchase_batch,
    create_stock_movement,
    force_inventory_save,
)
from cigars.inventory_audit import audit_inventory
from cigars.services import AgentContext, OrderServiceError, confirm_sales_order, create_sales_order_draft


class SalesFulfillmentServiceTest(TestCase):
    business_date = date(2026, 8, 10)

    def setUp(self):
        self.operator = User.objects.create_user(
            'fulfillment-operator', password='pass', is_staff=True,
        )
        Day1Initialization.objects.create(
            singleton_key='company', status=Day1Initialization.Status.COMPLETED,
            business_date=self.business_date, completed_by=self.operator,
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
        batch = create_purchase_batch(
            purchase_order_item=purchase_item, cigar=self.cigar, quantity=quantity,
            remaining=quantity, physical_remaining=quantity,
            original_cost_cny=Decimal(str(quantity)) * Decimal(str(unit_cost)),
            remaining_cost_cny=Decimal(str(quantity)) * Decimal(str(unit_cost)),
            unit_cost_cny=Decimal(str(unit_cost)), box_size=box_size,
            original_box_quantity=boxes, original_stick_quantity=sticks,
            physical_box_quantity=boxes, available_box_quantity=boxes,
            physical_stick_quantity=sticks, available_stick_quantity=sticks,
        )
        create_stock_movement(
            operator=self.operator,
            movement_type=StockMovement.MovementType.RECEIVE,
            cigar=self.cigar,
            purchase_batch=batch,
            quantity=quantity,
        )
        return batch

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

    def shipped_cross_batch_order(self, key):
        """构造跨两个批次出库的订单，供完整性测试使用。"""
        self.batch(quantity=2, unit_cost='10.00')
        self.batch(quantity=2, unit_cost='12.00')
        order = self.confirmed_order(quantity=3, unit_price='30.00')
        from cigars.sales_accounting import ship_sales_order
        ship_sales_order(
            order_id=order.pk, business_date=self.business_date,
            operator=self.operator, idempotency_key=key,
        )
        return order, list(StockAllocation.objects.filter(
            sales_order_item__sales_order=order,
        ).order_by('id'))

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

    def test_return_restores_cross_batch_cost_and_reverses_shipment(self):
        """整单退货按原分配成本恢复库存，并保留订单历史金额。"""
        first = self.batch(quantity=2, unit_cost='10.00')
        second = self.batch(quantity=2, unit_cost='12.00')
        order = self.confirmed_order(quantity=3, unit_price='30.00')
        from cigars.sales_accounting import return_sales_order, ship_sales_order

        shipped = ship_sales_order(
            order_id=order.id,
            business_date=self.business_date,
            operator=self.operator,
            idempotency_key='ship-before-return-1',
            note='出库',
        )
        sales_return = return_sales_order(
            order_id=order.id,
            business_date=date(2026, 8, 11),
            operator=self.operator,
            idempotency_key='return-order-1',
            reason='客户整单退回',
        )
        replayed = return_sales_order(
            order_id=order.id,
            business_date=date(2026, 8, 11),
            operator=self.operator,
            idempotency_key='return-order-1',
            reason='客户整单退回',
        )

        shipped.refresh_from_db()
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(replayed.pk, sales_return.pk)
        self.assertEqual(shipped.fulfillment_status, SalesOrder.FulfillmentStatus.RETURNED)
        self.assertEqual(shipped.payment_status, SalesOrder.PaymentStatus.UNPAID)
        self.assertEqual(shipped.fifo_cost_cny, Decimal('32.00'))
        self.assertEqual(shipped.total_cost, Decimal('32.00'))
        self.assertEqual(shipped.total_profit, Decimal('63.00'))
        self.assertEqual(first.physical_remaining, 2)
        self.assertEqual(first.remaining_cost_cny, Decimal('20.00'))
        self.assertEqual(first.sold_cost_cny, Decimal('0.00'))
        self.assertEqual(second.physical_remaining, 2)
        self.assertEqual(second.remaining_cost_cny, Decimal('24.00'))
        self.assertEqual(second.sold_cost_cny, Decimal('0.00'))
        self.assertEqual(
            StockAllocation.objects.filter(status=StockAllocation.Status.RETURNED).count(),
            2,
        )
        self.assertEqual(SalesReturn.objects.get(pk=sales_return.pk).fifo_cost_cny, Decimal('32.00'))
        original = SalesShipment.objects.get(sales_order=shipped).ledger_transaction
        original_rows = list(original.postings.order_by('id').values_list(
            'account_id', 'category', 'currency', 'amount', 'cny_amount',
        ))
        reversal_rows = list(sales_return.ledger_transaction.postings.order_by('id').values_list(
            'account_id', 'category', 'currency', 'amount', 'cny_amount',
        ))
        self.assertEqual(
            reversal_rows,
            [(account, category, currency, -amount, -cny)
             for account, category, currency, amount, cny in original_rows],
        )
        self.assertTrue(audit_inventory().ok)
        self.client.force_login(self.operator)
        report = self.client.get('/api/agent/reports/basic/').json()['sales']
        self.assertEqual(report['shipped_amount_due_cny'], 0)
        self.assertEqual(report['fifo_cost_cny'], 0)
        self.assertEqual(report['contribution_profit_cny'], 0)

    def test_sales_return_fact_rejects_plain_orm_writes(self):
        """整单退货事实创建后不可被普通 ORM 覆盖或删除。"""
        self.batch(quantity=1, unit_cost='10.00')
        order = self.confirmed_order(quantity=1, unit_price='30.00')
        from cigars.sales_accounting import return_sales_order, ship_sales_order
        ship_sales_order(
            order_id=order.pk, business_date=self.business_date,
            operator=self.operator, idempotency_key='ship-return-write-boundary',
        )
        sales_return = return_sales_order(
            order_id=order.pk, business_date=self.business_date,
            operator=self.operator, idempotency_key='return-write-boundary',
            reason='边界测试退货',
        )
        sales_return.reason = '禁止修改'
        actions = [
            lambda: sales_return.save(update_fields=['reason']),
            sales_return.delete,
            lambda: SalesReturn.objects.filter(pk=sales_return.pk).update(reason='禁止修改'),
            lambda: SalesReturn.objects.filter(pk=sales_return.pk).delete(),
            lambda: SalesReturn.objects.bulk_update([sales_return], ['reason']),
            lambda: SalesReturn.objects.bulk_create([sales_return]),
            lambda: SalesReturn.objects.update_or_create(pk=sales_return.pk, defaults={'reason': '禁止修改'}),
            lambda: SalesReturn.objects.get_or_create(pk=sales_return.pk),
        ]
        for write in actions:
            with self.subTest(write=write):
                with self.assertRaises(LedgerMutationError):
                    write()

    def test_return_rejects_missing_allocation_even_when_total_cost_matches(self):
        """缺少一条分配时，即使剩余成本被改成总成本也不能退货。"""
        order, allocations = self.shipped_cross_batch_order('ship-before-missing-allocation')
        shipment = SalesShipment.objects.get(sales_order=order)
        models.QuerySet.delete(StockAllocation.objects.filter(pk=allocations[0].pk))
        models.QuerySet.update(
            StockAllocation.objects.filter(pk=allocations[1].pk),
            fulfilled_cost_cny=shipment.fifo_cost_cny,
        )
        from cigars.sales_accounting import return_sales_order

        with self.assertRaises(OrderServiceError):
            return_sales_order(
                order_id=order.pk, business_date=self.business_date,
                operator=self.operator, idempotency_key='reject-missing-allocation',
                reason='损坏事实不能退货',
            )
        self.assertFalse(StockMovement.objects.filter(
            sales_order=order, movement_type=StockMovement.MovementType.RETURN,
        ).exists())

    def test_return_rejects_duplicate_allocation(self):
        """重复分配不能复用同一条 SHIP 流水恢复两次库存。"""
        order, allocations = self.shipped_cross_batch_order('ship-before-duplicate-allocation')
        source = allocations[0]
        duplicate = StockAllocation(
            sales_order_item_id=source.sales_order_item_id,
            purchase_batch_id=source.purchase_batch_id,
            quantity=source.quantity,
            inventory_form=source.inventory_form,
            box_size_snapshot=source.box_size_snapshot,
            status=source.status,
            fulfilled_at=source.fulfilled_at,
            fulfilled_cost_cny=source.fulfilled_cost_cny,
        )
        models.Model.save(duplicate, force_insert=True)
        from cigars.sales_accounting import return_sales_order

        with self.assertRaises(OrderServiceError):
            return_sales_order(
                order_id=order.pk, business_date=self.business_date,
                operator=self.operator, idempotency_key='reject-duplicate-allocation',
                reason='损坏事实不能退货',
            )

    def test_return_rejects_quantity_swap_with_same_total_and_cost(self):
        """分配数量互换后总量和总成本不变，仍必须与逐条 SHIP 流水一致。"""
        order, allocations = self.shipped_cross_batch_order('ship-before-quantity-swap')
        self.assertEqual([row.quantity for row in allocations], [2, 1])
        models.QuerySet.update(
            StockAllocation.objects.filter(pk=allocations[0].pk), quantity=1,
        )
        models.QuerySet.update(
            StockAllocation.objects.filter(pk=allocations[1].pk), quantity=2,
        )
        from cigars.sales_accounting import return_sales_order

        with self.assertRaises(OrderServiceError):
            return_sales_order(
                order_id=order.pk, business_date=self.business_date,
                operator=self.operator, idempotency_key='reject-quantity-swap',
                reason='损坏事实不能退货',
            )

    def test_audit_reports_tampered_shipment_cost_posting(self):
        """销售出库库存成本分录被篡改时，审计必须报警。"""
        self.batch(quantity=1, unit_cost='10.00')
        order = self.confirmed_order(quantity=1, unit_price='30.00')
        from cigars.sales_accounting import ship_sales_order
        ship_sales_order(
            order_id=order.pk, business_date=self.business_date,
            operator=self.operator, idempotency_key='shipment-posting-audit',
        )
        shipment = SalesShipment.objects.get(sales_order=order)
        models.QuerySet.update(
            LedgerPosting.objects.filter(
                transaction=shipment.ledger_transaction,
                category=LedgerPosting.Category.INVENTORY,
            ),
            amount=Decimal('-9.00'), cny_amount=Decimal('-9.00'),
        )

        self.assertIn(
            'SALES_SHIPMENT_LEDGER_MISMATCH',
            {issue.code for issue in audit_inventory().issues},
        )

    def test_return_rolls_back_inventory_when_ledger_reversal_fails(self):
        """退货冲正失败时，订单和库存必须保持已出库状态。"""
        batch = self.batch(quantity=3, unit_cost='10.00')
        order = self.confirmed_order(quantity=3, unit_price='30.00')
        from cigars.sales_accounting import return_sales_order, ship_sales_order

        shipped = ship_sales_order(
            order_id=order.id,
            business_date=self.business_date,
            operator=self.operator,
            idempotency_key='ship-before-failed-return',
        )
        with patch(
            'cigars.sales_accounting.reverse_ledger_transaction',
            side_effect=LedgerError('冲正失败'),
        ):
            with self.assertRaises(LedgerError):
                return_sales_order(
                    order_id=order.id,
                    business_date=date(2026, 8, 11),
                    operator=self.operator,
                    idempotency_key='failed-sales-return',
                    reason='测试回滚',
                )

        shipped.refresh_from_db()
        batch.refresh_from_db()
        allocation = StockAllocation.objects.get(sales_order_item__sales_order=order)
        self.assertEqual(shipped.fulfillment_status, SalesOrder.FulfillmentStatus.SHIPPED)
        self.assertEqual(batch.physical_remaining, 0)
        self.assertEqual(batch.sold_cost_cny, Decimal('30.00'))
        self.assertEqual(allocation.status, StockAllocation.Status.FULFILLED)
        self.assertFalse(SalesReturn.objects.filter(sales_order=order).exists())

    def test_audit_rejects_return_linked_to_another_orders_shipment(self):
        """退货事实关联到另一订单的出库单时必须报警。"""
        self.batch(quantity=2, unit_cost='10.00')
        from cigars.sales_accounting import return_sales_order, ship_sales_order

        first_order = self.confirmed_order(quantity=1, unit_price='30.00')
        ship_sales_order(
            order_id=first_order.id,
            business_date=self.business_date,
            operator=self.operator,
            idempotency_key='ship-before-cross-linked-return',
        )
        sales_return = return_sales_order(
            order_id=first_order.id,
            business_date=date(2026, 8, 11),
            operator=self.operator,
            idempotency_key='cross-linked-return',
            reason='客户退货',
        )
        second_order = self.confirmed_order(quantity=1, unit_price='30.00')
        ship_sales_order(
            order_id=second_order.id,
            business_date=self.business_date,
            operator=self.operator,
            idempotency_key='other-shipment-for-return-audit',
        )
        first_shipment = SalesShipment.objects.get(sales_order=first_order)
        second_shipment = SalesShipment.objects.get(sales_order=second_order)
        models.QuerySet.update(
            LedgerTransaction.objects.filter(pk=first_shipment.ledger_transaction_id),
            reversed_by_id=None,
        )
        models.QuerySet.update(
            LedgerTransaction.objects.filter(pk=second_shipment.ledger_transaction_id),
            reversed_by_id=sales_return.ledger_transaction_id,
        )
        models.QuerySet.update(
            SalesReturn.objects.filter(pk=sales_return.pk),
            sales_shipment_id=second_shipment.pk,
        )

        result = audit_inventory()

        self.assertIn(
            'SALES_RETURN_FACT_MISMATCH',
            {issue.code for issue in result.issues},
        )


    def test_ship_box_reduces_physical_box_and_cost(self):
        batch = self.batch(quantity=25, unit_cost='10.00', box_size=25)
        order = self.confirmed_order(quantity=1, unit_price='400.00', box_size=25)
        from cigars.sales_accounting import ship_sales_order
        shipped = ship_sales_order(
            order_id=order.id,
            business_date=self.business_date,
            operator=self.operator,
            idempotency_key='ship-box-1',
        )
        batch.refresh_from_db()
        item = shipped.items.get()
        self.assertEqual(batch.available_box_quantity, 0)
        self.assertEqual(batch.physical_box_quantity, 0)
        self.assertEqual(batch.physical_remaining, 0)
        self.assertEqual(item.cost, Decimal('250.00'))
        self.assertEqual(shipped.total_cost, Decimal('250.00'))

    def test_ship_preserves_fifo_tail_cost(self):
        batch = self.batch(quantity=3, unit_cost='3.3366666667')
        batch.original_cost_cny = Decimal('10.01')
        batch.remaining_cost_cny = Decimal('10.01')
        batch.unit_cost_cny = Decimal('3.3366666667')
        force_inventory_save(
            batch,
            update_fields=['original_cost_cny', 'remaining_cost_cny', 'unit_cost_cny'],
        )
        order = self.confirmed_order(quantity=3, unit_price='20.00')
        from cigars.sales_accounting import ship_sales_order
        shipped = ship_sales_order(
            order_id=order.id,
            business_date=self.business_date,
            operator=self.operator,
            idempotency_key='ship-tail-1',
        )
        batch.refresh_from_db()
        item = shipped.items.get()
        self.assertEqual(batch.remaining_cost_cny, Decimal('0.00'))
        self.assertEqual(batch.sold_cost_cny, Decimal('10.01'))
        self.assertEqual(item.cost, Decimal('10.01'))
        self.assertEqual(shipped.total_cost, Decimal('10.01'))
        self.assertEqual(shipped.total_profit, Decimal('54.99'))


    def test_ship_retries_locked_writer_and_commits_once(self):
        self.batch(quantity=3, unit_cost='10.00')
        order = self.confirmed_order(quantity=3, unit_price='20.00')
        from cigars.sales_accounting import ship_sales_order
        from django.db import OperationalError
        import accounting.services as accounting_services
        original_gate = accounting_services._acquire_sqlite_writer_gate
        calls = {'count': 0}

        def flaky_gate():
            calls['count'] += 1
            if calls['count'] == 1:
                raise OperationalError('database is locked')
            return original_gate()

        with patch('cigars.sales_accounting._acquire_sqlite_writer_gate', side_effect=flaky_gate):
            with patch('accounting.services.time.sleep'):
                shipped = ship_sales_order(
                    order_id=order.id,
                    business_date=self.business_date,
                    operator=self.operator,
                    idempotency_key='ship-retry-1',
                )
        self.assertEqual(shipped.fulfillment_status, SalesOrder.FulfillmentStatus.SHIPPED)
        self.assertEqual(SalesShipment.objects.count(), 1)
        self.assertEqual(StockMovement.objects.filter(movement_type=StockMovement.MovementType.SHIP).count(), 1)

    def test_ship_rolls_back_inventory_when_ledger_fails(self):
        batch = self.batch(quantity=3, unit_cost='10.00')
        order = self.confirmed_order(quantity=3, unit_price='20.00')
        from cigars.sales_accounting import ship_sales_order
        with patch('cigars.sales_accounting._post_transaction_once', side_effect=LedgerError('ledger failed')):
            with self.assertRaises(LedgerError):
                ship_sales_order(order_id=order.id, business_date=self.business_date, operator=self.operator, idempotency_key='ship-rollback-1')
        batch.refresh_from_db(); order.refresh_from_db()
        self.assertEqual(batch.physical_remaining, 3)
        self.assertEqual(batch.remaining_cost_cny, Decimal('30.00'))
        self.assertEqual(batch.sold_cost_cny, Decimal('0.00'))
        self.assertEqual(StockAllocation.objects.filter(status=StockAllocation.Status.RESERVED).count(), 1)
        self.assertEqual(StockMovement.objects.filter(movement_type=StockMovement.MovementType.SHIP).count(), 0)
        self.assertEqual(SalesShipment.objects.count(), 0)
        self.assertEqual(order.fulfillment_status, SalesOrder.FulfillmentStatus.CONFIRMED)
        self.assertEqual(order.total_cost, Decimal('0.00'))

    def test_ship_same_key_does_not_create_duplicate_facts(self):
        self.batch(quantity=3, unit_cost='10.00')
        order = self.confirmed_order(quantity=3, unit_price='20.00')
        from cigars.sales_accounting import ship_sales_order
        first = ship_sales_order(order_id=order.id, business_date=self.business_date, operator=self.operator, idempotency_key='ship-idempotent-1')
        second = ship_sales_order(order_id=order.id, business_date=self.business_date, operator=self.operator, idempotency_key='ship-idempotent-1')
        self.assertEqual(second.id, first.id)
        with self.assertRaises(Exception):
            ship_sales_order(order_id=order.id, business_date=self.business_date, operator=self.operator, idempotency_key='ship-idempotent-2')
        self.assertEqual(first.id, order.id)
        self.assertEqual(SalesShipment.objects.count(), 1)
        self.assertEqual(LedgerTransaction.objects.filter(transaction_type=LedgerTransaction.TransactionType.SALES_SHIPMENT).count(), 1)
        self.assertEqual(StockMovement.objects.filter(movement_type=StockMovement.MovementType.SHIP).count(), 1)


    def test_ship_same_key_replays_after_original_operator_loses_permission(self):
        """既有出库事实不能因原操作员后来降权而失去重放能力。"""
        self.batch(quantity=3, unit_cost='10.00')
        order = self.confirmed_order(quantity=3, unit_price='20.00')
        from cigars.sales_accounting import ship_sales_order

        first = ship_sales_order(
            order_id=order.id, business_date=self.business_date,
            operator=self.operator, idempotency_key='ship-replay-revoked',
        )
        self.operator.is_staff = False
        replay = ship_sales_order(
            order_id=order.id, business_date=self.business_date,
            operator=self.operator, idempotency_key='ship-replay-revoked',
        )

        self.assertEqual(replay.pk, first.pk)
    def test_receive_payment_after_shipment_clears_receivable(self):
        account = FundAccount.objects.create(name='销售收款账户', currency=FundAccount.Currency.CNY, custodian=self.operator, creation_idempotency_key='sales-receipt-account-1')
        self.batch(quantity=3, unit_cost='10.00')
        order = self.confirmed_order(quantity=3, unit_price='30.00')
        from cigars.sales_accounting import receive_sales_order_payment, ship_sales_order
        ship_sales_order(order_id=order.id, business_date=self.business_date, operator=self.operator, idempotency_key='ship-before-receipt-1', note='出库')
        received = receive_sales_order_payment(order_id=order.id, amount_cny=Decimal('95.00'), fund_account=account, business_date=self.business_date, operator=self.operator, idempotency_key='sales-receipt-1')
        account.refresh_from_db(); order.refresh_from_db()
        self.assertEqual(account_snapshot(account).original_balance, Decimal('95.00000000'))
        self.assertEqual(account_snapshot(account).cny_book_cost, Decimal('95.00'))
        ledger = received.ledger_transaction
        self.assertEqual(ledger.transaction_type, LedgerTransaction.TransactionType.SALES_RECEIPT)
        self.assertEqual(list(ledger.postings.order_by('id').values_list('category', 'amount', 'cny_amount')), [(LedgerPosting.Category.FUND_ACCOUNT, Decimal('95.00'), Decimal('95.00')), (LedgerPosting.Category.ACCOUNTS_RECEIVABLE, Decimal('-95.00'), Decimal('-95.00'))])
        self.assertEqual(received.amount_cny, Decimal('95.00'))
        self.assertEqual(received.fund_account_id, account.id)
        self.assertEqual(SalesReceipt.objects.get(sales_order=order).id, received.id)
        self.assertEqual(order.payment_status, SalesOrder.PaymentStatus.PAID)
        self.assertEqual(order.status, 'completed')
        self.assertEqual(order.fulfillment_status, SalesOrder.FulfillmentStatus.SHIPPED)


    def test_receive_payment_before_shipment_records_customer_prepayment(self):
        account = FundAccount.objects.create(name='预收人民币账户', currency=FundAccount.Currency.CNY, custodian=self.operator, creation_idempotency_key='prepay-account-1')
        self.batch(quantity=3, unit_cost='10.00')
        order = self.confirmed_order(quantity=3, unit_price='30.00')
        from cigars.sales_accounting import receive_sales_order_payment
        received = receive_sales_order_payment(order_id=order.id, amount_cny=Decimal('95.00'), fund_account=account, business_date=self.business_date, operator=self.operator, idempotency_key='prepay-receipt-1')
        order.refresh_from_db()
        self.assertEqual(order.fulfillment_status, SalesOrder.FulfillmentStatus.CONFIRMED)
        self.assertEqual(order.payment_status, SalesOrder.PaymentStatus.PAID)
        self.assertEqual(received.sales_order_id, order.id)
        self.assertEqual(account_snapshot(account).original_balance, Decimal('95.00000000'))
        self.assertEqual(list(received.ledger_transaction.postings.order_by('id').values_list('category', 'amount', 'cny_amount')), [
            (LedgerPosting.Category.FUND_ACCOUNT, Decimal('95.00'), Decimal('95.00')),
            (LedgerPosting.Category.CUSTOMER_PREPAYMENTS, Decimal('-95.00'), Decimal('-95.00')),
        ])
        self.assertFalse(received.ledger_transaction.postings.filter(category=LedgerPosting.Category.ACCOUNTS_RECEIVABLE).exists())

    def test_prepaid_order_shipment_releases_prepayment_and_posts_profit(self):
        account = FundAccount.objects.create(name='预收出库账户', currency=FundAccount.Currency.CNY, custodian=self.operator, creation_idempotency_key='prepay-account-2')
        batch = self.batch(quantity=3, unit_cost='10.00')
        order = self.confirmed_order(quantity=3, unit_price='30.00')
        from cigars.sales_accounting import receive_sales_order_payment, ship_sales_order
        receive_sales_order_payment(order_id=order.id, amount_cny=Decimal('95.00'), fund_account=account, business_date=self.business_date, operator=self.operator, idempotency_key='prepay-receipt-2')
        shipped = ship_sales_order(order_id=order.id, business_date=self.business_date, operator=self.operator, idempotency_key='prepay-ship-1')
        shipped.refresh_from_db(); batch.refresh_from_db()
        ledger = SalesShipment.objects.get(sales_order=shipped).ledger_transaction
        self.assertEqual((shipped.fulfillment_status, shipped.payment_status, shipped.status), (SalesOrder.FulfillmentStatus.SHIPPED, SalesOrder.PaymentStatus.PAID, 'completed'))
        self.assertEqual(batch.physical_remaining, 0)
        self.assertEqual(list(ledger.postings.order_by('id').values_list('category', 'amount', 'cny_amount')), [
            (LedgerPosting.Category.CUSTOMER_PREPAYMENTS, Decimal('95.00'), Decimal('95.00')),
            (LedgerPosting.Category.SALES_REVENUE, Decimal('-90.00'), Decimal('-90.00')),
            (LedgerPosting.Category.CUSTOMER_TRANSPORT_REVENUE, Decimal('-5.00'), Decimal('-5.00')),
            (LedgerPosting.Category.COST_OF_GOODS_SOLD, Decimal('30.00'), Decimal('30.00')),
            (LedgerPosting.Category.INVENTORY, Decimal('-30.00'), Decimal('-30.00')),
        ])
        self.assertFalse(ledger.postings.filter(category=LedgerPosting.Category.ACCOUNTS_RECEIVABLE).exists())

    def test_prepaid_receipt_same_key_replays_and_different_key_rejects(self):
        account = FundAccount.objects.create(name='预收幂等账户', currency=FundAccount.Currency.CNY, custodian=self.operator, creation_idempotency_key='prepay-account-3')
        self.batch(quantity=3, unit_cost='10.00')
        order = self.confirmed_order(quantity=3, unit_price='30.00')
        from cigars.sales_accounting import receive_sales_order_payment
        first = receive_sales_order_payment(order_id=order.id, amount_cny=Decimal('95.00'), fund_account=account, business_date=self.business_date, operator=self.operator, idempotency_key='prepay-idempotent-1')
        second = receive_sales_order_payment(order_id=order.id, amount_cny=Decimal('95.00'), fund_account=account, business_date=self.business_date, operator=self.operator, idempotency_key='prepay-idempotent-1')
        self.assertEqual(second.id, first.id)
        FundAccount.objects.filter(pk=account.pk).update(is_active=False)
        SalesOrder.objects.filter(pk=order.pk).update(
            fulfillment_status=SalesOrder.FulfillmentStatus.CANCELLED,
        )
        replay_after_state_change = receive_sales_order_payment(
            order_id=order.id, amount_cny=Decimal('95.00'),
            fund_account=account, business_date=self.business_date,
            operator=self.operator, idempotency_key='prepay-idempotent-1',
        )
        self.assertEqual(replay_after_state_change.pk, first.pk)
        with self.assertRaises((LedgerError, OrderServiceError)):
            receive_sales_order_payment(order_id=order.id, amount_cny=Decimal('95.00'), fund_account=account, business_date=self.business_date, operator=self.operator, idempotency_key='prepay-idempotent-2')
        self.assertEqual(SalesReceipt.objects.count(), 1)
        self.assertEqual(LedgerTransaction.objects.filter(transaction_type=LedgerTransaction.TransactionType.SALES_RECEIPT).count(), 1)

    def test_receipt_replay_rejects_non_posted_ledger_fact(self):
        """损坏为非 POSTED 的流水不能被当作成功收款事实重放。"""
        account = FundAccount.objects.create(
            name='预收状态校验账户', currency=FundAccount.Currency.CNY,
            custodian=self.operator, creation_idempotency_key='prepay-status-account',
        )
        self.batch(quantity=3, unit_cost='10.00')
        order = self.confirmed_order(quantity=3, unit_price='30.00')
        from cigars.sales_accounting import receive_sales_order_payment

        receipt = receive_sales_order_payment(
            order_id=order.id, amount_cny=Decimal('95.00'), fund_account=account,
            business_date=self.business_date, operator=self.operator,
            idempotency_key='prepay-status-replay',
        )
        transaction_obj = receipt.ledger_transaction
        transaction_obj.status = LedgerTransaction.Status.DRAFT
        models.Model.save(transaction_obj, update_fields=['status'])

        with self.assertRaises(OrderServiceError):
            receive_sales_order_payment(
                order_id=order.id, amount_cny=Decimal('95.00'), fund_account=account,
                business_date=self.business_date, operator=self.operator,
                idempotency_key='prepay-status-replay',
            )

    def test_receipt_replay_rejects_changed_receipt_operator(self):
        """收款模型与流水必须指向同一个原操作员。"""
        account = FundAccount.objects.create(
            name='预收操作员校验账户', currency=FundAccount.Currency.CNY,
            custodian=self.operator, creation_idempotency_key='prepay-operator-account',
        )
        self.batch(quantity=3, unit_cost='10.00')
        order = self.confirmed_order(quantity=3, unit_price='30.00')
        from cigars.sales_accounting import receive_sales_order_payment

        receipt = receive_sales_order_payment(
            order_id=order.id, amount_cny=Decimal('95.00'), fund_account=account,
            business_date=self.business_date, operator=self.operator,
            idempotency_key='prepay-operator-replay',
        )
        other = User.objects.create_user('changed-receipt-operator', is_staff=True)
        receipt.operator = other
        models.Model.save(receipt, update_fields=['operator'])

        with self.assertRaises(OrderServiceError):
            receive_sales_order_payment(
                order_id=order.id, amount_cny=Decimal('95.00'), fund_account=account,
                business_date=self.business_date, operator=self.operator,
                idempotency_key='prepay-operator-replay',
            )

    def test_prepaid_receipt_ledger_failure_rolls_back_everything(self):
        account = FundAccount.objects.create(name='预收回滚账户', currency=FundAccount.Currency.CNY, custodian=self.operator, creation_idempotency_key='prepay-account-4')
        self.batch(quantity=3, unit_cost='10.00')
        order = self.confirmed_order(quantity=3, unit_price='30.00')
        from cigars.sales_accounting import receive_sales_order_payment
        with patch('cigars.sales_accounting._post_transaction_once', side_effect=LedgerError('ledger failed')):
            with self.assertRaises(LedgerError):
                receive_sales_order_payment(order_id=order.id, amount_cny=Decimal('95.00'), fund_account=account, business_date=self.business_date, operator=self.operator, idempotency_key='prepay-rollback-1')
        order.refresh_from_db(); account.refresh_from_db()
        self.assertEqual((order.fulfillment_status, order.payment_status), (SalesOrder.FulfillmentStatus.CONFIRMED, SalesOrder.PaymentStatus.UNPAID))
        self.assertEqual(account_snapshot(account).original_balance, Decimal('0E-8'))
        self.assertEqual(SalesReceipt.objects.count(), 0)
        self.assertEqual(LedgerTransaction.objects.count(), 0)

    def test_prepaid_receipt_rejects_invalid_amount_or_account(self):
        from cigars.sales_accounting import receive_sales_order_payment
        cases = (('amount precision', Decimal('95.001'), FundAccount.Currency.CNY, True), ('inactive account', Decimal('95.00'), FundAccount.Currency.CNY, False), ('rub account', Decimal('95.00'), FundAccount.Currency.RUB, True))
        for index, (label, amount, currency, active) in enumerate(cases):
            with self.subTest(label=label):
                account = FundAccount.objects.create(name=f'预收校验账户{index}', currency=currency, custodian=self.operator, is_active=active, creation_idempotency_key=f'prepay-account-invalid-{index}')
                self.batch(quantity=3, unit_cost='10.00')
                order = self.confirmed_order(quantity=3, unit_price='30.00')
                with self.assertRaises((LedgerError, OrderServiceError)):
                    receive_sales_order_payment(order_id=order.id, amount_cny=amount, fund_account=account, business_date=self.business_date, operator=self.operator, idempotency_key=f'prepay-invalid-{index}')
                order.refresh_from_db()
                self.assertEqual(order.payment_status, SalesOrder.PaymentStatus.UNPAID)
                self.assertFalse(SalesReceipt.objects.filter(sales_order=order).exists())

    def test_prepaid_shipment_ledger_failure_preserves_inventory_and_reservation(self):
        account = FundAccount.objects.create(name='预收出库回滚账户', currency=FundAccount.Currency.CNY, custodian=self.operator, creation_idempotency_key='prepay-account-5')
        batch = self.batch(quantity=3, unit_cost='10.00')
        order = self.confirmed_order(quantity=3, unit_price='30.00')
        from cigars.sales_accounting import receive_sales_order_payment, ship_sales_order
        receive_sales_order_payment(order_id=order.id, amount_cny=Decimal('95.00'), fund_account=account, business_date=self.business_date, operator=self.operator, idempotency_key='prepay-receipt-rollback-1')
        with patch('cigars.sales_accounting._post_transaction_once', side_effect=LedgerError('ledger failed')):
            with self.assertRaises(LedgerError):
                ship_sales_order(order_id=order.id, business_date=self.business_date, operator=self.operator, idempotency_key='prepay-ship-rollback-1')
        batch.refresh_from_db(); order.refresh_from_db()
        self.assertEqual(batch.physical_remaining, 3)
        self.assertEqual(batch.remaining_cost_cny, Decimal('30.00'))
        self.assertEqual(StockAllocation.objects.filter(status=StockAllocation.Status.RESERVED).count(), 1)
        self.assertEqual(StockMovement.objects.filter(movement_type=StockMovement.MovementType.SHIP).count(), 0)
        self.assertEqual((order.fulfillment_status, order.payment_status), (SalesOrder.FulfillmentStatus.CONFIRMED, SalesOrder.PaymentStatus.PAID))
        self.assertEqual(SalesShipment.objects.count(), 0)

    def test_prepaid_receipt_rejects_mismatched_replay_and_cross_order_key(self):
        first_account = FundAccount.objects.create(name='预收严格账户1', currency=FundAccount.Currency.CNY, custodian=self.operator, creation_idempotency_key='prepay-account-strict-1')
        second_account = FundAccount.objects.create(name='预收严格账户2', currency=FundAccount.Currency.CNY, custodian=self.operator, creation_idempotency_key='prepay-account-strict-2')
        self.batch(quantity=6, unit_cost='10.00')
        first_order = self.confirmed_order(quantity=3, unit_price='30.00')
        second_order = self.confirmed_order(quantity=3, unit_price='30.00')
        from cigars.sales_accounting import receive_sales_order_payment
        receive_sales_order_payment(order_id=first_order.id, amount_cny=Decimal('95.00'), fund_account=first_account, business_date=self.business_date, operator=self.operator, idempotency_key='prepay-strict-1')
        with self.assertRaises(OrderServiceError):
            receive_sales_order_payment(order_id=first_order.id, amount_cny=Decimal('95.00'), fund_account=second_account, business_date=self.business_date, operator=self.operator, idempotency_key='prepay-strict-1')
        with self.assertRaises(OrderServiceError):
            receive_sales_order_payment(order_id=second_order.id, amount_cny=Decimal('95.00'), fund_account=second_account, business_date=self.business_date, operator=self.operator, idempotency_key='prepay-strict-1')


    def test_ship_same_key_cannot_be_reused_for_another_order(self):
        self.batch(quantity=6, unit_cost='10.00')
        first_order = self.confirmed_order(quantity=3, unit_price='30.00')
        second_order = self.confirmed_order(quantity=3, unit_price='30.00')
        from cigars.sales_accounting import ship_sales_order
        ship_sales_order(order_id=first_order.id, business_date=self.business_date, operator=self.operator, idempotency_key='ship-cross-order-1')
        with self.assertRaises(OrderServiceError):
            ship_sales_order(order_id=second_order.id, business_date=self.business_date, operator=self.operator, idempotency_key='ship-cross-order-1')
        second_order.refresh_from_db()
        self.assertEqual(second_order.fulfillment_status, SalesOrder.FulfillmentStatus.CONFIRMED)
        self.assertEqual(StockAllocation.objects.filter(sales_order_item__sales_order=second_order, status=StockAllocation.Status.RESERVED).count(), 1)
        self.assertEqual(SalesShipment.objects.filter(sales_order=second_order).count(), 0)

    def test_ship_same_key_replay_with_different_date_is_rejected(self):
        self.batch(quantity=3, unit_cost='10.00')
        order = self.confirmed_order(quantity=3, unit_price='30.00')
        from cigars.sales_accounting import ship_sales_order
        ship_sales_order(order_id=order.id, business_date=self.business_date, operator=self.operator, idempotency_key='ship-date-replay-1')
        with self.assertRaises(OrderServiceError):
            ship_sales_order(order_id=order.id, business_date=date(2026, 8, 11), operator=self.operator, idempotency_key='ship-date-replay-1')

    def test_ship_replay_rejects_changed_note(self):
        self.batch(quantity=3, unit_cost='10.00')
        order = self.confirmed_order(quantity=3, unit_price='30.00')
        from cigars.sales_accounting import ship_sales_order

        ship_sales_order(
            order_id=order.id, business_date=self.business_date,
            operator=self.operator, idempotency_key='ship-note-replay', note='仓库出库',
        )
        with self.assertRaises(OrderServiceError):
            ship_sales_order(
                order_id=order.id, business_date=self.business_date,
                operator=self.operator, idempotency_key='ship-note-replay', note='修改后备注',
            )

    def test_ship_replay_rejects_changed_operator(self):
        self.batch(quantity=3, unit_cost='10.00')
        order = self.confirmed_order(quantity=3, unit_price='30.00')
        other = User.objects.create_user('other-ship-operator', is_staff=True)
        from cigars.sales_accounting import ship_sales_order

        ship_sales_order(
            order_id=order.id, business_date=self.business_date,
            operator=self.operator, idempotency_key='ship-operator-replay',
        )
        with self.assertRaises(OrderServiceError):
            ship_sales_order(
                order_id=order.id, business_date=self.business_date,
                operator=other, idempotency_key='ship-operator-replay',
            )

    def test_ship_replay_rejects_corrupted_posting(self):
        """出库 replay 必须拒绝与 FIFO 事实不一致的损坏流水。"""
        self.batch(quantity=3, unit_cost='10.00')
        order = self.confirmed_order(quantity=3, unit_price='30.00')
        from cigars.sales_accounting import ship_sales_order

        ship_sales_order(
            order_id=order.id, business_date=self.business_date,
            operator=self.operator, idempotency_key='ship-posting-replay',
        )
        shipment = SalesShipment.objects.get(sales_order=order)
        posting = shipment.ledger_transaction.postings.get(
            category=LedgerPosting.Category.COST_OF_GOODS_SOLD,
        )
        posting.cny_amount += Decimal('1.00')
        models.Model.save(posting, update_fields=['cny_amount'])

        with self.assertRaises(OrderServiceError):
            ship_sales_order(
                order_id=order.id, business_date=self.business_date,
                operator=self.operator, idempotency_key='ship-posting-replay',
            )
