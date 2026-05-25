# Generated manually for rename: name → english_name + add Chinese name
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('cigars', '0008_add_brand_category_origin'),
    ]

    operations = [
        # === Brand: name → english_name, 新加 name (中文) ===
        migrations.RenameField(
            model_name='brand',
            old_name='name',
            new_name='english_name',
        ),
        migrations.AlterField(
            model_name='brand',
            name='english_name',
            field=models.CharField(max_length=100, unique=True, verbose_name='品牌英文名'),
        ),
        migrations.AddField(
            model_name='brand',
            name='name',
            field=models.CharField(blank=True, max_length=100, verbose_name='品牌中文名'),
        ),
        migrations.AlterModelOptions(
            name='brand',
            options={'ordering': ['english_name'], 'verbose_name': '品牌', 'verbose_name_plural': '品牌'},
        ),

        # === Cigar: name → english_name, 新加 name (中文) ===
        migrations.AlterUniqueTogether(
            name='cigar',
            unique_together=set(),
        ),
        migrations.RenameField(
            model_name='cigar',
            old_name='name',
            new_name='english_name',
        ),
        migrations.AlterField(
            model_name='cigar',
            name='english_name',
            field=models.CharField(max_length=200, verbose_name='英文品名'),
        ),
        migrations.AddField(
            model_name='cigar',
            name='name',
            field=models.CharField(blank=True, max_length=200, verbose_name='中文品名'),
        ),
        migrations.AlterUniqueTogether(
            name='cigar',
            unique_together={('brand', 'english_name', 'release_type')},
        ),
        migrations.AlterModelOptions(
            name='cigar',
            options={'ordering': ['brand', 'english_name'], 'verbose_name': '雪茄', 'verbose_name_plural': '雪茄'},
        ),
    ]
