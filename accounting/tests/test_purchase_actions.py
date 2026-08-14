from datetime import date
from decimal import Decimal

from django.test import TestCase

from accounting.models import Day1Initialization, FundAccount, LedgerPosting, LedgerTransaction, PurchasePayment
from accounting.purchase_actions import PurchaseActionError, pay_purchase_order, receive_paid_purchase_order
from accounting.services import record_opening_balance
from cigars.models import Brand, Cigar, PurchaseOrder, PurchaseOrderItem, Supplier, User


class PurchasePaymentTest(TestCase):
    def setUp(self):
        self.operator = User.objects.create_user(
            username="purchase-operator", password="x", is_staff=True,
        )
        Day1Initialization.objects.create(
            singleton_key="company", status=Day1Initialization.Status.COMPLETED,
            business_date=date(2026, 8, 10), completed_by=self.operator,
        )
        self.rub = FundAccount.objects.create(
            name="测试卢布", currency=FundAccount.Currency.RUB,
            creation_idempotency_key="fund-rub-1", custodian=self.operator,
        )
        record_opening_balance(
            self.rub, Decimal("1000.00"), Decimal("120.00"),
            LedgerPosting.Category.OPENING_CAPITAL, date(2026, 8, 10),
            self.operator, "opening-rub-1",
        )
        brand = Brand.objects.create(english_name="Test Brand", name="测试品牌")
        self.cigar = Cigar.objects.create(
            brand=brand.english_name, english_name="Test Cigar", name="测试雪茄",
        )
        supplier = Supplier.objects.create(name="测试供应商")
        self.order = PurchaseOrder.objects.create(
            supplier=supplier, rub_total=Decimal("300.00"), operator=self.operator,
            draft_business_date=date(2026, 8, 14),
        )
        PurchaseOrderItem.objects.create(
            purchase_order=self.order, cigar=self.cigar, quantity=25,
            box_size=25, box_quantity=1, unit_price_rub_per_box=Decimal("300.00"),
            packaging_status=PurchaseOrderItem.PackagingStatus.UNREPRESENTABLE,
        )

    def test_payment_uses_canonical_rub_total_and_moving_average(self):
        payment = pay_purchase_order(
            purchase_order_id=self.order.id, rub_account_id=self.rub.id,
            business_date=date(2026, 8, 14), operator=self.operator,
            idempotency_key="purchase-payment-1",
        )

        self.assertIsInstance(payment, PurchasePayment)
        self.assertEqual(payment.rub_amount, Decimal("300.00"))
        self.assertEqual(payment.cny_cost, Decimal("36.00"))
        self.assertEqual(PurchaseOrder.objects.get(pk=self.order.pk).status, PurchaseOrder.Status.IN_TRANSIT)
        self.assertEqual(
            LedgerTransaction.objects.filter(
                transaction_type=LedgerTransaction.TransactionType.PURCHASE_PAYMENT,
            ).count(), 1,
        )


    def test_receipt_allocates_canonical_tail_and_creates_batches(self):
        first = self.order.items.get()
        first.unit_price_rub_per_box = Decimal("100.00")
        first.save(update_fields=["unit_price_rub_per_box"])
        second = PurchaseOrderItem.objects.create(
            purchase_order=self.order, cigar=self.cigar, quantity=20,
            box_size=10, box_quantity=2, unit_price_rub_per_box=Decimal("100.00"),
            packaging_status=PurchaseOrderItem.PackagingStatus.UNREPRESENTABLE,
        )
        receipt_account = FundAccount.objects.create(
            name="测试卢布到货", currency=FundAccount.Currency.RUB,
            creation_idempotency_key="fund-rub-receipt", custodian=self.operator,
        )
        record_opening_balance(
            receipt_account, Decimal("300.00"), Decimal("100.00"),
            LedgerPosting.Category.OPENING_CAPITAL, date(2026, 8, 10),
            self.operator, "opening-rub-receipt",
        )
        payment = pay_purchase_order(
            purchase_order_id=self.order.id, rub_account_id=receipt_account.id,
            business_date=date(2026, 8, 14), operator=self.operator,
            idempotency_key="purchase-payment-receipt",
        )
        batches = receive_paid_purchase_order(
            purchase_order_id=self.order.id, business_date=date(2026, 8, 14),
            operator=self.operator, idempotency_key="purchase-receipt-1", note="到货",
        )
        self.assertEqual(payment.cny_cost, Decimal("100.00"))
        self.assertEqual([b.quantity for b in batches], [25, 20])
        self.assertEqual([b.original_cost_cny for b in batches], [Decimal("33.33"), Decimal("66.67")])
        self.assertEqual(sum((b.remaining_cost_cny for b in batches), Decimal("0.00")), Decimal("100.00"))
        receipt_tx = LedgerTransaction.objects.get(
            transaction_type=LedgerTransaction.TransactionType.PURCHASE_RECEIPT,
        )
        self.assertEqual(
            set(receipt_tx.postings.values_list("category", flat=True)),
            {LedgerPosting.Category.PURCHASE_IN_TRANSIT, LedgerPosting.Category.INVENTORY},
        )


    def test_payment_replay_and_conflict_are_stable(self):
        payment = pay_purchase_order(
            purchase_order_id=self.order.id, rub_account_id=self.rub.id,
            business_date=date(2026, 8, 14), operator=self.operator,
            idempotency_key="purchase-payment-replay",
        )
        replay = pay_purchase_order(
            purchase_order_id=self.order.id, rub_account_id=self.rub.id,
            business_date=date(2026, 8, 14), operator=self.operator,
            idempotency_key="purchase-payment-replay",
        )
        self.assertEqual(replay.pk, payment.pk)
        other = User.objects.create_user(username="other-operator", password="x", is_staff=True)
        with self.assertRaises(PurchaseActionError) as error:
            pay_purchase_order(
                purchase_order_id=self.order.id, rub_account_id=self.rub.id,
                business_date=date(2026, 8, 15), operator=other,
                idempotency_key="purchase-payment-replay",
            )
        self.assertEqual(error.exception.code, "idempotency_conflict")

    def test_receipt_replay_and_other_key_conflict(self):
        first = self.order.items.get()
        first.unit_price_rub_per_box = Decimal("100.00")
        first.save(update_fields=["unit_price_rub_per_box"])
        second = PurchaseOrderItem.objects.create(
            purchase_order=self.order, cigar=self.cigar, quantity=20,
            box_size=10, box_quantity=2, unit_price_rub_per_box=Decimal("100.00"),
            packaging_status=PurchaseOrderItem.PackagingStatus.UNREPRESENTABLE,
        )
        account = FundAccount.objects.create(
            name="测试卢布到货重放", currency=FundAccount.Currency.RUB,
            creation_idempotency_key="fund-rub-receipt-replay", custodian=self.operator,
        )
        record_opening_balance(account, Decimal("300.00"), Decimal("100.00"),
                               LedgerPosting.Category.OPENING_CAPITAL, date(2026, 8, 10),
                               self.operator, "opening-rub-receipt-replay")
        pay_purchase_order(purchase_order_id=self.order.id, rub_account_id=account.id,
                           business_date=date(2026, 8, 14), operator=self.operator,
                           idempotency_key="payment-for-receipt-replay")
        batches = receive_paid_purchase_order(
            purchase_order_id=self.order.id, business_date=date(2026, 8, 14),
            operator=self.operator, idempotency_key="receipt-replay",
        )
        replay = receive_paid_purchase_order(
            purchase_order_id=self.order.id, business_date=date(2026, 8, 14),
            operator=self.operator, idempotency_key="receipt-replay",
        )
        self.assertEqual([b.pk for b in replay], [b.pk for b in batches])
        with self.assertRaises(PurchaseActionError) as error:
            receive_paid_purchase_order(
                purchase_order_id=self.order.id, business_date=date(2026, 8, 14),
                operator=self.operator, idempotency_key="receipt-other",
            )
        self.assertEqual(error.exception.code, "idempotency_conflict")
