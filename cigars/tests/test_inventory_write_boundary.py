from decimal import Decimal

from django.contrib import admin
from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase

from cigars.audit import AgentContext
from cigars.inventory import open_stock, release_order, reserve_order_item
from cigars.inventory_scope import (
    _INVENTORY_WRITE_CAPABILITY, InventoryMutationError, inventory_mutation_scope,
)
from cigars.models import (
    Cigar,
    PurchaseBatch,
    SalesOrder,
    SalesOrderItem,
    StockAllocation,
    StockMovement,
    User,
)


class InventoryWriteBoundaryTest(TestCase):
    """模型层拒绝绕过统一库存 Module 的普通 ORM 写入。"""

    def setUp(self):
        self.operator = User.objects.create_user(
            'inventory-boundary-operator', is_staff=True,
        )
        self.cigar = Cigar.objects.create(
            brand='Boundary Brand',
            english_name='Boundary Cigar',
            name='库存边界雪茄',
        )
        self.context = AgentContext(
            agent_name='inventory-boundary-test',
            command_name='inventory_boundary',
        )
        self.batch = open_stock(
            cigar_id=self.cigar.pk,
            quantity=2,
            box_size=None,
            box_quantity=0,
            loose_sticks=2,
            total_cost_cny=Decimal('20.00'),
            unit_cost_cny=Decimal('10.00'),
            operator=self.operator,
            context=self.context,
        )
        self.order = SalesOrder.objects.create(
            customer_name='库存边界客户', operator=self.operator,
        )
        self.item = SalesOrderItem.objects.create(
            sales_order=self.order,
            cigar=self.cigar,
            quantity=1,
            unit_price=Decimal('20.00'),
            unit_cost=Decimal('0.00'),
            revenue=Decimal('20.00'),
            cost=Decimal('0.00'),
            profit=Decimal('0.00'),
            fulfillment_type=SalesOrderItem.FulfillmentType.IN_STOCK,
            sale_unit=SalesOrderItem.SaleUnit.STICK,
            sale_quantity=1,
        )

    def reserve(self):
        reserve_order_item(
            order=self.order,
            item=self.item,
            operator=self.operator,
            context=self.context,
        )
        return StockAllocation.objects.get(sales_order_item=self.item)

    def test_plain_create_is_rejected_for_every_inventory_fact(self):
        with self.assertRaises(InventoryMutationError):
            PurchaseBatch.objects.create(
                purchase_order_item=None,
                source=PurchaseBatch.Source.OPENING,
                cigar=self.cigar,
                quantity=1,
                remaining=1,
                physical_remaining=1,
                original_cost_cny=Decimal('10.00'),
                remaining_cost_cny=Decimal('10.00'),
                unit_cost_cny=Decimal('10.00'),
            )
        with self.assertRaises(InventoryMutationError):
            StockMovement.objects.create(
                movement_type=StockMovement.MovementType.RECEIVE,
                cigar=self.cigar,
                purchase_batch=self.batch,
                quantity=1,
                operator=self.operator,
            )
        with self.assertRaises(InventoryMutationError):
            StockAllocation.objects.create(
                sales_order_item=self.item,
                purchase_batch=self.batch,
                quantity=1,
            )

    def test_scope_requires_private_module_capability(self):
        with self.assertRaises(InventoryMutationError):
            with transaction.atomic(), inventory_mutation_scope(
                action='opening', operator=self.operator,
            ):
                pass

    def test_scope_rejects_fact_that_does_not_match_action(self):
        with self.assertRaises(InventoryMutationError):
            with transaction.atomic(), inventory_mutation_scope(
                action='opening', operator=self.operator,
                _capability=_INVENTORY_WRITE_CAPABILITY,
            ):
                PurchaseBatch.objects.create(
                    purchase_order_item=None,
                    source=PurchaseBatch.Source.ADJUSTMENT,
                    cigar=self.cigar,
                    quantity=1,
                    remaining=1,
                    physical_remaining=1,
                    original_cost_cny=Decimal('10.00'),
                    remaining_cost_cny=Decimal('10.00'),
                    unit_cost_cny=Decimal('10.00'),
                )

    def test_plain_instance_update_and_delete_are_rejected(self):
        self.batch.remaining = 1
        with self.assertRaises(InventoryMutationError):
            self.batch.save(update_fields=['remaining'])
        with self.assertRaises(InventoryMutationError):
            self.batch.delete()

        movement = StockMovement.objects.get(
            purchase_batch=self.batch,
            movement_type=StockMovement.MovementType.RECEIVE,
        )
        movement.note = '禁止修改'
        with self.assertRaises(InventoryMutationError):
            movement.save(update_fields=['note'])
        with self.assertRaises(InventoryMutationError):
            movement.delete()

        allocation = self.reserve()
        with self.assertRaises(InventoryMutationError):
            allocation.delete()

    def test_queryset_writes_are_rejected(self):
        movement = StockMovement.objects.get(purchase_batch=self.batch)
        actions = [
            lambda: PurchaseBatch.objects.filter(pk=self.batch.pk).update(remaining=1),
            lambda: PurchaseBatch.objects.filter(pk=self.batch.pk).delete(),
            lambda: PurchaseBatch._base_manager.filter(pk=self.batch.pk).update(remaining=1),
            lambda: PurchaseBatch._base_manager.filter(pk=self.batch.pk).delete(),
            lambda: PurchaseBatch.objects.bulk_create([PurchaseBatch(
                purchase_order_item=None,
                source=PurchaseBatch.Source.OPENING,
                cigar=self.cigar,
                quantity=1,
                remaining=1,
                physical_remaining=1,
                unit_cost_cny=Decimal('1.00'),
            )]),
            lambda: PurchaseBatch.objects.bulk_update([self.batch], ['remaining']),
            lambda: StockMovement.objects.filter(pk=movement.pk).update(note='禁止修改'),
            lambda: StockMovement.objects.filter(pk=movement.pk).delete(),
        ]
        for action in actions:
            with self.subTest(action=action):
                with self.assertRaises(InventoryMutationError):
                    action()

    def test_allocation_key_fields_cannot_change_inside_valid_scope(self):
        allocation = self.reserve()
        allocation.quantity = 2
        with self.assertRaises(InventoryMutationError):
            with transaction.atomic(), inventory_mutation_scope(
                action='release', operator=self.operator,
                _capability=_INVENTORY_WRITE_CAPABILITY,
            ):
                allocation.save(update_fields=['quantity'])

        allocation.refresh_from_db()
        self.assertEqual(allocation.quantity, 1)
        self.assertEqual(allocation.status, StockAllocation.Status.RESERVED)

    def test_allocation_only_leaves_reserved_once(self):
        allocation = self.reserve()
        release_order(
            order=self.order,
            operator=self.operator,
            context=self.context,
        )
        allocation.refresh_from_db()
        self.assertEqual(allocation.status, StockAllocation.Status.RELEASED)

        allocation.status = StockAllocation.Status.FULFILLED
        with self.assertRaises(InventoryMutationError):
            with transaction.atomic(), inventory_mutation_scope(
                action='ship', operator=self.operator,
                _capability=_INVENTORY_WRITE_CAPABILITY,
            ):
                allocation.save(update_fields=['status'])

    def test_sales_facts_cannot_cascade_delete_allocation(self):
        self.reserve()
        delete_actions = [
            self.item.delete,
            lambda: SalesOrderItem.objects.filter(pk=self.item.pk).delete(),
            self.order.delete,
        ]
        for action in delete_actions:
            with self.subTest(action=action):
                with self.assertRaises(ProtectedError), transaction.atomic():
                    action()

    def test_inventory_admins_are_read_only(self):
        for model in (PurchaseBatch, StockAllocation, StockMovement):
            model_admin = admin.site._registry[model]
            with self.subTest(model=model.__name__):
                self.assertFalse(model_admin.has_add_permission(None))
                self.assertFalse(model_admin.has_change_permission(None))
                self.assertFalse(model_admin.has_delete_permission(None))

    def test_legal_module_action_can_write_inventory_facts(self):
        allocation = self.reserve()
        self.batch.refresh_from_db()

        self.assertEqual(self.batch.remaining, 1)
        self.assertEqual(allocation.status, StockAllocation.Status.RESERVED)
        self.assertTrue(StockMovement.objects.filter(
            sales_order_item=self.item,
            movement_type=StockMovement.MovementType.RESERVE,
            quantity=1,
        ).exists())
