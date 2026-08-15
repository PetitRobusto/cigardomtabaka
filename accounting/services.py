from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from functools import wraps
import random
import time

from django.contrib.auth import get_user_model
from django.db import IntegrityError, OperationalError, connection, models, transaction
from django.db.models import Sum
from django.utils import timezone

from accounting.models import (
    AccountReconciliation, FundAccount, LedgerPosting, LedgerSequence,
    LedgerTransaction,
)
from accounting.guards import require_day1_completed
from accounting.selectors import account_snapshot


CUTOVER_DATE = date(2026, 8, 10)
CNY_PLACES = Decimal('0.01')
MAX_ORIGINAL_ABS = Decimal('1000000000000')
MAX_CNY_ABS = Decimal('1000000000000000000')
ORIGINAL_PLACES = {
    FundAccount.Currency.CNY: Decimal('0.01'),
    FundAccount.Currency.RUB: Decimal('0.01'),
    FundAccount.Currency.USDT: Decimal('0.00000001'),
}


class LedgerError(Exception):
    """可携带稳定 API code/details 的账务领域错误。"""

    def __init__(self, message, *, code=None, details=None):
        super().__init__(message)
        self.code = code
        self.details = details or {}


@dataclass(frozen=True)
class PostingInput:
    currency: str
    amount: Decimal
    cny_amount: Decimal
    account: FundAccount | None = None
    category: str = ''


@dataclass(frozen=True)
class _PreparedPosting:
    account_id: int | None
    category: str
    currency: str
    amount: Decimal
    cny_amount: Decimal


@dataclass(frozen=True)
class _OperationResult:
    transaction: LedgerTransaction
    created: bool


@dataclass(frozen=True)
class _ReconciliationOperationResult:
    reconciliation: AccountReconciliation
    created: bool


class ReconciliationConflictError(LedgerError):
    pass


def _decimal(value, places, field_name):
    try:
        decimal_value = Decimal(str(value)).quantize(places, rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError):
        raise LedgerError(f'{field_name}必须是有效金额')
    if not decimal_value.is_finite():
        raise LedgerError(f'{field_name}必须是有效金额')
    return decimal_value


def _strict_external_decimal(value, places, field_name):
    try:
        original_value = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise LedgerError(f'{field_name}必须是有效金额')
    if not original_value.is_finite():
        raise LedgerError(f'{field_name}必须是有效金额')
    amount = _decimal(original_value, places, field_name)
    if original_value != amount:
        raise LedgerError(f'{field_name}小数位数超出允许精度')
    return amount


def _reconciliation_key(value, field_name):
    if not isinstance(value, str) or not value or len(value) > 128:
        raise LedgerError(f'{field_name}无效')
    return value


def _reconciliation_result(record, created, return_result):
    if return_result:
        return _ReconciliationOperationResult(reconciliation=record, created=created)
    return record


def _require_operator(operator):
    user_model = get_user_model()
    if not isinstance(operator, user_model) or not operator.pk:
        raise LedgerError('必须提供真实操作人 operator')
    try:
        persisted = user_model.objects.get(pk=operator.pk)
    except user_model.DoesNotExist:
        raise LedgerError('必须提供真实操作人 operator')
    if not persisted.is_operator:
        raise LedgerError('必须提供操作员 operator')
    return persisted

def _operator_for_replay(operator):
    """重放只确认操作员身份存在，不重新检查当前操作权限。"""
    user_model = get_user_model()
    if not isinstance(operator, user_model) or not operator.pk:
        raise LedgerError('必须提供真实操作人 operator')
    try:
        return user_model.objects.get(pk=operator.pk)
    except user_model.DoesNotExist:
        raise LedgerError('必须提供真实操作人 operator')



def _validate_metadata(transaction_type, business_date, idempotency_key):
    if transaction_type not in LedgerTransaction.TransactionType.values:
        raise LedgerError('交易类型无效')
    if type(business_date) is not date:
        raise LedgerError('业务日期必须是 date')
    if business_date < CUTOVER_DATE:
        raise LedgerError('业务日期不能早于账务切换日')
    if not isinstance(idempotency_key, str) or not idempotency_key:
        raise LedgerError('幂等键不能为空')


def _require_active_accounts(account_map):
    if any(not account.is_active for account in account_map.values()):
        raise LedgerError('账户已停用')


