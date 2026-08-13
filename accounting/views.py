import json
from datetime import date
from decimal import Decimal, InvalidOperation

from django.db import IntegrityError, OperationalError, transaction
from django.db.models import Prefetch
from django.http import JsonResponse

from accounting.business_time import moscow_business_date
from accounting.decorators import staff_json_required
from accounting.day1 import (
    Day1Conflict, Day1ValidationError, Day1VersionConflict,
    confirm_day1, get_day1_state, save_day1_draft,
)
from accounting.day1_serializers import serialize_day1_state
from accounting.models import (
    AccountReconciliation, FundAccount, LedgerPosting, LedgerTransaction,
)
from accounting.selectors import (
    accounting_dashboard, accounting_summary, monthly_profit,
)
from accounting.serializers import serialize_account, serialize_snapshot, serialize_transaction
from accounting.services import (
    LedgerError,
    ReconciliationConflictError,
    _exchange_to_rub_with_result,
    _record_opening_balance_with_result,
    _transfer_same_currency_with_result,
    confirm_reconciliation,
    create_reconciliation,
)
from cigars.models import User


class ApiInputError(Exception):
    pass


def _json_value(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def _serialize_reconciliation(record):
    return {
        'id': record.id,
        'account_id': record.account_id,
        'business_date': record.business_date.isoformat(),
        'system_amount': format(record.system_amount, '.8f'),
        'actual_amount': format(record.actual_amount, '.8f'),
        'difference': format(record.difference, '.8f'),
        'status': record.status,
        'operator_id': record.operator_id,
        'confirmer_id': record.confirmer_id,
        'note': record.note,
        'created_at': record.created_at.isoformat(),
        'updated_at': record.updated_at.isoformat(),
    }


def _json_object(request):
    if request.content_type != 'application/json':
        raise ApiInputError('请求体必须是 JSON 对象')
    try:
        payload = json.loads(request.body.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ApiInputError('请求体必须是 JSON 对象')
    if not isinstance(payload, dict):
        raise ApiInputError('请求体必须是 JSON 对象')
    return payload


def _idempotency_key(request):
    key = request.headers.get('Idempotency-Key', '').strip()
    if not key:
        raise ApiInputError('幂等键不能为空')
    if len(key) > 128:
        raise ApiInputError('幂等键长度不能超过128个字符')
    return key


def _if_match_version(request):
    """Use the shared draft version to prevent silent operator overwrites."""
    raw = request.headers.get('If-Match', '').strip()
    if not raw:
        raise ApiInputError('If-Match 版本不能为空')
    # Bound the input before int() to avoid Python's huge-integer conversion limit.
    if len(raw) > 19 or not raw.isdecimal():
        raise ApiInputError('If-Match 版本无效')
    value = int(raw)
    if value < 0:
        raise ApiInputError('If-Match 版本无效')
    return value


def _required_id(payload, field_name):
    value = payload.get(field_name)
    if type(value) is int:
        parsed = value
    elif isinstance(value, str) and value.isdecimal():
        if len(value) > 19:
            raise ApiInputError(f'{field_name}无效')
        try:
            parsed = int(value)
        except ValueError:
            raise ApiInputError(f'{field_name}无效')
    else:
        raise ApiInputError(f'{field_name}无效')
    if not 1 <= parsed <= 9223372036854775807:
        raise ApiInputError(f'{field_name}无效')
    return parsed


def _required_decimal_string(payload, field_name):
    value = payload.get(field_name)
    if not isinstance(value, str):
        raise ApiInputError(f'{field_name}必须是金额字符串')
    try:
        decimal_value = Decimal(value)
    except InvalidOperation:
        raise ApiInputError(f'{field_name}必须是有效金额')
    if not decimal_value.is_finite():
        raise ApiInputError(f'{field_name}必须是有效金额')
    return decimal_value


def _required_business_date(payload):
    value = payload.get('business_date')
    return _parse_iso_date(value, 'business_date')


def _parse_iso_date(value, field_name):
    if not isinstance(value, str):
        raise ApiInputError(f'{field_name}无效')
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ApiInputError(f'{field_name}无效')


def _transaction_response(ledger_transaction, status=200):
    accounts = {
        posting.account_id: posting.account
        for posting in ledger_transaction.postings.select_related('account').all()
        if posting.account_id is not None
    }
    return JsonResponse({
        'transaction': serialize_transaction(ledger_transaction),
        'snapshots': [serialize_snapshot(account) for _, account in sorted(accounts.items())],
    }, status=status)


def _description(payload):
    value = payload.get('description', '')
    if not isinstance(value, str):
        raise ApiInputError('description无效')
    return value


def _day1_error_response(error):
    """Map domain failures to a stable API shape for the setup wizard."""
    if isinstance(error, Day1VersionConflict):
        return JsonResponse({
            'error': str(error), 'code': 'version_conflict',
        }, status=409)
    if isinstance(error, Day1Conflict):
        return JsonResponse({
            'error': str(error),
            'code': 'day1_conflict',
            'conflicts': list(error.conflicts),
        }, status=409)
    if isinstance(error, Day1ValidationError):
        return JsonResponse({
            'error': str(error),
            'code': 'validation_error',
            'details': error.details,
        }, status=400)
    return JsonResponse({
        'error': str(error), 'code': 'input_error',
    }, status=400)


@staff_json_required
def day1_status(request):
    if request.method != 'GET':
        return JsonResponse({'error': '请求方法不支持'}, status=405)
    return JsonResponse(serialize_day1_state(get_day1_state()))


@staff_json_required
def day1_draft(request):
    if request.method != 'PUT':
        return JsonResponse({'error': '请求方法不支持'}, status=405)
    try:
        saved = save_day1_draft(
            payload=_json_object(request),
            expected_version=_if_match_version(request),
            operator=request.accounting_operator,
        )
        # Re-read with prefetched children so the response exactly matches GET.
        return JsonResponse(serialize_day1_state(get_day1_state() or saved))
    except (ApiInputError, Day1ValidationError, Day1VersionConflict, Day1Conflict) as error:
        return _day1_error_response(error)
    except OperationalError:
        return JsonResponse({'error': '账务系统繁忙，请重试'}, status=503)


@staff_json_required
def day1_confirm(request):
    if request.method != 'POST':
        return JsonResponse({'error': '请求方法不支持'}, status=405)
    try:
        payload = _json_object(request)
        version = payload.get('version')
        if isinstance(version, bool) or not isinstance(version, int) or version < 0:
            raise ApiInputError('version 无效')
        confirm_day1(
            expected_version=version,
            operator=request.accounting_operator,
            idempotency_key=_idempotency_key(request),
        )
        return JsonResponse(serialize_day1_state(get_day1_state()))
    except (ApiInputError, Day1ValidationError, Day1VersionConflict, Day1Conflict) as error:
        return _day1_error_response(error)
    except OperationalError:
        return JsonResponse({'error': '账务系统繁忙，请重试'}, status=503)


@staff_json_required
def dashboard(request):
    if request.method != 'GET':
        return JsonResponse({'error': '请求方法不支持'}, status=405)
    initialization = get_day1_state()
    status = initialization.status if initialization else 'not_started'
    if status != 'completed':
        # Unknown opening values must remain null instead of looking like real zeros.
        return JsonResponse({
            'requires_day1': True,
            'day1_status': status,
            'stats': {
                'cny_funds_total': None,
                'inventory_book_cost_cny': None,
                'accounts_receivable_cny': None,
                'month_net_profit_cny': None,
            },
            'accounts': [],
            'monthly_profit': None,
            'reconciliation': {'pending_count': 0, 'latest': []},
        })
    # Accounting periods follow the Moscow operation, not Django's site timezone.
    data = accounting_dashboard(as_of=moscow_business_date())
    return JsonResponse(_json_value({
        'requires_day1': False,
        'day1_status': status,
        **data,
    }))


@staff_json_required
def accounts(request):
    if request.method == 'GET':
        accounts = FundAccount.objects.select_related('custodian')
        return JsonResponse({'accounts': [serialize_account(account) for account in accounts]})
    if request.method != 'POST':
        return JsonResponse({'error': '请求方法不支持'}, status=400)

    try:
        payload = _json_object(request)
        key = _idempotency_key(request)
        name = payload.get('name')
        currency = payload.get('currency')
        if not isinstance(name, str) or not name.strip():
            raise ApiInputError('账户名称不能为空')
        if currency not in FundAccount.Currency.values:
            raise ApiInputError('账户币种无效')

        custodian_id = payload.get('custodian_id')
        if custodian_id is not None:
            try:
                custodian_id = _required_id(payload, 'custodian_id')
                custodian = User.objects.get(pk=custodian_id)
            except User.DoesNotExist:
                raise ApiInputError('保管人不存在')
        else:
            custodian = None

        existing = FundAccount.objects.filter(creation_idempotency_key=key).first()
        if existing is not None:
            if (existing.name, existing.currency, existing.custodian_id) != (name, currency, custodian_id):
                raise ApiInputError('幂等键已用于不同账户请求')
            return JsonResponse({'account': serialize_account(existing)})

        try:
            with transaction.atomic():
                account = FundAccount.objects.create(
                    name=name,
                    currency=currency,
                    custodian=custodian,
                    creation_idempotency_key=key,
                )
        except IntegrityError:
            existing = FundAccount.objects.filter(creation_idempotency_key=key).first()
            if existing is not None:
                if (existing.name, existing.currency, existing.custodian_id) != (name, currency, custodian_id):
                    raise ApiInputError('幂等键已用于不同账户请求')
                return JsonResponse({'account': serialize_account(existing)})
            raise ApiInputError('账户名称已存在')
        return JsonResponse({'account': serialize_account(account)}, status=201)
    except ApiInputError as error:
        return JsonResponse({'error': str(error)}, status=400)


@staff_json_required
def opening_balances(request):
    if request.method != 'POST':
        return JsonResponse({'error': '请求方法不支持'}, status=400)
    try:
        payload = _json_object(request)
        key = _idempotency_key(request)
        account = FundAccount.objects.get(pk=_required_id(payload, 'account_id'))
        result = _record_opening_balance_with_result(
            account=account,
            original_amount=_required_decimal_string(payload, 'original_amount'),
            cny_book_cost=_required_decimal_string(payload, 'cny_book_cost'),
            equity_category=payload.get('equity_category'),
            business_date=_required_business_date(payload),
            operator=request.accounting_operator,
            idempotency_key=key,
        )
        return _transaction_response(result.transaction, status=201 if result.created else 200)
    except (ApiInputError, LedgerError, FundAccount.DoesNotExist, InvalidOperation, ValueError) as error:
        return JsonResponse({'error': str(error)}, status=400)


@staff_json_required
def exchanges(request):
    if request.method != 'POST':
        return JsonResponse({'error': '请求方法不支持'}, status=400)
    try:
        payload = _json_object(request)
        key = _idempotency_key(request)
        result = _exchange_to_rub_with_result(
            source_account=FundAccount.objects.get(pk=_required_id(payload, 'source_account_id')),
            rub_account=FundAccount.objects.get(pk=_required_id(payload, 'rub_account_id')),
            source_amount=_required_decimal_string(payload, 'source_amount'),
            rub_amount=_required_decimal_string(payload, 'rub_amount'),
            business_date=_required_business_date(payload),
            operator=request.accounting_operator,
            idempotency_key=key,
            description=_description(payload),
        )
        return _transaction_response(result.transaction, status=201 if result.created else 200)
    except (ApiInputError, LedgerError, FundAccount.DoesNotExist, InvalidOperation, ValueError) as error:
        return JsonResponse({'error': str(error)}, status=400)


@staff_json_required
def transfers(request):
    if request.method != 'POST':
        return JsonResponse({'error': '请求方法不支持'}, status=400)
    try:
        payload = _json_object(request)
        key = _idempotency_key(request)
        result = _transfer_same_currency_with_result(
            source_account=FundAccount.objects.get(pk=_required_id(payload, 'source_account_id')),
            target_account=FundAccount.objects.get(pk=_required_id(payload, 'target_account_id')),
            amount=_required_decimal_string(payload, 'amount'),
            business_date=_required_business_date(payload),
            operator=request.accounting_operator,
            idempotency_key=key,
            description=_description(payload),
        )
        return _transaction_response(result.transaction, status=201 if result.created else 200)
    except (ApiInputError, LedgerError, FundAccount.DoesNotExist, InvalidOperation, ValueError) as error:
        return JsonResponse({'error': str(error)}, status=400)


@staff_json_required
def overview(request):
    if request.method != 'GET':
        return JsonResponse({'error': '请求方法不支持'}, status=400)
    accounts = FundAccount.objects.filter(is_active=True).select_related('custodian')
    return JsonResponse({
        'accounts': [serialize_snapshot(account) for account in accounts],
    })


@staff_json_required
def transactions(request):
    if request.method != 'GET':
        return JsonResponse({'error': '请求方法不支持'}, status=405)
    try:
        raw_limit = request.GET.get('limit', '100')
        try:
            limit = int(raw_limit)
        except (TypeError, ValueError):
            raise ApiInputError('limit 必须是整数')
        if not 1 <= limit <= 500:
            raise ApiInputError('limit 必须在1到500之间')
        records = LedgerTransaction.objects.select_related('operator').prefetch_related(
            Prefetch('postings', queryset=LedgerPosting.objects.select_related('account').order_by('id')),
        )
        account_id = request.GET.get('account_id')
        if account_id is not None:
            records = records.filter(postings__account_id=_required_id({'account_id': account_id}, 'account_id'))
        date_from = request.GET.get('business_date_from')
        date_to = request.GET.get('business_date_to')
        if date_from is not None:
            date_from = _parse_iso_date(date_from, 'business_date_from')
            records = records.filter(business_date__gte=date_from)
        if date_to is not None:
            date_to = _parse_iso_date(date_to, 'business_date_to')
            records = records.filter(business_date__lte=date_to)
        if date_from is not None and date_to is not None and date_from > date_to:
            raise ApiInputError('business_date范围无效')
        records = records.distinct().order_by(
            'business_date', 'effective_sequence', 'id',
        )[:limit]
        return JsonResponse({'transactions': [serialize_transaction(record) for record in records]})
    except (ApiInputError, InvalidOperation, ValueError) as error:
        return JsonResponse({'error': str(error)}, status=400)


@staff_json_required
def monthly_profit_report(request):
    if request.method != 'GET':
        return JsonResponse({'error': '请求方法不支持'}, status=405)
    value = request.GET.get('month')
    try:
        if not isinstance(value, str) or len(value) != 7:
            raise ValueError
        month = date.fromisoformat(f'{value}-01')
        return JsonResponse(_json_value(monthly_profit(month=month)))
    except (TypeError, ValueError):
        return JsonResponse({'error': 'month 必须是 YYYY-MM'}, status=400)


@staff_json_required
def summary_report(request):
    if request.method != 'GET':
        return JsonResponse({'error': '请求方法不支持'}, status=405)
    try:
        as_of = _parse_iso_date(request.GET.get('as_of'), 'as_of')
        return JsonResponse(_json_value(accounting_summary(as_of=as_of)))
    except (ApiInputError, TypeError, ValueError) as error:
        return JsonResponse({'error': str(error)}, status=400)


@staff_json_required
def reconciliations(request):
    if request.method == 'GET':
        raw_limit = request.GET.get('limit', '50')
        try:
            limit = int(raw_limit)
        except (TypeError, ValueError):
            return JsonResponse({'error': 'limit 必须是整数'}, status=400)
        if not 1 <= limit <= 500:
            return JsonResponse({'error': 'limit 必须在1到500之间'}, status=400)
        records = AccountReconciliation.objects.select_related('account', 'operator')
        records = records[:limit]
        return JsonResponse({
            'reconciliations': [_serialize_reconciliation(record) for record in records],
        })
    if request.method != 'POST':
        return JsonResponse({'error': '请求方法不支持'}, status=405)
    try:
        payload = _json_object(request)
        key = _idempotency_key(request)
        note = payload.get('note', '')
        if not isinstance(note, str):
            raise ApiInputError('note无效')
        result = create_reconciliation(
            account=FundAccount.objects.get(pk=_required_id(payload, 'account_id')),
            business_date=_required_business_date(payload),
            actual_amount=_required_decimal_string(payload, 'actual_amount'),
            operator=request.accounting_operator,
            idempotency_key=key,
            note=note,
            return_result=True,
        )
        return JsonResponse({'reconciliation': _serialize_reconciliation(result.reconciliation)}, status=201 if result.created else 200)
    except ReconciliationConflictError as error:
        return JsonResponse({'error': str(error)}, status=409)
    except OperationalError:
        return JsonResponse({'error': '账务系统繁忙，请重试'}, status=503)
    except (ApiInputError, LedgerError, FundAccount.DoesNotExist, InvalidOperation, ValueError) as error:
        return JsonResponse({'error': str(error)}, status=400)


@staff_json_required
def reconciliation_confirm(request, reconciliation_id):
    if request.method != 'POST':
        return JsonResponse({'error': '请求方法不支持'}, status=405)
    try:
        _json_object(request)
        result = confirm_reconciliation(
            reconciliation_id=reconciliation_id,
            operator=request.accounting_operator,
            idempotency_key=_idempotency_key(request),
            return_result=True,
        )
        return JsonResponse({'reconciliation': _serialize_reconciliation(result.reconciliation)})
    except ReconciliationConflictError as error:
        return JsonResponse({'error': str(error)}, status=409)
    except OperationalError:
        return JsonResponse({'error': '账务系统繁忙，请重试'}, status=503)
    except (ApiInputError, LedgerError, InvalidOperation, ValueError) as error:
        return JsonResponse({'error': str(error)}, status=400)
