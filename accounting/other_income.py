"""已取得且已到账的其他收入；原币收付、人民币核算。"""
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction

from accounting.business_time import moscow_business_date
from accounting.guards import require_day1_completed
from accounting.income_categories import validate_income_category
from accounting.models import (
    AccountReconciliation, FundAccount, LedgerPosting, LedgerTransaction,
    OtherIncome, OtherIncomeReversal,
)
from accounting.mutation_scope import ledger_mutation_scope
from accounting.services import (
    CUTOVER_DATE, MAX_ORIGINAL_ABS, LedgerError, PostingInput,
    _acquire_sqlite_writer_gate, _positive_amount, _post_transaction_once,
    _require_operator, _retry_sqlite_locked, _reverse_ledger_transaction,
    _strict_external_decimal,
)


INCOME_CATEGORIES = {
    OtherIncome.Category.INTEREST: LedgerPosting.Category.INTEREST_INCOME,
    OtherIncome.Category.USED_ITEM: LedgerPosting.Category.USED_ITEM_INCOME,
    OtherIncome.Category.OTHER: LedgerPosting.Category.OTHER_INCOME,
}
_REVERSIBLE = frozenset({LedgerTransaction.TransactionType.OTHER_INCOME})


def _text(value, label, limit, *, required=False):
    if not isinstance(value, str) or len(value) > limit or (required and not value.strip()):
        raise LedgerError(f'{label}须为{limit}字以内的' + ('非空文本' if required else '文本'), code='input_error')
    return value


def _identity(value):
    if type(value) is not int or not 0 < value <= 9223372036854775807:
        raise LedgerError('记录或账户编号无效', code='input_error')
    return value


def _metadata(business_date, key, note, agent_source):
    if type(business_date) is not date or not CUTOVER_DATE <= business_date <= moscow_business_date():
        raise LedgerError('业务日期须在账务启用日至今天之间', code='invalid_business_date')
    _text(key, '操作编号', 128, required=True)
    _text(note, '来源说明或冲正原因', 2000, required=True)
    _text(agent_source, 'Agent 来源', 128)


def _unreconciled(account_id, business_date):
    if AccountReconciliation.objects.filter(
        account_id=account_id, status=AccountReconciliation.Status.CONFIRMED,
        business_date__gte=business_date,
    ).exists():
        raise LedgerError('该收入日期已被确认对账覆盖，不能直接入账或冲正', code='income_reconciled_period')


def _postings(account, category, amount, cny_amount):
    return [
        PostingInput(account=account, currency=account.currency, amount=amount, cny_amount=cny_amount),
        PostingInput(category=INCOME_CATEGORIES[category], currency='CNY', amount=-cny_amount, cny_amount=-cny_amount),
    ]


