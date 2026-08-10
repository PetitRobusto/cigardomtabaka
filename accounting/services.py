from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import time

from django.contrib.auth import get_user_model
from django.db import IntegrityError, OperationalError, connection, transaction
from django.db.models import Sum
from django.utils import timezone

from accounting.models import FundAccount, LedgerPosting, LedgerSequence, LedgerTransaction


CUTOVER_DATE = date(2026, 8, 10)
CNY_PLACES = Decimal('0.01')
ORIGINAL_PLACES = {
    FundAccount.Currency.CNY: Decimal('0.01'),
    FundAccount.Currency.RUB: Decimal('0.01'),
    FundAccount.Currency.USDT: Decimal('0.00000001'),
}


class LedgerError(Exception):
    pass


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


def _decimal(value, places, field_name):
    try:
        return Decimal(str(value)).quantize(places, rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError):
        raise LedgerError(f'{field_name}必须是有效金额')


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


def _validate_metadata(transaction_type, business_date, idempotency_key):
    if transaction_type not in LedgerTransaction.TransactionType.values:
        raise LedgerError('交易类型无效')
    if type(business_date) is not date:
        raise LedgerError('业务日期必须是 date')
    if business_date < CUTOVER_DATE:
        raise LedgerError('业务日期不能早于账务切换日')
    if not isinstance(idempotency_key, str) or not idempotency_key:
        raise LedgerError('幂等键不能为空')


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
        replay = [
            (row['transaction__business_date'], row['transaction__effective_sequence'], row['amount'], row['cny_amount'])
            for row in history
        ]
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


@transaction.atomic
def _post_transaction_once(*, transaction_type, business_date, postings, operator,
                           idempotency_key, description='', source_type='', source_id=''):
    _validate_metadata(transaction_type, business_date, idempotency_key)
    persisted_operator = _require_operator(operator)
    existing = _existing_transaction(idempotency_key, transaction_type)
    if existing is not None:
        return existing

    try:
        raw_postings = tuple(postings)
    except TypeError:
        raise LedgerError('postings必须是可迭代分录')
    account_map = _resolve_accounts(raw_postings)
    prepared = _prepare_postings(raw_postings, account_map)

    sequence, _ = LedgerSequence.objects.select_for_update().get_or_create(name='global')
    effective_sequence = sequence.next_value
    _validate_historical_balances(account_map, prepared, business_date, effective_sequence)

    try:
        with transaction.atomic():
            sequence.next_value += 1
            sequence.save(update_fields=['next_value'])
            ledger_transaction = LedgerTransaction.objects.create(
                transaction_type=transaction_type,
                status=LedgerTransaction.Status.POSTED,
                business_date=business_date,
                effective_sequence=effective_sequence,
                idempotency_key=idempotency_key,
                description=description or '',
                source_type=source_type or '',
                source_id=source_id or '',
                operator=persisted_operator,
                posted_at=timezone.now(),
            )
            LedgerPosting.objects.bulk_create([
                LedgerPosting(
                    transaction=ledger_transaction,
                    account_id=posting.account_id,
                    category=posting.category,
                    currency=posting.currency,
                    amount=posting.amount,
                    cny_amount=posting.cny_amount,
                )
                for posting in prepared
            ])
    except IntegrityError:
        existing = _existing_transaction(idempotency_key, transaction_type)
        if existing is not None:
            return existing
        raise LedgerError('创建账务交易失败')
    return ledger_transaction


def post_transaction(*, transaction_type, business_date, postings, operator,
                     idempotency_key, description='', source_type='', source_id=''):
    for attempt in range(5):
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
            if not locked_sqlite or attempt == 4:
                raise
            time.sleep(0.02 * (attempt + 1))
