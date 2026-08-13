from django.db import migrations, models


def backfill_creation_keys(apps, schema_editor):
    reconciliation_model = apps.get_model('accounting', 'AccountReconciliation')
    for record in reconciliation_model.objects.order_by('pk').iterator():
        record.creation_idempotency_key = f'legacy-reconciliation-{record.pk}'
        record.save(update_fields=['creation_idempotency_key'])


class Migration(migrations.Migration):

    dependencies = [
        ('accounting', '0007_accountreconciliation'),
    ]

    operations = [
        migrations.AddField(
            model_name='accountreconciliation',
            name='creation_idempotency_key',
            field=models.CharField(null=True, max_length=128, unique=True, verbose_name='创建幂等键'),
        ),
        migrations.AddField(
            model_name='accountreconciliation',
            name='confirmation_idempotency_key',
            field=models.CharField(blank=True, max_length=128, null=True, unique=True, verbose_name='确认幂等键'),
        ),
        migrations.RunPython(
            backfill_creation_keys,
            migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name='accountreconciliation',
            name='creation_idempotency_key',
            field=models.CharField(max_length=128, unique=True, verbose_name='创建幂等键'),
        ),
    ]
