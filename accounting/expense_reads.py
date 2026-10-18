"""费用列表的期间汇总与累计详情保持独立口径。"""
from decimal import Decimal

from django.db.models import Prefetch

from accounting.action_serializers import serialize_expense, serialize_expense_refund
from accounting.models import Expense, ExpenseRefund, LedgerTransaction


def expense_queryset():
    return Expense.objects.select_related(
        'fund_account', 'ledger_transaction', 'ledger_transaction__reversed_by',
    ).prefetch_related(Prefetch('refunds', queryset=ExpenseRefund.objects.select_related('fund_account')))


def expense_period(*, start=None, end=None, limit=100, page=1):
    expenses = expense_queryset().order_by('-business_date', '-id')
    refunds = ExpenseRefund.objects.select_related('fund_account', 'expense').order_by('-business_date', '-id')
    reversals = LedgerTransaction.objects.filter(
        transaction_type=LedgerTransaction.TransactionType.EXPENSE,
        source_type='ledger_reversal', status=LedgerTransaction.Status.POSTED,
    )
    for field, bound in [('gte', start), ('lt', end)]:
        if bound:
            expenses = expenses.filter(**{f'business_date__{field}': bound})
            refunds = refunds.filter(**{f'business_date__{field}': bound})
            reversals = reversals.filter(**{f'business_date__{field}': bound})
    total = lambda values: sum(values, Decimal('0.00')).quantize(Decimal('0.01'))
    spent = total(expenses.values_list('amount_cny', flat=True))
    returned = total(refunds.values_list('amount_cny', flat=True))
    reversed_amount = total(reversals.filter(postings__account__isnull=False).values_list('postings__cny_amount', flat=True))
    count, refund_count = expenses.count(), refunds.count()
    offset = (page - 1) * limit
    refund_rows = []
    for refund in refunds[offset:offset + limit]:
        row = serialize_expense_refund(refund)
        row.update({'expense_business_date': refund.expense.business_date.isoformat(),
                    'expense_note': refund.expense.note,
                    'expense_label': refund.expense.get_subcategory_display() or refund.expense.get_category_display()})
        refund_rows.append(row)
    return {
        'expenses': [serialize_expense(item) for item in expenses[offset:offset + limit]],
        'refunds': refund_rows,
        'count': count, 'refund_count': refund_count, 'page': page,
        'next_page': page + 1 if page * limit < max(count, refund_count) else None,
        'summary': {'spent_cny': str(spent), 'refunded_cny': str(returned),
                    'reversed_cny': str(reversed_amount), 'net_cny': str(spent - returned - reversed_amount)},
    }
