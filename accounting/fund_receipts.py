"""实际投入公司人民币资金的受控命令；不参与经营利润。"""
from datetime import date

from django.contrib.auth import get_user_model
from django.db import transaction

from accounting.business_time import moscow_business_date
from accounting.guards import require_day1_completed
from accounting.models import FundAccount, FundReceipt, LedgerPosting, LedgerTransaction
from accounting.mutation_scope import ledger_mutation_scope
from accounting.services import (
    CUTOVER_DATE, LedgerError, PostingInput, _acquire_sqlite_writer_gate,
    _positive_amount, _post_transaction_once, _require_operator, _retry_sqlite_locked,
)


def _positive_id(value):
    if type(value) is not int or not 0 < value <= 9223372036854775807:
        raise LedgerError('人员或账户编号无效', code='input_error')
    return value


def _postings(account, amount):
    return [
        PostingInput(account=account, currency='CNY', amount=amount, cny_amount=amount),
        PostingInput(category=LedgerPosting.Category.CONTRIBUTED_CAPITAL,
                     currency='CNY', amount=-amount, cny_amount=-amount),
    ]


@_retry_sqlite_locked
@transaction.atomic
def record_fund_receipt(*, contributor_id, fund_account_id, amount_cny, business_date,
                        operator, idempotency_key, note='', agent_source=''):
    contributor_id = _positive_id(contributor_id)
    fund_account_id = _positive_id(fund_account_id)
    amount = _positive_amount(amount_cny, 'CNY', '到账金额')
    if type(business_date) is not date or not CUTOVER_DATE <= business_date <= moscow_business_date():
        raise LedgerError('到账日期须在账务启用日至今天之间', code='invalid_business_date')
    if not isinstance(idempotency_key, str) or not idempotency_key.strip() or len(idempotency_key) > 128:
        raise LedgerError('操作编号无效', code='invalid_idempotency_key')
    if not isinstance(note, str) or len(note) > 2000:
        raise LedgerError('备注须为不超过 2000 字的文本', code='input_error')
    if not isinstance(agent_source, str) or len(agent_source) > 128:
        raise LedgerError('来源须为不超过 128 字的文本', code='input_error')
    _acquire_sqlite_writer_gate()
    # 相同账户串行化，并在锁内查询重放；账户停用不破坏既有事实的重试。
    account = FundAccount.objects.select_for_update().filter(pk=fund_account_id).first()
    if account is None:
        raise LedgerError('收款账户不存在', code='account_not_found')
    existing = FundReceipt.objects.select_related('ledger_transaction').filter(idempotency_key=idempotency_key).first()
    if existing is not None:
        if (existing.contributor_id != contributor_id or existing.fund_account_id != fund_account_id
                or existing.amount_cny != amount or existing.business_date != business_date
                or existing.operator_id != getattr(operator, 'pk', None)
                or existing.note != note or existing.agent_source != agent_source
                or existing.ledger_transaction.idempotency_key != idempotency_key
                or existing.ledger_transaction.reversed_by_id is not None):
            raise LedgerError('操作编号已用于不同的入账内容', code='idempotency_conflict')
        ledger = _post_transaction_once(
            transaction_type=LedgerTransaction.TransactionType.FUND_RECEIPT,
            business_date=business_date, postings=_postings(account, amount), operator=operator,
            idempotency_key=idempotency_key, description=note, source_type='fund_receipt',
            source_id=idempotency_key, _writer_gate=False,
        )
        if ledger.pk != existing.ledger_transaction_id:
            raise LedgerError('入账流水不一致', code='idempotency_conflict')
        return existing, False
    if LedgerTransaction.objects.filter(idempotency_key=idempotency_key).exists():
        raise LedgerError('操作编号已经使用', code='idempotency_conflict')
    require_day1_completed()
    persisted_operator = _require_operator(operator)
    if not account.is_active:
        raise LedgerError('收款账户已停用', code='account_inactive')
    if account.currency != 'CNY':
        raise LedgerError('请选择人民币收款账户', code='currency_rule')
    contributor = get_user_model().objects.filter(pk=contributor_id, is_active=True).first()
    if contributor is None:
        raise LedgerError('请选择启用的投入人', code='input_error')
    ledger = _post_transaction_once(
        transaction_type=LedgerTransaction.TransactionType.FUND_RECEIPT,
        business_date=business_date, postings=_postings(account, amount), operator=persisted_operator,
        idempotency_key=idempotency_key, description=note, source_type='fund_receipt',
        source_id=idempotency_key, _writer_gate=False,
    )
    receipt = FundReceipt(
        contributor=contributor, contributor_name=contributor.get_full_name() or contributor.username,
        fund_account=account, amount_cny=amount, business_date=business_date,
        operator=persisted_operator, agent_source=agent_source, note=note,
        ledger_transaction=ledger, idempotency_key=idempotency_key,
    )
    with ledger_mutation_scope(reason='fund_receipt', model='accounting.FundReceipt', operator=persisted_operator):
        receipt.save(force_insert=True)
    return receipt, True


def serialize_fund_receipt(receipt):
    return {
        'id': receipt.pk, 'contributor_id': receipt.contributor_id,
        'contributor_name': receipt.contributor_name, 'fund_account_id': receipt.fund_account_id,
        'fund_account_name': receipt.fund_account.name, 'amount_cny': str(receipt.amount_cny),
        'business_date': receipt.business_date.isoformat(), 'note': receipt.note,
        'operator_id': receipt.operator_id, 'agent_source': receipt.agent_source,
        'ledger_transaction_id': receipt.ledger_transaction_id,
    }
