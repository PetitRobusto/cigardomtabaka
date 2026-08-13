from decimal import Decimal

from django.db import migrations
from django.db.models import Sum


def backfill_purchase_batch_inventory_facts(apps, schema_editor):
    PurchaseBatch = apps.get_model('cigars', 'PurchaseBatch')
    StockAllocation = apps.get_model('cigars', 'StockAllocation')
    reserved_by_batch = {}
    for allocation in StockAllocation.objects.filter(
        status='reserved', quantity__lt=0
    ).iterator():
        raise RuntimeError(
            f'库存分配 {allocation.pk} 存在负预留数量，无法回填库存事实'
        )

    for row in StockAllocation.objects.filter(status='reserved').values('purchase_batch_id').annotate(
        reserved_quantity=Sum('quantity')
    ):
        reserved_by_batch[row['purchase_batch_id']] = row['reserved_quantity'] or 0

    for batch in PurchaseBatch.objects.all().iterator():
        reserved_quantity = reserved_by_batch.get(batch.pk, 0)
        if batch.quantity < 0 or batch.remaining < 0 or reserved_quantity < 0:
            raise RuntimeError(f'采购批次 {batch.pk} 存在负库存数据，无法回填库存事实')

        physical_remaining = batch.remaining + reserved_quantity
        if physical_remaining < 0 or physical_remaining > batch.quantity:
            raise RuntimeError(f'采购批次 {batch.pk} 的可用库存与预留库存超过物理库存')
        if batch.unit_cost_cny < 0:
            raise RuntimeError(f'采购批次 {batch.pk} 存在负单位成本，无法回填库存事实')

        remaining_cost_cny = Decimal(physical_remaining) * batch.unit_cost_cny
        sold_cost_cny = Decimal(batch.quantity - physical_remaining) * batch.unit_cost_cny
        if remaining_cost_cny < 0 or sold_cost_cny < 0:
            raise RuntimeError(f'采购批次 {batch.pk} 会产生负成本池，无法回填库存事实')

        PurchaseBatch.objects.filter(pk=batch.pk).update(
            physical_remaining=physical_remaining,
            remaining_cost_cny=remaining_cost_cny,
            sold_cost_cny=sold_cost_cny,
        )


class Migration(migrations.Migration):

    dependencies = [
        ('cigars', '0023_purchasebatch_physical_remaining_and_more'),
    ]

    operations = [
        migrations.RunPython(backfill_purchase_batch_inventory_facts, migrations.RunPython.noop),
    ]
