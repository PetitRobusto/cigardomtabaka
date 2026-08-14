from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from cigars.models import Cigar, PurchaseOrder, PurchaseOrderItem, Supplier
from django.contrib.auth import get_user_model


class PurchasePackagingModelTest(TestCase):
    def setUp(self):
        User = get_user_model()
        self.operator = User.objects.create_user(username="purchase-model")
        self.supplier = Supplier.objects.create(name="测试供应商")
        self.cigar = Cigar.objects.create(
            english_name="Test Cigar", name="测试雪茄", brand="Test"
        )
        self.order = PurchaseOrder.objects.create(
            supplier=self.supplier,
            operator=self.operator,
            rub_total="100.00",
            exchange_rate="12.0000",
            cny_total="8.33",
        )

    def test_quantity_box_check_and_model_clean_reject_mismatch(self):
        item = PurchaseOrderItem.objects.create(
            purchase_order=self.order,
            cigar=self.cigar,
            quantity=25,
            box_size=25,
            box_quantity=1,
            unit_price_rub="100.00",
            unit_price_cny="8.00",
            unit_price_rub_per_box="100.00",
            packaging_status="normalized",
        )
        item.quantity = 24
        with self.assertRaises(ValidationError):
            item.full_clean()

        item.quantity = 25
        item.save(update_fields=["quantity"])
        with self.assertRaises(IntegrityError):
            PurchaseOrderItem.objects.filter(pk=item.pk).update(quantity=24)

    def test_purchase_order_status_constraint_uses_paid_facts(self):
        with self.assertRaises(IntegrityError):
            PurchaseOrder.objects.filter(pk=self.order.pk).update(
                status="received", legacy_received=False
            )


    def test_database_constraints_reject_null_or_mismatched_canonical_fields(self):
        item = PurchaseOrderItem.objects.create(
            purchase_order=self.order, cigar=self.cigar, quantity=25, box_size=25,
            box_quantity=1, unit_price_rub='100.00', unit_price_cny='8.00',
            unit_price_rub_per_box='100.00', packaging_status='normalized',
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                PurchaseOrderItem.objects.filter(pk=item.pk).update(box_quantity=None)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                PurchaseOrderItem.objects.filter(pk=item.pk).update(
                    packaging_status='review_required', box_quantity=1,
                )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                PurchaseOrder.objects.filter(pk=self.order.pk).update(
                    legacy_received=True,
                )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                PurchaseOrder.objects.filter(pk=self.order.pk).update(
                    payment_idempotency_key='draft-payment-key',
                )
