from datetime import date
from decimal import Decimal
from threading import Thread
from unittest.mock import patch

from django.db import close_old_connections
from django.test import TestCase, TransactionTestCase

from accounting.models import (
    Day1Initialization, FundAccount, LedgerPosting, LedgerTransaction,
    PurchasePayment,
)
from accounting.purchase_actions import (
    PurchaseActionError, pay_purchase_order, receive_paid_purchase_order,
)
from accounting.services import record_opening_balance
from cigars.models import (
    Brand, Cigar, PurchaseBatch, PurchaseOrder, PurchaseOrderItem,
    SalesOrder, StockMovement, Supplier, User,
)
from cigars.sales_accounting import ship_sales_order
from cigars.services import (
    AgentContext, OrderServiceError, confirm_sales_order,
    create_sales_order_draft, receive_purchase_order, split_purchase_batch_box,
)


DAY = date(2026, 8, 14)
CUTOVER = date(2026, 8, 10)


class PurchaseSpecMixin:
    def make_fixture(self):
        self.operator = User.objects.create_user(
            username=f"purchase-spec-{User.objects.count()}", password="x", is_staff=True,
        )
        Day1Initialization.objects.create(
            singleton_key="company",
            status=Day1Initialization.Status.COMPLETED,
            business_date=CUTOVER, completed_by=self.operator,
        )
        self.rub = FundAccount.objects.create(
            name=f"测试卢布-{self.operator.pk}", currency=FundAccount.Currency.RUB,
            creation_idempotency_key=f"rub-{self.operator.pk}", custodian=self.operator,
        )
        record_opening_balance(
            self.rub, Decimal("1000.00"), Decimal("120.00"),
            LedgerPosting.Category.OPENING_CAPITAL, CUTOVER,
            self.operator, f"opening-rub-{self.operator.pk}",
        )
        brand = Brand.objects.create(english_name=f"Spec Brand {self.operator.pk}", name="规格品牌")
        self.cigar = Cigar.objects.create(
            brand=brand.english_name, english_name=f"Spec Cigar {self.operator.pk}", name="规格雪茄",
        )
        self.order = self.make_order(Decimal("300.00"))

    def make_order(self, amount=Decimal("300.00"), *, packaging=None):
        supplier = Supplier.objects.create(name=f"Spec Supplier {PurchaseOrder.objects.count()}")
        order = PurchaseOrder.objects.create(
            supplier=supplier, rub_total=amount, operator=self.operator,
            draft_business_date=DAY,
        )
        PurchaseOrderItem.objects.create(
            purchase_order=order, cigar=self.cigar, quantity=25,
            box_size=25, box_quantity=1, unit_price_rub_per_box=amount,
            packaging_status=packaging or PurchaseOrderItem.PackagingStatus.UNREPRESENTABLE,
        )
        return order

    def pay(self, order=None, key="payment"):
        return pay_purchase_order(
            purchase_order_id=(order or self.order).pk, rub_account_id=self.rub.pk,
            business_date=DAY, operator=self.operator, idempotency_key=key,
        )


