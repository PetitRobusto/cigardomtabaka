"""经营费用的受控入账动作。"""

from datetime import date
from decimal import Decimal

from django.db import transaction

from accounting.mutation_scope import ledger_mutation_scope
from accounting.models import (
    Expense, FundAccount, LedgerPosting, LedgerTransaction,
)
from accounting.guards import Day1IncompleteError, require_day1_completed as require_day1
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


_SUBCATEGORY_CATEGORY = {
    Expense.Subcategory.PERSONNEL_SALARY: Expense.Category.SALARY,
    Expense.Subcategory.PERSONNEL_BONUS: Expense.Category.SALARY,
    Expense.Subcategory.PERSONNEL_BENEFITS: Expense.Category.SALARY,
    Expense.Subcategory.PERSONNEL_RECRUITING: Expense.Category.SALARY,
    Expense.Subcategory.RENT: Expense.Category.RENT,
    Expense.Subcategory.PROPERTY: Expense.Category.RENT,
    Expense.Subcategory.VENUE_SERVICE: Expense.Category.RENT,
    Expense.Subcategory.ELECTRICITY: Expense.Category.UTILITIES,
    Expense.Subcategory.WATER: Expense.Category.UTILITIES,
    Expense.Subcategory.GAS_HEATING: Expense.Category.UTILITIES,
    Expense.Subcategory.OTHER_ENERGY: Expense.Category.UTILITIES,
    Expense.Subcategory.TRANSPORT_TAXI: Expense.Category.OTHER,
    Expense.Subcategory.TRANSPORT_PUBLIC: Expense.Category.OTHER,
    Expense.Subcategory.TRANSPORT_TRAVEL: Expense.Category.OTHER,
    Expense.Subcategory.TRANSPORT_DELIVERY: Expense.Category.OTHER,
    Expense.Subcategory.TRANSPORT_PARKING: Expense.Category.OTHER,
    Expense.Subcategory.TRANSPORT_FUEL: Expense.Category.OTHER,
    Expense.Subcategory.OFFICE_SUPPLIES: Expense.Category.OTHER,
    Expense.Subcategory.OFFICE_PRINTING: Expense.Category.OTHER,
    Expense.Subcategory.OFFICE_PHONE: Expense.Category.OTHER,
    Expense.Subcategory.OFFICE_INTERNET: Expense.Category.OTHER,
    Expense.Subcategory.OFFICE_SOFTWARE: Expense.Category.OTHER,
    Expense.Subcategory.OFFICE_POSTAGE: Expense.Category.OTHER,
    Expense.Subcategory.FACILITY_EQUIPMENT: Expense.Category.OTHER,
    Expense.Subcategory.FACILITY_TOOLS: Expense.Category.OTHER,
    Expense.Subcategory.FACILITY_REPAIR: Expense.Category.OTHER,
    Expense.Subcategory.FACILITY_CLEANING: Expense.Category.OTHER,
    Expense.Subcategory.MARKETING_ADVERTISING: Expense.Category.OTHER,
    Expense.Subcategory.MARKETING_PLATFORM: Expense.Category.OTHER,
    Expense.Subcategory.MARKETING_CREATIVE: Expense.Category.OTHER,
    Expense.Subcategory.MARKETING_GIFT: Expense.Category.OTHER,
    Expense.Subcategory.MARKETING_PROMOTION: Expense.Category.OTHER,
    Expense.Subcategory.PROFESSIONAL_ACCOUNTING: Expense.Category.PROFESSIONAL,
    Expense.Subcategory.PROFESSIONAL_LEGAL: Expense.Category.PROFESSIONAL,
    Expense.Subcategory.PROFESSIONAL_CONSULTING: Expense.Category.PROFESSIONAL,
    Expense.Subcategory.PROFESSIONAL_DESIGN: Expense.Category.PROFESSIONAL,
    Expense.Subcategory.PROFESSIONAL_TRANSLATION: Expense.Category.PROFESSIONAL,
    Expense.Subcategory.FINANCIAL_INTEREST: Expense.Category.INTEREST,
    Expense.Subcategory.FINANCIAL_BANK_FEE: Expense.Category.INTEREST,
    Expense.Subcategory.FINANCIAL_PAYMENT_FEE: Expense.Category.INTEREST,
    Expense.Subcategory.FINANCIAL_ACCOUNT_FEE: Expense.Category.INTEREST,
    Expense.Subcategory.TAX: Expense.Category.OTHER,
    Expense.Subcategory.REGISTRATION: Expense.Category.OTHER,
    Expense.Subcategory.LICENSE: Expense.Category.OTHER,
    Expense.Subcategory.NOTARY: Expense.Category.OTHER,
    Expense.Subcategory.OTHER: Expense.Category.OTHER,
}

