from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch
import json

from django.test import TestCase
from accounting.models import Day1Initialization, FundAccount, LedgerPosting
from accounting.purchase_actions import (create_purchase_order, update_purchase_order_draft,
    cancel_purchase_order, pay_purchase_order, receive_paid_purchase_order,
    reverse_received_purchase_order, PurchaseActionError)
from accounting.services import record_opening_balance
from cigars.models import Cigar, Supplier, User, StockMovement, StockAllocation
from cigars.services import (create_sales_order_draft, confirm_sales_order,
    cancel_confirmed_sales_order, serialize_sales_order, OrderServiceError)
from cigars.preorders import prepare_sales_preorder, source_options
from cigars.sales_accounting import receive_sales_order_payment, ship_sales_order, return_sales_order, refund_sales_order_payment


class PurchasePreorderTest(TestCase):
    day = date(2026, 8, 10)

    def setUp(self):
        self.operator = User.objects.create_user('preorder', password='x', is_staff=True)
        Day1Initialization.objects.create(singleton_key='company', status='completed', business_date=self.day, completed_by=self.operator)
        self.supplier = Supplier.objects.create(name='预售供货商')
        self.cigar = Cigar.objects.create(english_name='Preorder Cigar', name='预售雪茄')
        self.rub = FundAccount.objects.create(name='卢布', currency='RUB', creation_idempotency_key='rub')
        self.cny = FundAccount.objects.create(name='人民币', currency='CNY', creation_idempotency_key='cny')
        record_opening_balance(self.rub, Decimal('12000'), Decimal('1000'), LedgerPosting.Category.OPENING_CAPITAL, self.day, self.operator, 'opening')
        self.sequence = 0
        mock = patch('internal_notifications.business.schedule_order_notification')
        mock.start()
        self.addCleanup(mock.stop)

    def key(self):
        self.sequence += 1
        return f'preorder-test-{self.sequence}'

    def purchase_rows(self, quantity=10, box_size=None):
        return [dict(cigar_id=self.cigar.pk, purchase_unit='box', box_size=box_size, box_quantity=quantity, unit_price_rub_per_box='120') if box_size else
                dict(cigar_id=self.cigar.pk, purchase_unit='stick', quantity_sticks=quantity, unit_price_rub_per_stick='120')]

    def source(self, quantity=10, box_size=None):
        return create_purchase_order(supplier_id=self.supplier.pk, items=self.purchase_rows(quantity, box_size), business_date=self.day,
            operator=self.operator, idempotency_key=self.key())

    def draft(self, source, quantity=2, box_size=None, extra=None):
        item = dict(cigar_id=self.cigar.pk, fulfillment_type='preorder', quantity=quantity, unit_price='30', sale_unit='stick')
        if box_size:
            item.update(sale_unit='box', sale_quantity=quantity, quantity=quantity*box_size, box_size=box_size)
        if source:
            item['source_purchase_order_id'] = source.pk
        return create_sales_order_draft(items=[item, *(extra or [])], operator=self.operator, customer_name='测试客户')

    def confirm(self, order):
        return confirm_sales_order(sales_order_id=order.pk, operator=self.operator, business_date=self.day)

    def arrive(self, source):
        pay_purchase_order(purchase_order_id=source.pk, rub_account_id=self.rub.pk, business_date=self.day, operator=self.operator, idempotency_key=self.key())
        return receive_paid_purchase_order(purchase_order_id=source.pk, business_date=self.day, operator=self.operator, idempotency_key=self.key())

    def prepare(self, order, key=None, day=None):
        return prepare_sales_preorder(order_id=order.pk, business_date=day or self.day, operator=self.operator, idempotency_key=key or self.key())

    def receive(self, order, amount):
        return receive_sales_order_payment(order_id=order.pk, amount_cny=str(amount), fund_account=self.cny, business_date=self.day, operator=self.operator, idempotency_key=self.key())

    def test_purchase_draft_prepaid_then_arrival_direct_ship_tail_same_order(self):
        source = self.source()
        order = self.confirm(self.draft(source))
        self.assertEqual(StockMovement.objects.count(), 0)
        self.receive(order, 20)
        with self.assertRaisesMessage(OrderServiceError, '尚未到货'):
            self.prepare(order)
        self.assertNotIn('prepare_preorder', serialize_sales_order(order)['available_actions'])
        self.assertNotIn('ship', serialize_sales_order(order)['available_actions'])
        with self.assertRaises(OrderServiceError):
            ship_sales_order(order_id=order.pk, business_date=self.day, operator=self.operator, idempotency_key=self.key())
        self.arrive(source)
        key = self.key()
        count = StockMovement.objects.count()
        self.assertIn('ship', serialize_sales_order(order)['available_actions'])
        shipment = ship_sales_order(order_id=order.pk, business_date=self.day, operator=self.operator, idempotency_key=key)
        self.assertEqual(shipment.fifo_cost_cny, Decimal('20'))
        ship_sales_order(order_id=order.pk, business_date=self.day, operator=self.operator, idempotency_key=key)
        self.assertFalse(order.events.filter(command_name='prepare_sales_preorder').exists())
        self.receive(order, 40)
        order.refresh_from_db()
        self.assertEqual((order.fulfillment_status, order.payment_status), ('shipped', 'paid'))
        self.assertEqual(order.items.get().fulfillment_type, 'preorder')
        self.assertEqual(order.items.get().source_purchase_order_id, source.pk)
        self.assertEqual(sum(LedgerPosting.objects.filter(category='customer_prepayments').values_list('cny_amount', flat=True)), 0)
        self.assertEqual(sum(LedgerPosting.objects.filter(category='accounts_receivable').values_list('cny_amount', flat=True)), 0)
        self.assertEqual(StockMovement.objects.count(), count + 1)

    def test_arrival_reserves_before_picking_and_inventory_cost_stays_on_hand(self):
        source = self.source(10, 25)
        order = self.confirm(self.draft(source, 3, 25))
        batches = self.arrive(source)
        batch = batches[0]
        batch.refresh_from_db()
        self.assertEqual((batch.physical_remaining, batch.remaining), (250, 175))
        self.assertEqual(batch.remaining_cost_cny, Decimal('100'))
        serialized = serialize_sales_order(order)
        self.assertTrue(serialized['items'][0]['preorder_reserved'])
        self.assertFalse(serialized['items'][0]['preorder_prepared'])
        self.assertIn('ship', serialized['available_actions'])
        self.assertNotIn('prepare_preorder', serialized['available_actions'])
        self.client.force_login(self.operator)
        row = self.client.get('/api/inventory/').json()['cigars'][0]
        self.assertEqual((row['on_hand_quantity'], row['total_stock'], row['reserved_quantity'], row['preorder_waiting_quantity'], row['total_cost']), (250, 175, 75, 75, 100))
        from accounting.models import LedgerTransaction
        counts = (StockMovement.objects.count(), LedgerTransaction.objects.count())
        self.prepare(order)
        self.assertEqual((StockMovement.objects.count(), LedgerTransaction.objects.count()), counts)
        row = self.client.get('/api/inventory/').json()['cigars'][0]
        self.assertEqual((row['preorder_waiting_quantity'], row['preorder_prepared_quantity'], row['total_stock']), (0, 75, 175))
        stock_order = create_sales_order_draft(items=[dict(cigar_id=self.cigar.pk, sale_unit='box', sale_quantity=8, box_size=25, unit_price='30')], operator=self.operator)
        with self.assertRaises(OrderServiceError): self.confirm(stock_order)

    def test_fully_reserved_inventory_remains_visible_and_cancellation_releases_it(self):
        source = self.source(2)
        order = self.confirm(self.draft(source, 2))
        self.arrive(source)
        self.client.force_login(self.operator)
        row = self.client.get('/api/inventory/').json()['cigars'][0]
        self.assertEqual((row['total_stock'], row['on_hand_quantity'], row['preorder_waiting_quantity'], row['total_cost']), (0, 2, 2, 20))
        cancel_confirmed_sales_order(sales_order_id=order.pk, operator=self.operator)
        row = self.client.get('/api/inventory/').json()['cigars'][0]
        self.assertEqual((row['total_stock'], row['reserved_quantity'], row['preorder_waiting_quantity'], row['total_cost']), (2, 0, 0, 20))

    def test_arrival_replay_survives_auto_reserve_cancel_ship_and_return(self):
        for terminal in ['cancel', 'ship_return']:
            source = self.source(2, 25)
            order = self.confirm(self.draft(source, 2, 25))
            batches = self.arrive(source)
            source.refresh_from_db()
            def replay():
                before = StockMovement.objects.count()
                result = receive_paid_purchase_order(purchase_order_id=source.pk, business_date=self.day, operator=self.operator, idempotency_key=source.arrival_idempotency_key)
                self.assertEqual([b.pk for b in result], [b.pk for b in batches])
                self.assertEqual(StockMovement.objects.count(), before)
            replay()
            if terminal == 'cancel':
                cancel_confirmed_sales_order(sales_order_id=order.pk, operator=self.operator)
            else:
                self.prepare(order)
                ship_sales_order(order_id=order.pk, business_date=self.day, operator=self.operator, idempotency_key=self.key())
                replay()
                return_sales_order(order_id=order.pk, business_date=self.day, operator=self.operator, idempotency_key=self.key(), reason='测试退货')
            replay()

    def test_multiple_sources_reserve_each_arrival_but_require_all_before_picking(self):
        first, second = self.source(2), self.source(2)
        order = self.confirm(self.draft(first, 2, extra=[dict(cigar_id=self.cigar.pk, quantity=2, unit_price='30', sale_unit='stick', fulfillment_type='preorder', source_purchase_order_id=second.pk)]))
        self.arrive(first)
        self.assertEqual(StockAllocation.objects.count(), 1)
        with self.assertRaisesMessage(OrderServiceError, '尚未到货'): self.prepare(order)
        self.assertNotIn('ship', serialize_sales_order(order)['available_actions'])
        with self.assertRaisesMessage(OrderServiceError, '尚未到货'):
            ship_sales_order(order_id=order.pk, business_date=self.day, operator=self.operator, idempotency_key=self.key())
        self.assertEqual(StockAllocation.objects.count(), 1)
        self.arrive(second)
        self.assertEqual(StockAllocation.objects.count(), 2)
        ship_sales_order(order_id=order.pk, business_date=self.day, operator=self.operator, idempotency_key=self.key())
        self.assertEqual(StockAllocation.objects.count(), 2)

    def test_direct_shipment_checks_arrival_and_reservation_dates(self):
        source = self.source()
        order = self.draft(source)
        self.arrive(source)
        later = self.day + timedelta(days=1)
        confirm_sales_order(sales_order_id=order.pk, operator=self.operator, business_date=later)
        before = list(StockMovement.objects.values())
        with self.assertRaisesMessage(OrderServiceError, '到货日期'):
            ship_sales_order(order_id=order.pk, business_date=self.day-timedelta(days=1), operator=self.operator, idempotency_key=self.key())
        with self.assertRaisesMessage(OrderServiceError, '预留日期'):
            ship_sales_order(order_id=order.pk, business_date=self.day, operator=self.operator, idempotency_key=self.key())
        self.assertEqual(list(StockMovement.objects.values()), before)
        ship_sales_order(order_id=order.pk, business_date=later, operator=self.operator, idempotency_key=self.key())

    def test_legacy_unallocated_source_reserves_and_ships_in_one_transaction(self):
        source = self.source()
        order = self.confirm(self.draft(source))
        with patch('cigars.preorders.reserve_purchase_preorders'):
            self.arrive(source)  # 模拟旧版本到货时尚未自动分配。
        self.assertFalse(StockAllocation.objects.exists())
        ship_sales_order(order_id=order.pk, business_date=self.day, operator=self.operator, idempotency_key=self.key())
        self.assertEqual(StockAllocation.objects.get().status, 'fulfilled')
        self.assertFalse(order.events.filter(command_name='prepare_sales_preorder').exists())
        self.assertTrue(order.events.filter(command_name='reserve_sales_preorder').exists())

    def test_unsourced_legacy_cannot_ship_before_actual_batch_arrival(self):
        source = self.source()
        order = self.confirm(self.draft(None))
        pay_purchase_order(purchase_order_id=source.pk, rub_account_id=self.rub.pk, business_date=self.day, operator=self.operator, idempotency_key=self.key())
        later = self.day + timedelta(days=1)
        receive_paid_purchase_order(purchase_order_id=source.pk, business_date=later, operator=self.operator, idempotency_key=self.key())
        before = list(StockMovement.objects.values())
        with self.assertRaisesMessage(OrderServiceError, '实际分配批次的入库日期'):
            ship_sales_order(order_id=order.pk, business_date=self.day, operator=self.operator, idempotency_key=self.key())
        self.assertEqual(list(StockMovement.objects.values()), before)
        self.assertFalse(StockAllocation.objects.exists())
        self.assertFalse(order.events.filter(command_name='reserve_sales_preorder').exists())
        ship_sales_order(order_id=order.pk, business_date=later, operator=self.operator, idempotency_key=self.key())

    def test_legacy_cannot_ship_before_adjustment_inventory_exists(self):
        from cigars.audit import AgentContext
        from cigars.services import adjust_stock
        order = self.confirm(self.draft(None))
        later = self.day + timedelta(days=1)
        adjust_stock(cigar_id=self.cigar.pk, quantity_delta=2, unit_cost_cny='10',
            operator=self.operator, business_date=later, reason='测试调增',
            agent_context=AgentContext(command_name='adjust_stock', idempotency_key=self.key()))
        before = list(StockMovement.objects.values())
        with self.assertRaisesMessage(OrderServiceError, '库存调增日期'):
            ship_sales_order(order_id=order.pk, business_date=self.day, operator=self.operator, idempotency_key=self.key())
        self.assertEqual(list(StockMovement.objects.values()), before)
        self.assertFalse(StockAllocation.objects.exists())
        ship_sales_order(order_id=order.pk, business_date=later, operator=self.operator, idempotency_key=self.key())

    def test_reservation_failure_rolls_back_entire_arrival(self):
        from cigars.inventory import InventoryError
        from cigars.models import PurchaseBatch
        from accounting.models import LedgerTransaction
        source = self.source()
        self.confirm(self.draft(source))
        pay_purchase_order(purchase_order_id=source.pk, rub_account_id=self.rub.pk, business_date=self.day, operator=self.operator, idempotency_key=self.key())
        before = LedgerTransaction.objects.count()
        with patch('cigars.inventory.reserve_preorder_item', side_effect=InventoryError('模拟库存不足')):
            with self.assertRaises(PurchaseActionError):
                receive_paid_purchase_order(purchase_order_id=source.pk, business_date=self.day, operator=self.operator, idempotency_key=self.key())
        source.refresh_from_db()
        self.assertEqual(source.status, 'in_transit')
        self.assertFalse(source.arrival_idempotency_key)
        self.assertFalse(PurchaseBatch.objects.exists())
        self.assertFalse(StockMovement.objects.exists())
        self.assertEqual(LedgerTransaction.objects.count(), before)

    def test_confirm_capacity_is_net_of_cancelled_orders_and_drafts_do_not_reserve(self):
        source = self.source(5)
        first, second = self.draft(source, 4), self.draft(source, 2)
        self.assertEqual(source_options(source)['items'][0]['committed_quantity'], 0)
        self.confirm(first)
        with self.assertRaisesMessage(OrderServiceError, '剩余额度'):
            self.confirm(second)
        self.assertEqual(source_options(source)['items'][0]['remaining_quantity'], 1)
        cancel_confirmed_sales_order(sales_order_id=first.pk, operator=self.operator)
        self.confirm(second)
        self.assertEqual(source_options(source)['items'][0]['committed_quantity'], 2)

    def test_shipped_commitment_remains_until_return_and_source_is_retained(self):
        source = self.source(2)
        order = self.confirm(self.draft(source, 2))
        self.arrive(source)
        self.prepare(order)
        ship_sales_order(order_id=order.pk, business_date=self.day, operator=self.operator, idempotency_key=self.key())
        self.assertEqual(source_options(source)['items'][0]['remaining_quantity'], 0)
        return_sales_order(order_id=order.pk, business_date=self.day, reason='测试退货', operator=self.operator, idempotency_key=self.key())
        self.assertEqual(source_options(source)['items'][0]['remaining_quantity'], 2)
        order.refresh_from_db()
        item = serialize_sales_order(order)['items'][0]
        self.assertEqual((item['fulfillment_type'], item['source_purchase_order_id']), ('preorder', source.pk))

    def test_source_id_validation_and_unknown_source_leave_no_draft(self):
        from cigars.models import SalesOrder
        for invalid in [True, 1.5, 'abc', {}, [], 10**30, 999999]:
            with self.subTest(source=invalid), self.assertRaises(OrderServiceError):
                create_sales_order_draft(items=[dict(cigar_id=self.cigar.pk, quantity=1, unit_price='30', fulfillment_type='preorder', source_purchase_order_id=invalid)], operator=self.operator)
        self.assertFalse(SalesOrder.objects.exists())

    def test_purchase_edit_cancel_and_packaging_are_guarded(self):
        source = self.source(3, 25)
        order = self.confirm(self.draft(source, 2, 25))
        for rows in [self.purchase_rows(1, 25), self.purchase_rows(3, 10), self.purchase_rows(75)]:
            with self.assertRaises(PurchaseActionError) as caught:
                update_purchase_order_draft(purchase_order_id=source.pk, items=rows, expected_version=source.version, operator=self.operator, idempotency_key=self.key())
            self.assertEqual(caught.exception.code, 'preorder_commitment_conflict')
        with self.assertRaises(PurchaseActionError):
            cancel_purchase_order(purchase_order_id=source.pk, expected_version=source.version, operator=self.operator, idempotency_key=self.key())
        source = update_purchase_order_draft(purchase_order_id=source.pk, items=self.purchase_rows(4, 25), expected_version=source.version, operator=self.operator, idempotency_key=self.key())
        order.items.get().refresh_from_db()  # parent source survives replacement of purchase items
        self.assertEqual(source_options(source)['items'][0]['remaining_quantity'], 50)

    def test_draft_before_arrival_can_be_confirmed_after_arrival(self):
        source = self.source()
        order = self.draft(source)
        self.arrive(source)
        self.confirm(order)
        self.assertTrue(serialize_sales_order(order)['items'][0]['preorder_reserved'])
        self.assertFalse(serialize_sales_order(order)['items'][0]['preorder_prepared'])
        self.prepare(order)

    def test_picking_cannot_precede_late_confirmation_reservation(self):
        source = self.source()
        order = self.draft(source)
        self.arrive(source)
        later = self.day + timedelta(days=1)
        confirm_sales_order(sales_order_id=order.pk, operator=self.operator, business_date=later)
        with self.assertRaisesMessage(OrderServiceError, '不能早于预售预留日期'):
            self.prepare(order)
        self.prepare(order, day=later)

    def test_arrival_replay_still_rejects_corrupted_reserved_inventory(self):
        from cigars.models import PurchaseBatch
        from cigars.tests.inventory_fixtures import force_inventory_update
        source = self.source()
        self.confirm(self.draft(source))
        batch = self.arrive(source)[0]
        source.refresh_from_db()
        force_inventory_update(PurchaseBatch.objects.filter(pk=batch.pk), remaining=7, available_stick_quantity=7)
        with self.assertRaises(PurchaseActionError) as caught:
            receive_paid_purchase_order(purchase_order_id=source.pk, business_date=self.day, operator=self.operator, idempotency_key=source.arrival_idempotency_key)
        self.assertEqual(caught.exception.code, 'idempotency_conflict')

    def test_arrival_replay_rejects_balanced_cost_changes_without_business_facts(self):
        from cigars.models import PurchaseBatch
        from cigars.tests.inventory_fixtures import force_inventory_update
        source = self.source()
        self.confirm(self.draft(source))
        batch = self.arrive(source)[0]
        source.refresh_from_db()
        for changes in [dict(remaining_cost_cny=Decimal('99'), sold_cost_cny=Decimal('1')),
                        dict(remaining_cost_cny=Decimal('99'), adjustment_cost_cny=Decimal('1')),
                        dict(remaining_cost_cny=Decimal('101'), positive_adjustment_cost_cny=Decimal('1'))]:
            with self.subTest(changes=changes):
                force_inventory_update(PurchaseBatch.objects.filter(pk=batch.pk), **{
                    'remaining_cost_cny': Decimal('100'), 'sold_cost_cny': Decimal('0'),
                    'adjustment_cost_cny': Decimal('0'), 'positive_adjustment_cost_cny': Decimal('0'), **changes})
                with self.assertRaises(PurchaseActionError) as caught:
                    receive_paid_purchase_order(purchase_order_id=source.pk, business_date=self.day, operator=self.operator, idempotency_key=source.arrival_idempotency_key)
                self.assertEqual(caught.exception.code, 'idempotency_conflict')

    def test_arrival_replay_accepts_recorded_adjustments_and_their_reversal(self):
        from cigars.audit import AgentContext
        from cigars.models import InventoryAdjustmentAction
        from cigars.services import adjust_stock, reverse_stock_adjustment
        source = self.source()
        self.confirm(self.draft(source))
        batch = self.arrive(source)[0]
        source.refresh_from_db()
        def replay():
            result = receive_paid_purchase_order(purchase_order_id=source.pk, business_date=self.day, operator=self.operator, idempotency_key=source.arrival_idempotency_key)
            self.assertEqual([row.pk for row in result], [batch.pk])
        for quantity in [1, -1]:
            key = self.key()
            adjust_stock(cigar_id=self.cigar.pk, quantity_delta=quantity, operator=self.operator,
                         reason='测试库存调整', batch_id=batch.pk, business_date=self.day,
                         agent_context=AgentContext(command_name='adjust_stock', idempotency_key=key))
            replay()
            action = InventoryAdjustmentAction.objects.get(idempotency_key=key)
            reverse_stock_adjustment(adjustment_id=action.pk, business_date=self.day,
                                     operator=self.operator, idempotency_key=self.key(), reason='测试撤销调整')
            replay()

    def test_changed_cancelled_source_rejected_at_confirmation(self):
        source = self.source()
        order = self.draft(source)
        cancel_purchase_order(purchase_order_id=source.pk, expected_version=source.version, operator=self.operator, idempotency_key=self.key())
        with self.assertRaisesMessage(OrderServiceError, '已取消'):
            self.confirm(order)

    def test_fifo_from_other_purchase_still_blocks_reversing_source_arrival(self):
        older = self.source(10, 25)
        old_batches = self.arrive(older)
        source = self.source(10, 25)
        order = self.confirm(self.draft(source, 2, 25))
        self.arrive(source)
        self.prepare(order)
        self.assertEqual(StockAllocation.objects.get().purchase_batch_id, old_batches[0].pk)
        with self.assertRaises(PurchaseActionError) as caught:
            reverse_received_purchase_order(purchase_order_id=source.pk, business_date=self.day, operator=self.operator, idempotency_key=self.key(), reason='测试撤销')
        self.assertEqual(caught.exception.code, 'preorder_commitment_conflict')
        cancel_confirmed_sales_order(sales_order_id=order.pk, operator=self.operator)
        reverse_received_purchase_order(purchase_order_id=source.pk, business_date=self.day, operator=self.operator, idempotency_key=self.key(), reason='订单已取消')

    def test_prepare_date_and_replay_payload_guard(self):
        source = self.source()
        order = self.confirm(self.draft(source))
        self.arrive(source)
        with self.assertRaisesMessage(OrderServiceError, '早于'):
            self.prepare(order, day=self.day-timedelta(days=1))
        key = self.key()
        self.prepare(order, key, self.day+timedelta(days=1))
        with self.assertRaisesMessage(OrderServiceError, '幂等键'):
            self.prepare(order, key)
        with self.assertRaisesMessage(OrderServiceError, '备货日期'):
            ship_sales_order(order_id=order.pk, business_date=self.day, operator=self.operator, idempotency_key=self.key())

    def test_legacy_preorder_without_source_and_return_refund(self):
        self.arrive(self.source())
        order = self.confirm(self.draft(None))
        self.receive(order, 60)
        ship_sales_order(order_id=order.pk, business_date=self.day, operator=self.operator, idempotency_key=self.key())
        return_sales_order(order_id=order.pk, business_date=self.day, operator=self.operator, idempotency_key=self.key(), reason='整单退货')
        refund_sales_order_payment(order_id=order.pk, business_date=self.day, operator=self.operator, idempotency_key=self.key())
        order.refresh_from_db()
        self.assertEqual((order.fulfillment_status, order.payment_status), ('returned', 'refunded'))

    def test_web_permissions_idempotency_source_and_prepare(self):
        source = self.source()
        self.assertEqual(self.client.get(f'/api/sales/preorder-sources/{source.pk}/').status_code, 403)
        self.client.force_login(self.operator)
        response = self.client.get(f'/api/sales/preorder-sources/{source.pk}/')
        self.assertEqual(response.status_code, 200)
        order = self.confirm(self.draft(source))
        self.arrive(source)
        url=f'/api/sales/orders/{order.pk}/prepare-preorder/'
        payload=json.dumps({'business_date':self.day.isoformat()})
        response=self.client.post(url, payload, content_type='application/json', HTTP_IDEMPOTENCY_KEY='web-prepare')
        self.assertEqual(response.status_code, 200, response.content)
        replay=self.client.post(url, payload, content_type='application/json', HTTP_IDEMPOTENCY_KEY='web-prepare')
        self.assertEqual(response.json(), replay.json())
        self.assertTrue(response.json()['sales_order']['items'][0]['preorder_prepared'])
        self.assertEqual(StockAllocation.objects.count(), 1)

    def test_duplicate_sales_lines_share_capacity_and_wrong_packaging_rejected(self):
        source = self.source(3)
        extra = dict(cigar_id=self.cigar.pk, sale_unit='stick', quantity=2, unit_price='30', fulfillment_type='preorder', source_purchase_order_id=source.pk)
        with self.assertRaisesMessage(OrderServiceError, '剩余额度'):
            self.draft(source, 2, extra=[extra])
        with self.assertRaisesMessage(OrderServiceError, '不匹配'):
            self.draft(source, 1, 25)
        with self.assertRaisesMessage(OrderServiceError, '只有预售'):
            create_sales_order_draft(items=[{**extra, 'fulfillment_type':'in_stock'}], operator=self.operator)

    def test_mixed_order_shortage_rolls_back_preorder_reservations_and_preserves_in_stock(self):
        self.arrive(self.source(3))
        other = Cigar.objects.create(name='暂未到货', english_name='Missing Cigar')
        extra = [dict(cigar_id=self.cigar.pk, sale_unit='stick', quantity=1, unit_price='30', fulfillment_type='in_stock'),
                 dict(cigar_id=other.pk, sale_unit='stick', quantity=1, unit_price='30', fulfillment_type='preorder')]
        order = self.confirm(self.draft(None, 2, extra=extra))
        before = list(StockMovement.objects.values())
        with self.assertRaisesMessage(OrderServiceError, '库存不足'):
            self.prepare(order)
        with self.assertRaisesMessage(OrderServiceError, '库存不足'):
            ship_sales_order(order_id=order.pk, business_date=self.day, operator=self.operator, idempotency_key=self.key())
        self.assertEqual(list(StockMovement.objects.values()), before)
        self.assertEqual(StockAllocation.objects.count(), 1)
        self.assertEqual(StockAllocation.objects.get().sales_order_item.fulfillment_type, 'in_stock')

    def test_cancel_after_prepare_releases_inventory_and_replay_does_not_reserve(self):
        source = self.source()
        order = self.confirm(self.draft(source))
        batches = self.arrive(source)
        key = self.key()
        self.prepare(order, key)
        cancel_confirmed_sales_order(sales_order_id=order.pk, operator=self.operator)
        self.prepare(order, key)
        batches[0].refresh_from_db()
        self.assertEqual(batches[0].remaining, 10)
        self.assertEqual(StockAllocation.objects.get().status, 'released')

    def test_agent_prepare_rejects_invalid_ids_and_missing_order(self):
        self.client.force_login(self.operator)
        for invalid in ['abc', {}, [], True, False, 1.5, 1.0, 0, -1, None, '1.2', 10**30, '9' * 5000]:
            with self.subTest(order_id=invalid):
                response = self.client.post('/api/agent/orders/prepare-preorder/', json.dumps({
                    'sales_order_id': invalid, 'operator_id': self.operator.pk,
                    'agent': {'agent_name': 'preorder-test'},
                    'business_date': self.day.isoformat(), 'idempotency_key': self.key(),
                }), content_type='application/json')
                self.assertEqual(response.status_code, 400, response.content)
                self.assertIn('正整数', response.json()['error'])
        response = self.client.post('/api/agent/orders/prepare-preorder/', json.dumps({
            'sales_order_id': 999999, 'operator_id': self.operator.pk,
            'agent': {'agent_name': 'preorder-test'},
            'business_date': self.day.isoformat(), 'idempotency_key': self.key(),
        }), content_type='application/json')
        self.assertEqual(response.status_code, 404)
        self.assertFalse(StockAllocation.objects.exists())


