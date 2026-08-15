from decimal import Decimal

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def _fits_decimal_domain(value, *, max_digits):
    """只接受能按字段小数位无损保存的旧快照/新 canonical 价格。"""
    if value is None or not value.is_finite():
        return False
    try:
        quantized = value.quantize(Decimal("0.01"))
    except Exception:
        return False
    if quantized != value:
        return False
    digits = len(value.as_tuple().digits)
    integer_digits = max(digits + value.as_tuple().exponent, 0)
    return integer_digits + 2 <= max_digits


def _fits_canonical_box_price(value):
    return _fits_decimal_domain(value, max_digits=22)


def _fits_legacy_price(value):
    return (
        value is not None
        and value.is_finite()
        and value >= 0
        and _fits_decimal_domain(value, max_digits=12)
    )


def _is_nonfinite_raw(value):
    if value is None:
        return False
    if isinstance(value, Decimal):
        return not value.is_finite()
    return str(value).strip().lower() in {
        "nan", "+nan", "-nan",
        "inf", "+inf", "-inf",
        "infinity", "+infinity", "-infinity",
    }


def _scrub_nonfinite_legacy_prices(schema_editor, PurchaseOrderItem):
    """Read bad legacy decimals without the ORM converter, then NULL them."""
    table = schema_editor.quote_name(PurchaseOrderItem._meta.db_table)
    rub_column = schema_editor.quote_name("unit_price_rub")
    cny_column = schema_editor.quote_name("unit_price_cny")
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(f"SELECT id, {rub_column}, {cny_column} FROM {table}")
        rows = cursor.fetchall()
        nonfinite_rub_ids = {row[0] for row in rows if _is_nonfinite_raw(row[1])}
        nonfinite_cny_ids = {row[0] for row in rows if _is_nonfinite_raw(row[2])}
        if nonfinite_rub_ids:
            placeholders = ", ".join(["%s"] * len(nonfinite_rub_ids))
            cursor.execute(
                f"UPDATE {table} SET {rub_column} = NULL WHERE id IN ({placeholders})",
                list(nonfinite_rub_ids),
            )
        if nonfinite_cny_ids:
            placeholders = ", ".join(["%s"] * len(nonfinite_cny_ids))
            cursor.execute(
                f"UPDATE {table} SET {cny_column} = NULL WHERE id IN ({placeholders})",
                list(nonfinite_cny_ids),
            )
    return nonfinite_rub_ids, nonfinite_cny_ids


def migrate_purchase_facts(apps, schema_editor):
    PurchaseOrder = apps.get_model("cigars", "PurchaseOrder")
    PurchaseOrderItem = apps.get_model("cigars", "PurchaseOrderItem")

    # 历史 received 只保留原状态；没有付款凭证时绝不伪造付款事实。
    PurchaseOrder.objects.filter(status="received").update(legacy_received=True)
    nonfinite_rub_ids, nonfinite_cny_ids = _scrub_nonfinite_legacy_prices(
        schema_editor, PurchaseOrderItem,
    )
    for item in PurchaseOrderItem.objects.all().iterator():
        quantity = item.quantity
        box_size = item.box_size
        unit_price_rub = item.unit_price_rub
        if quantity is None or quantity <= 0 or box_size is None or box_size <= 0 or quantity % box_size:
            item.packaging_status = "review_required"
            item.box_quantity = None
            item.unit_price_rub_per_box = None
            item.legacy_snapshot_status = "unrepresentable"
            item.save(update_fields=[
                "packaging_status", "box_quantity", "unit_price_rub_per_box",
                "legacy_snapshot_status",
            ])
            continue
        if item.pk in nonfinite_rub_ids or unit_price_rub is None or not unit_price_rub.is_finite():
            item.packaging_status = "review_required"
            item.box_quantity = None
            item.unit_price_rub_per_box = None
            item.legacy_snapshot_status = "unrepresentable"
            item.save(update_fields=[
                "packaging_status", "box_quantity", "unit_price_rub_per_box",
                "legacy_snapshot_status",
            ])
            continue
        # 负价是历史异常，不能被迁移标成可用 canonical 采购价格。
        if unit_price_rub < 0:
            item.packaging_status = "review_required"
            item.box_quantity = None
            item.unit_price_rub_per_box = None
            item.legacy_snapshot_status = "unrepresentable"
            item.save(update_fields=[
                "packaging_status", "box_quantity", "unit_price_rub_per_box",
                "legacy_snapshot_status",
            ])
            continue
        box_price = unit_price_rub * box_size
        if not _fits_canonical_box_price(box_price):
            # 盒数虽可推导，但每盒 RUB 本身超出 canonical 域，只能人工复核。
            item.packaging_status = "review_required"
            item.box_quantity = None
            item.unit_price_rub_per_box = None
            item.legacy_snapshot_status = "unrepresentable"
            item.save(update_fields=[
                "packaging_status", "box_quantity", "unit_price_rub_per_box",
                "legacy_snapshot_status",
            ])
            continue
        item.box_quantity = quantity // box_size
        item.unit_price_rub_per_box = box_price
        if not (_fits_legacy_price(unit_price_rub) and item.pk not in nonfinite_cny_ids and _fits_legacy_price(item.unit_price_cny)):
            # canonical 价格可保留；无法无损保留旧两列快照时清空，绝不伪造旧报价。
            item.unit_price_rub = None
            item.unit_price_cny = None
            item.packaging_status = "unrepresentable"
            item.legacy_snapshot_status = "unrepresentable"
            item.save(update_fields=[
                "unit_price_rub", "unit_price_cny", "box_quantity",
                "unit_price_rub_per_box", "packaging_status", "legacy_snapshot_status",
            ])
            continue
        item.packaging_status = "normalized"
        item.legacy_snapshot_status = "derived"
        item.save(update_fields=[
            "box_quantity", "unit_price_rub_per_box", "packaging_status",
            "legacy_snapshot_status",
        ])


