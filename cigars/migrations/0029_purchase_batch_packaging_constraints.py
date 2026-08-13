from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cigars', '0028_purchase_batch_packaging_inventory'),
    ]

    operations = [
        migrations.AddConstraint(
            model_name='purchasebatch',
            constraint=models.CheckConstraint(
                condition=models.Q(original_box_quantity__gte=0, original_stick_quantity__gte=0, physical_box_quantity__gte=0, physical_stick_quantity__gte=0, available_box_quantity__gte=0, available_stick_quantity__gte=0),
                name='purchase_batch_packaging_nonnegative',
            ),
        ),
        migrations.AddConstraint(
            model_name='purchasebatch',
            constraint=models.CheckConstraint(
                condition=models.Q(available_box_quantity__lte=models.F('physical_box_quantity'), available_stick_quantity__lte=models.F('physical_stick_quantity')),
                name='purchase_batch_available_shape_lte_physical',
            ),
        ),
        migrations.AddConstraint(
            model_name='purchasebatch',
            constraint=models.CheckConstraint(
                condition=(models.Q(box_size__gt=0, quantity=models.F('original_box_quantity') * models.F('box_size') + models.F('original_stick_quantity'), physical_remaining=models.F('physical_box_quantity') * models.F('box_size') + models.F('physical_stick_quantity'), remaining=models.F('available_box_quantity') * models.F('box_size') + models.F('available_stick_quantity')) | models.Q(box_size__isnull=True, original_box_quantity=0, physical_box_quantity=0, available_box_quantity=0, original_stick_quantity=models.F('quantity'), physical_stick_quantity=models.F('physical_remaining'), available_stick_quantity=models.F('remaining'))),
                name='purchase_batch_packaging_shape_matches_aggregate',
            ),
        ),
    ]
