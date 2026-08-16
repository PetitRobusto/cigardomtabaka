from datetime import date
from decimal import Decimal
import json
from unittest.mock import patch

from django.db import models
from django.test import TestCase

from accounting.models import Day1Initialization, LedgerMutationError, LedgerPosting, LedgerTransaction
from accounting.services import LedgerError, PostingInput, _post_transaction_once
from cigars.audit import AgentContext
from cigars.inventory import open_stock
from cigars.inventory_audit import audit_inventory
from cigars.models import (
    Cigar,
    InventoryAdjustmentAction,
    InventoryAdjustmentLine,
    PurchaseBatch,
    StockMovement,
    User,
)
from cigars.services import OrderServiceError, adjust_stock, reverse_stock_adjustment
from cigars.tests.inventory_fixtures import force_inventory_update


class InventoryAdjustmentReversalTest(TestCase):
    business_date = date(2026, 8, 16)

    def setUp(self):
        self.operator = User.objects.create_user(
            'adjustment-reversal-operator', is_staff=True,
        )
        Day1Initialization.objects.create(
            singleton_key='company',
            status=Day1Initialization.Status.COMPLETED,
            business_date=self.business_date,
            completed_by=self.operator,
        )
        self.cigar = Cigar.objects.create(
            brand='Adjustment',
            english_name='Adjustment Reversal Cigar',
            name='调整撤销雪茄',
        )
        self.batch = open_stock(
            cigar_id=self.cigar.pk,
            quantity=10,
            box_size=None,
            box_quantity=0,
            loose_sticks=10,
            total_cost_cny=Decimal('100.00'),
            unit_cost_cny=Decimal('10.00'),
            operator=self.operator,
            context=AgentContext(command_name='day1_open_stock'),
        )

    def context(self, key):
        return AgentContext(
            agent_name='adjustment-reversal-test',
            command_name='adjust_stock',
            idempotency_key=key,
        )

    def test_adjustment_can_be_reversed_once_and_replayed(self):
        """结构化调整可整次恢复库存、成本和账务。"""
        adjust_stock(
            cigar_id=self.cigar.pk,
            quantity_delta=-3,
            operator=self.operator,
            reason='盘亏三支',
            batch_id=self.batch.pk,
            business_date=self.business_date,
            agent_context=self.context('adjust-before-reversal'),
        )
        action = InventoryAdjustmentAction.objects.get(
            idempotency_key='adjust-before-reversal',
        )

        reversed_action = reverse_stock_adjustment(
            adjustment_id=action.pk,
            business_date=self.business_date,
            operator=self.operator,
            idempotency_key='reverse-adjustment-1',
            reason='盘点数量录错',
        )
        replayed = reverse_stock_adjustment(
            adjustment_id=action.pk,
            business_date=self.business_date,
            operator=self.operator,
            idempotency_key='reverse-adjustment-1',
            reason='盘点数量录错',
        )

        self.batch.refresh_from_db()
        self.assertEqual(replayed.pk, reversed_action.pk)
        self.assertEqual(self.batch.remaining, 10)
        self.assertEqual(self.batch.physical_remaining, 10)
        self.assertEqual(self.batch.remaining_cost_cny, Decimal('100.00'))
        self.assertEqual(self.batch.adjustment_cost_cny, Decimal('0.00'))
        self.assertEqual(
            StockMovement.objects.filter(
                movement_type=StockMovement.MovementType.REVERSE_ADJUSTMENT,
            ).count(),
            1,
        )
        original = action.ledger_transaction
        original.refresh_from_db()
        self.assertEqual(original.reversed_by_id, reversed_action.reversal_transaction_id)
        self.assertEqual(
            LedgerTransaction.objects.filter(
                transaction_type=LedgerTransaction.TransactionType.INVENTORY_ADJUSTMENT,
            ).count(),
            2,
        )

    def test_adjustment_facts_reject_plain_orm_writes(self):
        """调整事实只能由受控服务创建、冲正，普通 ORM 不得改写。"""
        adjust_stock(
            cigar_id=self.cigar.pk,
            quantity_delta=-1,
            operator=self.operator,
            reason='边界测试调整',
            batch_id=self.batch.pk,
            business_date=self.business_date,
            agent_context=self.context('adjustment-write-boundary'),
        )
        action = InventoryAdjustmentAction.objects.get(
            idempotency_key='adjustment-write-boundary',
        )
        line = action.lines.get()
        action.reason = '禁止修改'
        line.cost_delta_cny = Decimal('999.00')

        actions = [
            lambda: action.save(update_fields=['reason']),
            action.delete,
            lambda: InventoryAdjustmentAction.objects.filter(pk=action.pk).update(reason='禁止修改'),
            lambda: InventoryAdjustmentAction.objects.filter(pk=action.pk).delete(),
            lambda: InventoryAdjustmentAction.objects.bulk_update([action], ['reason']),
            lambda: InventoryAdjustmentAction.objects.bulk_create([action]),
            lambda: InventoryAdjustmentAction.objects.update_or_create(pk=action.pk, defaults={'reason': '禁止修改'}),
            lambda: InventoryAdjustmentAction.objects.get_or_create(pk=action.pk),
            lambda: line.save(update_fields=['cost_delta_cny']),
            line.delete,
            lambda: InventoryAdjustmentLine.objects.filter(pk=line.pk).update(cost_delta_cny=Decimal('999.00')),
            lambda: InventoryAdjustmentLine.objects.filter(pk=line.pk).delete(),
            lambda: InventoryAdjustmentLine.objects.bulk_update([line], ['cost_delta_cny']),
            lambda: InventoryAdjustmentLine.objects.bulk_create([line]),
            lambda: InventoryAdjustmentLine.objects.update_or_create(pk=line.pk, defaults={'cost_delta_cny': Decimal('999.00')}),
            lambda: InventoryAdjustmentLine.objects.get_or_create(pk=line.pk),
        ]
        for write in actions:
            with self.subTest(write=write):
                with self.assertRaises(LedgerMutationError):
                    write()

    def test_adjustment_reversal_is_blocked_after_batch_changes(self):
        """调整后批次发生任何变化时，不再猜测并撤销旧动作。"""
        adjust_stock(
            cigar_id=self.cigar.pk,
            quantity_delta=-2,
            operator=self.operator,
            reason='第一次盘亏',
            batch_id=self.batch.pk,
            business_date=self.business_date,
            agent_context=self.context('adjust-before-later-change'),
        )
        first = InventoryAdjustmentAction.objects.get(
            idempotency_key='adjust-before-later-change',
        )
        adjust_stock(
            cigar_id=self.cigar.pk,
            quantity_delta=-1,
            operator=self.operator,
            reason='之后再次盘亏',
            batch_id=self.batch.pk,
            business_date=self.business_date,
            agent_context=self.context('later-adjustment'),
        )

        with self.assertRaises(OrderServiceError):
            reverse_stock_adjustment(
                adjustment_id=first.pk,
                business_date=self.business_date,
                operator=self.operator,
                idempotency_key='blocked-reverse-adjustment',
                reason='试图撤销旧动作',
            )
        first.refresh_from_db()
        self.assertIsNone(first.reversal_transaction_id)
        self.assertFalse(LedgerTransaction.objects.filter(
            idempotency_key='blocked-reverse-adjustment',
        ).exists())

    def test_staff_web_api_reverses_adjustment_and_runs_audit(self):
        """工作人员可通过公开接口撤销调整并读取审计结果。"""
        adjust_stock(
            cigar_id=self.cigar.pk,
            quantity_delta=-1,
            operator=self.operator,
            reason='接口盘亏',
            batch_id=self.batch.pk,
            business_date=self.business_date,
            agent_context=self.context('web-adjustment-before-reversal'),
        )
        action = InventoryAdjustmentAction.objects.get(
            idempotency_key='web-adjustment-before-reversal',
        )
        self.client.force_login(self.operator)

        response = self.client.post(
            f'/api/inventory/adjustments/{action.pk}/reverse/',
            data=json.dumps({
                'business_date': self.business_date.isoformat(),
                'reason': '接口撤销',
            }),
            content_type='application/json',
            HTTP_IDEMPOTENCY_KEY='web-reverse-adjustment',
        )
        audit = self.client.get('/api/inventory/audit/')

        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(response.json()['adjustment']['reversal_transaction_id'])
        self.assertEqual(audit.status_code, 200)
        self.assertTrue(audit.json()['ok'])
        self.assertEqual(audit.json()['issues'], [])

    def test_adjustment_reversal_rolls_back_inventory_when_ledger_fails(self):
        """调整撤销冲正失败时，库存仍保持调整后的状态。"""
        adjust_stock(
            cigar_id=self.cigar.pk,
            quantity_delta=-2,
            operator=self.operator,
            reason='回滚测试调整',
            batch_id=self.batch.pk,
            business_date=self.business_date,
            agent_context=self.context('adjust-before-failed-reversal'),
        )
        action = InventoryAdjustmentAction.objects.get(
            idempotency_key='adjust-before-failed-reversal',
        )

        with patch(
            'cigars.services.reverse_ledger_transaction',
            side_effect=LedgerError('冲正失败'),
        ):
            with self.assertRaises(LedgerError):
                reverse_stock_adjustment(
                    adjustment_id=action.pk,
                    business_date=self.business_date,
                    operator=self.operator,
                    idempotency_key='failed-adjustment-reversal',
                    reason='测试回滚',
                )

        self.batch.refresh_from_db()
        action.refresh_from_db()
        self.assertEqual(self.batch.remaining, 8)
        self.assertEqual(self.batch.adjustment_cost_cny, Decimal('20.00'))
        self.assertIsNone(action.reversal_transaction_id)
        self.assertFalse(StockMovement.objects.filter(
            movement_type=StockMovement.MovementType.REVERSE_ADJUSTMENT,
        ).exists())

    def test_positive_adjustment_new_batch_can_be_reversed(self):
        """正向调整创建的新批次可整次恢复为空批次。"""
        adjust_stock(
            cigar_id=self.cigar.pk,
            quantity_delta=2,
            operator=self.operator,
            reason='盘盈两支',
            unit_cost_cny=Decimal('9.00'),
            business_date=self.business_date,
            agent_context=self.context('positive-adjustment-new-batch'),
        )
        action = InventoryAdjustmentAction.objects.get(
            idempotency_key='positive-adjustment-new-batch',
        )

        reverse_stock_adjustment(
            adjustment_id=action.pk,
            business_date=self.business_date,
            operator=self.operator,
            idempotency_key='reverse-positive-adjustment-new-batch',
            reason='复核后确认没有盘盈',
        )

        batch = action.lines.get().purchase_batch
        batch.refresh_from_db()
        self.assertEqual(batch.physical_remaining, 0)
        self.assertEqual(batch.remaining_cost_cny, Decimal('0.00'))
        self.assertTrue(audit_inventory().ok)

    def test_audit_reports_tampered_adjustment_movement(self):
        """调整流水数量被篡改时必须破坏库存流水守恒。"""
        adjust_stock(
            cigar_id=self.cigar.pk,
            quantity_delta=-2,
            operator=self.operator,
            reason='盘亏两支',
            batch_id=self.batch.pk,
            business_date=self.business_date,
            agent_context=self.context('adjustment-before-audit-tamper'),
        )
        movement = StockMovement.objects.get(
            movement_type=StockMovement.MovementType.ADJUSTMENT,
            idempotency_key='adjustment-before-audit-tamper',
        )
        force_inventory_update(
            StockMovement.objects.filter(pk=movement.pk), quantity=-1,
        )

        result = audit_inventory()

        self.assertIn(
            'BATCH_MOVEMENT_PHYSICAL_MISMATCH',
            {issue.code for issue in result.issues},
        )

    def test_audit_reports_tampered_adjustment_transaction_type(self):
        """原调整交易类型被篡改时，审计必须识别账务关联损坏。"""
        adjust_stock(
            cigar_id=self.cigar.pk,
            quantity_delta=-1,
            operator=self.operator,
            reason='交易类型审计',
            batch_id=self.batch.pk,
            business_date=self.business_date,
            agent_context=self.context('adjustment-transaction-audit'),
        )
        action = InventoryAdjustmentAction.objects.get(
            idempotency_key='adjustment-transaction-audit',
        )
        models.QuerySet.update(
            LedgerTransaction.objects.filter(pk=action.ledger_transaction_id),
            transaction_type=LedgerTransaction.TransactionType.EXPENSE,
        )

        self.assertIn(
            'ADJUSTMENT_LEDGER_MISMATCH',
            {issue.code for issue in audit_inventory().issues},
        )

    def test_audit_reports_adjustment_linked_to_another_actions_transaction(self):
        """金额相同的调整交易也不能交叉绑定到另一调整动作。"""
        for key, reason in (
            ('first-adjustment-link-audit', '第一笔盘亏'),
            ('second-adjustment-link-audit', '第二笔盘亏'),
        ):
            adjust_stock(
                cigar_id=self.cigar.pk,
                quantity_delta=-1,
                operator=self.operator,
                reason=reason,
                batch_id=self.batch.pk,
                business_date=self.business_date,
                agent_context=self.context(key),
            )
        first = InventoryAdjustmentAction.objects.get(
            idempotency_key='first-adjustment-link-audit',
        )
        second = InventoryAdjustmentAction.objects.get(
            idempotency_key='second-adjustment-link-audit',
        )
        spare = _post_transaction_once(
            transaction_type=LedgerTransaction.TransactionType.INVENTORY_ADJUSTMENT,
            business_date=self.business_date,
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
            idempotency_key='spare-adjustment-link-audit',
            description='临时合法调整交易',
            source_type='stock_adjustment',
            source_id=f"stock_adjustment:{'f' * 64}:{self.batch.pk}",
        )
        models.QuerySet.update(
            InventoryAdjustmentAction.objects.filter(pk=second.pk),
            ledger_transaction_id=spare.pk,
        )
        models.QuerySet.update(
            InventoryAdjustmentAction.objects.filter(pk=first.pk),
            ledger_transaction_id=second.ledger_transaction_id,
        )

        self.assertIn(
            'ADJUSTMENT_LEDGER_MISMATCH',
            {issue.code for issue in audit_inventory().issues},
        )
