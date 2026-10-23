from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("storefront", "0001_initial")]

    operations = [
        migrations.AlterField(
            model_name="storetranslation",
            name="body",
            field=models.TextField(blank=True, verbose_name="正文（纯文本）"),
        ),
    ]
