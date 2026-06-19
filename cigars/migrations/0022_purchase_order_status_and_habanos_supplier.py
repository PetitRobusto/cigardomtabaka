from django.db import migrations, models


def seed_purchase_state(apps, schema_editor):
    PurchaseOrder = apps.get_model('cigars', 'PurchaseOrder')
    Supplier = apps.get_model('cigars', 'Supplier')

    PurchaseOrder.objects.all().update(status='received')

    supplier, _ = Supplier.objects.get_or_create(name='Habanos')
    if supplier.deleted_at is not None:
        supplier.deleted_at = None
        supplier.save(update_fields=['deleted_at'])


class Migration(migrations.Migration):

    dependencies = [
        ('cigars', '0021_stock_movement_opening_balances'),
    ]

    operations = [
        migrations.AddField(
            model_name='purchaseorder',
            name='status',
            field=models.CharField(
                choices=[
                    ('draft', '草稿'),
                    ('received', '已入库'),
                    ('cancelled', '已取消'),
                ],
                default='draft',
                max_length=20,
                verbose_name='状态',
            ),
        ),
        migrations.RunPython(seed_purchase_state, migrations.RunPython.noop),
    ]
