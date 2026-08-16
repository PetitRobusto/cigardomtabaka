"""测试专用库存事实工厂；生产代码不得引用。"""
from django.db import models, transaction

from cigars.inventory_scope import (
    _INVENTORY_WRITE_CAPABILITY, inventory_mutation_scope,
)
from cigars.models import PurchaseBatch, StockAllocation, StockMovement, User


def _test_operator(operator):
    if operator is not None:
        return operator
    operator, _ = User.objects.get_or_create(
        username='_inventory-fixture-operator',
        defaults={'is_staff': True},
    )
    return operator

def create_purchase_batch(*, operator=None, **fields):
    operator = _test_operator(operator)
    source = fields.get("source", PurchaseBatch.Source.PURCHASE)
    action = {
        PurchaseBatch.Source.OPENING: "opening",
        PurchaseBatch.Source.ADJUSTMENT: "adjust",
        PurchaseBatch.Source.PURCHASE: "receive",
    }[source]
    with transaction.atomic(), inventory_mutation_scope(
        action=action, operator=operator,
        _capability=_INVENTORY_WRITE_CAPABILITY,
    ):
        return PurchaseBatch.objects.create(**fields)


def create_stock_allocation(*, operator, **fields):
    with transaction.atomic(), inventory_mutation_scope(
        action="reserve", operator=operator,
        _capability=_INVENTORY_WRITE_CAPABILITY,
    ):
        return StockAllocation.objects.create(**fields)


def create_stock_movement(*, operator, **fields):
    fields.setdefault("operator", operator)
    with transaction.atomic(), inventory_mutation_scope(
        action="opening", operator=operator,
        _capability=_INVENTORY_WRITE_CAPABILITY,
    ):
        return StockMovement.objects.create(**fields)


def force_create_purchase_batch(**fields):
    """仅用于绕过模型门禁，直接验证数据库约束。"""
    instance = PurchaseBatch(**fields)
    if not any((
        instance.original_box_quantity, instance.original_stick_quantity,
        instance.physical_box_quantity, instance.physical_stick_quantity,
        instance.available_box_quantity, instance.available_stick_quantity,
    )):
        if instance.box_size:
            instance.original_box_quantity, instance.original_stick_quantity = divmod(
                instance.quantity, instance.box_size,
            )
            instance.available_box_quantity, instance.available_stick_quantity = divmod(
                instance.remaining, instance.box_size,
            )
            instance.physical_box_quantity = instance.available_box_quantity
            instance.physical_stick_quantity = (
                instance.available_stick_quantity
                + instance.physical_remaining - instance.remaining
            )
        else:
            instance.original_stick_quantity = instance.quantity
            instance.physical_stick_quantity = instance.physical_remaining
            instance.available_stick_quantity = instance.remaining
    models.Model.save(instance, force_insert=True)
    return instance


def force_inventory_update(queryset, **fields):
    """仅用于构造审计应识别的数据库损坏。"""
    return models.QuerySet.update(queryset, **fields)


def force_inventory_delete(queryset):
    """仅用于构造缺失库存事实的审计场景。"""
    return models.QuerySet.delete(queryset)


def force_inventory_save(instance, **kwargs):
    """仅用于验证数据库约束或构造损坏快照。"""
    return models.Model.save(instance, **kwargs)
