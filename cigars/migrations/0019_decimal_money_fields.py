from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cigars', '0018_cigarprice_can_preorder'),
    ]

    operations = [
        migrations.AlterField(
            model_name='adjustmentrecord',
            name='unit_cost_cny',
            field=models.DecimalField(decimal_places=2, max_digits=12, verbose_name='成本/支 (CNY)'),
        ),
        migrations.AlterField(
            model_name='purchasebatch',
            name='unit_cost_cny',
            field=models.DecimalField(decimal_places=2, max_digits=12, verbose_name='人民币成本单价'),
        ),
        migrations.AlterField(
            model_name='purchaseorder',
            name='cny_total',
            field=models.DecimalField(decimal_places=2, max_digits=12, verbose_name='人民币总额'),
        ),
        migrations.AlterField(
            model_name='purchaseorder',
            name='exchange_rate',
            field=models.DecimalField(decimal_places=4, max_digits=10, verbose_name='汇率 (RUB→CNY)'),
        ),
        migrations.AlterField(
            model_name='purchaseorder',
            name='rub_total',
            field=models.DecimalField(decimal_places=2, max_digits=12, verbose_name='卢布总额'),
        ),
        migrations.AlterField(
            model_name='purchaseorderitem',
            name='unit_price_cny',
            field=models.DecimalField(decimal_places=2, max_digits=12, verbose_name='人民币单价'),
        ),
        migrations.AlterField(
            model_name='purchaseorderitem',
            name='unit_price_rub',
            field=models.DecimalField(decimal_places=2, max_digits=12, verbose_name='卢布单价'),
        ),
        migrations.AlterField(
            model_name='salesorder',
            name='total_cost',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12, verbose_name='成本合计'),
        ),
        migrations.AlterField(
            model_name='salesorder',
            name='total_profit',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12, verbose_name='利润合计'),
        ),
        migrations.AlterField(
            model_name='salesorder',
            name='total_revenue',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12, verbose_name='收入合计'),
        ),
        migrations.AlterField(
            model_name='salesorderitem',
            name='cost',
            field=models.DecimalField(decimal_places=2, max_digits=12, verbose_name='成本'),
        ),
        migrations.AlterField(
            model_name='salesorderitem',
            name='profit',
            field=models.DecimalField(decimal_places=2, max_digits=12, verbose_name='利润'),
        ),
        migrations.AlterField(
            model_name='salesorderitem',
            name='revenue',
            field=models.DecimalField(decimal_places=2, max_digits=12, verbose_name='收入'),
        ),
        migrations.AlterField(
            model_name='salesorderitem',
            name='unit_cost',
            field=models.DecimalField(decimal_places=2, max_digits=12, verbose_name='成本/支 (CNY)'),
        ),
        migrations.AlterField(
            model_name='salesorderitem',
            name='unit_price',
            field=models.DecimalField(decimal_places=2, max_digits=12, verbose_name='售价/支 (CNY)'),
        ),
    ]
