"""采购草稿的 canonical 盒数语义与受控草稿动作。"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, DecimalException, InvalidOperation, ROUND_HALF_UP
import hashlib
import json

from django.utils import timezone
from django.db import IntegrityError, transaction
from django.db import models
from django.db.models import Q

from accounting.business_time import moscow_business_date
from accounting.mutation_scope import ledger_mutation_scope
from accounting.services import (
    LedgerError, PostingInput, _acquire_sqlite_writer_gate, _outflow_cny_cost,
    _post_transaction_once, _retry_sqlite_locked, reverse_ledger_transaction,
)
from accounting.selectors import account_snapshot
from accounting.models import (
    FundAccount, LedgerPosting, LedgerTransaction,
    PurchaseDraftAction, PurchasePayment,
)
from accounting.guards import Day1IncompleteError, require_day1_completed
from cigars.audit import AgentContext
from cigars.inventory import InventoryError, receive_stock, reverse_purchase_receipt
from cigars.models import (
    Cigar, PurchaseBatch, PurchaseOrder, PurchaseOrderItem, StockMovement,
    Supplier, User,
)


MONEY_PLACES = Decimal('0.01')
_MAX_ORDER_TOTAL = Decimal('9999999999.99')
_MAX_EXCHANGE_RATE = Decimal('999999.9999')
_CUTOVER_DATE = date(2026, 8, 10)
# IntegerField and PositiveIntegerField use a 32-bit portable range. SQLite
# stores larger integers, but accepting them here would make writes backend
# dependent and can overflow the IntegerField columns on other databases.
_MAX_DB_INTEGER = 2_147_483_647


class PurchaseActionError(Exception):
    """采购动作的稳定、可序列化异常。"""

    def __init__(self, code: str, details: dict[str, object] | None = None):
        super().__init__(code)
        self.code = code
        self.details = details or {}


def _decimal(value, field: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (DecimalException, TypeError, ValueError):
        raise PurchaseActionError('invalid_amount', {field: '必须是有效 Decimal'})
    if not result.is_finite():
        raise PurchaseActionError('invalid_amount', {field: '必须是有限 Decimal'})
    return result


def _positive_int(value, field: str, *, max_value=None) -> int:
    if isinstance(value, bool):
        raise PurchaseActionError('invalid_packaging', {field: '必须是正整数'})
    try:
        result = int(value)
    except (TypeError, ValueError, OverflowError):
        raise PurchaseActionError('invalid_packaging', {field: '必须是正整数'})
    if result <= 0 or str(value).strip() != str(result):
        raise PurchaseActionError('invalid_packaging', {field: '必须是正整数'})
    if max_value is not None and result > max_value:
        raise PurchaseActionError('invalid_packaging', {field: '超出数据库整数范围'})
    return result


def _purchase_order_id(value) -> int:
    """Normalize a purchase-order ID before it reaches Django's ORM."""
    try:
        return _positive_int(value, 'purchase_order_id', max_value=_MAX_DB_INTEGER)
    except PurchaseActionError:
        raise PurchaseActionError(
            'invalid_purchase_order_id',
            {'purchase_order_id': value},
        )



def _purchase_order_business_date(purchase_order_id):
    snapshot = PurchaseOrder.objects.filter(pk=purchase_order_id).values(
        'draft_business_date',
    ).first()
    if snapshot is None:
        raise PurchaseActionError(
            'purchase_order_not_found', {'purchase_order_id': purchase_order_id}
        )
    return snapshot['draft_business_date'] or moscow_business_date()


def _purchase_order_items_payload(purchase_order_id):
    return [
        {
            'cigar_id': item.cigar_id, 'box_size': item.box_size,
            'box_quantity': item.box_quantity,
            'unit_price_rub_per_box': str(item.unit_price_rub_per_box),
            'unit_price_rub': str(item.unit_price_rub) if item.unit_price_rub is not None else None,
            'unit_price_cny': str(item.unit_price_cny) if item.unit_price_cny is not None else None,
            'packaging_status': item.packaging_status,
            'legacy_snapshot_status': item.legacy_snapshot_status,
        }
        for item in PurchaseOrderItem.objects.filter(
            purchase_order_id=purchase_order_id,
        ).order_by('id')
    ]


def _cancel_fingerprint(*, purchase_order_id, items_payload, business_date,
                        operator, expected_version, note):
    payload = {
        'context': {'action_type': 'cancel', 'purchase_order_id': purchase_order_id},
        'purchase_order_id': purchase_order_id, 'items': items_payload,
        'business_date': business_date.isoformat() if business_date else None,
        'operator': operator.pk, 'expected_version': expected_version, 'note': note or '',
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(',', ':')).encode('utf-8')
    ).hexdigest()


def _date(value) -> date:
    if isinstance(value, date) and not hasattr(value, 'hour'):
        result = value
    elif isinstance(value, str):
        try:
            result = date.fromisoformat(value)
        except ValueError:
            raise PurchaseActionError('invalid_business_date', {'business_date': '必须是有效日期'})
    else:
        raise PurchaseActionError('invalid_business_date', {'business_date': '必须是日期'})
    if result < _CUTOVER_DATE:
        raise PurchaseActionError('invalid_business_date', {'business_date': '不能早于账务切换日'})
    return result


def _money_decimal(value, field: str, *, max_digits=22, nonnegative=False) -> Decimal:
    result = _decimal(value, field)
    try:
        quantized = result.quantize(MONEY_PLACES, rounding=ROUND_HALF_UP)
    except DecimalException:
        raise PurchaseActionError('invalid_money_precision', {field: '金额超出允许范围'})
    if result != quantized:
        raise PurchaseActionError('invalid_money_precision', {field: '最多允许两位小数'})
    if nonnegative and quantized < 0:
        raise PurchaseActionError('invalid_amount', {field: '不能为负数'})
    # DecimalField(max_digits, decimal_places) counts integer and fractional
    # digits together.  Check the bound before any ORM write so an overflow is
    # a stable business error and the enclosing transaction remains atomic.
    integer_digits = max_digits - 2
    if abs(quantized) > (Decimal(10) ** integer_digits - MONEY_PLACES):
        raise PurchaseActionError('invalid_money_precision', {field: '金额超出允许范围'})
    return quantized


