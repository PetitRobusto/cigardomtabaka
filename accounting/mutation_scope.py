"""账务事实受控写入作用域与模型级动作字段白名单。"""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import FrozenSet

from django.contrib.auth import get_user_model
from django.db import transaction


@dataclass(frozen=True)
class LedgerMutationScope:
    reason: str
    model_label: str
    operator_id: int
    allowed_fields: FrozenSet[str]


REASON_ALLOWED_FIELDS = {
    "purchase_payment": {
        "cigars.PurchaseOrder": frozenset({"id", "status", "paid_cny_cost", "paid_at", "payment_idempotency_key"}),
        "cigars.PurchaseOrderItem": frozenset({"id", "actual_cost_cny"}),
        "accounting.PurchasePayment": frozenset({"id", "status", "purchase_order", "fund_account", "rub_amount", "cny_cost", "business_date", "operator", "ledger_transaction", "idempotency_key", "request_fingerprint"}),
    },
    "purchase_receipt": {
        "cigars.PurchaseOrder": frozenset({"id", "status", "arrival_idempotency_key", "legacy_received"}),
        "cigars.PurchaseOrderItem": frozenset({"id", "actual_cost_cny"}),
    },
    "purchase_receipt_reversal": {
        "cigars.PurchaseOrder": frozenset({"id", "status", "arrival_idempotency_key", "legacy_received"}),
        "cigars.PurchaseOrderItem": frozenset({"id", "actual_cost_cny"}),
    },
    "sales_return_fact": {
        "cigars.SalesReturn": frozenset({
            "id", "sales_order", "sales_shipment", "amount_cny", "fifo_cost_cny",
            "ledger_transaction", "business_date", "operator", "reason", "created_at",
        }),
    },
    "inventory_adjustment_fact": {
        "cigars.InventoryAdjustmentAction": frozenset({
            "id", "cigar", "quantity_delta", "inventory_form", "ledger_transaction",
            "reversal_transaction", "business_date", "operator", "reason",
            "idempotency_key", "reversed_at", "reversal_operator", "reversal_reason",
            "created_at",
        }),
        "cigars.InventoryAdjustmentLine": frozenset({
            "id", "action", "purchase_batch", "stock_movement", "quantity_delta",
            "box_delta", "stick_delta", "cost_delta_cny", "batch_state_after",
        }),
    },
    "inventory_adjustment_reversal": {
        "cigars.InventoryAdjustmentAction": frozenset({
            "reversal_transaction", "reversed_at", "reversal_operator", "reversal_reason",
        }),
    },
    "expense_post": {
        "accounting.Expense": frozenset({"id", "status", "category", "subcategory", "fund_account", "original_amount", "amount_cny", "business_date", "operator", "ledger_transaction", "idempotency_key", "note"}),
    },
    "dividend_confirm": {
        "accounting.Dividend": frozenset({"id", "status", "ledger_transaction", "confirmed_by", "version", "confirm_idempotency_key", "confirm_request_fingerprint"}),
    },
    "purchase_draft_action": {
        "accounting.PurchaseDraftAction": frozenset({"id", "purchase_order", "action_type", "idempotency_key", "request_fingerprint", "result_version", "operator", "created_at"}),
    },
    "dividend_draft_action": {
        "accounting.DividendDraftAction": frozenset({"id", "dividend", "action_type", "idempotency_key", "request_fingerprint", "result_version", "operator", "created_at"}),
    },
}

_scope = ContextVar("accounting_ledger_mutation_scope", default=None)


def _operator_allowed(operator):
    operator_id = getattr(operator, "pk", None)
    if not operator_id:
        return False
    User = get_user_model()
    persisted = User.objects.filter(pk=operator_id, is_active=True).first()
    if persisted is None:
        return False
    if hasattr(persisted, "is_operator"):
        return bool(persisted.is_operator)
    return True  # 本项目若无 is_operator，则 active 用户即两位内部批准人。


@contextmanager
def ledger_mutation_scope(*, reason, model, operator, allowed_fields=None):
    if reason not in REASON_ALLOWED_FIELDS or model not in REASON_ALLOWED_FIELDS[reason]:
        raise ValueError("未知账务动作来源或模型")
    if not _operator_allowed(operator):
        raise ValueError("受控账务写入操作人不存在、未启用或无内部账权限")
    if not transaction.get_connection().in_atomic_block:
        raise RuntimeError("受控账务写入必须位于事务内")
    fields = frozenset(allowed_fields if allowed_fields is not None else REASON_ALLOWED_FIELDS[reason][model])
    if not fields <= REASON_ALLOWED_FIELDS[reason][model]:
        raise ValueError("受控账务写入字段超出模型动作白名单")
    parent = _scope.get()
    if parent is not None:
        if parent.reason != reason or parent.model_label != model or parent.operator_id != operator.pk:
            raise ValueError("嵌套受控写入必须保持同一 reason、model 和 operator")
        if not fields <= parent.allowed_fields:
            raise ValueError("嵌套受控写入只能收窄字段")
    state = LedgerMutationScope(reason, model, operator.pk, fields)
    token = _scope.set(state)
    try:
        yield state
    finally:
        _scope.reset(token)


def current_ledger_mutation_scope():
    return _scope.get()


def scope_allows(*, reason, model, fields, operator=None):
    state = _scope.get()
    if state is None or state.reason != reason or state.model_label != model:
        return False
    if operator is not None and state.operator_id != getattr(operator, "pk", operator):
        return False
    return frozenset(fields) <= state.allowed_fields


def assert_ledger_mutation(*, reason, model, operator, fields):
    state = _scope.get()
    if state is None:
        raise RuntimeError("缺少受控账务写入作用域")
    if state.reason != reason or state.model_label != model or state.operator_id != getattr(operator, "pk", operator):
        raise RuntimeError("受控账务写入来源、模型或操作人不匹配")
    if not frozenset(fields) <= state.allowed_fields:
        raise RuntimeError("受控账务写入包含未授权字段")


def _scope_active():
    return _scope.get() is not None


ledger_mutation_scope.active = _scope_active
