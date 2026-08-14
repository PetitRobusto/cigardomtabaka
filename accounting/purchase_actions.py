"""采购草稿的 canonical 盒数语义与受控草稿动作。"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, DecimalException, InvalidOperation, ROUND_HALF_UP
import hashlib
import json

from django.db import IntegrityError, transaction
from django.db import models
from django.db.models import Q

from accounting.business_time import moscow_business_date
from accounting.mutation_scope import ledger_mutation_scope
from accounting.services import _acquire_sqlite_writer_gate, _retry_sqlite_locked
from accounting.models import Day1Initialization, PurchaseDraftAction
from cigars.models import Cigar, PurchaseOrder, PurchaseOrderItem, Supplier, User


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
    if not Day1Initialization.objects.filter(
        singleton_key='company', status=Day1Initialization.Status.COMPLETED,
    ).exists():
        raise PurchaseActionError('day1_incomplete')


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


def _create_locked(*, supplier_id, items, business_date, operator, idempotency_key, expected_version, note, exchange_rate=None):
    operator = _validate_operator(operator)
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
    _require_day1_completed()
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
    _require_day1_completed()
    operator = _validate_operator(operator)
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
    _require_day1_completed()
    operator = _validate_operator(operator)
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