def _exchange_rate(value):
    if value in (None, ''):
        return None
    try:
        result = Decimal(str(value))
        if not result.is_finite() or result <= 0 or result.as_tuple().exponent < -4:
            raise ValueError
        quantized = result.quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)
    except (DecimalException, InvalidOperation, TypeError, ValueError):
        raise PurchaseActionError('invalid_exchange_rate')
    if quantized > _MAX_EXCHANGE_RATE:
        raise PurchaseActionError('invalid_exchange_rate')
    return quantized


def _legacy_snapshot(value, field: str):
    if value in (None, ''):
        return None
    return _money_decimal(value, field, max_digits=12, nonnegative=True)


def _aggregate_money(rows, field, *, value_key='rub_subtotal'):
    try:
        total = sum((row[value_key] for row in rows), Decimal('0.00')).quantize(
            MONEY_PLACES, rounding=ROUND_HALF_UP
        )
    except (DecimalException, InvalidOperation, TypeError, ValueError):
        raise PurchaseActionError('invalid_money_precision', {field: '金额超出允许范围'})
    if total < 0 or total > _MAX_ORDER_TOTAL:
        raise PurchaseActionError('invalid_money_precision', {field: '金额超出允许范围'})
    return total


def _legacy_cny_total(rows):
    if not any(row['unit_price_cny'] is not None for row in rows):
        return None
    try:
        values = [Decimal(row['unit_price_cny']) * row['sticks'] for row in rows]
    except (DecimalException, InvalidOperation, TypeError, ValueError):
        raise PurchaseActionError('invalid_money_precision', {'cny_total': '金额超出允许范围'})
    return _aggregate_money(
        [{'cny_subtotal': value} for value in values],
        'cny_total', value_key='cny_subtotal',
    )


def canonical_purchase_item(
    *,
    box_size: int,
    box_quantity: int,
    unit_price_rub_per_box: Decimal,
    legacy_unit_price_rub: Decimal | None = None,
    legacy_unit_price_cny: Decimal | None = None,
) -> dict:
    """只从盒规、盒数和每盒卢布价产生采购事实。"""
    box_size = _positive_int(box_size, 'box_size')
    box_quantity = _positive_int(box_quantity, 'box_quantity')
    per_box = _money_decimal(unit_price_rub_per_box, 'unit_price_rub_per_box')
    if per_box < 0:
        raise PurchaseActionError('invalid_packaging', {'unit_price_rub_per_box': '不能为负数'})

    legacy_rub = _legacy_snapshot(legacy_unit_price_rub, 'unit_price_rub')
    legacy_cny = _legacy_snapshot(legacy_unit_price_cny, 'unit_price_cny')
    if legacy_rub is not None and legacy_rub * box_size != per_box:
        raise PurchaseActionError(
            'legacy_snapshot_conflict',
            {'unit_price_rub': str(legacy_rub), 'unit_price_rub_per_box': str(per_box)},
        )

    # 新 canonical 输入不伪造旧报价快照；旧 adapter 显式传入时才保留。
    status = (
        PurchaseOrderItem.PackagingStatus.NORMALIZED
        if legacy_rub is not None
        else PurchaseOrderItem.PackagingStatus.UNREPRESENTABLE
    )
    if status == PurchaseOrderItem.PackagingStatus.UNREPRESENTABLE:
        legacy_rub = None
        legacy_cny = None
        snapshot_status = PurchaseOrderItem.LegacySnapshotStatus.UNREPRESENTABLE
    else:
        snapshot_status = (
            PurchaseOrderItem.LegacySnapshotStatus.EXPLICIT
            if legacy_cny is not None
            else PurchaseOrderItem.LegacySnapshotStatus.DERIVED
        )

    try:
        sticks = box_size * box_quantity
        if sticks > _MAX_DB_INTEGER:
            raise PurchaseActionError(
                'invalid_packaging', {'sticks': '超出数据库整数范围'}
            )
        rub_subtotal = (Decimal(box_quantity) * per_box).quantize(
            MONEY_PLACES, rounding=ROUND_HALF_UP
        )
    except (DecimalException, InvalidOperation, TypeError, ValueError):
        raise PurchaseActionError('invalid_money_precision', {'rub_subtotal': '金额超出允许范围'})

    return {
        'sticks': sticks,
        'rub_subtotal': rub_subtotal,
        'box_size': box_size,
        'box_quantity': box_quantity,
        'unit_price_rub_per_box': per_box.quantize(MONEY_PLACES),
        'unit_price_rub': legacy_rub,
        'unit_price_cny': legacy_cny,
        'packaging_status': status,
        'legacy_snapshot_status': snapshot_status,
    }


def normalize_legacy_purchase_item(
    *,
    box_size: int | None,
    quantity_sticks: int,
    unit_price_rub_per_stick: Decimal,
    unit_price_cny_per_stick: Decimal | None = None,
) -> dict:
    """兼容旧 agent 的支数输入；不可整盒时必须人工复核。"""
    try:
        quantity = _positive_int(quantity_sticks, 'quantity_sticks')
    except PurchaseActionError as error:
        error.details.setdefault('quantity_sticks', quantity_sticks)
        raise
    if box_size in (None, ''):
        raise PurchaseActionError(
            'packaging_review_required',
            {'quantity_sticks': quantity, 'box_size': box_size},
        )
    try:
        size = _positive_int(box_size, 'box_size')
    except PurchaseActionError:
        raise PurchaseActionError(
            'packaging_review_required',
            {'quantity_sticks': quantity, 'box_size': box_size},
        )
    if quantity % size:
        raise PurchaseActionError(
            'packaging_review_required',
            {'quantity_sticks': quantity, 'box_size': size},
        )
    per_stick = _money_decimal(unit_price_rub_per_stick, 'unit_price_rub')
    if per_stick < 0:
        raise PurchaseActionError('invalid_amount', {'unit_price_rub': '不能为负数'})
    return canonical_purchase_item(
        box_size=size,
        box_quantity=quantity // size,
        unit_price_rub_per_box=per_stick * size,
        legacy_unit_price_rub=per_stick,
        legacy_unit_price_cny=unit_price_cny_per_stick,
    )