def _resolve_accounts(postings):
    account_ids = set()
    for posting in postings:
        if posting.account is None:
            continue
        if (
            not isinstance(posting.account, FundAccount)
            or not posting.account.pk
            or posting.account._state.adding
        ):
            raise LedgerError('账户必须是已保存的资金账户')
        account_ids.add(posting.account.pk)

    accounts = FundAccount.objects.select_for_update().filter(pk__in=account_ids).order_by('pk')
    account_map = {account.pk: account for account in accounts}
    if len(account_map) != len(account_ids):
        raise LedgerError('账户不存在')
    _require_active_accounts(account_map)
    return account_map


def _prepare_postings(postings, account_map):
    if len(postings) < 2:
        raise LedgerError('一笔交易至少需要两条分录')

    prepared = []
    cny_total = Decimal('0.00')
    categories = LedgerPosting.Category.values
    currencies = FundAccount.Currency.values
    for raw in postings:
        if not isinstance(raw, PostingInput):
            raise LedgerError('分录必须是 PostingInput')
        if raw.currency not in currencies:
            raise LedgerError('原币无效')
        if raw.currency not in ORIGINAL_PLACES:
            raise LedgerError('原币无效')
        amount = _decimal(raw.amount, ORIGINAL_PLACES[raw.currency], '原币金额')
        cny_amount = _decimal(raw.cny_amount, CNY_PLACES, '人民币账面金额')
        if abs(amount) >= MAX_ORIGINAL_ABS:
            raise LedgerError('原币金额超出范围')
        if abs(cny_amount) >= MAX_CNY_ABS:
            raise LedgerError('人民币账面金额超出范围')
        if raw.account is not None:
            if raw.category:
                raise LedgerError('分录只能选择账户或内部分类之一')
            account = account_map[raw.account.pk]
            if raw.currency != account.currency:
                raise LedgerError('账户与分录原币不一致')
            if raw.currency == FundAccount.Currency.CNY and amount != cny_amount:
                raise LedgerError('人民币账户原币金额必须等于账面金额')
            prepared.append(_PreparedPosting(account.pk, '', raw.currency, amount, cny_amount))
        else:
            if raw.category not in categories:
                raise LedgerError('内部分类无效')
            if raw.currency != FundAccount.Currency.CNY:
                raise LedgerError('内部分类分录必须为人民币')
            if amount != cny_amount:
                raise LedgerError('内部分类原币金额必须等于账面金额')
            prepared.append(_PreparedPosting(None, raw.category, raw.currency, amount, cny_amount))
        cny_total += cny_amount

    if cny_total != Decimal('0.00'):
        raise LedgerError('交易人民币账面金额必须平衡')
    return prepared


def _validate_historical_balances(account_map, prepared, business_date, effective_sequence):
    totals_by_account = {}
    for posting in prepared:
        if posting.account_id is None:
            continue
        amount, cny_amount = totals_by_account.get(posting.account_id, (Decimal('0'), Decimal('0')))
        totals_by_account[posting.account_id] = (amount + posting.amount, cny_amount + posting.cny_amount)

    for account_id, (candidate_amount, candidate_cny) in totals_by_account.items():
        account = account_map[account_id]
        existing = LedgerPosting.objects.filter(
            account_id=account_id,
            transaction__status=LedgerTransaction.Status.POSTED,
        )
        if account.currency != FundAccount.Currency.CNY and existing.filter(
            transaction__business_date__gt=business_date,
        ).exists():
            raise LedgerError('非人民币账户不能在已有后续流水前回填')

        history = existing.values(
            'transaction__business_date', 'transaction__effective_sequence',
        ).annotate(amount=Sum('amount'), cny_amount=Sum('cny_amount')).order_by(
            'transaction__business_date', 'transaction__effective_sequence',
        )
        replay = []
        for row in history:
            if row['transaction__effective_sequence'] is None:
                raise LedgerError('已入账流水缺少有效顺序')
            replay.append(
                (row['transaction__business_date'], row['transaction__effective_sequence'], row['amount'], row['cny_amount'])
            )
        replay.append((business_date, effective_sequence, candidate_amount, candidate_cny))
        replay.sort(key=lambda row: (row[0], row[1]))

        original_balance = Decimal('0')
        cny_book_cost = Decimal('0')
        for _, _, amount, cny_amount in replay:
            original_balance += amount
            cny_book_cost += cny_amount
            if original_balance < 0 or cny_book_cost < 0:
                raise LedgerError('账户历史余额或人民币账面成本不能为负')


