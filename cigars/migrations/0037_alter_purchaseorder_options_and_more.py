from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('cigars', '0036_purchase_payment_state'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='purchaseorder',
            options={'base_manager_name': 'objects', 'ordering': ['-created_at'], 'verbose_name': '进货单', 'verbose_name_plural': '进货单'},
        ),
        migrations.AlterModelOptions(
            name='purchaseorderitem',
            options={'base_manager_name': 'objects', 'verbose_name': '进货明细', 'verbose_name_plural': '进货明细'},
        ),
    ]
