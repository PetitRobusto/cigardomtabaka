from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase

from accounting.models import Day1Initialization, Day1DraftAccount, Day1DraftInventory
from cigars.models import Cigar, PurchaseBatch


class Day1ModelTest(TestCase):
    def test_only_one_shared_company_initialization_can_exist(self):
        first = Day1Initialization.objects.create()

        with self.assertRaises(IntegrityError), transaction.atomic():
            Day1Initialization.objects.create()

        self.assertEqual(first.singleton_key, 'company')
        self.assertEqual(Day1Initialization.objects.count(), 1)

    def test_opening_purchase_batch_does_not_require_historical_order_item(self):
        cigar = Cigar.objects.create(
            brand='Day 1 Brand',
            english_name='Day 1 Cigar',
            name='期初雪茄',
        )

        batch = PurchaseBatch.objects.create(
            purchase_order_item=None,
            source=PurchaseBatch.Source.OPENING,
            cigar=cigar,
            quantity=10,
            remaining=10,
            physical_remaining=10,
            box_size=10,
            original_box_quantity=1,
            original_stick_quantity=0,
            physical_box_quantity=1,
            available_box_quantity=1,
            physical_stick_quantity=0,
            available_stick_quantity=0,
            original_cost_cny=Decimal('100.00'),
            remaining_cost_cny=Decimal('100.00'),
            unit_cost_cny=Decimal('10.00'),
        )

        self.assertIsNone(batch.purchase_order_item)
        self.assertEqual(batch.source, PurchaseBatch.Source.OPENING)

    def test_draft_account_slot_is_unique_per_initialization(self):
        initialization = Day1Initialization.objects.create()
        Day1DraftAccount.objects.create(
            initialization=initialization,
            slot=Day1DraftAccount.Slot.OWNER_CNY,
            account_name='老板人民币',
            currency='CNY',
            original_amount=Decimal('100.00'),
            cny_book_cost=Decimal('100.00'),
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            Day1DraftAccount.objects.create(
                initialization=initialization,
                slot=Day1DraftAccount.Slot.OWNER_CNY,
                account_name='重复账户',
                currency='CNY',
                original_amount=Decimal('1.00'),
                cny_book_cost=Decimal('1.00'),
            )

    def test_draft_inventory_is_unique_by_cigar_and_box_size(self):
        initialization = Day1Initialization.objects.create()
        cigar = Cigar.objects.create(
            brand='Day 1 Brand',
            english_name='Inventory Cigar',
            name='库存雪茄',
        )
        Day1DraftInventory.objects.create(
            initialization=initialization,
            cigar=cigar,
            box_size=25,
            box_quantity=1,
            loose_sticks=2,
            unit_cost_cny=Decimal('12.50'),
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            Day1DraftInventory.objects.create(
                initialization=initialization,
                cigar=cigar,
                box_size=25,
                box_quantity=2,
                loose_sticks=0,
                unit_cost_cny=Decimal('12.50'),
            )