def _existing_transaction(idempotency_key, transaction_type):
    existing = LedgerTransaction.objects.filter(idempotency_key=idempotency_key).first()
    if existing is None:
        return None
    if existing.transaction_type != transaction_type:
        raise LedgerError('幂等键已用于另一种交易类型')
    return existing


def _operation_result(ledger_transaction, created, return_result):
    if return_result:
        return _OperationResult(transaction=ledger_transaction, created=created)
    return ledger_transaction


def _sqlite_retry_delay(attempt, base_delay):
    """Decorrelate SQLite writers that start from the same retry boundary."""
    return base_delay * (attempt + 1) + random.uniform(0, base_delay / 2)


def _acquire_sqlite_writer_gate():
    """Acquire the ledger writer gate without consuming a ledger sequence.

    SQLite has no useful row-level lock for ``select_for_update``.  A controlled
    equal-value write upgrades the current outer transaction to a writer before
    account/history reads, so concurrent operations retry as whole transactions.
    ``LedgerSequence`` ordinary writes are intentionally guarded; this is the
    trusted low-level persistence boundary.
    """
    sequence, created = LedgerSequence.objects.select_for_update().get_or_create(name='global')
    if connection.vendor == 'sqlite' and not created:
        # Trusted low-level persistence boundary: equal write acquires SQLite writer lock.
        models.Model.save(sequence, update_fields=['next_value'])
    return sequence


def _validate_opening_balance_postings(business_date, prepared):
    if business_date != CUTOVER_DATE:
        raise LedgerError('期初余额只能记录在账务切换日')
    account_postings = [posting for posting in prepared if posting.account_id is not None]
    category_postings = [posting for posting in prepared if posting.account_id is None]
    if len(prepared) != 2 or len(account_postings) != 1 or len(category_postings) != 1:
        raise LedgerError('期初余额必须恰好包含一条账户分录和一条内部分类分录')
    if category_postings[0].category not in (
        LedgerPosting.Category.OPENING_CAPITAL,
        LedgerPosting.Category.OPENING_RETAINED_EARNINGS,
    ):
        raise LedgerError('期初余额内部分类无效')
    account_posting = account_postings[0]
    category_posting = category_postings[0]
    if account_posting.amount <= 0 or account_posting.cny_amount < 0:
        raise LedgerError('期初余额账户金额必须为正且账面成本不能为负')
    if category_posting.amount != -account_posting.cny_amount or category_posting.cny_amount != -account_posting.cny_amount:
        raise LedgerError('期初余额内部分类金额必须抵销账户账面成本')
    if LedgerPosting.objects.filter(account_id=account_posting.account_id).exists():
        raise LedgerError('已有分录的账户不能记录期初余额')


@transaction.atomic
def _post_transaction_once(*, transaction_type, business_date, postings, operator,
                           idempotency_key, description='', source_type='', source_id='', return_result=False,
                           _writer_gate=True):
    if _writer_gate:
        _acquire_sqlite_writer_gate()
    _validate_metadata(transaction_type, business_date, idempotency_key)
    persisted_operator = _require_operator(operator)
    existing = _existing_transaction(idempotency_key, transaction_type)
    if existing is not None:
        return _operation_result(existing, False, return_result)

    try:
        raw_postings = tuple(postings)
    except TypeError:
        raise LedgerError('postings必须是可迭代分录')
    account_map = _resolve_accounts(raw_postings)
    prepared = _prepare_postings(raw_postings, account_map)
    if transaction_type == LedgerTransaction.TransactionType.OPENING_BALANCE:
        _validate_opening_balance_postings(business_date, prepared)

    sequence, _ = LedgerSequence.objects.select_for_update().get_or_create(name='global')
    if (
        transaction_type == LedgerTransaction.TransactionType.OPENING_BALANCE
        and LedgerTransaction.objects.filter(status=LedgerTransaction.Status.POSTED).exclude(
            transaction_type=LedgerTransaction.TransactionType.OPENING_BALANCE,
        ).exists()
    ):
        raise LedgerError('日常业务开始后不能记录期初余额')
    effective_sequence = sequence.next_value
    _validate_historical_balances(account_map, prepared, business_date, effective_sequence)

    try:
        with transaction.atomic():
            sequence.next_value += 1
            # Trusted low-level persistence boundary: ordinary ORM writes are guarded by LedgerSequence.
            models.Model.save(sequence, update_fields=['next_value'])
            ledger_transaction = LedgerTransaction.objects.create(
                transaction_type=transaction_type,
                status=LedgerTransaction.Status.DRAFT,
                business_date=business_date,
                idempotency_key=idempotency_key,
                description=description or '',
                source_type=source_type or '',
                source_id=source_id or '',
                operator=persisted_operator,
            )
            for posting in prepared:
                LedgerPosting.objects.create(
                    transaction=ledger_transaction,
                    account_id=posting.account_id,
                    category=posting.category,
                    currency=posting.currency,
                    amount=posting.amount,
                    cny_amount=posting.cny_amount,
                )
            ledger_transaction.effective_sequence = effective_sequence
            ledger_transaction.status = LedgerTransaction.Status.POSTED
            ledger_transaction.posted_at = timezone.now()
            # Trusted low-level persistence boundary: ordinary ORM writes are guarded by LedgerTransaction.
            models.Model.save(
                ledger_transaction, update_fields=['effective_sequence', 'status', 'posted_at'],
            )
    except IntegrityError:
        existing = _existing_transaction(idempotency_key, transaction_type)
        if existing is not None:
            return _operation_result(existing, False, return_result)
        raise LedgerError('创建账务交易失败')
    return _operation_result(ledger_transaction, True, return_result)



