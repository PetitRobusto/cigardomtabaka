from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('storefront', '0003_product_translation_identity')]

    operations = [
        migrations.AddField(
            model_name='storetranslation',
            name='seo_title',
            field=models.CharField('搜索标题（可选）', max_length=180, blank=True, default=''),
        ),
    ]
