from django.db import migrations, models


def infer_existing_transport_payers(apps, schema_editor):
    """Preserve the meaning of transport charges created before this field existed."""
    SalesOrder = apps.get_model('cigars', 'SalesOrder')
    SalesOrder.objects.filter(customer_transport_fee_cny__gt=0).update(
        transport_payer='customer',
    )


class Migration(migrations.Migration):

    dependencies = [
        ('cigars', '0034_purchase_batch_source'),
    ]

    operations = [
        migrations.AddField(
            model_name='salesorder',
            name='transport_payer',
            field=models.CharField(
                choices=[('customer', '客户承担'), ('company', '公司承担')],
                default='company',
                max_length=12,
                verbose_name='人肉费承担方',
            ),
        ),
        migrations.RunPython(
            infer_existing_transport_payers,
            migrations.RunPython.noop,
        ),
        migrations.AddConstraint(
            model_name='salesorder',
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(transport_payer='customer')
                    | models.Q(
                        transport_payer='company',
                        customer_transport_fee_cny=0,
                    )
                ),
                name='sales_order_transport_payer_fee_match',
            ),
        ),
    ]
