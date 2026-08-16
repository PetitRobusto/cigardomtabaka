from decimal import Decimal
from datetime import date

from django.db import models
from django.test import TestCase
from django.utils import timezone

from cigars.audit import AgentContext
from cigars.inventory import reserve_order_item, return_order, ship_order
from cigars.inventory_audit import audit_inventory
from cigars.models import Cigar, SalesOrder, SalesOrderItem, StockMovement, User
from cigars.tests.inventory_fixtures import (
    create_purchase_batch,
    create_stock_movement,
    force_inventory_delete,
    force_inventory_update,
)
from accounting.models import LedgerPosting, LedgerTransaction
from accounting.services import PostingInput, _post_transaction_once, reverse_ledger_transaction


class InventoryAuditTest(TestCase):
    def setUp(self):
        self.operator = User.objects.create_user("inventory-audit", is_staff=True)
        self.cigar = Cigar.objects.create(
            brand="Audit", english_name="Audit Cigar", name="审计雪茄",
        )

    def make_batch(self, **overrides):
        values = {
            "purchase_order_item": None,
            "source": "opening",
            "cigar": self.cigar,
            "quantity": 10,
            "remaining": 10,
            "physical_remaining": 10,
            "box_size": None,
            "original_box_quantity": 0,
            "original_stick_quantity": 10,
            "physical_box_quantity": 0,
            "physical_stick_quantity": 10,
            "available_box_quantity": 0,
            "available_stick_quantity": 10,
            "original_cost_cny": Decimal("100.00"),
            "positive_adjustment_quantity": 0,
            "positive_adjustment_cost_cny": Decimal("0.00"),
            "adjustment_cost_cny": Decimal("0.00"),
            "remaining_cost_cny": Decimal("100.00"),
            "sold_cost_cny": Decimal("0.00"),
            "unit_cost_cny": Decimal("10.00"),
        }
        values.update(overrides)
        batch = create_purchase_batch(operator=self.operator, **values)
        create_stock_movement(
            operator=self.operator,
            movement_type=StockMovement.MovementType.RECEIVE,
            cigar=self.cigar,
            purchase_batch=batch,
            quantity=batch.quantity,
        )
        return batch

    def make_sale(self, batch, *, allocation_status="reserved"):
        order = SalesOrder.objects.create(
            customer_name="审计客户", operator=self.operator,
        )
        item = SalesOrderItem.objects.create(
            sales_order=order, cigar=self.cigar, quantity=2,
            unit_price=Decimal("20.00"), unit_cost=Decimal("10.00"),
            revenue=Decimal("40.00"), cost=Decimal("20.00"),
            profit=Decimal("20.00"), sale_unit="stick", sale_quantity=2,
        )
        reserve_order_item(
            order=order, item=item, operator=self.operator,
            context=AgentContext(agent_name="inventory-audit", command_name="audit"),
        )
        return order, item, item.allocations.get()

    def test_healthy_inventory_has_no_issues(self):
        batch = self.make_batch()
        order, item, allocation = self.make_sale(batch)
        result = audit_inventory()
        self.assertTrue(result.ok)
        self.assertEqual(result.issues, ())

    def test_fulfilled_and_returned_allocation_lifecycle_is_healthy(self):
        """持久化流水应支持预留、出库、退货的累计生命周期。"""
        batch = self.make_batch()
        order, item, allocation = self.make_sale(batch)
        context = AgentContext(
            agent_name='inventory-audit', command_name='audit-lifecycle',
        )

        ship_order(
            order=order,
            operator=self.operator,
            context=context,
        )
        self.assertTrue(audit_inventory().ok)

        return_order(
            order=order,
            operator=self.operator,
            context=context,
        )
        self.assertTrue(audit_inventory().ok)

    def test_cost_conservation_issue_is_reported(self):
        batch = self.make_batch()
        force_inventory_update(
            type(batch).objects.filter(pk=batch.pk), sold_cost_cny=Decimal("19.00"),
        )
        result = audit_inventory()
        self.assertIn("BATCH_COST_NOT_CONSERVED", {issue.code for issue in result.issues})

    def test_tampered_receive_quantity_is_reported(self):
        """活动批次的原始入库流水被篡改时必须报警。"""
        batch = self.make_batch()
        movement = StockMovement.objects.get(
            purchase_batch=batch,
            movement_type=StockMovement.MovementType.RECEIVE,
        )
        force_inventory_update(
            StockMovement.objects.filter(pk=movement.pk), quantity=batch.quantity - 1,
        )

        result = audit_inventory()

        self.assertIn(
            "BATCH_MOVEMENT_PHYSICAL_MISMATCH",
            {issue.code for issue in result.issues},
        )

    def test_missing_receive_movement_is_reported(self):
        """活动批次缺少原始入库流水时必须报警。"""
        batch = self.make_batch()
        force_inventory_delete(StockMovement.objects.filter(purchase_batch=batch))

        result = audit_inventory()

        self.assertIn(
            "BATCH_MOVEMENT_PHYSICAL_MISMATCH",
            {issue.code for issue in result.issues},
        )

    def test_allocation_timestamp_and_movement_link_issues_are_reported(self):
        batch = self.make_batch()
        order, item, allocation = self.make_sale(batch)
        force_inventory_update(type(allocation).objects.filter(pk=allocation.pk), released_at=timezone.now())
        movement = StockMovement.objects.get(sales_order_item=item)
        force_inventory_update(type(movement).objects.filter(pk=movement.pk), sales_order_id=None)
        result = audit_inventory()
        codes = {issue.code for issue in result.issues}
        self.assertIn("ALLOCATION_TIMESTAMP_MISMATCH", codes)
        self.assertIn("MOVEMENT_SALES_LINK_INCOMPLETE", codes)

    def test_missing_fulfillment_cost_snapshot_is_reported(self):
        """历史出库缺少分配级成本时，审计必须明确阻止猜测退货成本。"""
        batch = self.make_batch()
        order, item, allocation = self.make_sale(batch)
        ship_order(
            order=order,
            operator=self.operator,
            context=AgentContext(command_name='audit-missing-cost'),
        )
        force_inventory_update(
            type(allocation).objects.filter(pk=allocation.pk),
            fulfilled_cost_cny=None,
        )

        result = audit_inventory()

        self.assertIn(
            'ALLOCATION_COST_SNAPSHOT_MISSING',
            {issue.code for issue in result.issues},
        )

    def test_tampered_ledger_reversal_is_reported(self):
        """冲正分录不再逐笔相反时，库存审计必须报告。"""
        original = _post_transaction_once(
            transaction_type=LedgerTransaction.TransactionType.INVENTORY_ADJUSTMENT,
            business_date=date(2026, 8, 16),
            postings=[
                PostingInput(
                    category=LedgerPosting.Category.INVENTORY,
                    currency='CNY', amount=Decimal('-10.00'),
                    cny_amount=Decimal('-10.00'),
                ),
                PostingInput(
                    category=LedgerPosting.Category.INVENTORY_ADJUSTMENT_LOSS,
                    currency='CNY', amount=Decimal('10.00'),
                    cny_amount=Decimal('10.00'),
                ),
            ],
            operator=self.operator,
            idempotency_key='audit-original-adjustment',
            description='审计原调整',
            source_type='stock_adjustment',
            source_id='audit:1',
        )
        reversal = reverse_ledger_transaction(
            original_transaction=original,
            business_date=date(2026, 8, 16),
            operator=self.operator,
            idempotency_key='audit-adjustment-reversal',
            reason='审计冲正',
        )
        posting = reversal.postings.order_by('id').first()
        posting.amount += Decimal('1.00')
        posting.cny_amount += Decimal('1.00')
        models.Model.save(posting, update_fields=['amount', 'cny_amount'])

        result = audit_inventory()

        self.assertIn(
            'LEDGER_REVERSAL_POSTINGS_MISMATCH',
            {issue.code for issue in result.issues},
        )