_CATEGORY_RULES = {
    Expense.Category.SALARY: (
        {FundAccount.Currency.CNY, FundAccount.Currency.RUB}, LedgerPosting.Category.SALARY_EXPENSE,
    ),
    Expense.Category.RENT: (
        {FundAccount.Currency.CNY, FundAccount.Currency.RUB}, LedgerPosting.Category.RENT_EXPENSE,
    ),
    Expense.Category.UTILITIES: (
        {FundAccount.Currency.CNY, FundAccount.Currency.RUB}, LedgerPosting.Category.UTILITIES_EXPENSE,
    ),
    Expense.Category.PROFESSIONAL: (
        {FundAccount.Currency.CNY, FundAccount.Currency.RUB}, LedgerPosting.Category.PROFESSIONAL_EXPENSE,
    ),
    Expense.Category.INTEREST: (
        {FundAccount.Currency.CNY, FundAccount.Currency.RUB}, LedgerPosting.Category.INTEREST_EXPENSE,
    ),
    Expense.Category.OTHER: (
        {FundAccount.Currency.CNY, FundAccount.Currency.RUB}, LedgerPosting.Category.OTHER_EXPENSE,
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


def _replay(*, key, category, subcategory, amount, account_id, business_date, operator_id, note):
    existing = Expense.objects.select_for_update().filter(
        idempotency_key=key,
    ).first()
    if existing is not None:
        if (
            existing.category != category
            or existing.subcategory != subcategory
            or existing.original_amount != amount
            or existing.fund_account_id != account_id
            or existing.business_date != business_date
            or existing.operator_id != operator_id
            or existing.note != (note or '')
        ):
            raise ExpenseActionError('idempotency_conflict')
        _validate_replay_fact(existing, key=key)
        return existing
    if LedgerTransaction.objects.filter(idempotency_key=key).exists():
        raise ExpenseActionError('idempotency_conflict')
    return None


def _validate_replay_fact(expense, *, key):
    """重放只能返回完整的费用事实，不能把半笔流水当作成功。"""
    ledger = LedgerTransaction.objects.filter(
        pk=expense.ledger_transaction_id,
    ).first()
    if ledger is None or ledger.status != LedgerTransaction.Status.POSTED:
        raise ExpenseActionError('idempotency_conflict')
    if (
        expense.status != Expense.Status.POSTED
        or ledger.transaction_type != LedgerTransaction.TransactionType.EXPENSE
        or ledger.idempotency_key != key
        or ledger.source_type != 'expense'
        or ledger.source_id != key
        or ledger.business_date != expense.business_date
        or ledger.operator_id != expense.operator_id
    ):
        raise ExpenseActionError('idempotency_conflict')
    try:
        account_currency = expense.fund_account.currency
        posting_category = _CATEGORY_RULES[expense.category][1]
    except (FundAccount.DoesNotExist, KeyError):
        raise ExpenseActionError('idempotency_conflict')
    expected = sorted([
        (
            expense.fund_account_id, '', account_currency,
            -expense.original_amount, -expense.amount_cny,
        ),
        (
            None, posting_category, FundAccount.Currency.CNY,
            expense.amount_cny, expense.amount_cny,
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
        raise ExpenseActionError('idempotency_conflict')


def _normalise_subcategory(value, category):
    if value in (None, ''):
        return ''
    if not isinstance(value, str) or value not in _SUBCATEGORY_CATEGORY:
        raise ExpenseActionError('invalid_subcategory')
    if _SUBCATEGORY_CATEGORY[value] != category:
        raise ExpenseActionError('category_subcategory_mismatch')
    return value


def require_day1_completed():
    try:
        require_day1()
    except Day1IncompleteError as error:
        raise ExpenseActionError(error.code) from error


@_retry_sqlite_locked
def record_expense(*, category, amount, fund_account_id, business_date,
                   operator, idempotency_key, note='', subcategory=''):
    """记录经营费用；不是换汇，也不挪用销售人肉费路径。"""
    with transaction.atomic():
        _acquire_sqlite_writer_gate()
        try:
            allowed_currencies, posting_category = _CATEGORY_RULES[category]
        except KeyError:
            raise ExpenseActionError('invalid_category')
        key = _normalise_key(idempotency_key)
        subcategory = _normalise_subcategory(subcategory, category)
        account_id = _normalise_account_id(fund_account_id)
        business_date = _normalise_business_date(business_date)
        amount = _normalise_amount(amount)
        replay = _replay(
            key=key,
            category=category,
            subcategory=subcategory,
            amount=amount,
            account_id=account_id,
            business_date=business_date,
            operator_id=getattr(operator, 'pk', None),
            note=note,
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
        if account.currency not in allowed_currencies:
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
            subcategory=subcategory,
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
