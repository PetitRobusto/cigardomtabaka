from dataclasses import dataclass
import calendar
from decimal import Decimal

from django.db.models import Sum
from accounting.business_time import moscow_business_date
from accounting.models import (
    AccountReconciliation, Dividend, FundAccount, LedgerPosting, LedgerTransaction,
)
from cigars.models import PurchaseBatch, PurchaseOrder


@dataclass(frozen=True)
class AccountSnapshot:
    account_id: int
    currency: str
    original_balance: Decimal
    cny_book_cost: Decimal

    @property
    def moving_average_cny(self):
        if self.original_balance == Decimal('0.00000000'):
            return None
        return self.cny_book_cost / self.original_balance


def account_snapshot(account, as_of_business_date=None):
    postings = LedgerPosting.objects.filter(
        account=account,
        transaction__status=LedgerTransaction.Status.POSTED,
    )
    if as_of_business_date is not None:
        postings = postings.filter(transaction__business_date__lte=as_of_business_date)

    original_balance = Decimal('0.00000000')
    cny_book_cost = Decimal('0.00')
    for amount, cny_amount in postings.values_list('amount', 'cny_amount'):
        original_balance += amount
        cny_book_cost += cny_amount

    return AccountSnapshot(
        account_id=account.pk,
        currency=account.currency,
        original_balance=original_balance.quantize(Decimal('0.00000000')),
        cny_book_cost=cny_book_cost.quantize(Decimal('0.00')),
    )


def _month_bounds(month):
    if not hasattr(month, 'year') or not hasattr(month, 'month'):
        raise ValueError('month 必须是 date')
    period_start = month.replace(day=1)
    period_end = month.replace(day=calendar.monthrange(month.year, month.month)[1])
    return period_start, period_end


def _sum_category(category, *, start=None, end=None, transaction_type=None):
    postings = LedgerPosting.objects.filter(
        transaction__status=LedgerTransaction.Status.POSTED,
        category=category,
    )
    if start is not None:
        postings = postings.filter(transaction__business_date__gte=start)
    if end is not None:
        postings = postings.filter(transaction__business_date__lte=end)
    if transaction_type is not None:
        postings = postings.filter(transaction__transaction_type=transaction_type)
    total = sum((row for row in postings.values_list('cny_amount', flat=True)), Decimal('0.00'))
    return total.quantize(Decimal('0.01'))


def _operating_profit_facts(*, start=None, end=None):
    """Return one canonical set of signed operating facts for reports and retained earnings."""
    revenue = _sum_category(LedgerPosting.Category.SALES_REVENUE, start=start, end=end)
    transport_revenue = _sum_category(LedgerPosting.Category.CUSTOMER_TRANSPORT_REVENUE, start=start, end=end)
    cost = _sum_category(LedgerPosting.Category.COST_OF_GOODS_SOLD, start=start, end=end)
    # 销售人肉费必须来自销售人肉费交易，而非普通经营费用动作。
    transport_expense = _sum_category(
        LedgerPosting.Category.TRANSPORT_EXPENSE,
        start=start, end=end,
        transaction_type=LedgerTransaction.TransactionType.SALES_TRANSPORT_COST,
    )
    transport_settlement_expense = _sum_category(
        LedgerPosting.Category.TRANSPORT_SETTLEMENT_EXPENSE,
        start=start, end=end,
        transaction_type=LedgerTransaction.TransactionType.EXPENSE,
    )
    expenses = {
        'salary_expense_cny': _sum_category(LedgerPosting.Category.SALARY_EXPENSE, start=start, end=end),
        'rent_expense_cny': _sum_category(LedgerPosting.Category.RENT_EXPENSE, start=start, end=end),
        'utilities_expense_cny': _sum_category(LedgerPosting.Category.UTILITIES_EXPENSE, start=start, end=end),
        'professional_expense_cny': _sum_category(LedgerPosting.Category.PROFESSIONAL_EXPENSE, start=start, end=end),
        'interest_expense_cny': _sum_category(LedgerPosting.Category.INTEREST_EXPENSE, start=start, end=end),
        'other_expense_cny': _sum_category(LedgerPosting.Category.OTHER_EXPENSE, start=start, end=end),
    }
    inventory_gain = -_sum_category(LedgerPosting.Category.INVENTORY_ADJUSTMENT_GAIN, start=start, end=end)
    inventory_loss = _sum_category(LedgerPosting.Category.INVENTORY_ADJUSTMENT_LOSS, start=start, end=end)
    reconciliation_gain = -_sum_category(LedgerPosting.Category.RECONCILIATION_GAIN, start=start, end=end)
    reconciliation_loss = _sum_category(LedgerPosting.Category.RECONCILIATION_LOSS, start=start, end=end)
    net_profit = (
        -revenue - transport_revenue - cost - transport_expense
        - sum(expenses.values(), Decimal('0.00'))
        - transport_settlement_expense
        + inventory_gain - inventory_loss
        + reconciliation_gain - reconciliation_loss
    ).quantize(Decimal('0.01'))
    return {
        'sales_revenue_cny': revenue,
        'customer_transport_revenue_cny': transport_revenue,
        'cost_of_goods_sold_cny': cost,
        'transport_expense_cny': transport_expense,
        'transport_settlement_expense_cny': transport_settlement_expense,
        **expenses,
        'inventory_adjustment_gain_cny': inventory_gain,
        'inventory_adjustment_loss_cny': inventory_loss,
        'reconciliation_gain_cny': reconciliation_gain,
        'reconciliation_loss_cny': reconciliation_loss,
        'net_profit_cny': net_profit,
    }


