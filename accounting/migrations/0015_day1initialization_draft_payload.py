from decimal import Decimal, DecimalException

from django.db import IntegrityError, migrations, models, transaction


PAYLOAD_KEYS = frozenset({'business_date', 'accounts', 'inventory'})
ACCOUNT_KEYS = frozenset({
    'slot', 'name', 'currency', 'original_amount', 'cny_book_cost',
})
INVENTORY_KEYS = frozenset({
    'cigar_id', 'box_size', 'box_quantity', 'loose_sticks', 'unit_cost_cny',
})
SLOT_CURRENCIES = {
    'owner_cny': 'CNY',
    'partner_cny': 'CNY',
    'rub': 'RUB',
    'usdt': 'USDT',
}


def require_exact_keys(value, expected, label):
    if set(value) != expected:
        raise RuntimeError(f'无法回滚：{label}包含旧表无法表达的字段')


def require_legacy_decimal(value, max_digits, decimal_places, label):
    try:
        decimal_value = Decimal(str(value))
        quantum = Decimal(1).scaleb(-decimal_places)
        quantized = decimal_value.quantize(quantum)
    except (DecimalException, TypeError, ValueError) as error:
        raise RuntimeError(f'无法回滚：{label}不是旧表可表达的金额') from error
    integer_limit = Decimal(10) ** (max_digits - decimal_places)
    if (
        not decimal_value.is_finite()
        or decimal_value != quantized
        or abs(decimal_value) >= integer_limit
    ):
        raise RuntimeError(f'无法回滚：{label}精度或范围超出旧表限制')
    return decimal_value


def require_legacy_integer(value, label, *, positive=False):
    if isinstance(value, bool) or not isinstance(value, int):
        raise RuntimeError(f'无法回滚：{label}不是整数')
    if (positive and value <= 0) or (not positive and value < 0):
        raise RuntimeError(f'无法回滚：{label}超出旧表限制')
    return value


def copy_legacy_draft_payload(apps, schema_editor):
    Day1Initialization = apps.get_model('accounting', 'Day1Initialization')
    Day1DraftAccount = apps.get_model('accounting', 'Day1DraftAccount')
    Day1DraftInventory = apps.get_model('accounting', 'Day1DraftInventory')

    for initialization in Day1Initialization.objects.filter(draft_payload={}):
        accounts = [
            {
                'slot': row.slot,
                'name': row.account_name,
                'currency': row.currency,
                'original_amount': str(row.original_amount),
                'cny_book_cost': str(row.cny_book_cost),
            }
            for row in Day1DraftAccount.objects.filter(
                initialization_id=initialization.pk,
            ).order_by('slot', 'id')
        ]
        inventory = [
            {
                'cigar_id': row.cigar_id,
                'box_size': row.box_size,
                'box_quantity': row.box_quantity,
                'loose_sticks': row.loose_sticks,
                'unit_cost_cny': str(row.unit_cost_cny),
            }
            for row in Day1DraftInventory.objects.filter(
                initialization_id=initialization.pk,
            ).order_by('cigar_id', 'box_size', 'id')
        ]
        initialization.draft_payload = {
            'business_date': (
                initialization.business_date.isoformat()
                if initialization.business_date else None
            ),
            'accounts': accounts,
            'inventory': inventory,
        }
        initialization.save(update_fields=['draft_payload'])


