from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase

from accounting.models import Day1Initialization, PurchaseDraftAction, PurchasePayment
from accounting.purchase_actions import (
    PurchaseActionError,
    canonical_purchase_item,
    create_purchase_order,
    normalize_legacy_purchase_item,
    update_purchase_order_draft,
    cancel_purchase_order,
)
from cigars.models import Cigar, PurchaseOrder, PurchaseOrderItem, Supplier, User


class PurchaseDraftActionTest(TestCase):
    def setUp(self):
        self.operator = User.objects.create_user('purchase-draft', is_staff=True)
        self.supplier = Supplier.objects.create(name='Task3 Supplier')
        self.cigar = Cigar.objects.create(
            english_name='Task3 Cigar', name='Task3 雪茄', brand='Task3',
        )
        Day1Initialization.objects.create(status=Day1Initialization.Status.COMPLETED, updated_by=self.operator, completed_by=self.operator)

    def canonical_items(self):
        return [{
            'cigar_id': self.cigar.id,
            'box_size': 25,
            'box_quantity': 1,
            'unit_price_rub_per_box': '100.00',
        }]

    def create_kwargs(self):
        return {
            'supplier_id': self.supplier.id,
            'items': self.canonical_items(),
            'business_date': date(2026, 8, 14),
            'operator': self.operator,
            'idempotency_key': 'task3-create-1',
        }

    def test_canonical_item_uses_box_formula(self):
        normalized = canonical_purchase_item(
            box_size=25,
            box_quantity=1,
            unit_price_rub_per_box=Decimal('100.00'),
        )
        self.assertEqual(normalized['sticks'], 25)
        self.assertEqual(normalized['rub_subtotal'], Decimal('100.00'))

    def test_legacy_item_requires_lossless_box_conversion(self):
        normalized = normalize_legacy_purchase_item(
            box_size=25,
            quantity_sticks=25,
            unit_price_rub_per_stick=Decimal('4.00'),
        )
        self.assertEqual(normalized['box_quantity'], 1)
        self.assertEqual(normalized['unit_price_rub_per_box'], Decimal('100.00'))
        with self.assertRaises(PurchaseActionError) as raised:
            normalize_legacy_purchase_item(
                box_size=6,
                quantity_sticks=7,
                unit_price_rub_per_stick=Decimal('4.00'),
            )
        self.assertEqual(raised.exception.code, 'packaging_review_required')

    def test_create_is_idempotent_and_uses_canonical_totals(self):
        first = create_purchase_order(**self.create_kwargs())
        replay = create_purchase_order(**self.create_kwargs())
        self.assertEqual(first.pk, replay.pk)
        first.refresh_from_db()
        item = first.items.get()
        self.assertEqual(item.quantity, 25)
        self.assertEqual(item.packaging_status, PurchaseOrderItem.PackagingStatus.UNREPRESENTABLE)
        self.assertEqual(first.rub_total, Decimal('100.00'))
        self.assertEqual(PurchaseOrder.objects.count(), 1)

        changed = self.create_kwargs()
        changed['items'] = [{**self.canonical_items()[0], 'box_quantity': 2}]
        with self.assertRaises(PurchaseActionError) as raised:
            create_purchase_order(**changed)
        self.assertEqual(raised.exception.code, 'idempotency_conflict')

    def test_incomplete_draft_can_be_saved_and_completed_later(self):
        order = create_purchase_order(
            supplier_id=None,
            items=[],
            business_date=None,
            operator=self.operator,
            idempotency_key='incomplete-draft-create',
            note='先占一个草稿',
        )
        self.assertIsNone(order.supplier_id)
        self.assertIsNone(order.draft_business_date)
        self.assertEqual(order.rub_total, Decimal('0.00'))
        self.assertFalse(order.items.exists())

        completed = update_purchase_order_draft(
            purchase_order_id=order.pk,
            supplier_id=self.supplier.pk,
            business_date=date(2026, 8, 14),
            items=self.canonical_items(),
            expected_version=1,
            idempotency_key='incomplete-draft-complete',
            operator=self.operator,
        )
        completed.refresh_from_db()
        self.assertEqual(completed.supplier_id, self.supplier.pk)
        self.assertEqual(completed.draft_business_date, date(2026, 8, 14))
        self.assertEqual(completed.rub_total, Decimal('100.00'))
        self.assertEqual(completed.items.count(), 1)


    def test_create_is_blocked_before_day1(self):
        Day1Initialization.objects.all().delete()
        with self.assertRaises(PurchaseActionError) as raised:
            create_purchase_order(**self.create_kwargs())
        self.assertEqual(raised.exception.code, 'day1_incomplete')

    def test_failed_later_item_does_not_leave_order(self):
        kwargs = self.create_kwargs()
        kwargs['items'] = [
            self.canonical_items()[0],
            {'cigar_id': 999999, 'box_size': 10, 'box_quantity': 1,
             'unit_price_rub_per_box': '20.00'},
        ]
        with self.assertRaises(PurchaseActionError):
            create_purchase_order(**kwargs)
        self.assertFalse(PurchaseOrder.objects.exists())
        self.assertFalse(PurchaseOrderItem.objects.exists())


    def test_update_version_replay_conflict_and_state_guards(self):
        order = create_purchase_order(**self.create_kwargs())
        items = [{**self.canonical_items()[0], 'unit_price_rub_per_box': '120.00'}]

        updated = update_purchase_order_draft(
            purchase_order_id=order.pk, items=items, expected_version=1,
            idempotency_key='task3-update-1', operator=self.operator, note='updated',
        )
        replay = update_purchase_order_draft(
            purchase_order_id=order.pk, items=items, expected_version=1,
            idempotency_key='task3-update-1', operator=self.operator, note='updated',
        )
        self.assertEqual(updated.pk, replay.pk)
        updated.refresh_from_db()
        self.assertEqual(updated.version, 2)
        self.assertEqual(updated.rub_total, Decimal('120.00'))
        self.assertEqual(updated.items.get().unit_price_rub_per_box, Decimal('120.00'))

        with self.assertRaises(PurchaseActionError) as raised:
            update_purchase_order_draft(
                purchase_order_id=order.pk, items=items, expected_version=1,
                idempotency_key='task3-update-1', operator=self.operator, note='changed',
            )
        self.assertEqual(raised.exception.code, 'idempotency_conflict')

        with self.assertRaises(PurchaseActionError) as raised:
            update_purchase_order_draft(
                purchase_order_id=order.pk, items=items, expected_version=1,
                idempotency_key='task3-update-stale', operator=self.operator,
            )
        self.assertEqual(raised.exception.code, 'version_conflict')

        other_cigar = Cigar.objects.create(
            english_name='Task3 Cigar 2', name='Task3 Cigar 2', brand='Task3',
        )
        updated = update_purchase_order_draft(
            purchase_order_id=order.pk,
            items=[
                {**items[0], 'cigar_id': other_cigar.pk},
                self.canonical_items()[0],
            ],
            expected_version=2, idempotency_key='task3-update-cigar',
            operator=self.operator,
        )
        self.assertEqual(
            list(updated.items.order_by('id').values_list('cigar_id', flat=True)),
            [other_cigar.pk, self.cigar.pk],
        )

        cancel_purchase_order(
            purchase_order_id=order.pk, operator=self.operator,
            idempotency_key='task3-cancel-before-update', expected_version=3,
        )
        with self.assertRaises(PurchaseActionError) as raised:
            update_purchase_order_draft(
                purchase_order_id=order.pk, items=items, expected_version=4,
                idempotency_key='task3-update-cancelled', operator=self.operator,
            )
        self.assertEqual(raised.exception.code, 'invalid_state')
        actions = list(PurchaseDraftAction.objects.filter(purchase_order=order).order_by('id').values_list('action_type', flat=True))
        self.assertEqual(actions, [
            PurchaseDraftAction.ActionType.CREATE,
            PurchaseDraftAction.ActionType.UPDATE,
            PurchaseDraftAction.ActionType.UPDATE,
            PurchaseDraftAction.ActionType.CANCEL,
        ])
        self.assertEqual(PurchaseDraftAction.objects.filter(purchase_order=order).count(), 4)

    def test_update_replay_is_stable_after_later_optional_field_changes(self):
        order = create_purchase_order(**self.create_kwargs())
        first_items = [{
            **self.canonical_items()[0],
            'unit_price_rub_per_box': '120.00',
        }]
        first = update_purchase_order_draft(
            purchase_order_id=order.pk,
            items=first_items,
            expected_version=1,
            idempotency_key='stable-update-before-optional-fields-change',
            operator=self.operator,
        )
        other_supplier = Supplier.objects.create(name='Later Supplier')
        update_purchase_order_draft(
            purchase_order_id=order.pk,
            supplier_id=other_supplier.pk,
            business_date=date(2026, 8, 15),
            items=first_items,
            expected_version=2,
            idempotency_key='later-optional-fields-change',
            operator=self.operator,
        )

        replay = update_purchase_order_draft(
            purchase_order_id=order.pk,
            items=first_items,
            expected_version=1,
            idempotency_key='stable-update-before-optional-fields-change',
            operator=self.operator,
        )

        self.assertEqual(replay.pk, first.pk)
        replay.refresh_from_db()
        self.assertEqual(replay.version, 3)
        self.assertEqual(replay.supplier_id, other_supplier.pk)
        self.assertEqual(replay.draft_business_date, date(2026, 8, 15))

    def test_cancel_clears_payment_fields_replays_and_is_append_only(self):
        order = create_purchase_order(**self.create_kwargs())
        cancelled = cancel_purchase_order(
            purchase_order_id=order.pk, operator=self.operator,
            idempotency_key='task3-cancel-1', expected_version=1, note='cancelled',
        )
        replay = cancel_purchase_order(
            purchase_order_id=order.pk, operator=self.operator,
            idempotency_key='task3-cancel-1', expected_version=1, note='cancelled',
        )
        self.assertEqual(cancelled.pk, replay.pk)
        cancelled.refresh_from_db()
        self.assertEqual(cancelled.status, PurchaseOrder.Status.CANCELLED)
        self.assertEqual(cancelled.version, 2)
        self.assertEqual(cancelled.paid_cny_cost, Decimal('0.00'))
        self.assertIsNone(cancelled.paid_at)
        self.assertIsNone(cancelled.payment_idempotency_key)
        self.assertIsNone(cancelled.arrival_idempotency_key)
        self.assertEqual(PurchasePayment.objects.filter(purchase_order=order).count(), 0)

        with self.assertRaises(PurchaseActionError) as raised:
            cancel_purchase_order(
                purchase_order_id=order.pk, operator=self.operator,
                idempotency_key='task3-cancel-1', expected_version=1, note='changed',
            )
        self.assertEqual(raised.exception.code, 'idempotency_conflict')
        with self.assertRaises(PurchaseActionError) as raised:
            cancel_purchase_order(
                purchase_order_id=order.pk, operator=self.operator,
                idempotency_key='task3-cancel-again', expected_version=2,
            )
        self.assertEqual(raised.exception.code, 'invalid_state')

        actions = list(
            PurchaseDraftAction.objects.filter(purchase_order=order).order_by('id')
            .values_list('action_type', flat=True)

        )
        self.assertEqual(actions, [
            PurchaseDraftAction.ActionType.CREATE,
            PurchaseDraftAction.ActionType.CANCEL,
        ])
        self.assertEqual(PurchaseDraftAction.objects.filter(purchase_order=order).count(), 2)

    def test_idempotency_replay_and_conflict_skip_order_lock(self):
        order = create_purchase_order(**self.create_kwargs())
        update_items = [{**self.canonical_items()[0], 'unit_price_rub_per_box': '120.00'}]
        update_purchase_order_draft(
            purchase_order_id=order.pk, items=update_items, expected_version=1,
            idempotency_key='task3-lock-order-update', operator=self.operator,
        )
        with patch.object(PurchaseOrder.objects, 'select_for_update', side_effect=AssertionError('order lock')):
            replay = update_purchase_order_draft(
                purchase_order_id=order.pk, items=update_items, expected_version=1,
                idempotency_key='task3-lock-order-update', operator=self.operator,
            )
            self.assertEqual(replay.pk, order.pk)
            with self.assertRaises(PurchaseActionError) as raised:
                update_purchase_order_draft(
                    purchase_order_id=order.pk, items=update_items, expected_version=1,
                    idempotency_key='task3-lock-order-update', operator=self.operator,
                    note='conflict',
                )
            self.assertEqual(raised.exception.code, 'idempotency_conflict')

        cancel_order = create_purchase_order(**{
            **self.create_kwargs(), 'idempotency_key': 'task3-lock-order-cancel-create',
        })
        cancel_purchase_order(
            purchase_order_id=cancel_order.pk, operator=self.operator,
            idempotency_key='task3-lock-order-cancel', expected_version=1,
        )
        with patch.object(PurchaseOrder.objects, 'select_for_update', side_effect=AssertionError('order lock')):
            replay = cancel_purchase_order(
                purchase_order_id=cancel_order.pk, operator=self.operator,
                idempotency_key='task3-lock-order-cancel', expected_version=1,
            )
            self.assertEqual(replay.pk, cancel_order.pk)
            with self.assertRaises(PurchaseActionError) as raised:
                cancel_purchase_order(
                    purchase_order_id=cancel_order.pk, operator=self.operator,
                    idempotency_key='task3-lock-order-cancel', expected_version=1,
                    note='conflict',
                )
            self.assertEqual(raised.exception.code, 'idempotency_conflict')

    def test_matching_replays_survive_operator_permission_change(self):
        created = create_purchase_order(**{
            **self.create_kwargs(), 'idempotency_key': 'permission-create',
        })
        update_order = create_purchase_order(**{
            **self.create_kwargs(), 'idempotency_key': 'permission-update-create',
        })
        update_items = [{
            **self.canonical_items()[0], 'unit_price_rub_per_box': '120.00',
        }]
        update_purchase_order_draft(
            purchase_order_id=update_order.pk, items=update_items,
            expected_version=1, idempotency_key='permission-update',
            operator=self.operator, note='权限变化前更新',
        )
        cancel_order = create_purchase_order(**{
            **self.create_kwargs(), 'idempotency_key': 'permission-cancel-create',
        })
        cancel_purchase_order(
            purchase_order_id=cancel_order.pk, expected_version=1,
            idempotency_key='permission-cancel', operator=self.operator,
            note='权限变化前取消',
        )
        self.operator.is_staff = False
        self.operator.save(update_fields=['is_staff'])

        create_replay = create_purchase_order(**{
            **self.create_kwargs(), 'idempotency_key': 'permission-create',
        })
        update_replay = update_purchase_order_draft(
            purchase_order_id=update_order.pk, items=update_items,
            expected_version=1, idempotency_key='permission-update',
            operator=self.operator, note='权限变化前更新',
        )
        cancel_replay = cancel_purchase_order(
            purchase_order_id=cancel_order.pk, expected_version=1,
            idempotency_key='permission-cancel', operator=self.operator,
            note='权限变化前取消',
        )

        self.assertEqual(create_replay.pk, created.pk)
        self.assertEqual(update_replay.pk, update_order.pk)
        self.assertEqual(cancel_replay.pk, cancel_order.pk)

    def test_box_integer_boundaries_are_stable(self):
        max_integer = 2147483647
        normalized = canonical_purchase_item(
            box_size=max_integer, box_quantity=1,
            unit_price_rub_per_box='0.00',
        )
        self.assertEqual(normalized['sticks'], max_integer)
        with self.assertRaises(PurchaseActionError) as raised:
            canonical_purchase_item(
                box_size=max_integer + 1, box_quantity=1,
                unit_price_rub_per_box='0.00',
            )
        self.assertEqual(raised.exception.code, 'invalid_packaging')
        with self.assertRaises(PurchaseActionError) as raised:
            canonical_purchase_item(
                box_size=1, box_quantity=max_integer + 1,
                unit_price_rub_per_box='0.00',
            )
        self.assertEqual(raised.exception.code, 'invalid_packaging')
        with self.assertRaises(PurchaseActionError) as raised:
            canonical_purchase_item(
                box_size=2, box_quantity=max_integer,
                unit_price_rub_per_box='0.00',
            )
        self.assertEqual(raised.exception.code, 'invalid_packaging')

    def test_zero_price_huge_box_quantity_has_no_rows(self):
        kwargs = self.create_kwargs()
        kwargs['items'] = [{
            'cigar_id': self.cigar.id,
            'box_size': 1,
            'box_quantity': '999999999999999999999999999999',
            'unit_price_rub_per_box': '0.00',
        }]
        with self.assertRaises(PurchaseActionError) as raised:
            create_purchase_order(**kwargs)
        self.assertEqual(raised.exception.code, 'invalid_packaging')
        self.assertEqual(PurchaseOrder.objects.count(), 0)
        self.assertEqual(PurchaseOrderItem.objects.count(), 0)
        self.assertEqual(PurchaseDraftAction.objects.count(), 0)

    def test_huge_box_quantity_returns_stable_error_without_rows(self):
        kwargs = self.create_kwargs()
        kwargs['items'] = [{
            'cigar_id': self.cigar.id,
            'box_size': 25,
            'box_quantity': '999999999999999999999999999999',
            'unit_price_rub_per_box': '1.00',
        }]
        with self.assertRaises(PurchaseActionError) as raised:
            create_purchase_order(**kwargs)
        self.assertIn(raised.exception.code, {'invalid_money_precision', 'invalid_packaging'})
        self.assertEqual(PurchaseOrder.objects.count(), 0)
        self.assertEqual(PurchaseOrderItem.objects.count(), 0)

    def test_order_rub_total_respects_decimal_field_range(self):
        kwargs = self.create_kwargs()
        kwargs['items'] = [{
            'cigar_id': self.cigar.id,
            'box_size': 1,
            'box_quantity': 1,
            'unit_price_rub_per_box': '10000000000.00',
        }]
        with self.assertRaises(PurchaseActionError) as raised:
            create_purchase_order(**kwargs)
        self.assertEqual(raised.exception.code, 'invalid_money_precision')
        self.assertEqual(PurchaseOrder.objects.count(), 0)
        self.assertEqual(PurchaseOrderItem.objects.count(), 0)

    def test_exchange_rate_respects_decimal_field_range(self):
        kwargs = self.create_kwargs()
        kwargs['exchange_rate'] = '1000000.0000'
        with self.assertRaises(PurchaseActionError) as raised:
            create_purchase_order(**kwargs)
        self.assertEqual(raised.exception.code, 'invalid_exchange_rate')
        self.assertEqual(PurchaseOrder.objects.count(), 0)

    def test_legacy_negative_cny_is_rejected(self):
        kwargs = self.create_kwargs()
        kwargs['items'] = [{
            'cigar_id': self.cigar.id,
            'box_size': 25,
            'box_quantity': 1,
            'unit_price_rub_per_box': '100.00',
            'unit_price_rub': '4.00',
            'unit_price_cny': '-1.00',
        }]
        with self.assertRaises(PurchaseActionError) as raised:
            create_purchase_order(**kwargs)
        self.assertEqual(raised.exception.code, 'invalid_amount')
        self.assertEqual(PurchaseOrder.objects.count(), 0)

    def test_legacy_cny_overflow_is_atomic(self):
        kwargs = self.create_kwargs()
        kwargs['items'] = [{
            'cigar_id': self.cigar.id,
            'box_size': 25,
            'box_quantity': 1,
            'unit_price_rub_per_box': '100.00',
            'unit_price_rub': '4.00',
            'unit_price_cny': '1000000000.00',
        }]
        with self.assertRaises(PurchaseActionError) as raised:
            create_purchase_order(**kwargs)
        self.assertEqual(raised.exception.code, 'invalid_money_precision')
        self.assertEqual(PurchaseOrder.objects.count(), 0)
        self.assertEqual(PurchaseOrderItem.objects.count(), 0)
