"""Trusted service boundary for one-time company Day 1 initialization."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
import hashlib
import json

from django.db import transaction
from django.utils import timezone

from accounting.business_time import moscow_business_date
from accounting.models import (
    Day1DraftAccount, Day1DraftInventory, Day1Initialization,
    FundAccount, LedgerPosting, LedgerTransaction,
)
from accounting.services import (
    CUTOVER_DATE, CNY_PLACES, ORIGINAL_PLACES, LedgerError, PostingInput,
    _acquire_sqlite_writer_gate, _post_day1_opening, _require_operator,
    _retry_sqlite_locked,
    _strict_external_decimal,
)
from cigars.models import Cigar, PurchaseBatch, StockMovement


class Day1Error(LedgerError):
    pass


class Day1ValidationError(Day1Error):
    def __init__(self, message='期初初始化草稿无效', details=None):
        super().__init__(message)
        self.details = details or {}


class Day1VersionConflict(Day1Error):
    pass


class Day1Conflict(Day1Error):
    def __init__(self, message='期初初始化前提冲突', conflicts=None):
        super().__init__(message)
        self.conflicts = tuple(conflicts or ())


@dataclass(frozen=True)
class Day1ConfirmationResult:
    initialization_id: int
    version: int
    business_date: date
    retained_earnings_cny: Decimal
    opening_capital_cny: Decimal
    total_net_assets_cny: Decimal
    accounts_total_cny: Decimal
    inventory_total_cny: Decimal
    completion_summary: dict


_SLOTS = (
    Day1DraftAccount.Slot.OWNER_CNY,
    Day1DraftAccount.Slot.PARTNER_CNY,
    Day1DraftAccount.Slot.RUB,
    Day1DraftAccount.Slot.USDT,
)
_SLOT_CURRENCIES = {
    Day1DraftAccount.Slot.OWNER_CNY: FundAccount.Currency.CNY,
    Day1DraftAccount.Slot.PARTNER_CNY: FundAccount.Currency.CNY,
    Day1DraftAccount.Slot.RUB: FundAccount.Currency.RUB,
    Day1DraftAccount.Slot.USDT: FundAccount.Currency.USDT,
}


def get_day1_state():
    """Read the singleton without creating a draft."""
    return Day1Initialization.objects.prefetch_related(
        'draft_accounts', 'draft_inventory',
    ).filter(singleton_key='company').first()


def get_or_create_day1_draft():
    return Day1Initialization.objects.get_or_create(singleton_key='company')[0]


def _money(value, places, field):
    try:
        return _strict_external_decimal(value, places, field)
    except LedgerError as error:
        raise Day1ValidationError(str(error), {field: str(error)})


def _date(value):
    if isinstance(value, date) and not hasattr(value, 'hour'):
        result = value
    elif isinstance(value, str):
        try:
            result = date.fromisoformat(value)
        except ValueError:
            raise Day1ValidationError(details={'business_date': '必须是有效日期'})
    else:
        raise Day1ValidationError(details={'business_date': '必须是日期'})
    if result < CUTOVER_DATE:
        raise Day1ValidationError(details={'business_date': '不能早于账务切换日'})
    if result > moscow_business_date():
        raise Day1ValidationError(details={'business_date': '不能晚于莫斯科当前业务日'})
    return result


def _integer(value, field, positive=False):
    if isinstance(value, bool) or not isinstance(value, int):
        raise Day1ValidationError(details={field: '必须是整数'})
    if (positive and value <= 0) or (not positive and value < 0):
        raise Day1ValidationError(details={field: '必须为正数' if positive else '不能为负'})
    return value


def _declared_box_sizes(cigar):
    if not cigar.packagings:
        return set()
    try:
        data = json.loads(cigar.packagings)
    except (TypeError, json.JSONDecodeError):
        return set()
    if isinstance(data, dict):
        candidates = data.get('box_sizes', [])
    elif isinstance(data, list):
        candidates = [
            item.get('size') if isinstance(item, dict) else item
            for item in data
        ]
    else:
        return set()
    return {
        value for value in candidates
        if isinstance(value, int) and not isinstance(value, bool) and value > 0
    }


def _normalize_payload(payload):
    if not isinstance(payload, dict):
        raise Day1ValidationError(details={'payload': '必须是对象'})
    business_date = _date(payload.get('business_date'))
    accounts = payload.get('accounts')
    inventory = payload.get('inventory')
    if not isinstance(accounts, (list, tuple)) or len(accounts) != 4:
        raise Day1ValidationError(details={'accounts': '必须恰好包含四个固定账户槽位'})
    if not isinstance(inventory, (list, tuple)):
        raise Day1ValidationError(details={'inventory': '必须是列表'})
    slots, names, normalized_accounts = set(), set(), []
    for index, row in enumerate(accounts):
        if not isinstance(row, dict):
            raise Day1ValidationError(details={f'accounts[{index}]': '必须是对象'})
        slot = row.get('slot')
        if slot not in _SLOT_CURRENCIES or slot in slots:
            raise Day1ValidationError(details={f'accounts[{index}].slot': '固定账户槽位无效或重复'})
        slots.add(slot)
        currency = row.get('currency')
        if currency != _SLOT_CURRENCIES[slot]:
            raise Day1ValidationError(details={f'accounts[{index}].currency': '币种与固定槽位不匹配'})
        name = row.get('name', row.get('account_name'))
        if not isinstance(name, str) or not name.strip() or name in names:
            raise Day1ValidationError(details={f'accounts[{index}].name': '账户名称不能为空且不可重复'})
        names.add(name)
        original = _money(row.get('original_amount'), ORIGINAL_PLACES[currency], f'accounts[{index}].original_amount')
        cost = _money(row.get('cny_book_cost'), CNY_PLACES, f'accounts[{index}].cny_book_cost')
        if original < 0 or cost < 0:
            raise Day1ValidationError(details={f'accounts[{index}]': '金额不能为负'})
        if currency == FundAccount.Currency.CNY and original != cost:
            raise Day1ValidationError(details={f'accounts[{index}]': '人民币原币金额必须等于账面成本'})
        if currency != FundAccount.Currency.CNY and ((original == 0) != (cost == 0)):
            raise Day1ValidationError(details={f'accounts[{index}]': '外币原币金额与账面成本必须同时为零或同时为正'})
        normalized_accounts.append({
            'slot': slot, 'name': name, 'currency': currency,
            'original_amount': original, 'cny_book_cost': cost,
        })
    if slots != set(_SLOTS):
        raise Day1ValidationError(details={'accounts': '必须包含全部固定账户槽位'})
    normalized_inventory, unique_inventory = [], set()
    for index, row in enumerate(inventory):
        if not isinstance(row, dict):
            raise Day1ValidationError(details={f'inventory[{index}]': '必须是对象'})
        cigar_id = row.get('cigar_id')
        if isinstance(cigar_id, bool) or not isinstance(cigar_id, int):
            raise Day1ValidationError(details={f'inventory[{index}].cigar_id': '雪茄不存在'})
        cigar = Cigar.objects.filter(pk=cigar_id).only('id', 'packagings').first()
        if cigar is None:
            raise Day1ValidationError(details={f'inventory[{index}].cigar_id': '雪茄不存在'})
        box_size = _integer(row.get('box_size'), f'inventory[{index}].box_size', True)
        declared_box_sizes = _declared_box_sizes(cigar)
        if declared_box_sizes and box_size not in declared_box_sizes:
            raise Day1ValidationError(details={
                f'inventory[{index}].box_size': '包装规格不在雪茄目录中',
            })
        box_quantity = _integer(row.get('box_quantity'), f'inventory[{index}].box_quantity')
        loose_sticks = _integer(row.get('loose_sticks'), f'inventory[{index}].loose_sticks')
        unit_cost = _money(row.get('unit_cost_cny'), CNY_PLACES, f'inventory[{index}].unit_cost_cny')
        if unit_cost <= 0:
            raise Day1ValidationError(details={f'inventory[{index}].unit_cost_cny': '单支成本必须大于零'})
        if box_quantity * box_size + loose_sticks <= 0:
            raise Day1ValidationError(details={f'inventory[{index}]': '库存数量必须大于零'})
        key = (cigar_id, box_size)
        if key in unique_inventory:
            raise Day1ValidationError(details={f'inventory[{index}]': '雪茄和包装规格不可重复'})
        unique_inventory.add(key)
        normalized_inventory.append({
            'cigar_id': cigar_id, 'box_size': box_size, 'box_quantity': box_quantity,
            'loose_sticks': loose_sticks, 'unit_cost_cny': unit_cost,
        })
    return {'business_date': business_date, 'accounts': normalized_accounts, 'inventory': normalized_inventory}


@transaction.atomic
def save_day1_draft(*, payload, expected_version, operator):
    persisted_operator = _require_operator(operator)
    if isinstance(expected_version, bool) or not isinstance(expected_version, int) or expected_version < 0:
        raise Day1VersionConflict('草稿版本无效')
    normalized = _normalize_payload(payload)
    _acquire_sqlite_writer_gate()
    initialization = Day1Initialization.objects.select_for_update().filter(singleton_key='company').first()
    if initialization is None:
        if expected_version != 0:
            raise Day1VersionConflict('草稿版本已变化')
        initialization = Day1Initialization.objects.create(
            singleton_key='company', version=1, business_date=normalized['business_date'],
            updated_by=persisted_operator,
        )
    else:
        if initialization.status == Day1Initialization.Status.COMPLETED:
            raise Day1Conflict('期初初始化已完成，草稿不可修改', ['completed'])
        if expected_version != initialization.version:
            raise Day1VersionConflict(
                f'草稿版本冲突：expected={expected_version}, actual={initialization.version}',
            )
        initialization.version += 1
        initialization.business_date = normalized['business_date']
        initialization.updated_by = persisted_operator
        initialization.save(update_fields=['version', 'business_date', 'updated_by', 'updated_at'])
    initialization.draft_accounts.all().delete()
    initialization.draft_inventory.all().delete()
    Day1DraftAccount.objects.bulk_create([
        Day1DraftAccount(
            initialization=initialization, slot=row['slot'], account_name=row['name'],
            currency=row['currency'], original_amount=row['original_amount'],
            cny_book_cost=row['cny_book_cost'],
        ) for row in normalized['accounts']
    ])
    Day1DraftInventory.objects.bulk_create([
        Day1DraftInventory(initialization=initialization, **row)
        for row in normalized['inventory']
    ])
    return initialization


def _snapshot_payload(initialization):
    return {
        'business_date': initialization.business_date.isoformat(),
        'accounts': [
            {
                'slot': row.slot, 'name': row.account_name, 'currency': row.currency,
                'original_amount': str(row.original_amount), 'cny_book_cost': str(row.cny_book_cost),
            }
            for row in initialization.draft_accounts.order_by('slot', 'id')
        ],
        'inventory': [
            {
                'cigar_id': row.cigar_id, 'box_size': row.box_size,
                'box_quantity': row.box_quantity, 'loose_sticks': row.loose_sticks,
                'unit_cost_cny': str(row.unit_cost_cny),
            }
            for row in initialization.draft_inventory.order_by('cigar_id', 'box_size', 'id')
        ],
    }


def _request_hash(initialization):
    encoded = json.dumps(_snapshot_payload(initialization), ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(encoded.encode('utf-8')).hexdigest()


def _result_from_summary(initialization):
    summary = initialization.completion_summary
    return Day1ConfirmationResult(
        initialization_id=initialization.pk, version=initialization.version,
        business_date=initialization.business_date,
        retained_earnings_cny=Decimal(summary['retained_earnings_cny']),
        opening_capital_cny=Decimal(summary['opening_capital_cny']),
        total_net_assets_cny=Decimal(summary['total_net_assets_cny']),
        accounts_total_cny=Decimal(summary['accounts_total_cny']),
        inventory_total_cny=Decimal(summary['inventory_total_cny']),
        completion_summary=dict(summary),
    )


def _conflicts_for_confirmation():
    conflicts = []
    if FundAccount.objects.exists():
        conflicts.append('fund_accounts_exist')
    if LedgerTransaction.objects.filter(status=LedgerTransaction.Status.POSTED).exists():
        conflicts.append('posted_ledger_exists')
    if PurchaseBatch.objects.exists():
        conflicts.append('purchase_batches_exist')
    if StockMovement.objects.exists():
        conflicts.append('stock_movements_exist')
    return conflicts


@_retry_sqlite_locked
@transaction.atomic
def confirm_day1(*, expected_version, operator, idempotency_key):
    persisted_operator = _require_operator(operator)
    if not isinstance(idempotency_key, str) or not idempotency_key or len(idempotency_key) > 128:
        raise Day1ValidationError(details={'idempotency_key': '幂等键无效'})
    _acquire_sqlite_writer_gate()
    initialization = Day1Initialization.objects.select_for_update().filter(singleton_key='company').first()
    if initialization is None:
        raise Day1Conflict('尚未保存期初初始化草稿', ['draft_missing'])
    if initialization.status == Day1Initialization.Status.COMPLETED:
        return _result_from_summary(initialization)
    if expected_version != initialization.version:
        raise Day1VersionConflict(
            f'草稿版本冲突：expected={expected_version}, actual={initialization.version}',
        )
    conflicts = _conflicts_for_confirmation()
    if conflicts:
        raise Day1Conflict('期初初始化前提冲突', conflicts)
    _normalize_payload(_snapshot_payload(initialization))
    accounts = list(initialization.draft_accounts.order_by('slot', 'id'))
    inventory = list(initialization.draft_inventory.order_by('cigar_id', 'box_size', 'id'))
    if len(accounts) != 4 or {row.slot for row in accounts} != set(_SLOTS):
        raise Day1ValidationError(details={'accounts': '草稿账户槽位不完整'})

    account_objects = {}
    for row in accounts:
        account_objects[row.slot] = FundAccount.objects.create(
            name=row.account_name, currency=row.currency,
            custodian=persisted_operator,
            creation_idempotency_key=f'day1:{initialization.pk}:{row.slot}',
        )
    total_accounts = sum((row.cny_book_cost for row in accounts), Decimal('0.00')).quantize(CNY_PLACES)
    total_inventory = Decimal('0.00')
    postings = [
        PostingInput(
            account=account_objects[row.slot], currency=row.currency,
            amount=row.original_amount, cny_amount=row.cny_book_cost,
        ) for row in accounts
        if row.original_amount != 0 or row.cny_book_cost != 0
    ]
    for row in inventory:
        quantity = row.box_quantity * row.box_size + row.loose_sticks
        cost = (Decimal(quantity) * row.unit_cost_cny).quantize(CNY_PLACES)
        total_inventory += cost
    total_inventory = total_inventory.quantize(CNY_PLACES)
    if total_inventory:
        postings.append(PostingInput(
            category=LedgerPosting.Category.INVENTORY,
            currency=FundAccount.Currency.CNY,
            amount=total_inventory,
            cny_amount=total_inventory,
        ))
    total_assets = (total_accounts + total_inventory).quantize(CNY_PLACES)
    if total_assets <= 0:
        raise Day1ValidationError(details={'assets': '期初净资产必须大于零'})
    postings.append(PostingInput(
        category=LedgerPosting.Category.OPENING_CAPITAL,
        currency=FundAccount.Currency.CNY, amount=-total_assets, cny_amount=-total_assets,
    ))
    transaction_record = _post_day1_opening(
        business_date=initialization.business_date,
        postings=postings, operator=persisted_operator,
        idempotency_key=f'day1:{initialization.pk}:opening',
        source_id=str(initialization.pk),
    )
    batches = []
    for index, row in enumerate(inventory):
        quantity = row.box_quantity * row.box_size + row.loose_sticks
        cost = (Decimal(quantity) * row.unit_cost_cny).quantize(CNY_PLACES)
        batch = PurchaseBatch.objects.create(
            purchase_order_item=None, source=PurchaseBatch.Source.OPENING,
            cigar_id=row.cigar_id, quantity=quantity, remaining=quantity,
            physical_remaining=quantity, box_size=row.box_size,
            original_box_quantity=row.box_quantity, original_stick_quantity=row.loose_sticks,
            physical_box_quantity=row.box_quantity, available_box_quantity=row.box_quantity,
            physical_stick_quantity=row.loose_sticks, available_stick_quantity=row.loose_sticks,
            original_cost_cny=cost, remaining_cost_cny=cost,
            positive_adjustment_quantity=0, positive_adjustment_cost_cny=Decimal('0.00'),
            adjustment_cost_cny=Decimal('0.00'), sold_cost_cny=Decimal('0.00'),
            unit_cost_cny=row.unit_cost_cny,
        )
        batches.append(batch)
        StockMovement.objects.create(
            movement_type=StockMovement.MovementType.RECEIVE,
            cigar_id=row.cigar_id, purchase_batch=batch, quantity=quantity,
            operator=persisted_operator,
            idempotency_key=f'day1:{initialization.pk}:movement:{index}',
            command_name='day1_initialization', note=f'day1_initialization:{initialization.pk}',
        )
    summary = {
        'initialization_id': initialization.pk, 'idempotency_key': idempotency_key,
        'request_hash': _request_hash(initialization), 'operator_id': persisted_operator.pk,
        'business_date': initialization.business_date.isoformat(),
        'retained_earnings_cny': '0.00', 'opening_capital_cny': str(total_assets),
        'total_net_assets_cny': str(total_assets), 'accounts_total_cny': str(total_accounts),
        'inventory_total_cny': str(total_inventory), 'account_count': len(account_objects),
        'inventory_count': len(batches), 'ledger_transaction_id': transaction_record.pk,
        'accounts': [
            {
                'slot': row.slot,
                'name': row.account_name,
                'currency': row.currency,
                'original_amount': str(row.original_amount),
                'cny_book_cost': str(row.cny_book_cost),
                'account_id': account_objects[row.slot].pk,
            }
            for row in accounts
        ],
        'inventory': [
            {
                'cigar_id': row.cigar_id,
                'box_size': row.box_size,
                'box_quantity': row.box_quantity,
                'loose_sticks': row.loose_sticks,
                'unit_cost_cny': str(row.unit_cost_cny),
                'quantity': batch.quantity,
                'total_cost_cny': str(batch.original_cost_cny),
                'batch_id': batch.pk,
            }
            for row, batch in zip(inventory, batches)
        ],
    }
    initialization.status = Day1Initialization.Status.COMPLETED
    initialization.completed_by = persisted_operator
    initialization.completed_at = timezone.now()
    initialization.completion_summary = summary
    initialization.save(update_fields=['status', 'completed_by', 'completed_at', 'completion_summary', 'updated_at'])
    return _result_from_summary(initialization)