@_retry_sqlite_locked
@transaction.atomic
def record_other_income(*, category, fund_account_id, amount, business_date, operator,
                        idempotency_key, note, exchange_rate=None, rate_source='',
                        reference='', zero_book_value_confirmed=False, agent_source='',
                        subcategory='', recognition_confirmed=False):
    """收益与到账同日确认；汇率方向始终为一人民币对应的卢布。"""
    _metadata(business_date, idempotency_key, note, agent_source)
    _identity(fund_account_id)
    if not isinstance(category, str) or category not in INCOME_CATEGORIES:
        raise LedgerError('其他收入分类无效', code='invalid_category')
    _text(rate_source, '汇率来源', 500)
    _text(reference, '凭证或原记录参考', 500)
    if type(zero_book_value_confirmed) is not bool:
        raise LedgerError('账面价值确认须为布尔值', code='input_error')
    if category == OtherIncome.Category.USED_ITEM and not zero_book_value_confirmed:
        raise LedgerError('仅支持已费用化且剩余账面价值为零的旧物，请核实原成本记录', code='book_value_confirmation_required')
    if category != OtherIncome.Category.USED_ITEM and zero_book_value_confirmed:
        raise LedgerError('仅旧物出售需要确认账面价值', code='input_error')
    _acquire_sqlite_writer_gate()
    existing = OtherIncome.objects.select_related('ledger_transaction').filter(idempotency_key=idempotency_key).first()
    validate_income_category(category, subcategory, recognition_confirmed,
                             legacy=existing is not None and existing.subcategory == '')
    account = FundAccount.objects.select_for_update().filter(pk=fund_account_id).first()
    if account is None:
        raise LedgerError('收款账户不存在', code='account_not_found')
    if account.currency not in ('CNY', 'RUB'):
        raise LedgerError('其他收入仅支持人民币和卢布账户', code='currency_rule')
    amount = _positive_amount(amount, account.currency, '到账金额')
    if account.currency == 'RUB':
        _text(rate_source, '汇率来源', 500, required=True)
        rate = _strict_external_decimal(exchange_rate, Decimal('0.00000001'), '汇率')
        if not 0 < rate < Decimal('10000000000'):
            raise LedgerError('汇率必须大于零且小于 10000000000', code='invalid_exchange_rate')
    else:
        rate = Decimal('1.00000000') if exchange_rate is None else _strict_external_decimal(exchange_rate, Decimal('0.00000001'), '汇率')
        if rate != 1 or rate_source:
            raise LedgerError('人民币入账汇率须为 1，无需汇率来源', code='currency_rule')
    cny_amount = (amount / rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    # 内部收益科目也使用 CNY 原币字段，遵守统一分录的金额上限。
    if not 0 < cny_amount < MAX_ORIGINAL_ABS:
        raise LedgerError('人民币折算金额须至少为 0.01 且不能超出范围', code='invalid_amount')
    values = dict(
        category=category, subcategory=subcategory, recognition_confirmed=recognition_confirmed,
        fund_account_id=account.pk, currency=account.currency,
        original_amount=amount, amount_cny=cny_amount, exchange_rate=rate,
        rate_source=rate_source, reference=reference, zero_book_value_confirmed=zero_book_value_confirmed,
        business_date=business_date, operator_id=getattr(operator, 'pk', None),
        note=note, agent_source=agent_source,
    )
    if existing is not None:
        if any(getattr(existing, key) != value for key, value in values.items()) or existing.ledger_transaction.idempotency_key != idempotency_key:
            raise LedgerError('操作编号已用于不同的收入内容', code='idempotency_conflict')
        if existing.ledger_transaction.reversed_by_id is not None or OtherIncomeReversal.objects.filter(income=existing).exists():
            raise LedgerError('原收入已冲正，不能重新登记', code='already_reversed')
    else:
        if LedgerTransaction.objects.filter(idempotency_key=idempotency_key).exists():
            raise LedgerError('操作编号已经使用', code='idempotency_conflict')
        require_day1_completed()
        _require_operator(operator)
        if not account.is_active:
            raise LedgerError('收款账户已停用', code='account_inactive')
        _unreconciled(account.pk, business_date)
        if account.currency == 'RUB' and LedgerPosting.objects.filter(
            account=account, transaction__status=LedgerTransaction.Status.POSTED,
            transaction__business_date__gt=business_date,
        ).exists():
            raise LedgerError('卢布账户已有后续流水，不能在之前补录收入；请核对实际日期', code='historical_replay_required')
    ledger = _post_transaction_once(
        transaction_type=LedgerTransaction.TransactionType.OTHER_INCOME,
        business_date=business_date, postings=_postings(account, category, amount, cny_amount),
        operator=operator, idempotency_key=idempotency_key, description=note,
        source_type='other_income', source_id=idempotency_key, _writer_gate=False,
    )
    if existing is not None:
        if ledger.pk != existing.ledger_transaction_id:
            raise LedgerError('收入流水不一致', code='idempotency_conflict')
        return existing, False
    income = OtherIncome(**values, ledger_transaction=ledger, idempotency_key=idempotency_key)
    with ledger_mutation_scope(reason='other_income', model='accounting.OtherIncome', operator=operator):
        income.save(force_insert=True)
    return income, True


@_retry_sqlite_locked
@transaction.atomic
def reverse_other_income(*, income_id, business_date, operator, idempotency_key, note, agent_source=''):
    _metadata(business_date, idempotency_key, note, agent_source)
    _identity(income_id)
    _acquire_sqlite_writer_gate()
    income = OtherIncome.objects.select_for_update().select_related('ledger_transaction', 'fund_account').filter(pk=income_id).first()
    if income is None:
        raise LedgerError('其他收入不存在', code='income_not_found')
    original = income.ledger_transaction
    # 在反向入账前也核对原事实与原分录；不能冲正损坏或不完整的记录。
    verified = _post_transaction_once(
        transaction_type=LedgerTransaction.TransactionType.OTHER_INCOME,
        business_date=income.business_date,
        postings=_postings(income.fund_account, income.category, income.original_amount, income.amount_cny),
        operator=income.operator, idempotency_key=income.idempotency_key,
        description=income.note, source_type='other_income', source_id=income.idempotency_key,
        _writer_gate=False,
    )
    if verified.pk != original.pk:
        raise LedgerError('原收入流水不一致', code='idempotency_conflict')
    existing = OtherIncomeReversal.objects.filter(income=income).first()
    if existing is not None:
        if (existing.idempotency_key != idempotency_key or existing.business_date != business_date
                or existing.operator_id != getattr(operator, 'pk', None)
                or existing.note != note or existing.agent_source != agent_source
                or existing.ledger_transaction_id != original.reversed_by_id):
            raise LedgerError('冲正操作编号或内容不一致', code='idempotency_conflict')
    else:
        if original.reversed_by_id is not None:
            raise LedgerError('原收入已冲正', code='already_reversed')
        if LedgerTransaction.objects.filter(idempotency_key=idempotency_key).exists():
            raise LedgerError('操作编号已经使用', code='idempotency_conflict')
        require_day1_completed()
        _require_operator(operator)
        _unreconciled(income.fund_account_id, income.business_date)
        if LedgerPosting.objects.filter(
            account_id=income.fund_account_id, transaction__status=LedgerTransaction.Status.POSTED,
            transaction__effective_sequence__gt=original.effective_sequence,
        ).exists():
            raise LedgerError('收款账户已有后续资金流水，不能直接冲正收入', code='income_has_later_activity')
    reversal_ledger = _reverse_ledger_transaction(
        original_transaction=original, business_date=business_date, operator=operator,
        idempotency_key=idempotency_key, reason=note, reversible_transaction_types=_REVERSIBLE,
    )
    if existing is not None:
        if existing.ledger_transaction_id != reversal_ledger.pk:
            raise LedgerError('冲正流水不一致', code='idempotency_conflict')
        return existing, False
    reversal = OtherIncomeReversal(
        income=income, business_date=business_date, operator=operator, agent_source=agent_source,
        idempotency_key=idempotency_key, note=note, ledger_transaction=reversal_ledger,
    )
    with ledger_mutation_scope(reason='other_income', model='accounting.OtherIncomeReversal', operator=operator):
        reversal.save(force_insert=True)
    return reversal, True