def _canonical_payload(*, items, operator, business_date, expected_version=None, note='', context=None) -> tuple[list[dict], str]:
    if not isinstance(items, (list, tuple)) or not items:
        raise PurchaseActionError('invalid_items', {'items': '至少需要一个采购明细'})
    normalized = []
    for index, raw in enumerate(items):
        if not isinstance(raw, dict):
            raise PurchaseActionError('invalid_items', {'item_index': index, 'item': '必须是对象'})
        try:
            cigar_id = _positive_int(raw.get('cigar_id'), 'cigar_id')
            row = canonical_purchase_item(
                box_size=raw.get('box_size'),
                box_quantity=raw.get('box_quantity'),
                unit_price_rub_per_box=raw.get('unit_price_rub_per_box'),
                legacy_unit_price_rub=raw.get('unit_price_rub'),
                legacy_unit_price_cny=raw.get('unit_price_cny'),
            )
        except PurchaseActionError as error:
            error.details.setdefault('item_index', index)
            raise
        if not Cigar.objects.filter(pk=cigar_id).exists():
            raise PurchaseActionError('cigar_not_found', {'item_index': index, 'cigar_id': cigar_id})
        normalized.append({'cigar_id': cigar_id, **row})

    payload = {
        'context': context or {},
        'items': [
            {
                'cigar_id': row['cigar_id'],
                'box_size': row['box_size'],
                'box_quantity': row['box_quantity'],
                'unit_price_rub_per_box': str(row['unit_price_rub_per_box']),
                'unit_price_rub': str(row['unit_price_rub']) if row['unit_price_rub'] is not None else None,
                'unit_price_cny': str(row['unit_price_cny']) if row['unit_price_cny'] is not None else None,
                'packaging_status': row['packaging_status'],
                'legacy_snapshot_status': row['legacy_snapshot_status'],
            }
            for row in normalized
        ],
        'business_date': _date(business_date).isoformat(),
        'operator': operator.pk,
        'expected_version': expected_version,
        'note': note or '',
    }
    fingerprint = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
    ).hexdigest()
    return normalized, fingerprint


def _require_day1_completed():
    try:
        require_day1_completed()
    except Day1IncompleteError as error:
        raise PurchaseActionError(error.code) from error


def _action_fields(action):
    return {field.name for field in action._meta.concrete_fields}


def _write_action(*, purchase_order, action_type, idempotency_key, fingerprint, operator, result_version):
    action = PurchaseDraftAction(
        purchase_order=purchase_order,
        action_type=action_type,
        idempotency_key=idempotency_key,
        request_fingerprint=fingerprint,
        result_version=result_version,
        operator=operator,
    )
    with ledger_mutation_scope(
        reason='purchase_draft_action', model='accounting.PurchaseDraftAction',
        operator=operator, allowed_fields=_action_fields(action),
    ):
        action.save(force_insert=True)
    return action


def _check_key(*, action_type, idempotency_key, fingerprint):
    if not isinstance(idempotency_key, str) or not idempotency_key or len(idempotency_key) > 128:
        raise PurchaseActionError('invalid_idempotency_key', {'idempotency_key': '幂等键无效'})
    action = PurchaseDraftAction.objects.filter(idempotency_key=idempotency_key).first()
    if action is None:
        return None
    if action.action_type != action_type or action.request_fingerprint != fingerprint:
        raise PurchaseActionError('idempotency_conflict', {'idempotency_key': idempotency_key})
    return action.purchase_order


def _validate_operator(operator):
    if not isinstance(operator, User) or not operator.pk or not operator.is_operator:
        raise PurchaseActionError('invalid_operator')
    return User.objects.get(pk=operator.pk)


def _operator_id_for_replay(operator):
    """重放只核对原操作人身份，不重新要求其仍有操作权限。"""
    if not isinstance(operator, User) or not operator.pk:
        raise PurchaseActionError('invalid_operator')
    return operator.pk


def _create_locked(*, supplier_id, items, business_date, operator, idempotency_key, expected_version, note, exchange_rate=None):
    _operator_id_for_replay(operator)
    business_date = _date(business_date)
    exchange_rate = _exchange_rate(exchange_rate)
    normalized, fingerprint = _canonical_payload(
        items=items, operator=operator, business_date=business_date,
        expected_version=expected_version, note=note,
        context={'action_type': 'create', 'supplier_id': _positive_int(supplier_id, 'supplier_id'),
                 'exchange_rate': str(exchange_rate) if exchange_rate is not None else None},
    )
    replay = _check_key(action_type=PurchaseDraftAction.ActionType.CREATE, idempotency_key=idempotency_key, fingerprint=fingerprint)
    if replay is not None:
        return replay
    _require_day1_completed()
    operator = _validate_operator(operator)
    try:
        supplier = Supplier.objects.get(pk=_positive_int(supplier_id, 'supplier_id'), deleted_at__isnull=True)
    except Supplier.DoesNotExist:
        raise PurchaseActionError('supplier_not_found', {'supplier_id': supplier_id})

    kwargs = {
        'supplier': supplier,
        'rub_total': _aggregate_money(normalized, 'rub_total'),
        'exchange_rate': exchange_rate,
        'cny_total': _legacy_cny_total(normalized),
        'operator': operator,
        'note': note or '',
        'status': PurchaseOrder.Status.DRAFT,
        'draft_idempotency_key': idempotency_key,
        'draft_request_fingerprint': fingerprint,
        'draft_operator': operator,
        'draft_business_date': business_date,
    }
    order = PurchaseOrder.objects.create(**kwargs)
    for row in normalized:
        PurchaseOrderItem.objects.create(
            purchase_order=order,
            cigar_id=row['cigar_id'],
            quantity=row['sticks'],
            box_size=row['box_size'],
            box_quantity=row['box_quantity'],
            unit_price_rub_per_box=row['unit_price_rub_per_box'],
            unit_price_rub=row['unit_price_rub'],
            unit_price_cny=row['unit_price_cny'],
            packaging_status=row['packaging_status'],
            legacy_snapshot_status=row['legacy_snapshot_status'],
        )
    _write_action(
        purchase_order=order, action_type=PurchaseDraftAction.ActionType.CREATE,
        idempotency_key=idempotency_key, fingerprint=fingerprint,
        operator=operator, result_version=order.version,
    )
    return order


