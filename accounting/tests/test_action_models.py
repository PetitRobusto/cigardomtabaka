from datetime import date, datetime, timezone
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, models, transaction
from django.test import TestCase

from accounting.models import (
    Dividend,
    Expense,
    FundAccount,
    LedgerMutationError,
    LedgerPosting,
    LedgerTransaction,
    PurchasePayment,
)
from accounting.services import PostingInput, post_transaction
from accounting.mutation_scope import ledger_mutation_scope
from cigars.models import Cigar, PurchaseOrder, PurchaseOrderItem, Supplier, User


class ActionModelMutationTest(TestCase):
    def setUp(self):
        self.operator = User.objects.create_user("action-model", is_staff=True)
        self.account = FundAccount.objects.create(
            name="动作测试人民币账户",
            currency=FundAccount.Currency.CNY,
            creation_idempotency_key="action-model-cny",
        )
        self.rub_account = FundAccount.objects.create(
            name="动作测试卢布账户",
            currency=FundAccount.Currency.RUB,
            creation_idempotency_key="action-model-rub",
        )
        self.supplier = Supplier.objects.create(name="动作测试供应商")
        self.cigar = Cigar.objects.create(
            english_name="Action Test Cigar", name="动作测试雪茄", brand="Test"
        )

    def _posted_transaction(self, key):
        return post_transaction(
            transaction_type=LedgerTransaction.TransactionType.TRANSFER,
            business_date=date(2026, 8, 14),
            operator=self.operator,
            idempotency_key=key,
            postings=[
                PostingInput(
                    account=self.account,
                    currency=FundAccount.Currency.CNY,
                    amount=Decimal("10"),
                    cny_amount=Decimal("10"),
                ),
                PostingInput(
                    category=LedgerPosting.Category.OPENING_CAPITAL,
                    currency=FundAccount.Currency.CNY,
                    amount=Decimal("-10"),
                    cny_amount=Decimal("-10"),
                ),
            ],
        )

    def _paid_order(self):
        order = PurchaseOrder.objects.create(
            supplier=self.supplier,
            operator=self.operator,
            rub_total=Decimal("100"),
        )
        with transaction.atomic(), ledger_mutation_scope(
            reason="purchase_payment", model="cigars.PurchaseOrder", operator=self.operator,
            allowed_fields={"status", "paid_cny_cost", "paid_at"},
        ):
            order.status = PurchaseOrder.Status.IN_TRANSIT
            order.paid_cny_cost = Decimal("10")
            order.paid_at = datetime(2026, 8, 14, tzinfo=timezone.utc)
            order.save(update_fields=["status", "paid_cny_cost", "paid_at"])
        return order

    def _payment(self):
        order = self._paid_order()
        payment = PurchasePayment(
            purchase_order=order, fund_account=self.rub_account,
            rub_amount=Decimal("100"), cny_cost=Decimal("10"),
            business_date=date(2026, 8, 14), operator=self.operator,
            ledger_transaction=self._posted_transaction("payment-ledger"),
            idempotency_key="payment-action", request_fingerprint="payment-fingerprint",
        )
        fields = {field.name for field in payment._meta.concrete_fields}
        with transaction.atomic(), ledger_mutation_scope(reason="purchase_payment", model="accounting.PurchasePayment", operator=self.operator, allowed_fields=fields):
            models.Model.save(payment, force_insert=True)
        return payment

    def _expense(self):
        expense = Expense(
            category=Expense.Category.SALARY, fund_account=self.account,
            original_amount=Decimal("10"), amount_cny=Decimal("10"),
            business_date=date(2026, 8, 14), operator=self.operator,
            ledger_transaction=self._posted_transaction("expense-ledger"), idempotency_key="expense-action",
        )
        fields = {field.name for field in expense._meta.concrete_fields}
        with transaction.atomic(), ledger_mutation_scope(reason="expense_post", model="accounting.Expense", operator=self.operator, allowed_fields=fields):
            models.Model.save(expense, force_insert=True)
        return expense

    def _posted_dividend(self):
        ledger_transaction = self._posted_transaction("dividend-ledger")
        dividend = Dividend(
            status=Dividend.Status.POSTED, total_cny=Decimal("10"),
            partner_a_amount_cny=Decimal("5"), partner_b_amount_cny=Decimal("5"),
            partner_a_account=self.account, partner_b_account=self.rub_account,
            business_date=date(2026, 8, 14), created_by=self.operator,
            confirmed_by=self.operator, ledger_transaction=ledger_transaction,
        )
        fields = {field.name for field in dividend._meta.concrete_fields}
        with transaction.atomic(), ledger_mutation_scope(
            reason="dividend_confirm", model="accounting.Dividend", operator=self.operator,
            allowed_fields={"status", "ledger_transaction", "confirmed_by", "version", "confirm_idempotency_key", "confirm_request_fingerprint"},
        ):
            models.Model.save(dividend, force_insert=True)
        return dividend

    def test_posted_facts_reject_instance_save_and_delete(self):
        records = [self._payment(), self._expense(), self._posted_dividend()]
        for record in records:
            with self.subTest(model=type(record).__name__):
                with self.assertRaises(LedgerMutationError):
                    record.save()
                with self.assertRaises(LedgerMutationError):
                    record.delete()

    def test_posted_facts_reject_queryset_update_delete_bulk_update_and_existing_bulk_create(self):
        payment = self._payment()
        expense = self._expense()
        dividend = self._posted_dividend()
        for record in (payment, expense, dividend):
            model = type(record)
            with self.subTest(model=model.__name__, operation="update"):
                with self.assertRaises(LedgerMutationError):
                    model.objects.filter(pk=record.pk).update(note="bypass")
            with self.subTest(model=model.__name__, operation="delete"):
                with self.assertRaises(LedgerMutationError):
                    model.objects.filter(pk=record.pk).delete()
            with self.subTest(model=model.__name__, operation="bulk_update"):
                with self.assertRaises(LedgerMutationError):
                    model.objects.bulk_update([record], ["business_date"])
            with self.subTest(model=model.__name__, operation="bulk_create"):
                with self.assertRaises(LedgerMutationError):
                    model.objects.bulk_create([record])

    def test_purchase_order_and_item_final_facts_reject_ordinary_orm_paths(self):
        order = self._paid_order()
        item = PurchaseOrderItem(
            purchase_order=order, cigar=self.cigar, quantity=25, box_size=25, box_quantity=1,
            unit_price_rub_per_box=Decimal("100"), packaging_status="normalized",
        )
        with transaction.atomic(), ledger_mutation_scope(reason="purchase_receipt", model="cigars.PurchaseOrderItem", operator=self.operator, allowed_fields={"actual_cost_cny"}):
            models.Model.save(item, force_insert=True)
        order.note = "bypass"
        item.actual_cost_cny = Decimal("11")
        for operation in (
            lambda: order.save(update_fields=["note"]),
            lambda: order.delete(),
            lambda: PurchaseOrder.objects.filter(pk=order.pk).update(note="bypass"),
            lambda: PurchaseOrder.objects.filter(pk=order.pk).delete(),
            lambda: PurchaseOrder.objects.bulk_update([order], ["note"]),
            lambda: PurchaseOrder.objects.bulk_create([order]),
            lambda: item.save(update_fields=["actual_cost_cny"]),
            lambda: item.delete(),
            lambda: PurchaseOrderItem.objects.filter(pk=item.pk).update(actual_cost_cny=Decimal("11")),
            lambda: PurchaseOrderItem.objects.filter(pk=item.pk).delete(),
            lambda: PurchaseOrderItem.objects.bulk_update([item], ["actual_cost_cny"]),
            lambda: PurchaseOrderItem.objects.bulk_create([item]),
        ):
            with self.subTest(operation=operation), self.assertRaises(LedgerMutationError):
                operation()

    def test_amounts_are_nonnegative_at_database_boundary(self):
        payment = PurchasePayment(
            purchase_order=self._paid_order(), fund_account=self.rub_account,
            rub_amount=Decimal("-1"), cny_cost=Decimal("1"), business_date=date(2026, 8, 14),
            operator=self.operator, ledger_transaction=self._posted_transaction("negative-payment"),
            idempotency_key="negative-payment", request_fingerprint="negative",
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic(), ledger_mutation_scope(reason="purchase_payment", model="accounting.PurchasePayment", operator=self.operator, allowed_fields={field.name for field in payment._meta.concrete_fields}):
                models.Model.save(payment, force_insert=True)

        expense = Expense(
            category=Expense.Category.OTHER, fund_account=self.account,
            original_amount=Decimal("1"), amount_cny=Decimal("-1"), business_date=date(2026, 8, 14),
            operator=self.operator, ledger_transaction=self._posted_transaction("negative-expense"), idempotency_key="negative-expense",
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic(), ledger_mutation_scope(reason="expense_post", model="accounting.Expense", operator=self.operator, allowed_fields={field.name for field in expense._meta.concrete_fields}):
                models.Model.save(expense, force_insert=True)

        dividend = Dividend(total_cny=Decimal("1"), partner_a_amount_cny=Decimal("-1"), partner_b_amount_cny=Decimal("2"), business_date=date(2026, 8, 14))
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                models.Model.save(dividend, force_insert=True)