def refuse_unsafe_reverse(apps, schema_editor):
    PurchaseOrder = apps.get_model("cigars", "PurchaseOrder")
    PurchaseOrderItem = apps.get_model("cigars", "PurchaseOrderItem")
    PurchaseBatch = apps.get_model("cigars", "PurchaseBatch")
    if PurchaseOrderItem.objects.filter(
        legacy_snapshot_status="unrepresentable", unit_price_rub__isnull=True
    ).exists():
        raise RuntimeError("0036 cannot reverse: canonical rows lost legacy price snapshots")
    if PurchaseOrder.objects.filter(
        exchange_rate__isnull=True
    ).exists() or PurchaseOrder.objects.filter(cny_total__isnull=True).exists():
        raise RuntimeError("0036 cannot reverse: canonical orders lack legacy quote snapshots")
    if PurchaseOrder.objects.filter(status="received", legacy_received=False).exists():
        raise RuntimeError("0036 cannot reverse: new received facts have no legacy equivalent")
    if PurchaseOrder.objects.filter(status="in_transit").exists():
        raise RuntimeError("0036 cannot reverse: in-transit status has no legacy equivalent")
    if PurchaseBatch.objects.filter(source="adjustment").exists():
        raise RuntimeError("0036 cannot reverse: adjustment batches use the new source value")