@_retry_sqlite_locked
def create_purchase_order(*, supplier_id, items, business_date=None, operator,
                          idempotency_key, expected_version=None, note='', exchange_rate=None):
    """创建 canonical 采购草稿；所有明细和 action 在同一事务中写入。"""
    if business_date is None:
        raise PurchaseActionError('invalid_business_date', {'business_date': '必须显式提供'})
    with transaction.atomic():
        _acquire_sqlite_writer_gate()
        return _create_locked(
            supplier_id=supplier_id, items=items, business_date=business_date,
            operator=operator, idempotency_key=idempotency_key,
            expected_version=expected_version, note=note, exchange_rate=exchange_rate,
        )



@_retry_sqlite_locked
def update_purchase_order_draft(*, purchase_order_id, items, expected_version,
                               idempotency_key, operator, note=''):
    """编辑仍处于草稿状态的采购单，并以版本保护双人同时编辑。"""
    _operator_id_for_replay(operator)
    try:
        expected_version = int(expected_version)
    except (TypeError, ValueError):
        raise PurchaseActionError('version_conflict', {'expected_version': expected_version})
    purchase_order_id = _purchase_order_id(purchase_order_id)
    business_date = _purchase_order_business_date(purchase_order_id)
    normalized, fingerprint = _canonical_payload(
        items=items, operator=operator, business_date=business_date,
        expected_version=expected_version, note=note,
        context={'action_type': 'update', 'purchase_order_id': purchase_order_id},
    )
    with transaction.atomic():
        _acquire_sqlite_writer_gate()
        replay = _check_key(action_type=PurchaseDraftAction.ActionType.UPDATE,
                            idempotency_key=idempotency_key, fingerprint=fingerprint)
        if replay is not None:
            return replay
        try:
            order = PurchaseOrder.objects.select_for_update().get(pk=purchase_order_id)
        except PurchaseOrder.DoesNotExist:
            raise PurchaseActionError('purchase_order_not_found', {'purchase_order_id': purchase_order_id})
        actual_business_date = order.draft_business_date or moscow_business_date()
        if actual_business_date != business_date:
            business_date = actual_business_date
            normalized, fingerprint = _canonical_payload(
                items=items, operator=operator, business_date=business_date,
                expected_version=expected_version, note=note,
                context={'action_type': 'update', 'purchase_order_id': order.pk},
            )
            replay = _check_key(
                action_type=PurchaseDraftAction.ActionType.UPDATE,
                idempotency_key=idempotency_key, fingerprint=fingerprint,
            )
            if replay is not None:
                return replay
        operator = _validate_operator(operator)
        _require_day1_completed()
        if order.status != PurchaseOrder.Status.DRAFT:
            raise PurchaseActionError('invalid_state', {'status': order.status})
        if expected_version != order.version:
            raise PurchaseActionError('version_conflict', {
                'expected_version': expected_version, 'actual_version': order.version,
            })
        current_items = list(order.items.order_by('id'))
        if any(item.cigar_id != row['cigar_id'] for item, row in zip(current_items, normalized)):
            raise PurchaseActionError('cigar_change_forbidden')
        if len(current_items) != len(normalized):
            raise PurchaseActionError('invalid_items', {'items': '编辑暂不允许改变明细行数'})
        for item, row in zip(current_items, normalized):
            item.cigar_id = row['cigar_id']
            item.quantity = row['sticks']
            item.box_size = row['box_size']
            item.box_quantity = row['box_quantity']
            item.unit_price_rub_per_box = row['unit_price_rub_per_box']
            item.unit_price_rub = row['unit_price_rub']
            item.unit_price_cny = row['unit_price_cny']
            item.packaging_status = row['packaging_status']
            item.legacy_snapshot_status = row['legacy_snapshot_status']
            item.save(update_fields=[
                'cigar', 'quantity', 'box_size', 'box_quantity',
                'unit_price_rub_per_box', 'unit_price_rub', 'unit_price_cny',
                'packaging_status', 'legacy_snapshot_status',
            ])
        order.rub_total = _aggregate_money(normalized, 'rub_total')
        order.version += 1
        order.note = note or ''
        order.draft_request_fingerprint = fingerprint
        order.exchange_rate = None
        order.cny_total = _legacy_cny_total(normalized)
        order.save(update_fields=['rub_total', 'version', 'note', 'draft_request_fingerprint', 'exchange_rate', 'cny_total'])
        _write_action(purchase_order=order, action_type=PurchaseDraftAction.ActionType.UPDATE,
                      idempotency_key=idempotency_key, fingerprint=fingerprint,
                      operator=operator, result_version=order.version)
        return order


