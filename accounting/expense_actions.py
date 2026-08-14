"""经营费用的受控入账动作。"""

from datetime import date
from decimal import Decimal

from django.db import transaction

from accounting.mutation_scope import ledger_mutation_scope
from accounting.models import (
    Day1Initialization, Expense, FundAccount, LedgerPosting, LedgerTransaction,
)
from accounting.services import (
    MAX_ORIGINAL_ABS,
    CUTOVER_DATE,
    LedgerError,
    _acquire_sqlite_writer_gate,
    _outflow_cny_cost,
    _post_transaction_once,
    PostingInput,
    _require_operator,
    _retry_sqlite_locked,
    _strict_external_decimal,
)


class ExpenseActionError(Exception):
    """费用动作异常。"""

    def __init__(self, code, details=None):
        super().__init__(code)
        self.code = code
        self.details = details or {}


def _normalise_key(value):
    if not isinstance(value, str) or not value or len(value) > 128:
        raise ExpenseActionError('invalid_idempotency_key')
    return value


def _normalise_account_id(value):
    if isinstance(value, bool):
        raise ExpenseActionError('account_not_found')
    try:
        result = int(value)
    except (TypeError, ValueError, OverflowError):
        raise ExpenseActionError('account_not_found')
    if result <= 0 or str(value).strip() != str(result):
        raise ExpenseActionError('account_not_found')
    return result


def _normalise_business_date(value):
    if type(value) is not date or value < CUTOVER_DATE:
        raise ExpenseActionError('invalid_business_date')
    return value


_CATEGORY_RULES = {
    Expense.Category.SALARY: (
        FundAccount.Currency.CNY, LedgerPosting.Category.SALARY_EXPENSE,
    ),
    Expense.Category.RENT: (
        FundAccount.Currency.RUB, LedgerPosting.Category.RENT_EXPENSE,
    ),
    Expense.Category.UTILITIES: (
        FundAccount.Currency.RUB, LedgerPosting.Category.UTILITIES_EXPENSE,
    ),
    Expense.Category.OTHER: (
        FundAccount.Currency.RUB, LedgerPosting.Category.OTHER_EXPENSE,
    ),
}


def _normalise_amount(value):
    try:
        amount = _strict_external_decimal(value, Decimal('0.01'), 'amount')
    except LedgerError as error:
        code = (
            'invalid_money_precision'
            if '小数位数' in str(error)
            else 'invalid_amount'
        )
        raise ExpenseActionError(code, {'amount': str(error)}) from error
    if abs(amount) >= MAX_ORIGINAL_ABS:
        raise ExpenseActionError('invalid_money_precision')
    if amount <= 0:
        raise ExpenseActionError('invalid_amount')
    return amount


def _replay(*, key, category, amount, account_id, business_date, operator_id):
    existing = Expense.objects.select_for_update().filter(
        idempotency_key=key,
    ).first()
    if existing is not None:
        if (
            existing.category != category
            or existing.original_amount != amount
            or existing.fund_account_id != account_id
            or existing.business_date != business_date
            or existing.operator_id != operator_id
        ):
            raise ExpenseActionError('idempotency_conflict')
        return existing
    if LedgerTransaction.objects.filter(idempotency_key=key).exists():
        raise ExpenseActionError('idempotency_conflict')
    return None


def require_day1_completed():
    if not Day1Initialization.objects.filter(
        singleton_key='company',
        status=Day1Initialization.Status.COMPLETED,
    ).exists():
        raise ExpenseActionError('day1_incomplete')


@_retry_sqlite_locked
def record_expense(*, category, amount, fund_account_id, business_date,
                   operator, idempotency_key, note=''):
    """记录工资或 RUB 经营费用；不是换汇，也不挪用销售人肉费路径。"""
    with transaction.atomic():
        _acquire_sqlite_writer_gate()
        try:
            currency, posting_category = _CATEGORY_RULES[category]
        except KeyError:
            raise ExpenseActionError('invalid_category')
        key = _normalise_key(idempotency_key)
        account_id = _normalise_account_id(fund_account_id)
        business_date = _normalise_business_date(business_date)
        amount = _normalise_amount(amount)
        replay = _replay(
            key=key,
            category=category,
            amount=amount,
            account_id=account_id,
            business_date=business_date,
            operator_id=getattr(operator, 'pk', None),
        )
        if replay is not None:
            return replay
        require_day1_completed()
        try:
            persisted_operator = _require_operator(operator)
        except LedgerError as error:
            raise ExpenseActionError('invalid_operator') from error
        if not persisted_operator.is_active:
            raise ExpenseActionError('invalid_operator')
        account = FundAccount.objects.select_for_update().filter(pk=account_id).first()
        if account is None:
            raise ExpenseActionError('account_not_found')
        if account.currency != currency:
            raise ExpenseActionError('currency_rule')
        if not account.is_active:
            raise ExpenseActionError('account_inactive')
        if account.currency != FundAccount.Currency.CNY and LedgerPosting.objects.filter(
            account_id=account.pk,
            transaction__status=LedgerTransaction.Status.POSTED,
            transaction__business_date__gt=business_date,
        ).exists():
            raise ExpenseActionError('historical_replay_required')
        try:
            cny_cost = _outflow_cny_cost(account, amount)
        except LedgerError as error:
            if '余额不足' in str(error):
                raise ExpenseActionError('insufficient_balance') from error
            raise ExpenseActionError('ledger_error', {'message': str(error)}) from error
        ledger = _post_transaction_once(
            transaction_type=LedgerTransaction.TransactionType.EXPENSE,
            business_date=business_date,
            postings=[
                PostingInput(
                    account=account, currency=account.currency,
                    amount=-amount, cny_amount=-cny_cost,
                ),
                PostingInput(
                    category=posting_category,
                    currency=FundAccount.Currency.CNY,
                    amount=cny_cost, cny_amount=cny_cost,
                ),
            ],
            operator=persisted_operator,
            idempotency_key=key,
            description=note or '',
            source_type='expense',
            source_id=key,
            _writer_gate=False,
        )
        expense = Expense(
            category=category,
            fund_account=account,
            original_amount=amount,
            amount_cny=cny_cost,
            business_date=business_date,
            operator=persisted_operator,
            ledger_transaction=ledger,
            idempotency_key=key,
            note=note or '',
        )
        with ledger_mutation_scope(
            reason='expense_post', model='accounting.Expense',
            operator=persisted_operator,
            allowed_fields={field.name for field in expense._meta.concrete_fields},
        ):
            expense.save(force_insert=True)
        return expense