def post_transaction(*, transaction_type, business_date, postings, operator,
                     idempotency_key, description='', source_type='', source_id=''):
    if transaction_type == LedgerTransaction.TransactionType.DAY1_OPENING:
        raise LedgerError('Day 1 期初资产只能通过一次性初始化服务入账')
    try:
        postings = tuple(postings)
    except TypeError:
        raise LedgerError('postings必须是可迭代分录')
    for attempt in range(8):
        try:
            return _post_transaction_once(
                transaction_type=transaction_type,
                business_date=business_date,
                postings=postings,
                operator=operator,
                idempotency_key=idempotency_key,
                description=description,
                source_type=source_type,
                source_id=source_id,
            )
        except OperationalError as error:
            locked_sqlite = connection.vendor == 'sqlite' and 'locked' in str(error).lower()
            if not locked_sqlite or attempt == 7:
                raise
            time.sleep(_sqlite_retry_delay(attempt, 0.02))

def _retry_sqlite_locked(operation):

    @wraps(operation)
    def retrying_operation(*args, **kwargs):
        for attempt in range(5):
            try:
                return operation(*args, **kwargs)
            except OperationalError as error:
                locked_sqlite = connection.vendor == 'sqlite' and 'locked' in str(error).lower()
                if not locked_sqlite or attempt == 4:
                    raise
                time.sleep(_sqlite_retry_delay(attempt, 0.1))
    return retrying_operation


def _post_day1_opening(*, business_date, postings, operator, idempotency_key,
                       source_id, description='公司 Day 1 期初资产初始化'):
    """Use the single ledger writer after enforcing the one-time opening shape."""
    if not isinstance(source_id, str) or not source_id.isdigit():
        raise LedgerError('Day 1 初始化来源无效')
    try:
        postings = tuple(postings)
    except TypeError:
        raise LedgerError('Day 1 分录必须是可迭代对象')

    account_assets = []
    inventory_assets = []
    capital = []
    for posting in postings:
        if not isinstance(posting, PostingInput):
            raise LedgerError('Day 1 分录必须是 PostingInput')
        if posting.account is not None:
            if posting.category or posting.amount <= 0 or posting.cny_amount < 0:
                raise LedgerError('Day 1 账户资产分录无效')
            account_assets.append(posting)
        elif posting.category == LedgerPosting.Category.INVENTORY:
            if posting.amount <= 0 or posting.cny_amount <= 0:
                raise LedgerError('Day 1 库存资产分录必须为正')
            inventory_assets.append(posting)
        elif posting.category == LedgerPosting.Category.OPENING_CAPITAL:
            if posting.amount >= 0 or posting.cny_amount >= 0:
                raise LedgerError('Day 1 期初资本分录必须为负')
            capital.append(posting)
        else:
            raise LedgerError('Day 1 期初分录包含不允许的内部分类')

    if not account_assets and not inventory_assets:
        raise LedgerError('Day 1 期初资产必须大于零')
    if len(inventory_assets) > 1 or len(capital) != 1:
        raise LedgerError('Day 1 必须包含至多一条库存资产和恰好一条期初资本分录')
    asset_total = sum(
        (posting.cny_amount for posting in (*account_assets, *inventory_assets)),
        Decimal('0.00'),
    ).quantize(CNY_PLACES)
    capital_amount = capital[0].cny_amount.quantize(CNY_PLACES)
    if asset_total <= 0 or capital_amount != -asset_total:
        raise LedgerError('Day 1 期初资本必须精确抵销全部资产')

    return _post_transaction_once(
        transaction_type=LedgerTransaction.TransactionType.DAY1_OPENING,
        business_date=business_date,
        postings=postings,
        operator=operator,
        idempotency_key=idempotency_key,
        description=description,
        source_type='day1_initialization',
        source_id=source_id,
        _writer_gate=False,
    )