class Migration(migrations.Migration):
    dependencies = [("cigars", "0035_sales_order_transport_payer")]

    operations = [
        migrations.AlterField(
            model_name="purchaseorder",
            name="status",
            field=models.CharField(
                choices=[
                    ("draft", "草稿"),
                    ("in_transit", "在途"),
                    ("received", "已入库"),
                    ("cancelled", "已取消"),
                ], default="draft", max_length=20, verbose_name="状态",
            ),
        ),
        migrations.AlterField(
            model_name="purchaseorder",
            name="exchange_rate",
            field=models.DecimalField(
                blank=True, decimal_places=4, max_digits=10,
                null=True, verbose_name="汇率 (RUB→CNY)",
            ),
        ),
        migrations.AlterField(
            model_name="purchaseorder",
            name="cny_total",
            field=models.DecimalField(
                blank=True, decimal_places=2, max_digits=12,
                null=True, verbose_name="人民币总额",
            ),
        ),
        migrations.AddField(
            model_name="purchaseorder", name="paid_cny_cost",
            field=models.DecimalField(blank=True, decimal_places=2, default=Decimal("0.00"), max_digits=22, null=True, verbose_name="已付款人民币成本"),
        ),
        migrations.AddField(
            model_name="purchaseorder", name="paid_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="付款时间"),
        ),
        migrations.AddField(
            model_name="purchaseorder", name="payment_idempotency_key",
            field=models.CharField(blank=True, max_length=128, null=True, unique=True, verbose_name="付款幂等键"),
        ),
        migrations.AddField(
            model_name="purchaseorder", name="arrival_idempotency_key",
            field=models.CharField(blank=True, max_length=128, null=True, unique=True, verbose_name="到货幂等键"),
        ),
        migrations.AddField(
            model_name="purchaseorder", name="draft_idempotency_key",
            field=models.CharField(blank=True, max_length=128, null=True, unique=True, verbose_name="草稿幂等键"),
        ),
        migrations.AddField(
            model_name="purchaseorder", name="draft_request_fingerprint",
            field=models.CharField(blank=True, max_length=64, null=True, verbose_name="草稿请求摘要"),
        ),
        migrations.AddField(
            model_name="purchaseorder", name="draft_operator",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="+", to=settings.AUTH_USER_MODEL, verbose_name="草稿操作人"),
        ),
        migrations.AddField(
            model_name="purchaseorder", name="draft_business_date",
            field=models.DateField(blank=True, null=True, verbose_name="草稿业务日期"),
        ),
        migrations.AddField(
            model_name="purchaseorder", name="version",
            field=models.PositiveIntegerField(default=1, verbose_name="版本"),
        ),
        migrations.AddField(
            model_name="purchaseorder", name="legacy_received",
            field=models.BooleanField(default=False, verbose_name="历史已入库标记"),
        ),
        migrations.AlterField(
            model_name="purchaseorderitem", name="unit_price_rub",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True, verbose_name="卢布单价"),
        ),
        migrations.AlterField(
            model_name="purchaseorderitem", name="unit_price_cny",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True, verbose_name="人民币单价"),
        ),
        migrations.AddField(
            model_name="purchaseorderitem", name="box_quantity",
            field=models.PositiveIntegerField(blank=True, null=True, verbose_name="采购盒数"),
        ),
        migrations.AddField(
            model_name="purchaseorderitem", name="unit_price_rub_per_box",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=22, null=True, verbose_name="每盒卢布价格"),
        ),
        migrations.AddField(
            model_name="purchaseorderitem", name="packaging_status",
            field=models.CharField(choices=[("normalized", "已规范化"), ("review_required", "需人工复核"), ("unrepresentable", "兼容快照不可表示")], default="review_required", max_length=20, verbose_name="包装规范状态"),
        ),
        migrations.AddField(
            model_name="purchaseorderitem", name="actual_cost_cny",
            field=models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=22, verbose_name="实际人民币成本"),
        ),
        migrations.AddField(
            model_name="purchaseorderitem", name="legacy_snapshot_status",
            field=models.CharField(choices=[("explicit", "显式报价"), ("derived", "可逆派生"), ("unrepresentable", "不可表示")], default="unrepresentable", max_length=24, verbose_name="旧报价快照状态"),
        ),
        migrations.AlterField(
            model_name="purchasebatch", name="source",
            field=models.CharField(
                choices=[("purchase", "采购入库"), ("opening", "期初库存"), ("adjustment", "库存调整")],
                default="purchase", max_length=12, verbose_name="来源",
            ),
        ),
        migrations.RemoveConstraint(
            model_name="purchasebatch", name="purchase_batch_source_item_match",
        ),
        migrations.AddConstraint(
            model_name="purchasebatch",
            constraint=models.CheckConstraint(
                condition=(models.Q(source="purchase", purchase_order_item__isnull=False) | models.Q(source__in=["opening", "adjustment"], purchase_order_item__isnull=True)),
                name="purchase_batch_source_item_match",
            ),
        ),
        migrations.RunPython(migrate_purchase_facts, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="purchaseorder",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(status="draft", legacy_received=False, paid_cny_cost=Decimal("0.00"), paid_cny_cost__isnull=False, paid_at__isnull=True, payment_idempotency_key__isnull=True, arrival_idempotency_key__isnull=True)
                    | models.Q(status="in_transit", legacy_received=False, paid_cny_cost__gt=0, paid_cny_cost__isnull=False, paid_at__isnull=False)
                    | models.Q(status="received", legacy_received=False, paid_cny_cost__gt=0, paid_cny_cost__isnull=False, paid_at__isnull=False)
                    | models.Q(status="received", legacy_received=True, paid_at__isnull=True, paid_cny_cost__isnull=True)
                    | models.Q(status="received", legacy_received=True, paid_at__isnull=True, paid_cny_cost=Decimal("0.00"), paid_cny_cost__isnull=False)
                    | models.Q(status="cancelled", legacy_received=False, paid_cny_cost=Decimal("0.00"), paid_cny_cost__isnull=False, paid_at__isnull=True, payment_idempotency_key__isnull=True, arrival_idempotency_key__isnull=True)
                ), name="purchase_order_status_payment_consistent",
            ),
        ),
        migrations.AddConstraint(
            model_name="purchaseorderitem",
            constraint=models.CheckConstraint(condition=(models.Q(packaging_status="review_required", box_quantity__isnull=True, unit_price_rub_per_box__isnull=True) | models.Q(packaging_status="normalized", box_size__isnull=False, box_size__gt=0, box_quantity__isnull=False, box_quantity__gt=0, unit_price_rub_per_box__isnull=False, unit_price_rub_per_box__gte=0) | models.Q(packaging_status="unrepresentable", box_size__isnull=False, box_size__gt=0, box_quantity__isnull=False, box_quantity__gt=0, unit_price_rub_per_box__isnull=False, unit_price_rub_per_box__gte=0, unit_price_rub__isnull=True, unit_price_cny__isnull=True)), name="purchase_item_packaging_consistent"),
        ),
        migrations.AddConstraint(
            model_name="purchaseorderitem",
            constraint=models.CheckConstraint(condition=models.Q(actual_cost_cny__gte=0), name="purchase_item_actual_cost_nonnegative"),
        ),
        migrations.AddConstraint(
            model_name="purchaseorderitem",
            constraint=models.CheckConstraint(condition=(models.Q(packaging_status="review_required") | models.Q(packaging_status__in=["normalized", "unrepresentable"], quantity=models.F("box_size") * models.F("box_quantity"))), name="purchase_item_quantity_matches_boxes"),
        ),
        migrations.RunPython(migrations.RunPython.noop, refuse_unsafe_reverse),
    ]