def monthly_profit(*, month):
    period_start, period_end = _month_bounds(month)
    facts = _operating_profit_facts(start=period_start, end=period_end)
    transaction_count = LedgerTransaction.objects.filter(
        status=LedgerTransaction.Status.POSTED,
        business_date__gte=period_start,
        business_date__lte=period_end,
    ).count()
    return {
        'period_start': period_start, 'period_end': period_end,
        **facts,
        'transaction_count': transaction_count,
    }


def retained_earnings(*, as_of):
    """Derive retained earnings from posted operating facts and confirmed dividends."""
    if not hasattr(as_of, 'year') or not hasattr(as_of, 'month'):
        raise ValueError('as_of 必须是 date')
    profit = _operating_profit_facts(end=as_of)['net_profit_cny']
    dividends = sum(
        Dividend.objects.filter(
            status=Dividend.Status.POSTED, business_date__lte=as_of,
        ).values_list('total_cny', flat=True), Decimal('0.00'),
    )
    return (profit - dividends).quantize(Decimal('0.01'))


def _account_rows(*, as_of):
    """用固定两次查询聚合全部账户余额，避免按账户逐笔读取流水。"""
    accounts = list(
        FundAccount.objects.filter(is_active=True).order_by('currency', 'id')
    )
    totals = {
        row['account_id']: row
        for row in LedgerPosting.objects.filter(
            account__is_active=True,
            transaction__status=LedgerTransaction.Status.POSTED,
            transaction__business_date__lte=as_of,
        ).values('account_id').annotate(
            original_balance=Sum('amount'),
            cny_book_cost=Sum('cny_amount'),
        )
    }
    rows = []
    for account in accounts:
        total = totals.get(account.pk, {})
        snapshot = AccountSnapshot(
            account_id=account.pk,
            currency=account.currency,
            original_balance=(total.get('original_balance') or Decimal('0.00')).quantize(Decimal('0.00000000')),
            cny_book_cost=(total.get('cny_book_cost') or Decimal('0.00')).quantize(Decimal('0.00')),
        )
        rows.append({
            'id': account.pk,
            'account_id': account.pk,
            'name': account.name,
            'currency': account.currency,
            'custodian_id': account.custodian_id,
            'original_balance': snapshot.original_balance,
            'cny_book_cost': snapshot.cny_book_cost,
            'moving_average_cny': snapshot.moving_average_cny,
        })
    return rows


