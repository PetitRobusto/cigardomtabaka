"""按轮分配与分别领取；新事实只追加，不改写历史 A/B 分红。"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import transaction

from accounting.dividend_actions import (
    DividendActionError, _date, _fingerprint, _key, _money, _note,
    _operator, _operator_id, _positive_integer, _require_day1, _warning,
)
from accounting.models import DividendPayout, DividendRound, FundAccount, LedgerPosting, LedgerTransaction
from accounting.mutation_scope import ledger_mutation_scope
from accounting.selectors import retained_earnings
from accounting.services import (
    LedgerError, PostingInput, _acquire_sqlite_writer_gate,
    _outflow_cny_cost, _post_transaction_once, _retry_sqlite_locked,
)


def _agent(value):
    if not isinstance(value, str) or len(value) > 128:
        raise DividendActionError('invalid_agent_source')
    return value


def _round_input(*, total_cny, partner_a_id, partner_b_id, business_date, note='', agent_source=''):
    total = _money(total_cny)
    if total <= 0:
        raise DividendActionError('invalid_amount')
    if (total * 100) % 2:
        raise DividendActionError('uneven_split')
    a = _positive_integer(partner_a_id, 'invalid_recipient')
    b = _positive_integer(partner_b_id, 'invalid_recipient')
    if a == b:
        raise DividendActionError('recipient_same')
    return {
        'total_cny': str(total), 'partner_a_id': a, 'partner_b_id': b,
        'business_date': _date(business_date).isoformat(), 'note': _note(note),
        'agent_source': _agent(agent_source),
    }


def _partners(a, b):
    users = {user.pk: user for user in get_user_model().objects.filter(pk__in=[a, b], is_active=True)}
    if len(users) != 2:
        raise DividendActionError('invalid_recipient')
    return users


def _name(user):
    return (user.get_full_name() or user.username)[:255]


def _preview(body, operator):
    retained = retained_earnings(as_of=_date(body['business_date']))
    warning, _ = _warning(retained=retained, requested=Decimal(body['total_cny']))
    return {
        'retained_earnings_cny': str(retained), 'requested_cny': body['total_cny'],
        'warning': warning,
        'warning_fingerprint': _fingerprint({'request': body, 'operator_id': _operator_id(operator), 'retained_earnings_cny': str(retained)}),
    }


def preview_dividend_round(*, operator, **payload):
    _require_day1()
    _operator(operator)
    body = _round_input(**payload)
    _partners(body['partner_a_id'], body['partner_b_id'])
    return _preview(body, operator)


def _round_postings(total):
    return [
        PostingInput(category=LedgerPosting.Category.DIVIDEND_DISTRIBUTION, currency='CNY', amount=total, cny_amount=total),
        PostingInput(category=LedgerPosting.Category.DIVIDEND_PAYABLE, currency='CNY', amount=-total, cny_amount=-total),
    ]


def _payout_postings(account, amount):
    return [
        PostingInput(category=LedgerPosting.Category.DIVIDEND_PAYABLE, currency='CNY', amount=amount, cny_amount=amount),
        PostingInput(account=account, currency='CNY', amount=-amount, cny_amount=-amount),
    ]


def _post(*, fact_type, key, body, operator, postings):
    return _post_transaction_once(
        transaction_type=LedgerTransaction.TransactionType.DIVIDEND if fact_type == 'dividend_round' else LedgerTransaction.TransactionType.DIVIDEND_PAYOUT,
        business_date=_date(body['business_date']), postings=postings,
        operator=operator, idempotency_key=key,
        description='分红分配' if fact_type == 'dividend_round' else '分红领取',
        source_type=fact_type, source_id=key, _writer_gate=False,
    )


def _fact_signature(fact):
    """核对不可变快照，包括姓名、利润快照和流水指针，而非当前人员名称。"""
    return _fingerprint({field.attname: str(getattr(fact, field.attname))
                         for field in fact._meta.concrete_fields
                         if field.name not in ('id', 'created_at', 'fact_fingerprint')})


def _verify_fact(fact):
    if fact.fact_fingerprint != _fact_signature(fact):
        raise DividendActionError('idempotency_conflict')


def _save(fact, reason):
    fact.fact_fingerprint = _fact_signature(fact)
    with ledger_mutation_scope(reason=reason, model=f'accounting.{type(fact).__name__}', operator=fact.operator, allowed_fields={field.name for field in fact._meta.concrete_fields}):
        fact.save(force_insert=True)
    return fact


@_retry_sqlite_locked
def confirm_dividend_round(*, operator, idempotency_key, warning_fingerprint, warning_ack, **payload):
    key = _key(idempotency_key)
    body = _round_input(**payload)
    if not isinstance(warning_fingerprint, str) or not warning_fingerprint or type(warning_ack) is not bool:
        raise DividendActionError('warning_required')
    fingerprint = _fingerprint({**body, 'operator_id': _operator_id(operator), 'warning_fingerprint': warning_fingerprint, 'warning_ack': warning_ack})
    with transaction.atomic():
        _acquire_sqlite_writer_gate()
        existing = DividendRound.objects.select_for_update().filter(idempotency_key=key).first()
        if existing:
            _verify_fact(existing)
            if existing.request_fingerprint != fingerprint or any(str(getattr(existing, name)) != str(value) for name, value in body.items()) or existing.operator_id != _operator_id(operator) or existing.warning_fingerprint != warning_fingerprint or existing.warning_ack != warning_ack:
                raise DividendActionError('idempotency_conflict')
            ledger = _post(fact_type='dividend_round', key=key, body=body, operator=operator, postings=_round_postings(Decimal(body['total_cny'])))
            if ledger.pk != existing.ledger_transaction_id or existing.status != 'posted':
                raise DividendActionError('idempotency_conflict')
            return existing
        if LedgerTransaction.objects.filter(idempotency_key=key).exists():
            raise DividendActionError('idempotency_conflict')
        _require_day1()
        operator = _operator(operator)
        users = _partners(body['partner_a_id'], body['partner_b_id'])
        preview = _preview(body, operator)
        if warning_fingerprint != preview['warning_fingerprint']:
            raise DividendActionError('warning_stale', preview)
        if preview['warning'] and not warning_ack:
            raise DividendActionError('warning_required', preview)
        ledger = _post(fact_type='dividend_round', key=key, body=body, operator=operator, postings=_round_postings(Decimal(body['total_cny'])))
        return _save(DividendRound(
            **{**body, 'total_cny': Decimal(body['total_cny']), 'business_date': _date(body['business_date'])},
            partner_a_name=_name(users[body['partner_a_id']]), partner_b_name=_name(users[body['partner_b_id']]),
            operator=operator, ledger_transaction=ledger, idempotency_key=key, request_fingerprint=fingerprint,
            warning_fingerprint=warning_fingerprint, warning_ack=warning_ack,
            warning_retained_earnings_cny=Decimal(preview['retained_earnings_cny']),
        ), 'dividend_round')


@_retry_sqlite_locked
def record_dividend_payout(*, round_id, recipient_id, fund_account_id, amount_cny, business_date, operator, idempotency_key, note='', agent_source=''):
    key = _key(idempotency_key)
    amount = _money(amount_cny, 'amount_cny')
    if amount <= 0:
        raise DividendActionError('invalid_amount')
    body = {
        'round_id': _positive_integer(round_id, 'dividend_not_found'),
        'recipient_id': _positive_integer(recipient_id, 'invalid_recipient'),
        'fund_account_id': _positive_integer(fund_account_id, 'account_not_found'),
        'amount_cny': str(amount), 'business_date': _date(business_date).isoformat(),
        'note': _note(note), 'agent_source': _agent(agent_source),
    }
    fingerprint = _fingerprint({**body, 'operator_id': _operator_id(operator)})
    with transaction.atomic():
        _acquire_sqlite_writer_gate()
        existing = DividendPayout.objects.select_for_update().filter(idempotency_key=key).first()
        if existing:
            _verify_fact(existing)
            if existing.request_fingerprint != fingerprint or any(str(getattr(existing, name)) != str(value) for name, value in body.items()) or existing.operator_id != _operator_id(operator):
                raise DividendActionError('idempotency_conflict')
            ledger = _post(fact_type='dividend_payout', key=key, body=body, operator=operator, postings=_payout_postings(existing.fund_account, amount))
            if ledger.pk != existing.ledger_transaction_id or existing.status != 'posted':
                raise DividendActionError('idempotency_conflict')
            return existing
        if LedgerTransaction.objects.filter(idempotency_key=key).exists():
            raise DividendActionError('idempotency_conflict')
        _require_day1()
        operator = _operator(operator)
        round = DividendRound.objects.select_for_update().filter(pk=body['round_id']).first()
        if round is None:
            raise DividendActionError('dividend_not_found')
        _verify_fact(round)
        recipient = body['recipient_id']
        if recipient not in (round.partner_a_id, round.partner_b_id):
            raise DividendActionError('invalid_recipient')
        if not get_user_model().objects.filter(pk=recipient, is_active=True).exists():
            raise DividendActionError('invalid_recipient')
        if _date(body['business_date']) < round.business_date:
            raise DividendActionError('invalid_business_date')
        paid = sum(round.payouts.filter(recipient_id=recipient).values_list('amount_cny', flat=True), Decimal('0.00'))
        if amount > round.total_cny / 2 - paid:
            raise DividendActionError('payout_exceeded')
        account = FundAccount.objects.select_for_update().filter(pk=body['fund_account_id']).first()
        if account is None:
            raise DividendActionError('account_not_found')
        if not account.is_active:
            raise DividendActionError('account_inactive')
        if account.currency != 'CNY':
            raise DividendActionError('currency_rule')
        try:
            _outflow_cny_cost(account, amount)
        except LedgerError as error:
            raise DividendActionError('insufficient_balance') from error
        ledger = _post(fact_type='dividend_payout', key=key, body=body, operator=operator, postings=_payout_postings(account, amount))
        return _save(DividendPayout(
            **{**body, 'amount_cny': amount, 'business_date': _date(body['business_date'])},
            recipient_name=round.partner_a_name if recipient == round.partner_a_id else round.partner_b_name,
            operator=operator, ledger_transaction=ledger, idempotency_key=key, request_fingerprint=fingerprint,
        ), 'dividend_payout')
