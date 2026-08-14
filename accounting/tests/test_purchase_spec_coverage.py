"""Task 4 采购付款与到货规格回归入口。"""

from decimal import Decimal

from django.db import connection

from accounting.purchase_actions import PurchaseActionError, receive_paid_purchase_order
from accounting.tests import purchase_spec_coverage_cases as cases
from cigars.models import PurchaseBatch, PurchaseOrderItem


class PurchaseSpecTest(cases.PurchaseSpecTest):
    def test_receipt_draft_review_normalized_unrepresentable_and_existing_batch_guards(self):
        with self.assertRaises(PurchaseActionError) as ctx:
            receive_paid_purchase_order(
                purchase_order_id=self.order.pk, business_date=cases.DAY,
                operator=self.operator, idempotency_key="draft-receipt",
            )
        self.assertEqual(ctx.exception.code, "invalid_state")

        self.pay(key="review-payment")
        item = self.order.items.get()
        # 仅测试模拟迁移遗留的需复核行，不能扩大正式账务写入白名单。
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE cigars_purchaseorderitem "
                "SET packaging_status = %s, box_size = NULL, box_quantity = NULL, "
                "unit_price_rub_per_box = NULL WHERE id = %s",
                [PurchaseOrderItem.PackagingStatus.REVIEW_REQUIRED, item.pk],
            )
        with self.assertRaises(PurchaseActionError) as ctx:
            receive_paid_purchase_order(
                purchase_order_id=self.order.pk, business_date=cases.DAY,
                operator=self.operator, idempotency_key="review-receipt",
            )
        self.assertEqual(ctx.exception.code, "packaging_review_required")
        self.assertEqual(PurchaseBatch.objects.count(), 0)

        normalized = self.make_order(
            Decimal("100.00"),
            packaging=PurchaseOrderItem.PackagingStatus.NORMALIZED,
        )
        self.pay(normalized, "normalized-payment")
        receive_paid_purchase_order(
            purchase_order_id=normalized.pk, business_date=cases.DAY,
            operator=self.operator, idempotency_key="normalized-receipt",
        )
        self.assertEqual(
            PurchaseBatch.objects.filter(
                purchase_order_item__purchase_order=normalized,
            ).count(),
            1,
        )

    def test_receipt_replay_conflict_postings_and_cost_conservation(self):
        second = cases.PurchaseOrderItem.objects.create(
            purchase_order=self.order, cigar=self.cigar, quantity=20,
            box_size=10, box_quantity=2,
            unit_price_rub_per_box=Decimal("100.00"),
            packaging_status=PurchaseOrderItem.PackagingStatus.UNREPRESENTABLE,
        )
        first = self.order.items.first()
        first.unit_price_rub_per_box = Decimal("100.00")
        first.save(update_fields=["unit_price_rub_per_box"])
        self.pay(key="receipt-payment")
        batches = receive_paid_purchase_order(
            purchase_order_id=self.order.pk, business_date=cases.DAY,
            operator=self.operator, idempotency_key="receipt-key",
        )
        replay = receive_paid_purchase_order(
            purchase_order_id=self.order.pk, business_date=cases.DAY,
            operator=self.operator, idempotency_key="receipt-key",
        )
        self.assertEqual([batch.pk for batch in replay], [batch.pk for batch in batches])
        with self.assertRaises(PurchaseActionError) as ctx:
            receive_paid_purchase_order(
                purchase_order_id=self.order.pk, business_date=cases.DAY,
                operator=self.operator, idempotency_key="other-receipt",
            )
        self.assertEqual(ctx.exception.code, "idempotency_conflict")

        tx = cases.LedgerTransaction.objects.get(transaction_type="purchase_receipt")
        self.assertEqual(
            set(tx.postings.values_list("category", flat=True)),
            {
                cases.LedgerPosting.Category.PURCHASE_IN_TRANSIT,
                cases.LedgerPosting.Category.INVENTORY,
            },
        )
        paid = cases.PurchaseOrder.objects.get(pk=self.order.pk).paid_cny_cost
        self.assertEqual(
            sum((batch.original_cost_cny for batch in batches), Decimal("0.00")),
            paid,
        )
        self.assertEqual(
            sum((batch.remaining_cost_cny for batch in batches), Decimal("0.00")),
            paid,
        )
        for batch in batches:
            self.assertEqual(
                batch.original_cost_cny,
                batch.remaining_cost_cny + batch.sold_cost_cny + batch.adjustment_cost_cny,
            )
        second.refresh_from_db()
        self.assertEqual(second.actual_cost_cny, batches[1].original_cost_cny)


class PurchaseConcurrencySpecTest(cases.PurchaseConcurrencySpecTest):
    pass