@_retry_sqlite_locked
def cancel_purchase_order(*, purchase_order_id, operator, idempotency_key,
                          expected_version, note=''):
    """取消未付款草稿；取消本身也留下不可变动作日志。"""
    _operator_id_for_replay(operator)
    try:
        expected_version = int(expected_version)
    except (TypeError, ValueError):
        raise PurchaseActionError('version_conflict', {'expected_version': expected_version})
    purchase_order_id = _purchase_order_id(purchase_order_id)
    business_date = _purchase_order_business_date(purchase_order_id)
    items_payload = _purchase_order_items_payload(purchase_order_id)
    fingerprint = _cancel_fingerprint(
        purchase_order_id=purchase_order_id, items_payload=items_payload,
        business_date=business_date, operator=operator,
        expected_version=expected_version, note=note,
    )
    with transaction.atomic():
        _acquire_sqlite_writer_gate()
        replay = _check_key(
            action_type=PurchaseDraftAction.ActionType.CANCEL,
            idempotency_key=idempotency_key, fingerprint=fingerprint,
        )
        if replay is not None:
            return replay
        try:
            order = PurchaseOrder.objects.select_for_update().get(pk=purchase_order_id)
        except PurchaseOrder.DoesNotExist:
            raise PurchaseActionError('purchase_order_not_found', {'purchase_order_id': purchase_order_id})
        actual_business_date = order.draft_business_date or moscow_business_date()
        actual_items_payload = _purchase_order_items_payload(purchase_order_id)
        if actual_business_date != business_date or actual_items_payload != items_payload:
            business_date = actual_business_date
            items_payload = actual_items_payload
            fingerprint = _cancel_fingerprint(
                purchase_order_id=purchase_order_id, items_payload=items_payload,
                business_date=business_date, operator=operator,
                expected_version=expected_version, note=note,
            )
            replay = _check_key(
                action_type=PurchaseDraftAction.ActionType.CANCEL,
                idempotency_key=idempotency_key, fingerprint=fingerprint,
            )
            if replay is not None:
                return replay
        operator = _validate_operator(operator)
        _require_day1_completed()
        if order.status != PurchaseOrder.Status.DRAFT or order.paid_at is not None or (order.paid_cny_cost or 0) != 0:
            raise PurchaseActionError('invalid_state', {'status': order.status})
        if expected_version != order.version:
            raise PurchaseActionError('version_conflict', {
                'expected_version': expected_version, 'actual_version': order.version,
            })
        order.status = PurchaseOrder.Status.CANCELLED
        order.paid_cny_cost = Decimal('0.00')
        order.paid_at = None
        order.payment_idempotency_key = None
        order.arrival_idempotency_key = None
        order.note = note or order.note
        order.version += 1
        # 取消同时改写受保护的终态字段，直接使用 trusted model boundary。
        models.Model.save(order, update_fields=[
            'status', 'paid_cny_cost', 'paid_at', 'payment_idempotency_key',
            'arrival_idempotency_key', 'note', 'version',
        ])
        _write_action(purchase_order=order, action_type=PurchaseDraftAction.ActionType.CANCEL,
                      idempotency_key=idempotency_key, fingerprint=fingerprint,
                      operator=operator, result_version=order.version)
        return order



def _action_key(value):
    if not isinstance(value, str) or not value or len(value) > 128:
        raise PurchaseActionError('invalid_idempotency_key')
    return value


def _canonical_order_rows(order):
    rows = []
    for item in order.items.select_related('cigar').order_by('id'):
        if item.packaging_status == PurchaseOrderItem.PackagingStatus.REVIEW_REQUIRED:
            raise PurchaseActionError('packaging_review_required', {'item_id': item.pk})
        if not item.box_size or not item.box_quantity or item.unit_price_rub_per_box is None:
            raise PurchaseActionError('packaging_review_required', {'item_id': item.pk})
        quantity = item.box_size * item.box_quantity
        if item.quantity != quantity:
            raise PurchaseActionError('packaging_review_required', {'item_id': item.pk})
        subtotal = (Decimal(item.box_quantity) * item.unit_price_rub_per_box).quantize(MONEY_PLACES)
        rows.append((item, quantity, subtotal))
    if not rows:
        raise PurchaseActionError('invalid_items')
    return rows


def _canonical_rub_total(rows):
    return sum((row[2] for row in rows), Decimal('0.00')).quantize(MONEY_PLACES)


def _payment_conflict():
    raise PurchaseActionError('idempotency_conflict')


def _postings_match(transaction_obj, expected):
    postings = list(transaction_obj.postings.order_by('id'))
    if len(postings) != len(expected):
        return False
    actual = sorted(
        (-1 if posting.account_id is None else posting.account_id,
         posting.category, posting.currency,
         posting.amount, posting.cny_amount)
        for posting in postings
    )
    return actual == sorted(
        (-1 if account_id is None else account_id, category, currency,
         amount, cny_amount)
        for account_id, category, currency, amount, cny_amount in expected
    )


def _payment_facts_match(*, payment, order, key, business_date, operator_id, rub_amount):
    transaction_obj = payment.ledger_transaction
    if not (
        order.status in (PurchaseOrder.Status.IN_TRANSIT, PurchaseOrder.Status.RECEIVED)
        and order.payment_idempotency_key == key
        and order.paid_cny_cost == payment.cny_cost
        and order.paid_at is not None
        and payment.status == PurchasePayment.Status.POSTED
        and transaction_obj.transaction_type == LedgerTransaction.TransactionType.PURCHASE_PAYMENT
        and transaction_obj.status == LedgerTransaction.Status.POSTED
        and transaction_obj.idempotency_key == payment.idempotency_key
        and transaction_obj.business_date == business_date
        and transaction_obj.operator_id == operator_id
        and transaction_obj.source_type == 'purchase_order'
        and transaction_obj.source_id == str(order.pk)
        and payment.rub_amount == rub_amount
    ):
        return False
    return _postings_match(transaction_obj, [
        (payment.fund_account_id, '', FundAccount.Currency.RUB,
         -payment.rub_amount, -payment.cny_cost),
        (None, LedgerPosting.Category.PURCHASE_IN_TRANSIT,
         FundAccount.Currency.CNY, payment.cny_cost, payment.cny_cost),
    ])


def _payment_replay(*, key, order, account_id, business_date, operator_id, rub_amount):
    payment = PurchasePayment.objects.select_related('ledger_transaction').filter(
        idempotency_key=key,
    ).first()
    if payment is None:
        tx = LedgerTransaction.objects.filter(idempotency_key=key).first()
        if tx is not None:
            _payment_conflict()
        return None
    if (
        payment.purchase_order_id != order.pk
        or payment.fund_account_id != account_id
        or payment.business_date != business_date
        or payment.operator_id != operator_id
        or not _payment_facts_match(
            payment=payment, order=order, key=key, business_date=business_date,
            operator_id=operator_id, rub_amount=rub_amount,
        )
    ):
        _payment_conflict()
    return payment