from threading import Barrier, Thread
from django.db import close_old_connections
from django.test import Client, TransactionTestCase
from django.test import tag
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


@tag('migration', 'migration-other')
class PreorderSourceMigrationTest(TransactionTestCase):
    def test_existing_orders_keep_values_and_have_no_invented_purchase_source(self):
        executor = MigrationExecutor(connection)
        leaves = executor.loader.graph.leaf_nodes()
        before = [('cigars', '0044_sales_partial_receipts')]
        after = [('cigars', '0045_sales_preorder_source')]
        executor.migrate(before)
        self.addCleanup(lambda: MigrationExecutor(connection).migrate(leaves))
        apps = executor.loader.project_state(before).apps
        user = apps.get_model('cigars', 'User').objects.create(username='migration-preorder')
        cigar = apps.get_model('cigars', 'Cigar').objects.create(english_name='Migration Cigar')
        order = apps.get_model('cigars', 'SalesOrder').objects.create(operator=user, fulfillment_status='confirmed', payment_status='partial', amount_due_cny='60')
        old_item = apps.get_model('cigars', 'SalesOrderItem').objects.create(
            sales_order=order, cigar=cigar, fulfillment_type='preorder', quantity=2,
            unit_price='30', unit_cost='0', revenue='60', cost='0', profit='60')
        original = apps.get_model('cigars', 'SalesOrderItem').objects.values().get(pk=old_item.pk)
        executor = MigrationExecutor(connection)
        executor.migrate(after)
        apps = executor.loader.project_state(after).apps
        migrated = apps.get_model('cigars', 'SalesOrderItem').objects.values().get(pk=old_item.pk)
        self.assertIsNone(migrated.pop('source_purchase_order_id'))
        self.assertEqual(migrated, original)
        migrated_order = apps.get_model('cigars', 'SalesOrder').objects.get(pk=order.pk)
        self.assertEqual((migrated_order.fulfillment_status, migrated_order.payment_status, migrated_order.amount_due_cny), ('confirmed', 'partial', Decimal('60')))


