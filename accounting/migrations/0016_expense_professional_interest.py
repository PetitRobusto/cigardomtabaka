from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounting', '0015_day1initialization_draft_payload'),
    ]

    operations = [
        migrations.AlterField(
            model_name='expense',
            name='category',
            field=models.CharField(choices=[('salary', '工资'), ('rent', '房租'), ('utilities', '水电'), ('professional', '会计（专业服务）'), ('interest', '利息支出（财务费用）'), ('other', '其他')], max_length=20),
        ),
        migrations.AlterField(
            model_name='ledgerposting',
            name='category',
            field=models.CharField(blank=True, choices=[('opening_capital', '期初投入资本'), ('opening_retained_earnings', '期初未分配利润'), ('accounts_receivable', '应收款'), ('customer_prepayments', '客户预收款'), ('inventory', '库存'), ('', '资金账户'), ('sales_revenue', '销售收入'), ('customer_transport_revenue', '客户人肉费收入'), ('cost_of_goods_sold', '销售成本'), ('transport_expense', '人肉费用'), ('purchase_in_transit', '在途采购'), ('salary_expense', '工资费用'), ('rent_expense', '房租费用'), ('utilities_expense', '水电费用'), ('professional_expense', '会计（专业服务）'), ('interest_expense', '利息支出（财务费用）'), ('other_expense', '其他经营费用'), ('dividend_distribution', '分红分配'), ('inventory_adjustment_gain', '库存调整收益'), ('inventory_adjustment_loss', '库存调整损失'), ('reconciliation_gain', '对账收益'), ('reconciliation_loss', '对账损失')], max_length=48, verbose_name='内部分类'),
        ),
    ]
