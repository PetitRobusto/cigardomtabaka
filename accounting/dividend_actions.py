"""分红草稿、留存收益预览和一次性确认动作。"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json

from django.db import transaction

from accounting.dividend_types import DividendPreview
from accounting.errors import DividendActionError
from accounting.mutation_scope import ledger_mutation_scope
from accounting.models import (
    Dividend, DividendDraftAction, FundAccount,
    LedgerPosting, LedgerTransaction,
)
from accounting.guards import Day1IncompleteError, require_day1_completed
from accounting.services import (
    CUTOVER_DATE, LedgerError, PostingInput, _acquire_sqlite_writer_gate,
    _outflow_cny_cost, _post_transaction_once, _require_operator,
    _retry_sqlite_locked, _strict_external_decimal,
)
from accounting.selectors import retained_earnings


MONEY_PLACES = Decimal('0.01')
MAX_DIVIDEND = Decimal('99999999999999999999.99')


def _fingerprint(payload: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()
    ).hexdigest()


def _key(value):
    if not isinstance(value, str) or not value or len(value) > 128:
        raise DividendActionError('invalid_idempotency_key')
    return value


def _operator(value):
    try:
        result = _require_operator(value)
    except LedgerError as error:
        raise DividendActionError('invalid_operator') from error
    if not result.is_active:
        raise DividendActionError('invalid_operator')
    return result


def _operator_id(value):
    """读取幂等身份；新动作再执行 active/operator 外键校验。"""
    result = getattr(value, 'pk', None)
    if result is None:
        raise DividendActionError('invalid_operator')
    return result


def _positive_integer(value, code):
    """只接受正整数或无空白的规范数字字符串。"""
    if isinstance(value, bool):
        raise DividendActionError(code)
    if isinstance(value, int):
        result = value
    elif isinstance(value, str) and value and value.isascii() and value.isdecimal():
        result = int(value)
        if str(result) != value:
            raise DividendActionError(code)
    else:
        raise DividendActionError(code)
    if result <= 0:
        raise DividendActionError(code)
    return result


def _note(value):
    if not isinstance(value, str):
        raise DividendActionError('invalid_note')
    return value


def _date(value):
    if isinstance(value, date) and not hasattr(value, 'hour'):
        result = value
    elif isinstance(value, str):
        try:
            result = date.fromisoformat(value)
        except ValueError as error:
            raise DividendActionError('invalid_business_date') from error
    else:
        raise DividendActionError('invalid_business_date')
    if result < CUTOVER_DATE:
        raise DividendActionError('invalid_business_date')
    return result


def _money(value, field='total_cny'):
    try:
        result = _strict_external_decimal(value, MONEY_PLACES, field)
    except LedgerError as error:
        code = 'invalid_money_precision' if '小数位数' in str(error) else 'invalid_amount'
        raise DividendActionError(code, {field: str(error)}) from error
    if result < 0:
        raise DividendActionError('invalid_amount', {field: '不能为负数'})
    if result > MAX_DIVIDEND:
        raise DividendActionError('invalid_money_precision', {field: '金额超出范围'})
    return result


def _require_day1():
    try:
        require_day1_completed()
    except Day1IncompleteError as error:
        raise DividendActionError(error.code) from error


def _action_replay(*, key, fingerprint):
    action = DividendDraftAction.objects.select_for_update().filter(
        idempotency_key=key,
    ).first()
    if action is None:
        return None
    if action.request_fingerprint != fingerprint:
        raise DividendActionError('idempotency_conflict')
    return Dividend.objects.get(pk=action.dividend_id)


def _draft_fingerprint_for_id(*, action_type, total, business_date, operator_id,
                              note, dividend_id=None, a_amount=None,
                              b_amount=None, a_account_id=None,
                              b_account_id=None, expected_version=None):
    return _fingerprint({
        'action_type': action_type,
        'dividend_id': dividend_id,
        'total_cny': str(total),
        'business_date': business_date.isoformat(),
        'operator': operator_id,
        'note': note or '',
        'partner_a_amount_cny': str(a_amount) if a_amount is not None else None,
        'partner_b_amount_cny': str(b_amount) if b_amount is not None else None,
        'partner_a_account_id': a_account_id,
        'partner_b_account_id': b_account_id,
        'expected_version': expected_version,
    })


def _save_action(*, dividend, action_type, key, fingerprint, operator):
    action = DividendDraftAction(
        dividend=dividend, action_type=action_type,
        idempotency_key=key, request_fingerprint=fingerprint,
        result_version=dividend.version, operator=operator,
    )
    with ledger_mutation_scope(
        reason='dividend_draft_action', model='accounting.DividendDraftAction',
        operator=operator,
        allowed_fields={field.name for field in action._meta.concrete_fields},
    ):
        action.save(force_insert=True)


def _lock_cny_accounts(account_ids):
    """一次按 ID 顺序锁定两个账户，再映射回合伙人 A/B。"""
    ordered_ids = sorted(account_ids)
    rows = list(
        FundAccount.objects.select_for_update().filter(pk__in=ordered_ids).order_by('pk')
    )
    if len(rows) != len(ordered_ids):
        raise DividendActionError('account_not_found')
    for account in rows:
        if not account.is_active:
            raise DividendActionError('account_inactive')
        if account.currency != FundAccount.Currency.CNY:
            raise DividendActionError('currency_rule')
    return {account.pk: account for account in rows}


def _retained_earnings(*, as_of):
    """Use the report selector so preview and monthly reports share one formula."""
    return retained_earnings(as_of=as_of)


def _warning(*, retained, requested):
    code = 'retained_earnings_exceeded' if requested > retained else None
    body = {
        'code': code,
        'retained_earnings_cny': str(retained),
        'requested_cny': str(requested),
    }
    fingerprint = _fingerprint(body)
    warning = {**body, 'fingerprint': fingerprint} if code else None
    return warning, fingerprint


@_retry_sqlite_locked
def create_dividend_draft(*, total_cny, business_date, operator,
                          idempotency_key, note='') -> Dividend:
    key = _key(idempotency_key)
    operator_id = _operator_id(operator)
    note = _note(note)
    total = _money(total_cny)
    business_date = _date(business_date)
    fingerprint = _draft_fingerprint_for_id(
        action_type=DividendDraftAction.ActionType.CREATE, total=total,
        business_date=business_date, operator_id=operator_id, note=note,
    )
    with transaction.atomic():
        _acquire_sqlite_writer_gate()
        replay = _action_replay(key=key, fingerprint=fingerprint)
        if replay is not None:
            return replay
        _require_day1()
        operator = _operator(operator)
        half = (total / Decimal('2')).quantize(MONEY_PLACES, rounding=ROUND_HALF_UP)
        dividend = Dividend.objects.create(
            total_cny=total, partner_a_amount_cny=half,
            partner_b_amount_cny=total - half,
            business_date=business_date, created_by=operator, updated_by=operator,
        )
        _save_action(
            dividend=dividend, action_type=DividendDraftAction.ActionType.CREATE,
            key=key, fingerprint=fingerprint, operator=operator,
        )
        return dividend


@_retry_sqlite_locked
def preview_dividend(*, dividend_id, operator) -> DividendPreview:
    _operator(operator)
    dividend_id = _positive_integer(dividend_id, 'dividend_not_found')
    with transaction.atomic():
        _acquire_sqlite_writer_gate()
        # Preview 会更新不可编辑的 warning 快照，因此也属于 Day 1 后的正式写动作。
        _require_day1()
        dividend = Dividend.objects.select_for_update().filter(pk=dividend_id).first()
        if dividend is None:
            raise DividendActionError('dividend_not_found')
        if dividend.status != Dividend.Status.DRAFT:
            raise DividendActionError('invalid_state', {'status': dividend.status})
        retained = _retained_earnings(as_of=dividend.business_date)
        warning, fingerprint = _warning(retained=retained, requested=dividend.total_cny)
        dividend.warning_retained_earnings_cny = retained
        dividend.warning_fingerprint = fingerprint
        dividend.warning_code = warning['code'] if warning else ''
        dividend.warning_ack = False
        dividend.save(update_fields=[
            'warning_retained_earnings_cny', 'warning_fingerprint',
            'warning_code', 'warning_ack',
        ])
        return DividendPreview(
            retained_earnings_cny=retained,
            requested_cny=dividend.total_cny,
            warning=warning,
            warning_fingerprint=fingerprint,
        )


@_retry_sqlite_locked
def update_dividend_draft(*, dividend_id, total_cny, partner_a_amount_cny,
                          partner_b_amount_cny, partner_a_account_id,
                          partner_b_account_id, expected_version,
                          idempotency_key, operator, note='') -> Dividend:
    key = _key(idempotency_key)
    operator_id = _operator_id(operator)
    note = _note(note)
    dividend_id = _positive_integer(dividend_id, 'dividend_not_found')
    expected_version = _positive_integer(expected_version, 'version_conflict')
    total = _money(total_cny)
    a_amount = _money(partner_a_amount_cny, 'partner_a_amount_cny')
    b_amount = _money(partner_b_amount_cny, 'partner_b_amount_cny')
    if a_amount + b_amount != total:
        raise DividendActionError('amount_split_mismatch')
    account_ids = []
    for value in (partner_a_account_id, partner_b_account_id):
        if value in (None, ''):
            account_ids.append(None)
            continue
        account_ids.append(_positive_integer(value, 'account_not_found'))
    target = Dividend.objects.filter(pk=dividend_id).first()
    if target is None:
        raise DividendActionError('dividend_not_found')
    fingerprint = _draft_fingerprint_for_id(
        action_type=DividendDraftAction.ActionType.UPDATE, total=total,
        business_date=target.business_date, operator_id=operator_id, note=note,
        dividend_id=dividend_id, a_amount=a_amount, b_amount=b_amount,
        a_account_id=account_ids[0], b_account_id=account_ids[1],
        expected_version=expected_version,
    )
    with transaction.atomic():
        _acquire_sqlite_writer_gate()
        replay = _action_replay(key=key, fingerprint=fingerprint)
        if replay is not None:
            return replay
        _require_day1()
        operator = _operator(operator)
        dividend = Dividend.objects.select_for_update().filter(pk=dividend_id).first()
        if dividend is None:
            raise DividendActionError('dividend_not_found')
        if dividend.status != Dividend.Status.DRAFT:
            raise DividendActionError('invalid_state', {'status': dividend.status})
        if dividend.version != expected_version:
            raise DividendActionError('version_conflict', {
                'expected_version': expected_version, 'actual_version': dividend.version,
            })
        if account_ids[0] is None or account_ids[1] is None:
            raise DividendActionError('account_required')
        if account_ids[0] == account_ids[1]:
            raise DividendActionError('account_same')
        accounts = _lock_cny_accounts(sorted(account_ids))
        a_account = accounts[account_ids[0]]
        b_account = accounts[account_ids[1]]
        dividend.total_cny = total
        dividend.partner_a_amount_cny = a_amount
        dividend.partner_b_amount_cny = b_amount
        dividend.partner_a_account = a_account
        dividend.partner_b_account = b_account
        dividend.updated_by = operator
        dividend.version += 1
        dividend.warning_fingerprint = None
        dividend.warning_ack = None
        dividend.warning_code = ''
        dividend.warning_retained_earnings_cny = None
        dividend.save(update_fields=[
            'total_cny', 'partner_a_amount_cny', 'partner_b_amount_cny',
            'partner_a_account', 'partner_b_account', 'updated_by', 'version',
            'warning_fingerprint', 'warning_ack', 'warning_code',
            'warning_retained_earnings_cny',
        ])
        _save_action(
            dividend=dividend, action_type=DividendDraftAction.ActionType.UPDATE,
            key=key, fingerprint=fingerprint, operator=operator,
        )
        return dividend


def _confirm_fingerprint(*, dividend, operator_id, expected_version,
                         warning_fingerprint, warning_ack):
    return _fingerprint({
        'action_type': 'confirm', 'dividend_id': dividend.pk,
        'operator': operator_id, 'expected_version': expected_version,
        'total_cny': str(dividend.total_cny),
        'partner_a_amount_cny': str(dividend.partner_a_amount_cny),
        'partner_b_amount_cny': str(dividend.partner_b_amount_cny),
        'partner_a_account_id': dividend.partner_a_account_id,
        'partner_b_account_id': dividend.partner_b_account_id,
        'business_date': dividend.business_date.isoformat(),
        'warning_fingerprint': warning_fingerprint,
        'warning_ack': warning_ack,
    })


def _warning_error(*, retained, requested, fingerprint):
    warning, current_fingerprint = _warning(retained=retained, requested=requested)
    raise DividendActionError('warning_stale', {
        'warning': warning,
        'fingerprint': current_fingerprint,
    })


def _validate_confirm_replay(dividend, *, key):
    """确认重放必须指向一笔完整、已入账且形状不变的分红流水。"""
    ledger = LedgerTransaction.objects.filter(
        pk=dividend.ledger_transaction_id,
    ).first()
    if ledger is None or ledger.status != LedgerTransaction.Status.POSTED:
        raise DividendActionError('idempotency_conflict')
    if (
        dividend.status != Dividend.Status.POSTED
        or dividend.confirm_idempotency_key != key
        or dividend.confirmed_by_id is None
        or ledger.transaction_type != LedgerTransaction.TransactionType.DIVIDEND
        or ledger.idempotency_key != key
        or ledger.source_type != 'dividend'
        or ledger.source_id != str(dividend.pk)
        or ledger.business_date != dividend.business_date
        or ledger.operator_id != dividend.confirmed_by_id
    ):
        raise DividendActionError('idempotency_conflict')
    if dividend.partner_a_account_id is None or dividend.partner_b_account_id is None:
        raise DividendActionError('idempotency_conflict')
    expected = sorted([
        (
            dividend.partner_a_account_id, '', FundAccount.Currency.CNY,
            -dividend.partner_a_amount_cny, -dividend.partner_a_amount_cny,
        ),
        (
            dividend.partner_b_account_id, '', FundAccount.Currency.CNY,
            -dividend.partner_b_amount_cny, -dividend.partner_b_amount_cny,
        ),
        (
            None, LedgerPosting.Category.DIVIDEND_DISTRIBUTION,
            FundAccount.Currency.CNY, dividend.total_cny, dividend.total_cny,
        ),
    ], key=lambda row: (row[0] is None, row[0] or 0, row[1]))
    actual = sorted([
        (row['account_id'], row['category'], row['currency'],
         row['amount'], row['cny_amount'])
        for row in ledger.postings.values(
            'account_id', 'category', 'currency', 'amount', 'cny_amount',
        )
    ], key=lambda row: (row[0] is None, row[0] or 0, row[1]))
    if actual != expected:
        raise DividendActionError('idempotency_conflict')


@_retry_sqlite_locked
def confirm_dividend(*, dividend_id, operator, idempotency_key, expected_version,
                     warning_fingerprint: str, warning_ack: bool) -> Dividend:
    key = _key(idempotency_key)
    operator_id = _operator_id(operator)
    dividend_id = _positive_integer(dividend_id, 'dividend_not_found')
    expected_version = _positive_integer(expected_version, 'version_conflict')
    if not isinstance(warning_fingerprint, str) or not warning_fingerprint:
        raise DividendActionError('warning_required')
    if not isinstance(warning_ack, bool):
        raise DividendActionError('warning_required')
    target = Dividend.objects.filter(pk=dividend_id).first()
    if target is None:
        raise DividendActionError('dividend_not_found')
    fingerprint = _confirm_fingerprint(
        dividend=target, operator_id=operator_id,
        expected_version=expected_version,
        warning_fingerprint=warning_fingerprint, warning_ack=warning_ack,
    )
    with transaction.atomic():
        _acquire_sqlite_writer_gate()
        existing = Dividend.objects.select_for_update().filter(
            confirm_idempotency_key=key,
        ).first()
        if existing is not None:
            if existing.confirm_request_fingerprint != fingerprint:
                raise DividendActionError('idempotency_conflict')
            _validate_confirm_replay(existing, key=key)
            return existing
        if LedgerTransaction.objects.filter(idempotency_key=key).exists():
            raise DividendActionError('idempotency_conflict')
        _require_day1()
        operator = _operator(operator)
        dividend = Dividend.objects.select_for_update().filter(pk=dividend_id).first()
        if dividend is None:
            raise DividendActionError('dividend_not_found')
        fingerprint = _confirm_fingerprint(
            dividend=dividend, operator_id=operator.pk,
            expected_version=expected_version,
            warning_fingerprint=warning_fingerprint, warning_ack=warning_ack,
        )
        if dividend.status != Dividend.Status.DRAFT:
            raise DividendActionError('invalid_state', {'status': dividend.status})
        if dividend.version != expected_version:
            raise DividendActionError('version_conflict', {
                'expected_version': expected_version, 'actual_version': dividend.version,
            })
        retained = _retained_earnings(as_of=dividend.business_date)
        warning, current_warning_fingerprint = _warning(
            retained=retained, requested=dividend.total_cny,
        )
        if warning_fingerprint != current_warning_fingerprint:
            _warning_error(
                retained=retained, requested=dividend.total_cny,
                fingerprint=warning_fingerprint,
            )
        if warning is not None and not warning_ack:
            raise DividendActionError('warning_required', {
                'warning': warning, 'fingerprint': current_warning_fingerprint,
            })
        if dividend.partner_a_account_id is None or dividend.partner_b_account_id is None:
            raise DividendActionError('account_required')
        if dividend.partner_a_account_id == dividend.partner_b_account_id:
            raise DividendActionError('account_same')
        account_ids = sorted((dividend.partner_a_account_id, dividend.partner_b_account_id))
        accounts = _lock_cny_accounts(account_ids)
        try:
            a_account = accounts[dividend.partner_a_account_id]
            b_account = accounts[dividend.partner_b_account_id]
            _outflow_cny_cost(a_account, dividend.partner_a_amount_cny)
            _outflow_cny_cost(b_account, dividend.partner_b_amount_cny)
        except LedgerError as error:
            raise DividendActionError('insufficient_balance') from error
        ledger = _post_transaction_once(
            transaction_type=LedgerTransaction.TransactionType.DIVIDEND,
            business_date=dividend.business_date,
            postings=[
                PostingInput(
                    account=a_account, currency=FundAccount.Currency.CNY,
                    amount=-dividend.partner_a_amount_cny,
                    cny_amount=-dividend.partner_a_amount_cny,
                ),
                PostingInput(
                    account=b_account, currency=FundAccount.Currency.CNY,
                    amount=-dividend.partner_b_amount_cny,
                    cny_amount=-dividend.partner_b_amount_cny,
                ),
                PostingInput(
                    category=LedgerPosting.Category.DIVIDEND_DISTRIBUTION,
                    currency=FundAccount.Currency.CNY,
                    amount=dividend.total_cny, cny_amount=dividend.total_cny,
                ),
            ],
            operator=operator, idempotency_key=key,
            description='分红确认', source_type='dividend',
            source_id=str(dividend.pk), _writer_gate=False,
        )
        # 预览字段是快照，确认时锁内刷新，避免 ACK 旧收益边界。
        dividend.warning_retained_earnings_cny = retained
        dividend.warning_fingerprint = current_warning_fingerprint
        dividend.warning_code = warning['code'] if warning else ''
        dividend.warning_ack = warning_ack
        dividend.save(update_fields=[
            'warning_retained_earnings_cny', 'warning_fingerprint',
            'warning_code', 'warning_ack',
        ])
        dividend.status = Dividend.Status.POSTED
        dividend.ledger_transaction = ledger
        dividend.confirmed_by = operator
        dividend.version += 1
        dividend.confirm_idempotency_key = key
        dividend.confirm_request_fingerprint = fingerprint
        with ledger_mutation_scope(
            reason='dividend_confirm', model='accounting.Dividend',
            operator=operator,
            allowed_fields={
                'status', 'ledger_transaction', 'confirmed_by', 'version',
                'confirm_idempotency_key', 'confirm_request_fingerprint',
            },
        ):
            dividend.save(update_fields=[
                'status', 'ledger_transaction', 'confirmed_by', 'version',
                'confirm_idempotency_key', 'confirm_request_fingerprint',
            ])
        return dividend
