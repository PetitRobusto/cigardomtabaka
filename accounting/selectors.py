from dataclasses import dataclass
import calendar
from decimal import Decimal

from accounting.models import FundAccount, LedgerPosting, LedgerTransaction
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


def _sum_category(category, *, start=None, end=None):
    postings = LedgerPosting.objects.filter(
        transaction__status=LedgerTransaction.Status.POSTED,
        category=category,
    )
    if start is not None:
        postings = postings.filter(transaction__business_date__gte=start)
    if end is not None:
        postings = postings.filter(transaction__business_date__lte=end)
    total = sum((row for row in postings.values_list('cny_amount', flat=True)), Decimal('0.00'))
    return total.quantize(Decimal('0.01'))


def monthly_profit(*, month):
    period_start, period_end = _month_bounds(month)
    revenue = _sum_category(LedgerPosting.Category.SALES_REVENUE, start=period_start, end=period_end)
    transport_revenue = _sum_category(LedgerPosting.Category.CUSTOMER_TRANSPORT_REVENUE, start=period_start, end=period_end)
    cost = _sum_category(LedgerPosting.Category.COST_OF_GOODS_SOLD, start=period_start, end=period_end)
    transport_expense = _sum_category(LedgerPosting.Category.TRANSPORT_EXPENSE, start=period_start, end=period_end)
    net_profit = (-revenue - transport_revenue - cost - transport_expense).quantize(Decimal('0.01'))
    transaction_count = LedgerTransaction.objects.filter(
        status=LedgerTransaction.Status.POSTED,
        business_date__gte=period_start,
        business_date__lte=period_end,
    ).count()
    return {
        'period_start': period_start, 'period_end': period_end,
        'sales_revenue_cny': revenue,
        'customer_transport_revenue_cny': transport_revenue,
        'cost_of_goods_sold_cny': cost,
        'transport_expense_cny': transport_expense,
        'net_profit_cny': net_profit, 'transaction_count': transaction_count,
    }


def accounting_summary(*, as_of):
    if not hasattr(as_of, 'year') or not hasattr(as_of, 'month'):
        raise ValueError('as_of 必须是 date')
    fund_accounts = []
    for account in FundAccount.objects.filter(is_active=True).order_by('currency', 'id'):
        snapshot = account_snapshot(account, as_of_business_date=as_of)
        fund_accounts.append({
            'account_id': account.id, 'name': account.name, 'currency': account.currency,
            'original_balance': snapshot.original_balance, 'cny_book_cost': snapshot.cny_book_cost,
        })
    inventory = sum((v for v in PurchaseBatch.objects.filter(remaining__gt=0).values_list('remaining_cost_cny', flat=True)), Decimal('0.00')).quantize(Decimal('0.01'))
    in_transit = sum((v for v in PurchaseOrder.objects.filter(status=PurchaseOrder.Status.DRAFT).values_list('cny_total', flat=True)), Decimal('0.00')).quantize(Decimal('0.01'))
    return {
        'as_of': as_of, 'fund_accounts': fund_accounts,
        'accounts_receivable_cny': _sum_category(LedgerPosting.Category.ACCOUNTS_RECEIVABLE, end=as_of),
        'customer_prepayments_cny': -_sum_category(LedgerPosting.Category.CUSTOMER_PREPAYMENTS, end=as_of),
        'inventory_remaining_cost_cny': inventory, 'purchase_in_transit_cny': in_transit,
    }
