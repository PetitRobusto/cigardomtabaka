from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounting", "0013_draft_actions")]
    operations = [migrations.AlterField(
        model_name="ledgertransaction", name="transaction_type",
        field=models.CharField(choices=[
            ("opening_balance", "期初余额"), ("day1_opening", "Day 1 期初资产"),
            ("exchange", "换汇"), ("transfer", "同币种转账"),
            ("sales_shipment", "销售出库"), ("sales_receipt", "销售收款"),
            ("sales_transport_cost", "销售人肉费"), ("sales_refund", "销售退款"),
            ("purchase_payment", "采购付款"), ("purchase_receipt", "采购到货"),
            ("expense", "经营费用"), ("dividend", "分红"),
            ("inventory_adjustment", "库存调整"),
        ], max_length=32, verbose_name="交易类型")
    )]
