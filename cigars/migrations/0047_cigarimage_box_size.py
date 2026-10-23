from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cigars', '0046_cigarprice_retail_price_rub_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='cigarimage',
            name='box_size',
            field=models.PositiveIntegerField(
                blank=True,
                help_text='仅包装或特殊包装图片可填写；未知或未核实的盒规留空',
                null=True,
                verbose_name='对应盒规',
            ),
        ),
        migrations.AddConstraint(
            model_name='cigarimage',
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(('box_size__isnull', True))
                    | models.Q(('box_size__gt', 0), ('image_type__in', ['packaging', 'special']))
                ),
                name='cigar_image_box_size_requires_packaging_type',
            ),
        ),
    ]
