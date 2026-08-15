from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.test import TestCase, TransactionTestCase

from accounting.models import (
    Dividend,
    DividendDraftAction,
    LedgerMutationError,
    PurchaseDraftAction,
)
from cigars.models import User
from accounting.mutation_scope import ledger_mutation_scope, current_ledger_mutation_scope


class DraftActionModelTest(TestCase):
    def setUp(self):
        self.operator = User.objects.create_user("draft-action", is_staff=True)

    def test_purchase_draft_action_is_append_only(self):
        action = PurchaseDraftAction(
            action_type=PurchaseDraftAction.ActionType.CREATE,
            idempotency_key="purchase-draft-create", request_fingerprint="fingerprint", operator=self.operator,
        )
        fields = {field.name for field in action._meta.concrete_fields}
        with transaction.atomic(), ledger_mutation_scope(reason="purchase_draft_action", model="accounting.PurchaseDraftAction", operator=self.operator, allowed_fields=fields):
            models.Model.save(action, force_insert=True)
        with self.assertRaises(LedgerMutationError):
            action.save()
        with self.assertRaises(LedgerMutationError):
            action.delete()
        with self.assertRaises(LedgerMutationError):
            PurchaseDraftAction.objects.filter(pk=action.pk).update(request_fingerprint="changed")
        with self.assertRaises(LedgerMutationError):
            PurchaseDraftAction.objects.filter(pk=action.pk).delete()
        with self.assertRaises(LedgerMutationError):
            PurchaseDraftAction.objects.bulk_update([action], ["request_fingerprint"])
        with self.assertRaises(LedgerMutationError):
            PurchaseDraftAction.objects.bulk_create([action])

    def test_bulk_create_requires_scope_and_allows_new_rows(self):
        action = PurchaseDraftAction(
            action_type=PurchaseDraftAction.ActionType.CREATE,
            idempotency_key='purchase-draft-bulk-create',
            request_fingerprint='bulk-fingerprint', operator=self.operator,
        )
        with self.assertRaises(LedgerMutationError):
            PurchaseDraftAction.objects.bulk_create([action])
        fields = {field.name for field in action._meta.concrete_fields}
        with transaction.atomic(), ledger_mutation_scope(
            reason='purchase_draft_action', model='accounting.PurchaseDraftAction',
            operator=self.operator, allowed_fields=fields,
        ):
            created = PurchaseDraftAction.objects.bulk_create([action])
        self.assertEqual(created[0].pk, action.pk)

    def test_dividend_draft_action_is_append_only_and_has_no_cancel_type(self):
        dividend = Dividend.objects.create(
            total_cny="0.00",
            partner_a_amount_cny="0.00",
            partner_b_amount_cny="0.00",
            business_date="2026-08-14",
        )
        action = DividendDraftAction(
            dividend=dividend, action_type=DividendDraftAction.ActionType.CREATE,
            idempotency_key="dividend-draft-create", request_fingerprint="fingerprint", operator=self.operator,
        )
        fields = {field.name for field in action._meta.concrete_fields}
        with transaction.atomic(), ledger_mutation_scope(reason="dividend_draft_action", model="accounting.DividendDraftAction", operator=self.operator, allowed_fields=fields):
            models.Model.save(action, force_insert=True)
        with self.assertRaises(LedgerMutationError):
            action.save()
        with self.assertRaises(LedgerMutationError):
            DividendDraftAction.objects.filter(pk=action.pk).delete()
        self.assertNotIn("cancel", DividendDraftAction.ActionType.values)


class MutationScopeTest(TransactionTestCase):
    def test_scope_requires_atomic_persisted_operator_and_is_immutable_nested(self):
        with self.assertRaises(ValueError):
            with ledger_mutation_scope(reason="unknown", model="accounting.Dividend", operator=User(username="unsaved")):
                pass
        operator = User.objects.create_user("scope-operator", is_staff=True)
        with self.assertRaises(ValueError):
            with ledger_mutation_scope(reason="unknown", model="accounting.Dividend", operator=operator):
                pass
        with self.assertRaises(ValueError):
            with transaction.atomic(), ledger_mutation_scope(reason="dividend_confirm", model="accounting.Dividend", operator=operator, allowed_fields={"not_allowed"}):
                pass
        with self.assertRaises(RuntimeError):
            with ledger_mutation_scope(reason="dividend_confirm", model="accounting.Dividend", operator=operator):
                pass
        with transaction.atomic(), ledger_mutation_scope(reason="dividend_confirm", model="accounting.Dividend", operator=operator, allowed_fields={"status", "confirmed_by"}) as outer:
            self.assertEqual(outer.allowed_fields, frozenset({"status", "confirmed_by"}))
            with transaction.atomic(), ledger_mutation_scope(reason="dividend_confirm", model="accounting.Dividend", operator=operator, allowed_fields={"status"}):
                self.assertEqual(current_ledger_mutation_scope().reason, "dividend_confirm")
            self.assertEqual(current_ledger_mutation_scope().reason, "dividend_confirm")
        self.assertIsNone(current_ledger_mutation_scope())
        operator.is_active = False
        User.objects.filter(pk=operator.pk).update(is_active=False)
        with self.assertRaises(ValueError):
            with transaction.atomic(), ledger_mutation_scope(reason="dividend_confirm", model="accounting.Dividend", operator=operator):
                pass