def _receipt_replay_facts(*, order, transaction_obj, key, business_date, operator_id, note):
    if not (
        transaction_obj.idempotency_key == key
        and transaction_obj.transaction_type == LedgerTransaction.TransactionType.PURCHASE_RECEIPT
        and transaction_obj.status == LedgerTransaction.Status.POSTED
        and transaction_obj.business_date == business_date
        and transaction_obj.operator_id == operator_id
        and transaction_obj.source_type == 'purchase_order'
        and transaction_obj.source_id == str(order.pk)
    ):
        return False

    if order.paid_cny_cost is None:
        return False
    paid = Decimal(order.paid_cny_cost).quantize(MONEY_PLACES)
    try:
        rows = _canonical_order_rows(order)
    except PurchaseActionError:
        return False
    rub_total = _canonical_rub_total(rows)
    if paid <= 0 or rub_total <= 0:
        return False
    allocations = []
    allocated = Decimal('0.00')
    for index, (item, quantity, rub_subtotal) in enumerate(rows):
        if index == len(rows) - 1:
            actual = paid - allocated
        else:
            actual = (paid * rub_subtotal / rub_total).quantize(MONEY_PLACES)
            allocated += actual
        allocations.append((item, quantity, actual.quantize(MONEY_PLACES)))

    if not _postings_match(transaction_obj, [
        (None, LedgerPosting.Category.PURCHASE_IN_TRANSIT,
         FundAccount.Currency.CNY, -paid, -paid),
        (None, LedgerPosting.Category.INVENTORY,
         FundAccount.Currency.CNY, paid, paid),
    ]):
        return False

    items = [item for item, _quantity, _actual in allocations]
    movements = list(StockMovement.objects.filter(
        movement_type=StockMovement.MovementType.RECEIVE,
        purchase_batch__purchase_order_item__purchase_order_id=order.pk,
        idempotency_key=key,
    ).order_by('purchase_batch_id', 'id'))
    batch_ids = [movement.purchase_batch_id for movement in movements]
    batches = list(PurchaseBatch.objects.filter(
        pk__in=batch_ids,
    ).order_by('purchase_order_item_id', 'id'))
    if len(batches) != len(items):
        return False
    if len(movements) != len(batches):
        return False
    batches_by_item = {}
    for batch in batches:
        batches_by_item.setdefault(batch.purchase_order_item_id, []).append(batch)
    movements_by_batch = {}
    for movement in movements:
        movements_by_batch.setdefault(movement.purchase_batch_id, []).append(movement)

    for item, quantity, actual in allocations:
        matching = batches_by_item.get(item.pk, [])
        if len(matching) != 1:
            return False
        batch = matching[0]
        unit_cost = (actual / quantity).quantize(MONEY_PLACES, rounding=ROUND_HALF_UP)
        common_valid = (
            batch.cigar_id == item.cigar_id
            and batch.quantity == quantity
            and batch.original_cost_cny == actual
            and batch.sold_cost_cny == Decimal('0.00')
            and batch.unit_cost_cny == unit_cost
            and batch.box_size == item.box_size
            and batch.original_box_quantity == item.box_quantity
            and len(movements_by_batch.get(batch.pk, [])) == 1
        )
        if transaction_obj.reversed_by_id is None:
            state_valid = (
                batch.reversed_at is None
                and batch.remaining == quantity
                and batch.physical_remaining == quantity
                and batch.remaining_cost_cny == actual
                and item.actual_cost_cny == actual
            )
        else:
            state_valid = (
                batch.reversed_at is not None
                and batch.remaining == 0
                and batch.physical_remaining == 0
                and batch.remaining_cost_cny == Decimal('0.00')
                and batch.reversed_quantity == quantity
                and batch.reversed_cost_cny == actual
            )
        if not common_valid or not state_valid:
            return False
        movement = movements_by_batch[batch.pk][0]
        if not (
            movement.cigar_id == item.cigar_id
            and movement.quantity == quantity
            and movement.operator_id == operator_id
            and movement.idempotency_key == key
            and movement.note == (note or '')
        ):
            return False
    return True


def _receipt_batches_for_key(*, order_id, key):
    batch_ids = StockMovement.objects.filter(
        movement_type=StockMovement.MovementType.RECEIVE,
        purchase_batch__purchase_order_item__purchase_order_id=order_id,
        idempotency_key=key,
    ).values_list('purchase_batch_id', flat=True)
    return list(PurchaseBatch.objects.filter(pk__in=batch_ids).order_by('id'))


