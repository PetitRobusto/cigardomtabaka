from django.db import migrations


COMMAND_NAME = 'migration_stock_opening_balance'


def create_opening_balances(apps, schema_editor):
    PurchaseBatch = apps.get_model('cigars', 'PurchaseBatch')
    StockMovement = apps.get_model('cigars', 'StockMovement')

    batches = PurchaseBatch.objects.filter(remaining__gt=0).select_related(
        'purchase_order_item__purchase_order'
    )
    movements = []
    for batch in batches.iterator():
        movements.append(StockMovement(
            movement_type='receive',
            cigar_id=batch.cigar_id,
            purchase_batch_id=batch.id,
            quantity=batch.remaining,
            operator_id=batch.purchase_order_item.purchase_order.operator_id,
            command_name=COMMAND_NAME,
            note='Opening balance imported from PurchaseBatch.remaining',
        ))
    StockMovement.objects.bulk_create(movements, batch_size=500)


def remove_opening_balances(apps, schema_editor):
    StockMovement = apps.get_model('cigars', 'StockMovement')
    StockMovement.objects.filter(command_name=COMMAND_NAME).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('cigars', '0020_agent_order_inventory_commands'),
    ]

    operations = [
        migrations.RunPython(create_opening_balances, remove_opening_balances),
    ]