def restore_legacy_draft_rows(apps, schema_editor):
    Day1Initialization = apps.get_model('accounting', 'Day1Initialization')
    Day1DraftAccount = apps.get_model('accounting', 'Day1DraftAccount')
    Day1DraftInventory = apps.get_model('accounting', 'Day1DraftInventory')

    for initialization in Day1Initialization.objects.exclude(draft_payload={}):
        payload = initialization.draft_payload
        if not isinstance(payload, dict):
            raise RuntimeError('无法回滚：Day 1 JSON 草稿不是对象')
        require_exact_keys(payload, PAYLOAD_KEYS, 'Day 1 草稿')
        stored_date = payload.get('business_date')
        legacy_date = (
            initialization.business_date.isoformat()
            if initialization.business_date else None
        )
        if stored_date != legacy_date:
            raise RuntimeError('无法回滚：Day 1 草稿日期无法由旧表无损表达')
        accounts = payload.get('accounts')
        inventory = payload.get('inventory')
        if not isinstance(accounts, list) or not isinstance(inventory, list):
            raise RuntimeError('无法回滚：Day 1 JSON 草稿结构不完整')
        for row in accounts:
            if not isinstance(row, dict):
                raise RuntimeError('无法回滚：Day 1 账户草稿不是对象')
            require_exact_keys(row, ACCOUNT_KEYS, 'Day 1 账户草稿')
            if (
                row['slot'] not in SLOT_CURRENCIES
                or row['currency'] != SLOT_CURRENCIES[row['slot']]
                or not isinstance(row['name'], str)
                or len(row['name']) > 120
            ):
                raise RuntimeError('无法回滚：Day 1 账户草稿超出旧表限制')
            original_amount = require_legacy_decimal(
                row['original_amount'], 20, 8, 'Day 1 原币金额',
            )
            cny_book_cost = require_legacy_decimal(
                row['cny_book_cost'], 20, 2, 'Day 1 人民币账面成本',
            )
            if original_amount < 0 or cny_book_cost < 0:
                raise RuntimeError('无法回滚：Day 1 账户金额超出旧表限制')
            try:
                with transaction.atomic():
                    restored = Day1DraftAccount.objects.create(
                        initialization_id=initialization.pk,
                        slot=row['slot'],
                        account_name=row['name'],
                        currency=row['currency'],
                        original_amount=row['original_amount'],
                        cny_book_cost=row['cny_book_cost'],
                    )
                    stored = Day1DraftAccount.objects.get(pk=restored.pk)
                    if (
                        stored.original_amount != original_amount
                        or stored.cny_book_cost != cny_book_cost
                    ):
                        raise RuntimeError(
                            '无法回滚：Day 1 账户金额无法由旧表无损存储',
                        )
            except (DecimalException, IntegrityError, KeyError, TypeError, ValueError) as error:
                raise RuntimeError(
                    '无法回滚：Day 1 账户草稿无法由旧表无损表达',
                ) from error
        for row in inventory:
            if not isinstance(row, dict):
                raise RuntimeError('无法回滚：Day 1 库存草稿不是对象')
            require_exact_keys(row, INVENTORY_KEYS, 'Day 1 库存草稿')
            require_legacy_integer(row['cigar_id'], 'Day 1 雪茄 ID', positive=True)
            require_legacy_integer(row['box_size'], 'Day 1 盒规', positive=True)
            require_legacy_integer(row['box_quantity'], 'Day 1 整盒数量')
            require_legacy_integer(row['loose_sticks'], 'Day 1 散支数量')
            unit_cost = require_legacy_decimal(
                row['unit_cost_cny'], 12, 2, 'Day 1 单支成本',
            )
            if unit_cost < 0:
                raise RuntimeError('无法回滚：Day 1 单支成本超出旧表限制')
            try:
                with transaction.atomic():
                    restored = Day1DraftInventory.objects.create(
                        initialization_id=initialization.pk,
                        cigar_id=row['cigar_id'],
                        box_size=row['box_size'],
                        box_quantity=row['box_quantity'],
                        loose_sticks=row['loose_sticks'],
                        unit_cost_cny=row['unit_cost_cny'],
                    )
                    stored = Day1DraftInventory.objects.get(pk=restored.pk)
                    if stored.unit_cost_cny != unit_cost:
                        raise RuntimeError(
                            '无法回滚：Day 1 单支成本无法由旧表无损存储',
                        )
            except (DecimalException, IntegrityError, KeyError, TypeError, ValueError) as error:
                raise RuntimeError(
                    '无法回滚：Day 1 库存草稿无法由旧表无损表达',
                ) from error


class Migration(migrations.Migration):
    dependencies = [
        ('accounting', '0014_inventory_adjustment_transaction'),
    ]

    operations = [
        migrations.AddField(
            model_name='day1initialization',
            name='draft_payload',
            field=models.JSONField(blank=True, default=dict, verbose_name='原始草稿'),
        ),
        migrations.RunPython(copy_legacy_draft_payload, restore_legacy_draft_rows),
        migrations.DeleteModel(name='Day1DraftInventory'),
        migrations.DeleteModel(name='Day1DraftAccount'),
    ]