@_retry_sqlite_locked
def pay_purchase_order(*, purchase_order_id, rub_account_id, business_date,
                       operator, idempotency_key):
    """一次性采购付款：按付款前卢布账户移动平均成本转入在途。"""
    business_date = _date(business_date)
    key = _action_key(idempotency_key)
    order_id = _purchase_order_id(purchase_order_id)
    account_id = _positive_int(rub_account_id, 'rub_account_id')
    operator_id = _operator_id_for_replay(operator)

    with transaction.atomic():
        _acquire_sqlite_writer_gate()
        # 先核对不可变付款事实；Day 1 或人员状态变化不能破坏合法重放。
        existing_payment = PurchasePayment.objects.filter(idempotency_key=key).first()
        if existing_payment is not None:
            if existing_payment.purchase_order_id != order_id:
                _payment_conflict()
            replay_order = PurchaseOrder.objects.filter(pk=order_id).first()
            if replay_order is None:
                _payment_conflict()
            replay = _payment_replay(
                key=key, order=replay_order, account_id=account_id,
                business_date=business_date, operator_id=operator_id,
                rub_amount=_canonical_rub_total(_canonical_order_rows(replay_order)),
            )
            if replay is not None:
                return replay
        elif LedgerTransaction.objects.filter(idempotency_key=key).exists():
            _payment_conflict()

        _require_day1_completed()
        operator = _validate_operator(operator)
        order = PurchaseOrder.objects.select_for_update().filter(pk=order_id).first()
        if order is None:
            raise PurchaseActionError(
                'purchase_order_not_found', {'purchase_order_id': order_id}
            )
        account = FundAccount.objects.select_for_update().filter(pk=account_id).first()
        if account is None:
            raise PurchaseActionError('account_not_found')
        rows = _canonical_order_rows(order)
        rub_amount = _canonical_rub_total(rows)
        if order.status != PurchaseOrder.Status.DRAFT:
            raise PurchaseActionError('invalid_state', {'status': order.status})
        if rub_amount <= 0:
            raise PurchaseActionError('invalid_amount')
        if account.currency != FundAccount.Currency.RUB:
            raise PurchaseActionError('invalid_account_currency')
        if not account.is_active:
            raise PurchaseActionError('account_inactive')
        snapshot = account_snapshot(account)
        if rub_amount > snapshot.original_balance:
            raise PurchaseActionError('insufficient_balance')
        try:
            cny_cost = _outflow_cny_cost(account, rub_amount)
        except LedgerError as error:
            if '余额不足' in str(error):
                raise PurchaseActionError('insufficient_balance') from error
            raise PurchaseActionError('ledger_error', {'message': str(error)}) from error

        ledger = _post_transaction_once(
            transaction_type=LedgerTransaction.TransactionType.PURCHASE_PAYMENT,
            business_date=business_date,
            postings=[
                PostingInput(account=account, currency=FundAccount.Currency.RUB,
                             amount=-rub_amount, cny_amount=-cny_cost),
                PostingInput(category=LedgerPosting.Category.PURCHASE_IN_TRANSIT,
                             currency=FundAccount.Currency.CNY,
                             amount=cny_cost, cny_amount=cny_cost),
            ],
            operator=operator, idempotency_key=key,
            description=f'采购单 {order.order_number} 付款',
            source_type='purchase_order', source_id=str(order.pk),
            _writer_gate=False,
        )
        now = timezone.now()
        with ledger_mutation_scope(
            reason='purchase_payment', model='cigars.PurchaseOrder',
            operator=operator,
            allowed_fields={'status', 'paid_cny_cost', 'paid_at', 'payment_idempotency_key'},
        ):
            order.status = PurchaseOrder.Status.IN_TRANSIT
            order.paid_cny_cost = cny_cost
            order.paid_at = now
            order.payment_idempotency_key = key
            order.save(update_fields=[
                'status', 'paid_cny_cost', 'paid_at', 'payment_idempotency_key',
            ])
        payment = PurchasePayment(
            purchase_order=order, fund_account=account, rub_amount=rub_amount,
            cny_cost=cny_cost, business_date=business_date, operator=operator,
            ledger_transaction=ledger, idempotency_key=key,
            request_fingerprint=hashlib.sha256(
                f'{order.pk}|{account.pk}|{rub_amount}|{business_date.isoformat()}|{operator.pk}'.encode()
            ).hexdigest(),
        )
        with ledger_mutation_scope(
            reason='purchase_payment', model='accounting.PurchasePayment',
            operator=operator,
            allowed_fields={field.name for field in payment._meta.concrete_fields},
        ):
            payment.save(force_insert=True)
        return payment


@_retry_sqlite_locked
def receive_paid_purchase_order(*, purchase_order_id, business_date, operator,
                                idempotency_key, note='', agent_context=None):
    """整单到货：按 canonical 卢布小计分配已付款人民币尾差。"""
    business_date = _date(business_date)
    key = _action_key(idempotency_key)
    order_id = _purchase_order_id(purchase_order_id)
    operator_id = _operator_id_for_replay(operator)

    with transaction.atomic():
        _acquire_sqlite_writer_gate()
        # 到货事实先于当前门禁核对，保证终态订单可稳定重放。
        existing_tx = LedgerTransaction.objects.filter(idempotency_key=key).first()
        replay_order = PurchaseOrder.objects.filter(pk=order_id).first()
        if replay_order is None:
            if existing_tx is not None:
                raise PurchaseActionError('idempotency_conflict')
            raise PurchaseActionError(
                'purchase_order_not_found', {'purchase_order_id': order_id}
            )
        existing_order_tx = LedgerTransaction.objects.filter(
            source_type='purchase_order', source_id=str(order_id),
            transaction_type=LedgerTransaction.TransactionType.PURCHASE_RECEIPT,
            reversed_by__isnull=True,
        ).first()
        if (
            existing_tx is not None
            and existing_tx.transaction_type == LedgerTransaction.TransactionType.PURCHASE_RECEIPT
            and existing_tx.source_type == 'purchase_order'
            and existing_tx.source_id == str(order_id)
            and existing_tx.reversed_by_id is not None
        ):
            if _receipt_replay_facts(
                order=replay_order, transaction_obj=existing_tx,
                key=key, business_date=business_date,
                operator_id=operator_id, note=note,
            ):
                return _receipt_batches_for_key(order_id=order_id, key=key)
            raise PurchaseActionError('idempotency_conflict')
        if existing_order_tx is not None:
            if (
                replay_order.arrival_idempotency_key == key
                and _receipt_replay_facts(
                    order=replay_order, transaction_obj=existing_order_tx,
                    key=key, business_date=business_date,
                    operator_id=operator_id, note=note,
                )
            ):
                return _receipt_batches_for_key(order_id=order_id, key=key)
            raise PurchaseActionError('idempotency_conflict')
        if existing_tx is not None or replay_order.arrival_idempotency_key:
            raise PurchaseActionError('idempotency_conflict')

        _require_day1_completed()
        operator = _validate_operator(operator)
        order = PurchaseOrder.objects.select_for_update().get(pk=order_id)
        items = list(order.items.select_for_update().select_related('cigar').order_by('id'))
        if order.status != PurchaseOrder.Status.IN_TRANSIT:
            raise PurchaseActionError('invalid_state', {'status': order.status})
        if order.paid_cny_cost is None or order.paid_cny_cost <= 0 or order.paid_at is None:
            raise PurchaseActionError('missing_payment')
        if PurchaseBatch.objects.filter(
            purchase_order_item__purchase_order_id=order_id,
            reversed_at__isnull=True,
        ).exists():
            raise PurchaseActionError('already_received')
        rows = _canonical_order_rows(order)
        rub_total = _canonical_rub_total(rows)
        paid = Decimal(order.paid_cny_cost).quantize(MONEY_PLACES)
        if rub_total <= 0:
            raise PurchaseActionError('invalid_amount')

        allocations = []
        allocated = Decimal('0.00')
        for index, (item, quantity, rub_subtotal) in enumerate(rows):
            if index == len(rows) - 1:
                actual = paid - allocated
            else:
                actual = (paid * rub_subtotal / rub_total).quantize(MONEY_PLACES)
                allocated += actual
            allocations.append((item, quantity, actual.quantize(MONEY_PLACES)))

        batches = []
        context = agent_context or AgentContext(command_name='receive_paid_purchase_order', idempotency_key=key)
        for item, quantity, actual in allocations:
            unit_cost = (actual / quantity).quantize(MONEY_PLACES, rounding=ROUND_HALF_UP)
            with ledger_mutation_scope(
                reason='purchase_receipt', model='cigars.PurchaseOrderItem',
                operator=operator, allowed_fields={'actual_cost_cny'},
            ):
                item.actual_cost_cny = actual
                item.save(update_fields=['actual_cost_cny'])
            batch = receive_stock(
                purchase_order_item=item,
                quantity=quantity,
                total_cost_cny=actual,
                unit_cost_cny=unit_cost,
                operator=operator,
                context=context,
                note=note,
            )
            batches.append(batch)

        ledger = _post_transaction_once(
            transaction_type=LedgerTransaction.TransactionType.PURCHASE_RECEIPT,
            business_date=business_date,
            postings=[
                PostingInput(category=LedgerPosting.Category.PURCHASE_IN_TRANSIT,
                             currency=FundAccount.Currency.CNY,
                             amount=-paid, cny_amount=-paid),
                PostingInput(category=LedgerPosting.Category.INVENTORY,
                             currency=FundAccount.Currency.CNY,
                             amount=paid, cny_amount=paid),
            ],
            operator=operator, idempotency_key=key,
            description=f'采购单 {order.order_number} 到货',
            source_type='purchase_order', source_id=str(order.pk),
            _writer_gate=False,
        )
        with ledger_mutation_scope(
            reason='purchase_receipt', model='cigars.PurchaseOrder',
            operator=operator,
            allowed_fields={'status', 'arrival_idempotency_key', 'legacy_received'},
        ):
            order.status = PurchaseOrder.Status.RECEIVED
            order.arrival_idempotency_key = key
            order.legacy_received = False
            order.save(update_fields=['status', 'arrival_idempotency_key', 'legacy_received'])
        return batches


