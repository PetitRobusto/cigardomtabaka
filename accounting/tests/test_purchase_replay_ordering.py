"""Task 4 幂等优先、成本池与锁重试回归。"""

from decimal import Decimal
from unittest.mock import patch

from django.db import OperationalError
from django.test import TestCase

from accounting.models import Day1Initialization, LedgerTransaction
from accounting.purchase_actions import (
    PurchaseActionError, receive_paid_purchase_order,
)
from accounting.tests import purchase_spec_coverage_cases as cases
from cigars.models import PurchaseBatch, PurchaseOrderItem, StockMovement
from cigars.sales_accounting import ship_sales_order
from cigars.tests.inventory_fixtures import create_purchase_batch
from cigars.services import (
    AgentContext, confirm_sales_order, create_sales_order_draft,
    receive_purchase_order, split_purchase_batch_box,
)


class PurchaseReplayOrderingTest(cases.PurchaseSpecMixin, TestCase):
    def setUp(self):
        self.make_fixture()

    def test_payment_replay_survives_day1_and_operator_state_change(self):
        payment = self.pay(key="payment-before-day1-change")
        Day1Initialization.objects.all().delete()
        self.operator.is_active = False
        self.operator.save(update_fields=["is_active"])

        replay = self.pay(key="payment-before-day1-change")

        self.assertEqual(replay.pk, payment.pk)

    def test_receipt_replay_survives_day1_and_operator_state_change(self):
        self.pay(key="receipt-replay-payment")
        batches = receive_paid_purchase_order(
            purchase_order_id=self.order.pk, business_date=cases.DAY,
            operator=self.operator, idempotency_key="receipt-before-day1-change",
        )
        Day1Initialization.objects.all().delete()
        self.operator.is_active = False
        self.operator.save(update_fields=["is_active"])

        replay = receive_paid_purchase_order(
            purchase_order_id=self.order.pk, business_date=cases.DAY,
            operator=self.operator, idempotency_key="receipt-before-day1-change",
        )

        self.assertEqual([batch.pk for batch in replay], [batch.pk for batch in batches])

    def test_legacy_receive_propagates_explicit_key_to_stock_movement(self):
        self.pay(key="legacy-explicit-payment")

        batches = receive_purchase_order(
            purchase_order_id=self.order.pk, business_date=cases.DAY,
            operator=self.operator, idempotency_key="legacy-explicit-receipt",
        )

        movement = StockMovement.objects.get(purchase_batch=batches[0])
        self.assertEqual(movement.idempotency_key, "legacy-explicit-receipt")

    def test_receipt_rejects_existing_batch_without_posting(self):
        self.pay(key="existing-batch-payment")
        item = self.order.items.get()
        create_purchase_batch(
            operator=self.operator,
            purchase_order_item=item, cigar=item.cigar,
            quantity=25, remaining=25, physical_remaining=25,
            original_cost_cny=Decimal("0.00"), remaining_cost_cny=Decimal("0.00"),
            sold_cost_cny=Decimal("0.00"), unit_cost_cny=Decimal("0.00"),
            box_size=25, original_box_quantity=1, original_stick_quantity=0,
            physical_box_quantity=1, available_box_quantity=1,
            physical_stick_quantity=0, available_stick_quantity=0,
        )

        with self.assertRaises(PurchaseActionError) as ctx:
            receive_paid_purchase_order(
                purchase_order_id=self.order.pk, business_date=cases.DAY,
                operator=self.operator, idempotency_key="existing-batch-receipt",
            )

        self.assertEqual(ctx.exception.code, "already_received")
        self.assertFalse(LedgerTransaction.objects.filter(
            idempotency_key="existing-batch-receipt",
        ).exists())

    def test_two_batches_split_and_fifo_finish_cost_pools(self):
        first = self.order.items.get()
        first.unit_price_rub_per_box = Decimal("100.00")
        first.save(update_fields=["unit_price_rub_per_box"])
        PurchaseOrderItem.objects.create(
            purchase_order=self.order, cigar=self.cigar,
            quantity=20, box_size=10, box_quantity=2,
            unit_price_rub_per_box=Decimal("100.00"),
            packaging_status=PurchaseOrderItem.PackagingStatus.UNREPRESENTABLE,
        )
        self.pay(key="two-batch-payment")
        batches = receive_paid_purchase_order(
            purchase_order_id=self.order.pk, business_date=cases.DAY,
            operator=self.operator, idempotency_key="two-batch-receipt",
        )
        split_purchase_batch_box(
            batch_id=batches[0].pk, operator=self.operator,
            agent_context=AgentContext(command_name="split", idempotency_key="split-first"),
        )
        for index in range(2):
            split_purchase_batch_box(
                batch_id=batches[1].pk, operator=self.operator,
                agent_context=AgentContext(
                    command_name="split", idempotency_key=f"split-second-{index}",
                ),
            )
        draft = create_sales_order_draft(
            items=[{"cigar_id": self.cigar.pk, "quantity": 45, "unit_price": "2.00"}],
            operator=self.operator,
            agent_context=AgentContext(command_name="draft", idempotency_key="two-batch-draft"),
        )
        confirm_sales_order(
            sales_order_id=draft.pk, operator=self.operator,
            agent_context=AgentContext(command_name="confirm", idempotency_key="two-batch-confirm"),
        )
        ship_sales_order(
            order_id=draft.pk, business_date=cases.DAY,
            operator=self.operator, idempotency_key="two-batch-ship",
        )

        for batch in PurchaseBatch.objects.filter(pk__in=[batch.pk for batch in batches]):
            self.assertEqual(batch.remaining_cost_cny, Decimal("0.00"))
            self.assertEqual(
                batch.original_cost_cny,
                batch.remaining_cost_cny + batch.sold_cost_cny + batch.adjustment_cost_cny,
            )

    def test_payment_and_receipt_retry_sqlite_lock(self):
        with patch(
            "accounting.purchase_actions._acquire_sqlite_writer_gate",
            side_effect=[OperationalError("database is locked"), None],
        ) as payment_gate:
            self.pay(key="retry-payment")
        self.assertEqual(payment_gate.call_count, 2)

        with patch(
            "accounting.purchase_actions._acquire_sqlite_writer_gate",
            side_effect=[OperationalError("database is locked"), None],
        ) as receipt_gate:
            receive_paid_purchase_order(
                purchase_order_id=self.order.pk, business_date=cases.DAY,
                operator=self.operator, idempotency_key="retry-receipt",
            )
        self.assertEqual(receipt_gate.call_count, 2)