def _positive_amount(value, currency, field_name):

    if currency not in ORIGINAL_PLACES:
        raise LedgerError('原币无效')
    amount = _strict_external_decimal(value, ORIGINAL_PLACES[currency], field_name)
    if abs(amount) >= MAX_ORIGINAL_ABS:
        raise LedgerError(f'{field_name}超出范围')
    if amount <= 0:
        raise LedgerError(f'{field_name}必须大于零')
    return amount


def _nonnegative_cny_amount(value, field_name):
    amount = _strict_external_decimal(value, CNY_PLACES, field_name)
    if abs(amount) >= MAX_CNY_ABS:
        raise LedgerError(f'{field_name}超出范围')
    if amount < 0:
        raise LedgerError(f'{field_name}不能为负')
    return amount


def _existing_operation(transaction_type, business_date, operator, idempotency_key):
    _validate_metadata(transaction_type, business_date, idempotency_key)
    existing = _existing_transaction(idempotency_key, transaction_type)
    if existing is not None:
        return _operator_for_replay(operator), existing
    return _require_operator(operator), None


def _money_operation_replay(
    existing, *, source_account, target_account, source_amount, target_amount,
    business_date, operator, description, transaction_type,
):
    """同一资金动作幂等键只能重放完全一致的原始请求。"""
    for account in (source_account, target_account):
        if not isinstance(account, FundAccount) or not account.pk or account._state.adding:
            raise LedgerError('账户必须是已保存的资金账户')
    source_amount = _positive_amount(source_amount, source_account.currency, '转出原币金额')
    target_amount = _positive_amount(target_amount, target_account.currency, '转入原币金额')
    rows = tuple(existing.postings.order_by('id').values_list(
        'account_id', 'category', 'currency', 'amount', 'cny_amount',
    ))
    expected_rows = (
        (source_account.pk, '', source_account.currency, -source_amount),
        (target_account.pk, '', target_account.currency, target_amount),
    )
    if (
        existing.transaction_type != transaction_type
        or existing.status != LedgerTransaction.Status.POSTED
        or existing.source_type != ''
        or existing.source_id != ''
        or existing.business_date != business_date
        or existing.operator_id != operator.pk
        or existing.description != (description or '')
        or len(rows) != 2
        or tuple(row[:4] for row in rows) != expected_rows
        or rows[0][4] >= 0
        or rows[1][4] <= 0
        or rows[0][4] + rows[1][4] != 0
        or (source_account.currency == FundAccount.Currency.CNY and rows[0][4] != -source_amount)
        or (target_account.currency == FundAccount.Currency.CNY and rows[1][4] != target_amount)
    ):
        raise LedgerError('幂等键已用于不同的资金动作参数', code='idempotency_conflict')


def _lock_accounts(*accounts):
    account_ids = set()
    for account in accounts:
        if (
            not isinstance(account, FundAccount)
            or not account.pk
            or account._state.adding
        ):
            raise LedgerError('账户必须是已保存的资金账户')
        account_ids.add(account.pk)

    locked = FundAccount.objects.select_for_update().filter(pk__in=account_ids).order_by('pk')
    account_map = {account.pk: account for account in locked}
    if len(account_map) != len(account_ids):
        raise LedgerError('账户不存在')
    _require_active_accounts(account_map)
    return account_map

def _outflow_cny_cost(account, amount):
    snapshot = account_snapshot(account)
    if amount > snapshot.original_balance:
        raise LedgerError('账户原币余额不足')
    if account.currency == FundAccount.Currency.CNY:
        return amount
    if amount == snapshot.original_balance:
        return snapshot.cny_book_cost
    return (snapshot.cny_book_cost / snapshot.original_balance * amount).quantize(
        CNY_PLACES, rounding=ROUND_HALF_UP,
    )