@_retry_sqlite_locked
def reverse_received_purchase_order(*, purchase_order_id, business_date, operator,
                                    idempotency_key, reason=''):
    """整单撤销一次完全未使用的采购到货。"""
    business_date = _date(business_date)
    key = _action_key(idempotency_key)
    order_id = _purchase_order_id(purchase_order_id)
    reason = str(reason or '').strip()
    if not reason:
        raise PurchaseActionError('reason_required')

    with transaction.atomic():
        _acquire_sqlite_writer_gate()
        order = PurchaseOrder.objects.select_for_update().filter(pk=order_id).first()
        if order is None:
            raise PurchaseActionError('purchase_order_not_found', {'purchase_order_id': order_id})
        existing_reversal = LedgerTransaction.objects.filter(idempotency_key=key).first()
        if existing_reversal is not None:
            historical_receipt = LedgerTransaction.objects.filter(
                transaction_type=LedgerTransaction.TransactionType.PURCHASE_RECEIPT,
                source_type='purchase_order', source_id=str(order.pk),
                reversed_by=existing_reversal,
            ).first()
            if historical_receipt is None:
                raise PurchaseActionError('idempotency_conflict')
            reverse_ledger_transaction(
                original_transaction=historical_receipt,
                business_date=business_date, operator=operator,
                idempotency_key=key, reason=reason,
            )
            batch_ids = StockMovement.objects.filter(
                movement_type=StockMovement.MovementType.REVERSE_RECEIVE,
                purchase_batch__purchase_order_item__purchase_order_id=order.pk,
                idempotency_key=key,
            ).values_list('purchase_batch_id', flat=True)
            return list(PurchaseBatch.objects.filter(pk__in=batch_ids).order_by('id'))

        require_day1_completed()
        operator = _validate_operator(operator)
        if order.status != PurchaseOrder.Status.RECEIVED:
            raise PurchaseActionError('invalid_state', {'status': order.status})
        original = LedgerTransaction.objects.select_for_update().filter(
            transaction_type=LedgerTransaction.TransactionType.PURCHASE_RECEIPT,
            source_type='purchase_order', source_id=str(order.pk),
            reversed_by__isnull=True,
        ).first()
        if original is None:
            raise PurchaseActionError('missing_receipt_transaction')
        context = AgentContext(
            command_name='reverse_received_purchase_order', idempotency_key=key,
        )
        try:
            batches = reverse_purchase_receipt(
                order=order, operator=operator, context=context, note=reason,
            )
        except InventoryError as error:
            raise PurchaseActionError(
                'receipt_already_used', {'message': str(error)},
            ) from error
        reverse_ledger_transaction(
            original_transaction=original, business_date=business_date,
            operator=operator, idempotency_key=key, reason=reason,
        )
        with ledger_mutation_scope(
            reason='purchase_receipt_reversal', model='cigars.PurchaseOrder',
            operator=operator,
            allowed_fields={'status', 'arrival_idempotency_key', 'legacy_received'},
        ):
            order.status = PurchaseOrder.Status.IN_TRANSIT
            order.arrival_idempotency_key = None
            order.legacy_received = False
            order.save(update_fields=['status', 'arrival_idempotency_key', 'legacy_received'])
        return batches
