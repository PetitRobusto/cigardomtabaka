import json
from datetime import date
from decimal import Decimal, InvalidOperation

from django.db import IntegrityError, transaction
from django.db.models import Prefetch
from django.http import JsonResponse

from accounting.decorators import staff_json_required
from accounting.models import FundAccount, LedgerPosting, LedgerTransaction
from accounting.serializers import serialize_account, serialize_snapshot, serialize_transaction
from accounting.services import (
    LedgerError,
    _exchange_to_rub_with_result,
    _record_opening_balance_with_result,
    _transfer_same_currency_with_result,
)
from cigars.models import User


class ApiInputError(Exception):
    pass


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


def _required_id(payload, field_name):
    value = payload.get(field_name)
    if type(value) is int:
        parsed = value
    elif isinstance(value, str) and value.isdecimal():
        parsed = int(value)
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
        return JsonResponse({'error': '请求方法不支持'}, status=400)
    try:
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
        records = records.distinct().order_by('business_date', 'effective_sequence', 'id')
        return JsonResponse({'transactions': [serialize_transaction(record) for record in records]})
    except (ApiInputError, InvalidOperation, ValueError) as error:
        return JsonResponse({'error': str(error)}, status=400)