@_retry_sqlite_locked
@transaction.atomic
def record_opening_balance(account, original_amount, cny_book_cost, equity_category,
                           business_date, operator, idempotency_key):
    return _record_opening_balance(
        account, original_amount, cny_book_cost, equity_category,
        business_date, operator, idempotency_key,
    )


def _record_opening_balance(account, original_amount, cny_book_cost, equity_category,
                            business_date, operator, idempotency_key, return_result=False):
    _acquire_sqlite_writer_gate()
    _validate_metadata(LedgerTransaction.TransactionType.OPENING_BALANCE, business_date, idempotency_key)
    persisted_operator = _require_operator(operator)
    if business_date != CUTOVER_DATE:
        raise LedgerError('期初余额只能记录在账务切换日')
    existing = _existing_transaction(
        idempotency_key,
        LedgerTransaction.TransactionType.OPENING_BALANCE,
    )
    if existing is not None:
        return _operation_result(existing, False, return_result)
    if equity_category not in (
        LedgerPosting.Category.OPENING_CAPITAL,
        LedgerPosting.Category.OPENING_RETAINED_EARNINGS,
    ):
        raise LedgerError('期初余额内部分类无效')

    account_map = _lock_accounts(account)
    locked_account = account_map[account.pk]
    original_amount = _positive_amount(original_amount, locked_account.currency, '期初原币金额')
    cny_book_cost = _nonnegative_cny_amount(cny_book_cost, '期初人民币账面成本')
    if locked_account.currency == FundAccount.Currency.CNY and cny_book_cost != original_amount:
        raise LedgerError('人民币期初原币金额必须等于账面成本')
    if LedgerPosting.objects.filter(account=locked_account).exists():
        raise LedgerError('已有分录的账户不能记录期初余额')

    return _post_transaction_once(
        transaction_type=LedgerTransaction.TransactionType.OPENING_BALANCE,
        business_date=business_date,
        postings=[
            PostingInput(account=locked_account, currency=locked_account.currency,
                         amount=original_amount, cny_amount=cny_book_cost),
            PostingInput(category=equity_category, currency=FundAccount.Currency.CNY,
                         amount=-cny_book_cost, cny_amount=-cny_book_cost),
        ],
        operator=persisted_operator,
        idempotency_key=idempotency_key,
        return_result=return_result,
        _writer_gate=False,
    )


@_retry_sqlite_locked
@transaction.atomic
def _record_opening_balance_with_result(account, original_amount, cny_book_cost, equity_category,
                                        business_date, operator, idempotency_key):
    return _record_opening_balance(
        account, original_amount, cny_book_cost, equity_category,
        business_date, operator, idempotency_key, return_result=True,
    )


@_retry_sqlite_locked
@transaction.atomic
def exchange_to_rub(source_account, rub_account, source_amount, rub_amount,
                    business_date, operator, idempotency_key, description=''):
    return _exchange_to_rub(
        source_account, rub_account, source_amount, rub_amount,
        business_date, operator, idempotency_key, description,
    )


def _exchange_to_rub(source_account, rub_account, source_amount, rub_amount,
                     business_date, operator, idempotency_key, description='', return_result=False):
    _acquire_sqlite_writer_gate()
    persisted_operator, existing = _existing_operation(
        LedgerTransaction.TransactionType.EXCHANGE, business_date, operator, idempotency_key,
    )
    if existing is not None:
        _money_operation_replay(
            existing,
            source_account=source_account,
            target_account=rub_account,
            source_amount=source_amount,
            target_amount=rub_amount,
            business_date=business_date,
            transaction_type=LedgerTransaction.TransactionType.EXCHANGE,
            operator=persisted_operator,
            description=description,
        )
        return _operation_result(existing, False, return_result)
    require_day1_completed()

    account_map = _lock_accounts(source_account, rub_account)
    source_account = account_map[source_account.pk]
    rub_account = account_map[rub_account.pk]
    if source_account.pk == rub_account.pk:
        raise LedgerError('转出和转入账户不能相同')
    if source_account.currency == FundAccount.Currency.RUB:
        raise LedgerError('换汇转出账户不能为卢布')
    if rub_account.currency != FundAccount.Currency.RUB:
        raise LedgerError('换汇转入账户必须为卢布')

    source_amount = _positive_amount(source_amount, source_account.currency, '换汇转出原币金额')
    rub_amount = _positive_amount(rub_amount, FundAccount.Currency.RUB, '换汇转入卢布金额')
    cny_cost = _outflow_cny_cost(source_account, source_amount)

    return _post_transaction_once(
        transaction_type=LedgerTransaction.TransactionType.EXCHANGE,
        business_date=business_date,
        postings=[
            PostingInput(account=source_account, currency=source_account.currency,
                         amount=-source_amount, cny_amount=-cny_cost),
            PostingInput(account=rub_account, currency=FundAccount.Currency.RUB,
                         amount=rub_amount, cny_amount=cny_cost),
        ],
        operator=persisted_operator,
        idempotency_key=idempotency_key,
        description=description,
        return_result=return_result,
        _writer_gate=False,
    )