class PurchaseSpecTest(PurchaseSpecMixin, TestCase):
    def setUp(self):
        self.make_fixture()

    def test_payment_currency_and_balance_guards_are_side_effect_free(self):
        before = (
            self.order.status, PurchasePayment.objects.count(),
            LedgerTransaction.objects.filter(transaction_type="purchase_payment").count(),
        )
        for currency in (FundAccount.Currency.CNY, FundAccount.Currency.USDT):
            account = FundAccount.objects.create(
                name=f"wrong-{currency}", currency=currency,
                creation_idempotency_key=f"wrong-{currency}", custodian=self.operator,
            )
            with self.assertRaises(PurchaseActionError) as ctx:
                pay_purchase_order(
                    purchase_order_id=self.order.pk, rub_account_id=account.pk,
                    business_date=DAY, operator=self.operator, idempotency_key=f"wrong-{currency}",
                )
            self.assertEqual(ctx.exception.code, "invalid_account_currency")
        poor = FundAccount.objects.create(
            name="poor-rub", currency=FundAccount.Currency.RUB,
            creation_idempotency_key="poor-rub", custodian=self.operator,
        )
        record_opening_balance(poor, Decimal("100.00"), Decimal("12.00"),
                               LedgerPosting.Category.OPENING_CAPITAL, CUTOVER,
                               self.operator, "poor-opening")
        with self.assertRaises(PurchaseActionError) as ctx:
            pay_purchase_order(
                purchase_order_id=self.order.pk, rub_account_id=poor.pk,
                business_date=DAY, operator=self.operator, idempotency_key="poor-payment",
            )
        self.assertEqual(ctx.exception.code, "insufficient_balance")
        self.order.refresh_from_db()
        self.assertEqual((self.order.status, PurchasePayment.objects.count(),
                          LedgerTransaction.objects.filter(transaction_type="purchase_payment").count()), before)

    def test_payment_key_fingerprint_conflicts_and_in_transit_replay(self):
        payment = self.pay(key="fingerprint")
        other_account = FundAccount.objects.create(
            name="other-rub", currency=FundAccount.Currency.RUB,
            creation_idempotency_key="other-rub", custodian=self.operator,
        )
        other_operator = User.objects.create_user("fingerprint-other", password="x", is_staff=True)
        order_with_other_amount = self.make_order(Decimal("200.00"))
        variants = (
            {"rub_account_id": other_account.pk},
            {"business_date": date(2026, 8, 15)},
            {"operator": other_operator},
            {"purchase_order_id": order_with_other_amount.pk},
        )
        for variant in variants:
            kwargs = dict(purchase_order_id=self.order.pk, rub_account_id=self.rub.pk,
                          business_date=DAY, operator=self.operator, idempotency_key="fingerprint")
            kwargs.update(variant)
            with self.subTest(variant=variant), self.assertRaises(PurchaseActionError) as ctx:
                pay_purchase_order(**kwargs)
            self.assertEqual(ctx.exception.code, "idempotency_conflict")
        replay = self.pay(key="fingerprint")
        self.assertEqual(replay.pk, payment.pk)
        self.assertEqual(PurchasePayment.objects.count(), 1)

    def test_injected_payment_and_receipt_failures_roll_back_and_retry(self):
        with patch("accounting.purchase_actions._post_transaction_once", side_effect=RuntimeError("injected")):
            with self.assertRaises(RuntimeError):
                self.pay(key="rollback-payment")
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, PurchaseOrder.Status.DRAFT)
        self.assertEqual(PurchasePayment.objects.count(), 0)
        self.assertEqual(LedgerTransaction.objects.filter(transaction_type="purchase_payment").count(), 0)
        self.pay(key="rollback-payment")
        before = (PurchaseBatch.objects.count(), StockMovement.objects.count(), LedgerPosting.objects.count())
        with patch("accounting.purchase_actions._post_transaction_once", side_effect=RuntimeError("injected receipt")):
            with self.assertRaises(RuntimeError):
                receive_paid_purchase_order(purchase_order_id=self.order.pk, business_date=DAY,
                                             operator=self.operator, idempotency_key="rollback-receipt")
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, PurchaseOrder.Status.IN_TRANSIT)
        self.assertEqual((PurchaseBatch.objects.count(), StockMovement.objects.count(), LedgerPosting.objects.count()), before)
        receive_paid_purchase_order(purchase_order_id=self.order.pk, business_date=DAY,
                                    operator=self.operator, idempotency_key="rollback-receipt")

    def test_receipt_draft_review_normalized_unrepresentable_and_existing_batch_guards(self):
        with self.assertRaises(PurchaseActionError) as ctx:
            receive_paid_purchase_order(purchase_order_id=self.order.pk, business_date=DAY,
                                         operator=self.operator, idempotency_key="draft-receipt")
        self.assertEqual(ctx.exception.code, "invalid_state")
        item = self.order.items.get()
        item.packaging_status = PurchaseOrderItem.PackagingStatus.REVIEW_REQUIRED
        item.box_size = item.box_quantity = item.unit_price_rub_per_box = None
        item.save(update_fields=["packaging_status", "box_size", "box_quantity", "unit_price_rub_per_box"])
        with self.assertRaises(PurchaseActionError) as ctx:
            self.pay(key="review-payment")
        self.assertEqual(ctx.exception.code, "packaging_review_required")
        self.assertEqual(PurchaseBatch.objects.count(), 0)

        normalized = self.make_order(Decimal("100.00"), packaging=PurchaseOrderItem.PackagingStatus.NORMALIZED)
        self.pay(normalized, "normalized-payment")
        receive_paid_purchase_order(purchase_order_id=normalized.pk, business_date=DAY,
                                    operator=self.operator, idempotency_key="normalized-receipt")
        self.assertEqual(PurchaseBatch.objects.filter(purchase_order_item__purchase_order=normalized).count(), 1)

    def test_receipt_replay_conflict_postings_and_cost_conservation(self):
        second = PurchaseOrderItem.objects.create(
            purchase_order=self.order, cigar=self.cigar, quantity=20, box_size=10,
            box_quantity=2, unit_price_rub_per_box=Decimal("100.00"),
            packaging_status=PurchaseOrderItem.PackagingStatus.UNREPRESENTABLE,
        )
        first = self.order.items.first()
        first.unit_price_rub_per_box = Decimal("100.00")
        first.save(update_fields=["unit_price_rub_per_box"])
        self.pay(key="receipt-payment")
        batches = receive_paid_purchase_order(purchase_order_id=self.order.pk, business_date=DAY,
                                               operator=self.operator, idempotency_key="receipt-key")
        replay = receive_paid_purchase_order(purchase_order_id=self.order.pk, business_date=DAY,
                                              operator=self.operator, idempotency_key="receipt-key")
        self.assertEqual([batch.pk for batch in replay], [batch.pk for batch in batches])
        with self.assertRaises(PurchaseActionError) as ctx:
            receive_paid_purchase_order(purchase_order_id=self.order.pk, business_date=DAY,
                                         operator=self.operator, idempotency_key="other-receipt")
        self.assertEqual(ctx.exception.code, "idempotency_conflict")
        tx = LedgerTransaction.objects.get(transaction_type="purchase_receipt")
        self.assertEqual(set(tx.postings.values_list("category", flat=True)),
                         {LedgerPosting.Category.PURCHASE_IN_TRANSIT, LedgerPosting.Category.INVENTORY})
        paid = PurchaseOrder.objects.get(pk=self.order.pk).paid_cny_cost
        self.assertEqual(sum((batch.original_cost_cny for batch in batches), Decimal("0.00")), paid)
        self.assertEqual(sum((batch.remaining_cost_cny for batch in batches), Decimal("0.00")), paid)
        for batch in batches:
            self.assertEqual(batch.original_cost_cny,
                             batch.remaining_cost_cny + batch.sold_cost_cny + batch.adjustment_cost_cny)
        second.refresh_from_db()
        self.assertEqual(second.actual_cost_cny, batches[1].original_cost_cny)

    def test_legacy_receive_supports_agent_context_replay_and_conflict(self):
        with self.assertRaises(OrderServiceError):
            receive_purchase_order(purchase_order_id=self.order.pk, operator=self.operator,
                                    business_date=DAY, idempotency_key="legacy-draft")
        self.pay(key="legacy-payment")
        context = AgentContext(agent_name="legacy", agent_run_id="run", agent_request_id="request",
                               command_name="legacy_receive", idempotency_key="legacy-receipt")
        batches = receive_purchase_order(purchase_order_id=self.order.pk, operator=self.operator,
                                          business_date=DAY, agent_context=context)
        replay = receive_purchase_order(purchase_order_id=self.order.pk, operator=self.operator,
                                         business_date=DAY, agent_context=context)
        self.assertEqual([batch.pk for batch in replay], [batch.pk for batch in batches])
        movement = StockMovement.objects.get(movement_type=StockMovement.MovementType.RECEIVE)
        self.assertEqual((movement.command_name, movement.idempotency_key, movement.agent_run_id),
                         ("legacy_receive", "legacy-receipt", "run"))
        with self.assertRaises(OrderServiceError):
            receive_purchase_order(purchase_order_id=self.order.pk, operator=self.operator,
                                   business_date=DAY, idempotency_key="legacy-other")

    def test_split_box_and_sales_fifo_leave_no_cost_tail(self):
        self.pay(key="fifo-payment")
        receive_paid_purchase_order(purchase_order_id=self.order.pk, business_date=DAY,
                                    operator=self.operator, idempotency_key="fifo-receipt")
        batch = PurchaseBatch.objects.get(purchase_order_item__purchase_order=self.order)
        pool = batch.remaining_cost_cny
        split_purchase_batch_box(batch_id=batch.pk, operator=self.operator,
                                 agent_context=AgentContext(command_name="split", idempotency_key="split-key"))
        batch.refresh_from_db()
        self.assertEqual(batch.remaining_cost_cny, pool)
        draft = create_sales_order_draft(
            items=[{"cigar_id": self.cigar.pk, "quantity": 25, "unit_price": "2.00"}],
            operator=self.operator, agent_context=AgentContext(command_name="draft", idempotency_key="sales-draft"),
        )
        confirm_sales_order(sales_order_id=draft.pk, operator=self.operator,
                            agent_context=AgentContext(command_name="confirm", idempotency_key="sales-confirm"))
        ship_sales_order(order_id=draft.pk, business_date=DAY, operator=self.operator, idempotency_key="sales-ship")
        batch.refresh_from_db()
        self.assertEqual(batch.remaining, 0)
        self.assertEqual(batch.original_cost_cny,
                         batch.remaining_cost_cny + batch.sold_cost_cny + batch.adjustment_cost_cny)
        self.assertEqual(batch.remaining_cost_cny, Decimal("0.00"))


