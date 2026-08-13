from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cigars', '0029_purchase_batch_packaging_constraints'),
    ]

    operations = [
        migrations.AlterField(
            model_name='stockmovement',
            name='movement_type',
            field=models.CharField(
                choices=[
                    ('receive', '入库'),
                    ('reserve', '预留'),
                    ('release_reservation', '释放预留'),
                    ('ship', '出库'),
                    ('adjustment', '库存修正'),
                    ('split_box', '拆盒'),
                ],
                max_length=30,
                verbose_name='类型',
            ),
        ),
    ]
