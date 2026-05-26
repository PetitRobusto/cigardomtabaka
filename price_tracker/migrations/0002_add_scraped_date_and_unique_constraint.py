"""Add scraped_date and unique constraint to PriceSnapshot"""
from django.db import migrations, models
from django.utils import timezone


def backfill_scraped_date(apps, schema_editor):
    """Set scraped_date from scraped_at for existing rows"""
    PriceSnapshot = apps.get_model('price_tracker', 'PriceSnapshot')
    db_alias = schema_editor.connection.alias
    for obj in PriceSnapshot.objects.using(db_alias).iterator():
        obj.scraped_date = obj.scraped_at.date()
        obj.save(update_fields=['scraped_date'])


class Migration(migrations.Migration):

    dependencies = [
        ('price_tracker', '0001_initial'),
    ]

    operations = [
        # Step 1: Add nullable scraped_date for existing rows
        migrations.AddField(
            model_name='pricesnapshot',
            name='scraped_date',
            field=models.DateField(
                verbose_name='抓取日期',
                null=True,
            ),
        ),
        # Step 2: Backfill from scraped_at
        migrations.RunPython(
            backfill_scraped_date,
            reverse_code=migrations.RunPython.noop,
        ),
        # Step 3: Make non-nullable with auto_now_add for new rows
        migrations.AlterField(
            model_name='pricesnapshot',
            name='scraped_date',
            field=models.DateField(
                auto_now_add=True,
                verbose_name='抓取日期',
            ),
        ),
        # Step 4: Add unique constraint
        migrations.AddConstraint(
            model_name='pricesnapshot',
            constraint=models.UniqueConstraint(
                fields=['cigar', 'source', 'box_size', 'scraped_date'],
                name='uq_snapshot_per_day',
            ),
        ),
    ]