@_retry_sqlite_locked
@transaction.atomic
def _exchange_to_rub_with_result(source_account, rub_account, source_amount, rub_amount,
                                 business_date, operator, idempotency_key, description=''):
    return _exchange_to_rub(
        source_account, rub_account, source_amount, rub_amount,
        business_date, operator, idempotency_key, description, return_result=True,
    )


@_retry_sqlite_locked
@transaction.atomic
def transfer_same_currency(source_account, target_account, amount, business_date,
                           operator, idempotency_key, description=''):
    return _transfer_same_currency(
        source_account, target_account, amount, business_date,
        operator, idempotency_key, description,
    )


def _transfer_same_currency(source_account, target_account, amount, business_date,
                            operator, idempotency_key, description='', return_result=False):
    _acquire_sqlite_writer_gate()
    persisted_operator, existing = _existing_operation(
        LedgerTransaction.TransactionType.TRANSFER, business_date, operator, idempotency_key,
    )
    if existing is not None:
        _money_operation_replay(
            existing,
            source_account=source_account,
            target_account=target_account,
            source_amount=amount,
            target_amount=amount,
            business_date=business_date,
            transaction_type=LedgerTransaction.TransactionType.TRANSFER,
            operator=persisted_operator,
            description=description,
        )
        return _operation_result(existing, False, return_result)
    require_day1_completed()

    account_map = _lock_accounts(source_account, target_account)
    source_account = account_map[source_account.pk]
    target_account = account_map[target_account.pk]
    if source_account.pk == target_account.pk:
        raise LedgerError('转出和转入账户不能相同')
    if source_account.currency != target_account.currency:
        raise LedgerError('同币种转账账户币种必须一致')

    amount = _positive_amount(amount, source_account.currency, '转账原币金额')
    cny_cost = _outflow_cny_cost(source_account, amount)

    return _post_transaction_once(
        transaction_type=LedgerTransaction.TransactionType.TRANSFER,
        business_date=business_date,
        postings=[
            PostingInput(account=source_account, currency=source_account.currency,
                         amount=-amount, cny_amount=-cny_cost),
            PostingInput(account=target_account, currency=target_account.currency,
                         amount=amount, cny_amount=cny_cost),
        ],
        operator=persisted_operator,
        idempotency_key=idempotency_key,
        description=description,
        return_result=return_result,
        _writer_gate=False,
    )


@_retry_sqlite_locked
@transaction.atomic
def _transfer_same_currency_with_result(source_account, target_account, amount, business_date,
                                        operator, idempotency_key, description=''):
    return _transfer_same_currency(
        source_account, target_account, amount, business_date,
        operator, idempotency_key, description, return_result=True,
    )