class PreorderConcurrencyTest(TransactionTestCase):
    day = PurchasePreorderTest.day
    setUp = PurchasePreorderTest.setUp
    key = PurchasePreorderTest.key
    source = PurchasePreorderTest.source
    draft = PurchasePreorderTest.draft
    purchase_rows = PurchasePreorderTest.purchase_rows
    arrive = PurchasePreorderTest.arrive
    confirm = PurchasePreorderTest.confirm

    def compete(self, paths, payloads, keys):
        clients = [Client(), Client()]
        for client in clients:
            client.force_login(self.operator)
        barrier = Barrier(2)
        results = []
        def worker(index):
            close_old_connections()
            try:
                barrier.wait()
                response = clients[index].post(paths[index], json.dumps(payloads[index]), content_type='application/json', HTTP_IDEMPOTENCY_KEY=keys[index])
                results.append((response.status_code, response.json()))
            except Exception as exc:
                results.append((500, str(exc)))
            finally:
                close_old_connections()
        threads = [Thread(target=worker, args=(i,)) for i in range(2)]
        for thread in threads: thread.start()
        for thread in threads:
            thread.join(20)
            self.assertFalse(thread.is_alive())
        return results

    def test_competing_confirmations_cannot_oversell_source(self):
        source = self.source(3)
        orders = [self.draft(source, 2), self.draft(source, 2)]
        results = self.compete([f'/api/sales/orders/{o.pk}/confirm/' for o in orders], [{}, {}], ['confirm-a', 'confirm-b'])
        self.assertEqual(sorted(row[0] for row in results), [200, 400], results)
        self.assertEqual(source_options(source)['items'][0]['committed_quantity'], 2)

    def test_concurrent_prepare_same_key_reserves_once(self):
        source = self.source()
        order = self.confirm(self.draft(source))
        self.arrive(source)
        path = f'/api/sales/orders/{order.pk}/prepare-preorder/'
        results = self.compete([path,path], [{'business_date':self.day.isoformat()}]*2, ['prepare-same']*2)
        self.assertEqual([row[0] for row in results], [200,200], results)
        self.assertEqual(StockAllocation.objects.count(), 1)

    def test_concurrent_direct_ship_same_key_consumes_once(self):
        source = self.source()
        order = self.confirm(self.draft(source))
        self.arrive(source)
        path = f'/api/sales/orders/{order.pk}/ship/'
        results = self.compete([path, path], [{'business_date': self.day.isoformat()}]*2, ['direct-ship-same']*2)
        self.assertEqual([row[0] for row in results], [200, 200], results)
        self.assertEqual(StockMovement.objects.filter(movement_type='reserve').count(), 1)
        self.assertEqual(StockMovement.objects.filter(movement_type='ship').count(), 1)

    def test_arrival_racing_confirmation_reserves_exactly_once(self):
        source = self.source()
        order = self.draft(source)
        pay_purchase_order(purchase_order_id=source.pk, rub_account_id=self.rub.pk, business_date=self.day, operator=self.operator, idempotency_key=self.key())
        results = self.compete(
            [f'/api/accounting/purchases/{source.pk}/receive/', f'/api/sales/orders/{order.pk}/confirm/'],
            [{'business_date': self.day.isoformat()}, {}], ['arrival-race', 'confirm-race'])
        self.assertEqual(sorted(row[0] for row in results), [200, 200], results)
        allocation = StockAllocation.objects.get()
        self.assertEqual((allocation.status, allocation.quantity), ('reserved', 2))
        self.assertEqual(allocation.purchase_batch.remaining, 8)

    def test_arrival_racing_cancellation_leaves_no_active_reservation(self):
        source = self.source()
        order = self.confirm(self.draft(source))
        pay_purchase_order(purchase_order_id=source.pk, rub_account_id=self.rub.pk, business_date=self.day, operator=self.operator, idempotency_key=self.key())
        results = self.compete(
            [f'/api/accounting/purchases/{source.pk}/receive/', f'/api/sales/orders/{order.pk}/cancel/'],
            [{'business_date': self.day.isoformat()}, {}], ['arrival-cancel-race', 'cancel-race'])
        self.assertEqual(sorted(row[0] for row in results), [200, 200], results)
        self.assertFalse(StockAllocation.objects.filter(status='reserved').exists())
        from cigars.models import PurchaseBatch
        self.assertEqual(PurchaseBatch.objects.get().remaining, 10)
