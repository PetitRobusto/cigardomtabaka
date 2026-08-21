from decimal import Decimal

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('cigars', '0039_inventory_reversal_audit'),
    ]

    operations = [
        migrations.AddField(
            model_name='supplier',
            name='creation_idempotency_key',
            field=models.CharField(blank=True, max_length=128, null=True, unique=True, verbose_name='创建幂等键'),
        ),
        migrations.AlterField(
            model_name='purchaseorder',
            name='supplier',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='cigars.supplier', verbose_name='供应商'),
        ),
        migrations.AlterField(
            model_name='purchaseorder',
            name='rub_total',
            field=models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=12, verbose_name='卢布总额'),
        ),
        migrations.RemoveConstraint(
            model_name='purchaseorderitem',
            name='purchase_item_packaging_consistent',
        ),
        migrations.AddConstraint(
            model_name='purchaseorderitem',
            constraint=models.CheckConstraint(
                condition=(
                    (
                        models.Q(packaging_status='review_required')
                        & (models.Q(box_size__isnull=True) | models.Q(box_size__gte=0))
                        & (models.Q(box_quantity__isnull=True) | models.Q(box_quantity__gte=0))
                        & (models.Q(unit_price_rub_per_box__isnull=True) | models.Q(unit_price_rub_per_box__gte=0))
                    )
                    | models.Q(packaging_status='normalized', box_size__isnull=False, box_size__gt=0, box_quantity__isnull=False, box_quantity__gt=0, unit_price_rub_per_box__isnull=False, unit_price_rub_per_box__gte=0)
                    | models.Q(packaging_status='unrepresentable', box_size__isnull=False, box_size__gt=0, box_quantity__isnull=False, box_quantity__gt=0, unit_price_rub_per_box__isnull=False, unit_price_rub_per_box__gte=0, unit_price_rub__isnull=True, unit_price_cny__isnull=True)
                ),
                name='purchase_item_packaging_consistent',
            ),
        ),
    ]