class PurchaseConcurrencySpecTest(PurchaseSpecMixin, TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.make_fixture()

    def run_threads(self, action):
        outcomes = []
        def worker():
            close_old_connections()
            try:
                outcomes.append(("ok", action()))
            except Exception as error:  # concurrent loser is a business conflict
                outcomes.append(("error", getattr(error, "code", str(error))))
            finally:
                close_old_connections()
        threads = [Thread(target=worker) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
        return outcomes

    def test_payment_same_key_is_single_fact_and_different_key_does_not_double_pay(self):
        outcomes = self.run_threads(lambda: self.pay(key="concurrent-payment"))
        self.assertEqual(len(outcomes), 2)
        self.assertEqual(PurchasePayment.objects.filter(idempotency_key="concurrent-payment").count(), 1)
        self.assertEqual(LedgerTransaction.objects.filter(idempotency_key="concurrent-payment").count(), 1)
        self.assertEqual(sum(result == "ok" for result, _ in outcomes), 2)

        self.order = self.make_order(Decimal("100.00"))
        outcomes = self.run_threads(lambda: self.pay(self.order, "different-payment-a"))
        # One transaction wins; the other sees IN_TRANSIT and cannot pay again.
        self.assertEqual(PurchasePayment.objects.filter(purchase_order=self.order).count(), 1)
        self.assertEqual(LedgerTransaction.objects.filter(source_id=str(self.order.pk), transaction_type="purchase_payment").count(), 1)

    def test_receipt_same_key_is_single_batch_set_and_different_key_conflicts(self):
        self.pay(key="receipt-concurrent-payment")
        outcomes = self.run_threads(lambda: receive_paid_purchase_order(
            purchase_order_id=self.order.pk, business_date=DAY, operator=self.operator,
            idempotency_key="concurrent-receipt",
        ))
        self.assertEqual(len(outcomes), 2)
        self.assertEqual(PurchaseBatch.objects.filter(purchase_order_item__purchase_order=self.order).count(), 1)
        self.assertEqual(LedgerTransaction.objects.filter(idempotency_key="concurrent-receipt").count(), 1)
        self.assertEqual(sum(result == "ok" for result, _ in outcomes), 2)