def accounting_summary(*, as_of, require_current=True, account_rows=None):
    if not hasattr(as_of, 'year') or not hasattr(as_of, 'month'):
        raise ValueError('as_of 必须是 date')
    if require_current and as_of != moscow_business_date():
        raise ValueError('as_of 仅支持当前日期')
    account_rows = account_rows if account_rows is not None else _account_rows(as_of=as_of)
    fund_accounts = [
        {
            'account_id': row['account_id'],
            'name': row['name'],
            'currency': row['currency'],
            'original_balance': row['original_balance'],
            'cny_book_cost': row['cny_book_cost'],
        }
        for row in account_rows
    ]
    inventory = sum((v for v in PurchaseBatch.objects.filter(remaining__gt=0).values_list('remaining_cost_cny', flat=True)), Decimal('0.00')).quantize(Decimal('0.01'))
    # 在途归属以已入账付款的显式业务日为准，不能用服务器 paid_at 推导。
    from accounting.models import PurchasePayment
    in_transit_orders = PurchaseOrder.objects.filter(
        status=PurchaseOrder.Status.IN_TRANSIT,
        purchasepayment__status=PurchasePayment.Status.POSTED,
        purchasepayment__business_date__lte=as_of,
    )
    in_transit = sum(((v or Decimal('0.00')) for v in in_transit_orders.values_list('paid_cny_cost', flat=True)), Decimal('0.00')).quantize(Decimal('0.01'))
    return {
        'as_of': as_of, 'fund_accounts': fund_accounts,
        'accounts_receivable_cny': _sum_category(LedgerPosting.Category.ACCOUNTS_RECEIVABLE, end=as_of),
        'customer_prepayments_cny': -_sum_category(LedgerPosting.Category.CUSTOMER_PREPAYMENTS, end=as_of),
        'inventory_remaining_cost_cny': inventory, 'purchase_in_transit_cny': in_transit,
    }


def accounting_dashboard(*, as_of):
    """Build trusted dashboard totals after Day 1 has established opening facts."""
    # The HTTP boundary computes today's Moscow date once for a consistent snapshot.
    accounts = _account_rows(as_of=as_of)
    summary = accounting_summary(
        as_of=as_of, require_current=False, account_rows=accounts,
    )
    profit = monthly_profit(month=as_of.replace(day=1))
    cny_funds_total = sum(
        (row['original_balance'] for row in accounts if row['currency'] == FundAccount.Currency.CNY),
        Decimal('0.00'),
    )
    fund_accounts_book_cost = (
        LedgerPosting.objects.filter(
            account_id__isnull=False,
            transaction__status=LedgerTransaction.Status.POSTED,
            transaction__business_date__lte=as_of,
        ).aggregate(total=Sum('cny_amount'))['total'] or Decimal('0.00')
    )
    total_funds_cny = (
        fund_accounts_book_cost
        + summary['inventory_remaining_cost_cny']
        + summary['accounts_receivable_cny']
    ).quantize(Decimal('0.01'))

    # Pending reconciliation records are actionable; latest records provide context.
    reconciliation_rows = AccountReconciliation.objects.select_related(
        'account',
    ).filter(business_date__lte=as_of).order_by('-business_date', '-id')
    latest = [
        {
            'id': row.pk,
            'account_id': row.account_id,
            'account_name': row.account.name,
            'business_date': row.business_date,
            'system_amount': row.system_amount,
            'actual_amount': row.actual_amount,
            'difference': row.difference,
            'status': row.status,
        }
        for row in reconciliation_rows[:5]
    ]
    return {
        'stats': {
            'total_funds_cny': total_funds_cny,
            'cny_funds_total': cny_funds_total.quantize(Decimal('0.01')),
            'inventory_book_cost_cny': summary['inventory_remaining_cost_cny'],
            'accounts_receivable_cny': summary['accounts_receivable_cny'],
            'month_net_profit_cny': profit['net_profit_cny'],
        },
        'accounts': accounts,
        'monthly_profit': profit,
        'reconciliation': {
            'pending_count': reconciliation_rows.filter(
                status=AccountReconciliation.Status.PENDING,
            ).count(),
            'latest': latest,
        },
    }
