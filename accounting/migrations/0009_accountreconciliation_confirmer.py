from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('accounting', '0008_accountreconciliation_idempotency_keys')]
    operations = [
        migrations.AddField(
            model_name='accountreconciliation', name='confirmer',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                related_name='confirmed_account_reconciliations',
                to=settings.AUTH_USER_MODEL, verbose_name='确认人',
            ),
        ),
    ]
