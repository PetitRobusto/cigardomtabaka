"""收入和冲正在实际发生月份独立展示，汇总不受分页影响。"""
from decimal import Decimal

from django.db.models import Sum

from accounting.models import OtherIncome, OtherIncomeReversal
from accounting.income_categories import classification


def income_queryset():
    return OtherIncome.objects.select_related('fund_account', 'ledger_transaction', 'reversal')


def serialize_income_reversal(reversal):
    return {
        'id': reversal.pk, 'income_id': reversal.income_id,
        'business_date': reversal.business_date.isoformat(), 'note': reversal.note,
        'operator_id': reversal.operator_id, 'agent_source': reversal.agent_source,
        'ledger_transaction_id': reversal.ledger_transaction_id,
    }


def serialize_income(income):
    reversal = getattr(income, 'reversal', None)
    return {
        'id': income.pk, 'category': income.category, 'category_label': income.get_category_display(),
        **classification(income), 'recognition_confirmed': income.recognition_confirmed,
        'fund_account_id': income.fund_account_id, 'fund_account_name': income.fund_account.name,
        'currency': income.currency, 'amount': str(income.original_amount), 'amount_cny': str(income.amount_cny),
        'exchange_rate': str(income.exchange_rate), 'rate_source': income.rate_source,
        'reference': income.reference, 'zero_book_value_confirmed': income.zero_book_value_confirmed,
        'business_date': income.business_date.isoformat(), 'note': income.note,
        'operator_id': income.operator_id, 'agent_source': income.agent_source,
        'ledger_transaction_id': income.ledger_transaction_id,
        'status': 'reversed' if income.ledger_transaction.reversed_by_id else 'posted',
        'reversal': serialize_income_reversal(reversal) if reversal else None,
    }


def income_period(*, start=None, end=None, page=1, limit=20):
    incomes = income_queryset()
    reversals = OtherIncomeReversal.objects.select_related('income', 'income__fund_account')
    for lookup, bound in [('gte', start), ('lt', end)]:
        if bound:
            incomes = incomes.filter(**{f'business_date__{lookup}': bound})
            reversals = reversals.filter(**{f'business_date__{lookup}': bound})
    def total(queryset, field):
        return (queryset.aggregate(value=Sum(field))['value'] or Decimal('0.00')).quantize(Decimal('0.01'))
    received, reversed_amount = total(incomes, 'amount_cny'), total(reversals, 'income__amount_cny')
    count, reversal_count = incomes.count(), reversals.count()
    offset = (page - 1) * limit
    reversal_rows = []
    for reversal in reversals[offset:offset + limit]:
        income = reversal.income
        reversal_rows.append({**serialize_income_reversal(reversal),
                              **classification(income),
                              'income_business_date': income.business_date.isoformat(),
                              'category_label': income.get_category_display(),
                              'fund_account_name': income.fund_account.name, 'currency': income.currency,
                              'amount': str(income.original_amount), 'amount_cny': str(income.amount_cny)})
    return {
        'incomes': [serialize_income(income) for income in incomes[offset:offset + limit]],
        'reversals': reversal_rows, 'count': count, 'reversal_count': reversal_count, 'page': page,
        'next_page': page + 1 if page * limit < max(count, reversal_count) else None,
        'summary': {'received_cny': str(received), 'reversed_cny': str(reversed_amount),
                    'net_cny': str(received - reversed_amount)},
    }
