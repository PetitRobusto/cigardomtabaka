"""库存事实的模型级受控写入作用域。"""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from django.contrib.auth import get_user_model
from django.db import transaction


class InventoryMutationError(RuntimeError):
    """普通 ORM 尝试绕过库存 Module 时抛出。"""


@dataclass(frozen=True)
class InventoryMutationScope:
    action: str
    operator_id: int


_BATCH_RESERVE_FIELDS = frozenset({"remaining", "available_box_quantity", "available_stick_quantity"})
_BATCH_SHIP_FIELDS = frozenset({
    "physical_remaining", "physical_box_quantity", "physical_stick_quantity",
    "remaining_cost_cny", "sold_cost_cny",
})
_BATCH_ADJUST_FIELDS = frozenset({
    "positive_adjustment_quantity", "positive_adjustment_cost_cny", "adjustment_cost_cny",
    "remaining", "physical_remaining", "available_box_quantity", "physical_box_quantity",
    "available_stick_quantity", "physical_stick_quantity", "remaining_cost_cny",
})
_BATCH_SPLIT_FIELDS = frozenset({
    "physical_box_quantity", "available_box_quantity",
    "physical_stick_quantity", "available_stick_quantity",
})

# 每个动作只开放完成该动作所需的模型与字段。
ACTION_RULES = {
    "opening": {
        "cigars.PurchaseBatch": {"create": True, "update": frozenset()},
        "cigars.StockMovement": {"create": True, "update": frozenset()},
    },
    "receive": {
        "cigars.PurchaseBatch": {"create": True, "update": frozenset()},
        "cigars.StockMovement": {"create": True, "update": frozenset()},
    },
    "reserve": {
        "cigars.PurchaseBatch": {"create": False, "update": _BATCH_RESERVE_FIELDS},
        "cigars.StockAllocation": {"create": True, "update": frozenset()},
        "cigars.StockMovement": {"create": True, "update": frozenset()},
    },
    "release": {
        "cigars.PurchaseBatch": {"create": False, "update": _BATCH_RESERVE_FIELDS},
        "cigars.StockAllocation": {
            "create": False, "update": frozenset({"status", "released_at"}),
        },
        "cigars.StockMovement": {"create": True, "update": frozenset()},
    },
    "ship": {
        "cigars.PurchaseBatch": {"create": False, "update": _BATCH_SHIP_FIELDS},
        "cigars.StockAllocation": {
            "create": False, "update": frozenset({"status", "fulfilled_at"}),
        },
        "cigars.StockMovement": {"create": True, "update": frozenset()},
    },
    "adjust": {
        "cigars.PurchaseBatch": {"create": True, "update": _BATCH_ADJUST_FIELDS},
        "cigars.StockMovement": {"create": True, "update": frozenset()},
    },
    "split_box": {
        "cigars.PurchaseBatch": {"create": False, "update": _BATCH_SPLIT_FIELDS},
        "cigars.StockMovement": {"create": True, "update": frozenset()},
    },
}

# 只有统一库存 Module 和测试夹具持有写入能力。
_INVENTORY_WRITE_CAPABILITY = object()
_scope = ContextVar("cigar_inventory_mutation_scope", default=None)


def _operator_allowed(operator):
    operator_id = getattr(operator, "pk", None)
    if not operator_id:
        return False
    persisted = get_user_model().objects.filter(pk=operator_id, is_active=True).first()
    return bool(persisted and getattr(persisted, "is_operator", True))


@contextmanager
def inventory_mutation_scope(*, action, operator, _capability=None):
    """仅供统一库存 Module 使用；作用域必须处于数据库事务内。"""
    if _capability is not _INVENTORY_WRITE_CAPABILITY:
        raise InventoryMutationError("库存写入作用域只能由统一库存 Module 开启")
    if action not in ACTION_RULES:
        raise ValueError("未知库存动作")
    if not _operator_allowed(operator):
        raise ValueError("受控库存写入操作人不存在、未启用或无内部账权限")
    if not transaction.get_connection().in_atomic_block:
        raise RuntimeError("受控库存写入必须位于事务内")
    parent = _scope.get()
    if parent is not None and (
        parent.action != action or parent.operator_id != operator.pk
    ):
        raise ValueError("嵌套库存写入必须保持同一动作和操作人")
    token = _scope.set(InventoryMutationScope(action=action, operator_id=operator.pk))
    try:
        yield
    finally:
        _scope.reset(token)


def current_inventory_action():
    """返回当前受控动作；模型层据此校验新事实语义。"""
    state = _scope.get()
    return state.action if state is not None else None


def inventory_scope_allows(*, model, operation, fields=()):
    state = _scope.get()
    if state is None:
        return False
    rule = ACTION_RULES[state.action].get(model)
    if rule is None:
        return False
    if operation == "create":
        return bool(rule["create"])
    if operation == "update":
        return frozenset(fields) <= rule["update"]
    return False