@_retry_sqlite_locked
@transaction.atomic
def create_reconciliation(*, account, business_date, actual_amount, operator,
                          idempotency_key, note='', return_result=False):
    """记录账户实盘余额快照，不修改或生成账务流水。"""
    _acquire_sqlite_writer_gate()
    persisted_operator = _require_operator(operator)
    if type(business_date) is not date:
        raise LedgerError('业务日期必须是 date')
    if business_date < CUTOVER_DATE:
        raise LedgerError('业务日期不能早于账务切换日')
    key = _reconciliation_key(idempotency_key, '创建幂等键')
    if not isinstance(account, FundAccount) or not account.pk:
        raise LedgerError('对账账户必须是已保存的资金账户')
    locked_account = FundAccount.objects.select_for_update().filter(pk=account.pk).first()
    if locked_account is None:
        raise LedgerError('对账账户不存在')
    if not locked_account.is_active:
        raise LedgerError('账户已停用')
    actual = _strict_external_decimal(
        actual_amount, ORIGINAL_PLACES[locked_account.currency], '实际余额',
    )
    if abs(actual) >= MAX_ORIGINAL_ABS:
        raise LedgerError('实际余额超出范围')
    if actual < 0:
        raise LedgerError('实际余额不能为负')
    existing_key = AccountReconciliation.objects.select_for_update().filter(
        creation_idempotency_key=key,
    ).first()
    if existing_key is not None:
        if (
            existing_key.account_id != locked_account.pk
            or existing_key.business_date != business_date
            or existing_key.actual_amount != actual
            or existing_key.operator_id != persisted_operator.pk
            or existing_key.note != (note or '')
        ):
            raise ReconciliationConflictError('创建对账幂等键参数不匹配')
        return _reconciliation_result(existing_key, False, return_result)
    if AccountReconciliation.objects.select_for_update().filter(
        account=locked_account, business_date=business_date,
    ).exists():
        raise ReconciliationConflictError('该账户在此业务日已经对账')
    system = account_snapshot(
        locked_account, as_of_business_date=business_date,
    ).original_balance
    places = ORIGINAL_PLACES[locked_account.currency]
    difference = (actual - system).quantize(places)
    record = AccountReconciliation(
            account=locked_account,
            business_date=business_date,
            system_amount=system,
            actual_amount=actual,
            difference=difference,
            operator=persisted_operator,
            note=note or '',
            creation_idempotency_key=key,
        )
    try:
        with transaction.atomic():
            # Trusted persistence boundary; ordinary ORM creation is guarded.
            models.Model.save(record, force_insert=True)
    except IntegrityError as error:
        existing_key = AccountReconciliation.objects.filter(
            creation_idempotency_key=key,
        ).first()
        if existing_key is not None:
            if (
                existing_key.account_id == locked_account.pk
                and existing_key.business_date == business_date
                and existing_key.actual_amount == actual
                and existing_key.operator_id == persisted_operator.pk
                and existing_key.note == (note or '')
            ):
                return _reconciliation_result(existing_key, False, return_result)
            raise ReconciliationConflictError('创建对账幂等键参数不匹配') from error
        raise ReconciliationConflictError('该账户在此业务日已经对账') from error
    return _reconciliation_result(record, True, return_result)


@_retry_sqlite_locked
@transaction.atomic
def confirm_reconciliation(*, reconciliation_id, operator, idempotency_key,
                           return_result=False):
    """确认对账快照；确认不会调整或覆盖任何账务流水。"""
    _acquire_sqlite_writer_gate()
    persisted_operator = _require_operator(operator)
    key = _reconciliation_key(idempotency_key, '确认幂等键')
    try:
        reconciliation = AccountReconciliation.objects.select_for_update().get(
            pk=int(reconciliation_id),
        )
    except (AccountReconciliation.DoesNotExist, TypeError, ValueError):
        raise LedgerError('对账记录不存在')
    if reconciliation.status == AccountReconciliation.Status.CONFIRMED:
        if (
            reconciliation.confirmation_idempotency_key == key
            and reconciliation.confirmer_id == persisted_operator.pk
        ):
            return _reconciliation_result(reconciliation, False, return_result)
        raise ReconciliationConflictError('对账记录已经确认')
    if reconciliation.status != AccountReconciliation.Status.PENDING:
        raise LedgerError('对账记录状态无效')
    if AccountReconciliation.objects.filter(
        confirmation_idempotency_key=key,
    ).exclude(pk=reconciliation.pk).exists():
        raise ReconciliationConflictError('确认幂等键已用于其他对账记录')
    reconciliation.status = AccountReconciliation.Status.CONFIRMED
    reconciliation.confirmation_idempotency_key = key
    reconciliation.confirmer = persisted_operator
    # The model guard protects ordinary callers; this is the service's controlled boundary.
    try:
        models.Model.save(reconciliation, update_fields=[
            'status', 'confirmation_idempotency_key', 'confirmer', 'updated_at',
        ])
    except IntegrityError as error:
        raise ReconciliationConflictError('确认幂等键已用于其他对账记录') from error
    return _reconciliation_result(reconciliation, True, return_result)
