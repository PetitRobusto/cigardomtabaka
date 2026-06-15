# Generated manually for agent order/inventory command API.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cigars', '0019_decimal_money_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='salesorderitem',
            name='fulfillment_type',
            field=models.CharField(
                choices=[('in_stock', '现货'), ('preorder', '预售')],
                default='in_stock',
                max_length=20,
                verbose_name='履约类型',
            ),
        ),
        migrations.CreateModel(
            name='IdempotencyRecord',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('key', models.CharField(max_length=255, unique=True, verbose_name='幂等键')),
                ('command_name', models.CharField(max_length=100, verbose_name='命令')),
                ('request_hash', models.CharField(max_length=64, verbose_name='请求摘要')),
                ('request_body', models.JSONField(default=dict, verbose_name='请求体')),
                ('response_body', models.JSONField(default=dict, verbose_name='首次响应')),
                ('status_code', models.IntegerField(default=200, verbose_name='HTTP 状态码')),
                ('agent_name', models.CharField(max_length=100, verbose_name='Agent 名称')),
                ('agent_run_id', models.CharField(blank=True, max_length=200, verbose_name='Agent Run ID')),
                ('agent_request_id', models.CharField(blank=True, max_length=200, verbose_name='Agent Request ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='创建时间')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='更新时间')),
                ('operator', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='idempotency_records', to=settings.AUTH_USER_MODEL, verbose_name='操作人')),
            ],
            options={
                'verbose_name': '幂等记录',
                'verbose_name_plural': '幂等记录',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='OrderEvent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('agent_name', models.CharField(blank=True, max_length=100, verbose_name='Agent 名称')),
                ('agent_run_id', models.CharField(blank=True, max_length=200, verbose_name='Agent Run ID')),
                ('agent_request_id', models.CharField(blank=True, max_length=200, verbose_name='Agent Request ID')),
                ('command_name', models.CharField(max_length=100, verbose_name='命令')),
                ('note', models.TextField(blank=True, verbose_name='备注')),
                ('metadata', models.JSONField(blank=True, default=dict, verbose_name='上下文')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='创建时间')),
                ('operator', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='order_events', to=settings.AUTH_USER_MODEL, verbose_name='操作人')),
                ('sales_order', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='events', to='cigars.salesorder', verbose_name='销售单')),
            ],
            options={
                'verbose_name': '订单事件',
                'verbose_name_plural': '订单事件',
                'ordering': ['created_at', 'id'],
            },
        ),
        migrations.CreateModel(
            name='StockAllocation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('quantity', models.IntegerField(verbose_name='数量')),
                ('status', models.CharField(choices=[('reserved', '已预留'), ('fulfilled', '已出库'), ('released', '已释放')], default='reserved', max_length=20, verbose_name='状态')),
                ('reserved_at', models.DateTimeField(auto_now_add=True, verbose_name='预留时间')),
                ('fulfilled_at', models.DateTimeField(blank=True, null=True, verbose_name='出库时间')),
                ('released_at', models.DateTimeField(blank=True, null=True, verbose_name='释放时间')),
                ('purchase_batch', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='stock_allocations', to='cigars.purchasebatch', verbose_name='采购批次')),
                ('sales_order_item', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='allocations', to='cigars.salesorderitem', verbose_name='销售明细')),
            ],
            options={
                'verbose_name': '库存分配',
                'verbose_name_plural': '库存分配',
                'ordering': ['id'],
            },
        ),
        migrations.CreateModel(
            name='StockMovement',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('movement_type', models.CharField(choices=[('receive', '入库'), ('reserve', '预留'), ('release_reservation', '释放预留'), ('ship', '出库'), ('adjustment', '库存修正')], max_length=30, verbose_name='类型')),
                ('quantity', models.IntegerField(verbose_name='数量')),
                ('agent_name', models.CharField(blank=True, max_length=100, verbose_name='Agent 名称')),
                ('agent_run_id', models.CharField(blank=True, max_length=200, verbose_name='Agent Run ID')),
                ('agent_request_id', models.CharField(blank=True, max_length=200, verbose_name='Agent Request ID')),
                ('command_name', models.CharField(blank=True, max_length=100, verbose_name='命令')),
                ('idempotency_key', models.CharField(blank=True, max_length=255, verbose_name='幂等键')),
                ('note', models.TextField(blank=True, verbose_name='备注')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='创建时间')),
                ('cigar', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='cigars.cigar', verbose_name='雪茄')),
                ('operator', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='stock_movements', to=settings.AUTH_USER_MODEL, verbose_name='操作人')),
                ('purchase_batch', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='stock_movements', to='cigars.purchasebatch', verbose_name='采购批次')),
                ('sales_order', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='stock_movements', to='cigars.salesorder', verbose_name='销售单')),
                ('sales_order_item', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='stock_movements', to='cigars.salesorderitem', verbose_name='销售明细')),
            ],
            options={
                'verbose_name': '库存流水',
                'verbose_name_plural': '库存流水',
                'ordering': ['-created_at', '-id'],
            },
        ),
        migrations.AddIndex(
            model_name='idempotencyrecord',
            index=models.Index(fields=['command_name', 'created_at'], name='cigars_idem_command_d7ce50_idx'),
        ),
        migrations.AddIndex(
            model_name='idempotencyrecord',
            index=models.Index(fields=['agent_name', 'created_at'], name='cigars_idem_agent_n_f67dd9_idx'),
        ),
        migrations.AddIndex(
            model_name='orderevent',
            index=models.Index(fields=['sales_order', 'created_at'], name='cigars_orde_sales_o_a5ab6c_idx'),
        ),
        migrations.AddIndex(
            model_name='orderevent',
            index=models.Index(fields=['command_name', 'created_at'], name='cigars_orde_command_ac399e_idx'),
        ),
        migrations.AddIndex(
            model_name='stockallocation',
            index=models.Index(fields=['sales_order_item', 'status'], name='cigars_stoc_sales_o_8103d6_idx'),
        ),
        migrations.AddIndex(
            model_name='stockallocation',
            index=models.Index(fields=['purchase_batch', 'status'], name='cigars_stoc_purchas_ed839a_idx'),
        ),
        migrations.AddIndex(
            model_name='stockmovement',
            index=models.Index(fields=['cigar', 'created_at'], name='cigars_stoc_cigar_i_383431_idx'),
        ),
        migrations.AddIndex(
            model_name='stockmovement',
            index=models.Index(fields=['purchase_batch', 'created_at'], name='cigars_stoc_purchas_3522af_idx'),
        ),
        migrations.AddIndex(
            model_name='stockmovement',
            index=models.Index(fields=['sales_order', 'created_at'], name='cigars_stoc_sales_o_bd9919_idx'),
        ),
        migrations.AddIndex(
            model_name='stockmovement',
            index=models.Index(fields=['movement_type', 'created_at'], name='cigars_stoc_movemen_7f20d7_idx'),
        ),
        migrations.AddIndex(
            model_name='stockmovement',
            index=models.Index(fields=['idempotency_key'], name='cigars_stoc_idempot_296a23_idx'),
        ),
    ]
