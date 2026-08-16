from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.db import connection, models
from django.test import TestCase

from accounting.models import Day1Initialization, FundAccount, LedgerPosting, LedgerTransaction, PurchasePayment
from accounting.purchase_actions import (
    PurchaseActionError,
    pay_purchase_order,
    receive_paid_purchase_order,
    reverse_received_purchase_order,
)
from accounting.services import record_opening_balance
from accounting.services import LedgerError
from cigars.models import Brand, Cigar, PurchaseBatch, PurchaseOrder, PurchaseOrderItem, StockMovement, Supplier, User
from cigars.inventory_audit import audit_inventory
from cigars.audit import AgentContext
from cigars.inventory import split_box
from cigars.tests.inventory_fixtures import force_inventory_update


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

    def test_payment_replay_rejects_tampered_posting(self):
        payment = pay_purchase_order(
            purchase_order_id=self.order.id, rub_account_id=self.rub.id,
            business_date=date(2026, 8, 14), operator=self.operator,
            idempotency_key="purchase-payment-tampered-posting",
        )
        posting_id = payment.ledger_transaction.postings.order_by('id').first().pk
        with connection.cursor() as cursor:
            cursor.execute('DELETE FROM accounting_ledgerposting WHERE id = %s', [posting_id])

        with self.assertRaises(PurchaseActionError) as error:
            pay_purchase_order(
                purchase_order_id=self.order.id, rub_account_id=self.rub.id,
                business_date=date(2026, 8, 14), operator=self.operator,
                idempotency_key="purchase-payment-tampered-posting",
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
            note="仓库签收",
        )
        replay = receive_paid_purchase_order(
            purchase_order_id=self.order.id, business_date=date(2026, 8, 14),
            operator=self.operator, idempotency_key="receipt-replay",
            note="仓库签收",
        )
        self.assertEqual([b.pk for b in replay], [b.pk for b in batches])
        with self.assertRaises(PurchaseActionError) as note_error:
            receive_paid_purchase_order(
                purchase_order_id=self.order.id, business_date=date(2026, 8, 14),
                operator=self.operator, idempotency_key="receipt-replay",
                note="签收备注被修改",
            )
        self.assertEqual(note_error.exception.code, "idempotency_conflict")
        with self.assertRaises(PurchaseActionError) as error:
            receive_paid_purchase_order(
                purchase_order_id=self.order.id, business_date=date(2026, 8, 14),
                operator=self.operator, idempotency_key="receipt-other",
            )
        self.assertEqual(error.exception.code, "idempotency_conflict")

    def test_receipt_can_be_reversed_and_received_again_with_new_key(self):
        """未使用到货可整单撤销，并在保留历史后重新到货。"""
        pay_purchase_order(
            purchase_order_id=self.order.id,
            rub_account_id=self.rub.id,
            business_date=date(2026, 8, 14),
            operator=self.operator,
            idempotency_key="payment-for-receipt-reversal",
        )
        original_batches = receive_paid_purchase_order(
            purchase_order_id=self.order.id,
            business_date=date(2026, 8, 14),
            operator=self.operator,
            idempotency_key="receipt-before-reversal",
            note="首次到货",
        )

        reversed_batches = reverse_received_purchase_order(
            purchase_order_id=self.order.id,
            business_date=date(2026, 8, 15),
            operator=self.operator,
            idempotency_key="reverse-receipt-1",
            reason="仓库确认录错",
        )
        replayed = reverse_received_purchase_order(
            purchase_order_id=self.order.id,
            business_date=date(2026, 8, 15),
            operator=self.operator,
            idempotency_key="reverse-receipt-1",
            reason="仓库确认录错",
        )

        self.assertEqual([batch.pk for batch in reversed_batches], [original_batches[0].pk])
        self.assertEqual([batch.pk for batch in replayed], [original_batches[0].pk])
        original = PurchaseBatch.objects.get(pk=original_batches[0].pk)
        self.assertEqual(original.remaining, 0)
        self.assertEqual(original.reversed_quantity, original.quantity)
        self.assertEqual(original.reversed_cost_cny, original.original_cost_cny)
        self.assertIsNotNone(original.reversed_at)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, PurchaseOrder.Status.IN_TRANSIT)
        self.assertIsNone(self.order.arrival_idempotency_key)
        item = self.order.items.get()
        self.assertEqual(item.actual_cost_cny, original.original_cost_cny)
        historical_receipt = receive_paid_purchase_order(
            purchase_order_id=self.order.id,
            business_date=date(2026, 8, 14),
            operator=self.operator,
            idempotency_key='receipt-before-reversal',
            note='首次到货',
        )
        self.assertEqual(
            [batch.pk for batch in historical_receipt],
            [original.pk],
        )

        new_batches = receive_paid_purchase_order(
            purchase_order_id=self.order.id,
            business_date=date(2026, 8, 16),
            operator=self.operator,
            idempotency_key="receipt-after-reversal",
            note="重新到货",
        )
        replayed_new = receive_paid_purchase_order(
            purchase_order_id=self.order.id,
            business_date=date(2026, 8, 16),
            operator=self.operator,
            idempotency_key="receipt-after-reversal",
            note="重新到货",
        )
        self.assertNotEqual(new_batches[0].pk, original.pk)
        self.assertEqual([batch.pk for batch in replayed_new], [new_batches[0].pk])
        self.assertTrue(audit_inventory().ok)

        reverse_received_purchase_order(
            purchase_order_id=self.order.id,
            business_date=date(2026, 8, 16),
            operator=self.operator,
            idempotency_key='reverse-receipt-2',
            reason='第二次到货仍录错',
        )
        replayed_first_cycle = reverse_received_purchase_order(
            purchase_order_id=self.order.id,
            business_date=date(2026, 8, 15),
            operator=self.operator,
            idempotency_key='reverse-receipt-1',
            reason='仓库确认录错',
        )
        self.assertEqual(
            [batch.pk for batch in replayed_first_cycle],
            [original.pk],
        )

    def test_receipt_reversal_rolls_back_inventory_when_ledger_fails(self):
        """到货撤销账务失败时，采购单和批次必须保持已到货。"""
        pay_purchase_order(
            purchase_order_id=self.order.id,
            rub_account_id=self.rub.id,
            business_date=date(2026, 8, 14),
            operator=self.operator,
            idempotency_key='payment-before-failed-reversal',
        )
        batch = receive_paid_purchase_order(
            purchase_order_id=self.order.id,
            business_date=date(2026, 8, 14),
            operator=self.operator,
            idempotency_key='receipt-before-failed-reversal',
        )[0]

        with patch(
            'accounting.purchase_actions.reverse_ledger_transaction',
            side_effect=LedgerError('冲正失败'),
        ):
            with self.assertRaises(LedgerError):
                reverse_received_purchase_order(
                    purchase_order_id=self.order.id,
                    business_date=date(2026, 8, 15),
                    operator=self.operator,
                    idempotency_key='failed-receipt-reversal',
                    reason='测试回滚',
                )

        self.order.refresh_from_db()
        batch.refresh_from_db()
        self.assertEqual(self.order.status, PurchaseOrder.Status.RECEIVED)
        self.assertEqual(batch.remaining, batch.quantity)
        self.assertIsNone(batch.reversed_at)
        self.assertFalse(LedgerTransaction.objects.filter(
            idempotency_key='failed-receipt-reversal',
        ).exists())

    def test_receipt_reversal_is_blocked_after_batch_is_used(self):
        """到货批次一旦拆盒或参与库存动作，就不能撤销原到货。"""
        pay_purchase_order(
            purchase_order_id=self.order.id,
            rub_account_id=self.rub.id,
            business_date=date(2026, 8, 14),
            operator=self.operator,
            idempotency_key='payment-before-used-receipt',
        )
        batch = receive_paid_purchase_order(
            purchase_order_id=self.order.id,
            business_date=date(2026, 8, 14),
            operator=self.operator,
            idempotency_key='receipt-before-split',
        )[0]
        split_box(
            batch_id=batch.pk,
            operator=self.operator,
            context=AgentContext(command_name='split-received-box'),
        )

        with self.assertRaises(PurchaseActionError) as raised:
            reverse_received_purchase_order(
                purchase_order_id=self.order.id,
                business_date=date(2026, 8, 15),
                operator=self.operator,
                idempotency_key='blocked-used-receipt-reversal',
                reason='不能撤销已拆盒批次',
            )

        self.assertEqual(raised.exception.code, 'receipt_already_used')
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, PurchaseOrder.Status.RECEIVED)

    def test_receipt_reversal_rejects_tampered_receive_movement(self):
        """原到货流水语义损坏时不得继续创建撤销流水。"""
        pay_purchase_order(
            purchase_order_id=self.order.id,
            rub_account_id=self.rub.id,
            business_date=date(2026, 8, 14),
            operator=self.operator,
            idempotency_key='payment-before-tampered-receipt',
        )
        batch = receive_paid_purchase_order(
            purchase_order_id=self.order.id,
            business_date=date(2026, 8, 14),
            operator=self.operator,
            idempotency_key='tampered-receipt',
        )[0]
        movement = StockMovement.objects.get(purchase_batch=batch)
        force_inventory_update(
            StockMovement.objects.filter(pk=movement.pk),
            movement_type=StockMovement.MovementType.SPLIT_BOX,
        )

        with self.assertRaises(PurchaseActionError) as raised:
            reverse_received_purchase_order(
                purchase_order_id=self.order.id,
                business_date=date(2026, 8, 15),
                operator=self.operator,
                idempotency_key='reject-tampered-receipt',
                reason='流水已经损坏',
            )

        self.assertEqual(raised.exception.code, 'receipt_already_used')

    def test_inventory_audit_reports_tampered_receipt_source(self):
        """采购到货交易来源被篡改时，库存审计必须报警。"""
        pay_purchase_order(
            purchase_order_id=self.order.pk, rub_account_id=self.rub.pk,
            business_date=date(2026, 8, 14), operator=self.operator,
            idempotency_key='payment-before-receipt-source-audit',
        )
        receive_paid_purchase_order(
            purchase_order_id=self.order.pk, business_date=date(2026, 8, 14),
            operator=self.operator, idempotency_key='receipt-source-audit',
        )
        transaction_obj = LedgerTransaction.objects.get(
            idempotency_key='receipt-source-audit',
        )
        models.QuerySet.update(
            LedgerTransaction.objects.filter(pk=transaction_obj.pk),
            source_id='999999',
        )

        self.assertIn(
            'PURCHASE_RECEIPT_LEDGER_MISMATCH',
            {issue.code for issue in audit_inventory().issues},
        )

    def test_inventory_audit_reports_tampered_reversed_receipt_source(self):
        """到货撤销后，原到货交易来源仍必须可追溯到采购单。"""
        pay_purchase_order(
            purchase_order_id=self.order.pk, rub_account_id=self.rub.pk,
            business_date=date(2026, 8, 14), operator=self.operator,
            idempotency_key='payment-before-reversed-receipt-audit',
        )
        receive_paid_purchase_order(
            purchase_order_id=self.order.pk, business_date=date(2026, 8, 14),
            operator=self.operator, idempotency_key='reversed-receipt-source-audit',
        )
        reverse_received_purchase_order(
            purchase_order_id=self.order.pk, business_date=date(2026, 8, 15),
            operator=self.operator, idempotency_key='reverse-before-source-audit',
            reason='审计历史到货',
        )
        transaction_obj = LedgerTransaction.objects.get(
            idempotency_key='reversed-receipt-source-audit',
        )
        models.QuerySet.update(
            LedgerTransaction.objects.filter(pk=transaction_obj.pk),
            source_type='tampered_receipt', source_id='999999',
        )

        self.assertIn(
            'PURCHASE_RECEIPT_LEDGER_MISMATCH',
            {issue.code for issue in audit_inventory().issues},
        )

    def test_receipt_reversal_requires_one_batch_per_order_item(self):
        """批次与采购明细不是一一对应时不得整单撤销。"""
        second = PurchaseOrderItem.objects.create(
            purchase_order=self.order,
            cigar=self.cigar,
            quantity=10,
            box_size=10,
            box_quantity=1,
            unit_price_rub_per_box=Decimal('100.00'),
            packaging_status=PurchaseOrderItem.PackagingStatus.UNREPRESENTABLE,
        )
        pay_purchase_order(
            purchase_order_id=self.order.id,
            rub_account_id=self.rub.id,
            business_date=date(2026, 8, 14),
            operator=self.operator,
            idempotency_key='payment-before-batch-map-corruption',
        )
        batches = receive_paid_purchase_order(
            purchase_order_id=self.order.id,
            business_date=date(2026, 8, 14),
            operator=self.operator,
            idempotency_key='receipt-before-batch-map-corruption',
        )
        first_item = self.order.items.exclude(pk=second.pk).get()
        force_inventory_update(
            PurchaseBatch.objects.filter(pk=batches[1].pk),
            purchase_order_item_id=first_item.pk,
        )

        with self.assertRaises(PurchaseActionError) as raised:
            reverse_received_purchase_order(
                purchase_order_id=self.order.id,
                business_date=date(2026, 8, 15),
                operator=self.operator,
                idempotency_key='reject-invalid-batch-map',
                reason='批次映射损坏',
            )

        self.assertEqual(raised.exception.code, 'receipt_already_used')

    def test_receipt_reversal_accepts_multiple_valid_order_items(self):
        """多明细采购单在事实完整时可整单撤销。"""
        PurchaseOrderItem.objects.create(
            purchase_order=self.order,
            cigar=self.cigar,
            quantity=10,
            box_size=10,
            box_quantity=1,
            unit_price_rub_per_box=Decimal('100.00'),
            packaging_status=PurchaseOrderItem.PackagingStatus.UNREPRESENTABLE,
        )
        pay_purchase_order(
            purchase_order_id=self.order.id,
            rub_account_id=self.rub.id,
            business_date=date(2026, 8, 14),
            operator=self.operator,
            idempotency_key='payment-before-multi-item-reversal',
        )
        received = receive_paid_purchase_order(
            purchase_order_id=self.order.id,
            business_date=date(2026, 8, 14),
            operator=self.operator,
            idempotency_key='multi-item-receipt',
        )

        reversed_batches = reverse_received_purchase_order(
            purchase_order_id=self.order.id,
            business_date=date(2026, 8, 15),
            operator=self.operator,
            idempotency_key='multi-item-receipt-reversal',
            reason='整单录入错误',
        )

        self.assertEqual(
            {batch.pk for batch in reversed_batches},
            {batch.pk for batch in received},
        )
        self.assertTrue(all(batch.reversed_at for batch in reversed_batches))

    def test_receipt_replay_rejects_missing_receive_movement(self):
        account = FundAccount.objects.create(
            name="测试卢布到货流水", currency=FundAccount.Currency.RUB,
            creation_idempotency_key="fund-rub-receipt-movement", custodian=self.operator,
        )
        record_opening_balance(
            account, Decimal("300.00"), Decimal("100.00"),
            LedgerPosting.Category.OPENING_CAPITAL, date(2026, 8, 10),
            self.operator, "opening-rub-receipt-movement",
        )
        pay_purchase_order(
            purchase_order_id=self.order.id, rub_account_id=account.id,
            business_date=date(2026, 8, 14), operator=self.operator,
            idempotency_key="payment-for-receipt-movement",
        )
        batches = receive_paid_purchase_order(
            purchase_order_id=self.order.id, business_date=date(2026, 8, 14),
            operator=self.operator, idempotency_key="receipt-missing-movement", note="到货",
        )
        movement = StockMovement.objects.get(purchase_batch=batches[0])
        with connection.cursor() as cursor:
            cursor.execute('DELETE FROM cigars_stockmovement WHERE id = %s', [movement.pk])

        with self.assertRaises(PurchaseActionError) as error:
            receive_paid_purchase_order(
                purchase_order_id=self.order.id, business_date=date(2026, 8, 14),
                operator=self.operator, idempotency_key="receipt-missing-movement", note="到货",
            )
        self.assertEqual(error.exception.code, "idempotency_conflict")
