"""Read-only dividend totals, independent of detail pagination and month filters."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Sum

from accounting.models import DividendPayout, DividendRound


@transaction.atomic
def dividend_summary():
    allocated = {}
    for role in ('partner_a_id', 'partner_b_id'):
        for row in DividendRound.objects.filter(status='posted').order_by().values(role).annotate(total=Sum('total_cny')):
            user_id = row[role]
            allocated[user_id] = allocated.get(user_id, Decimal('0.00')) + row['total'] / 2
    paid = {
        row['recipient_id']: row['total']
        for row in DividendPayout.objects.filter(status='posted', round__status='posted')
        .order_by().values('recipient_id').annotate(total=Sum('amount_cny'))
    }
    partners = []
    for user in get_user_model().objects.filter(pk__in=allocated).order_by('id'):
        amount = allocated[user.pk]
        received = paid.get(user.pk, Decimal('0.00'))
        partners.append({
            'id': user.pk, 'name': user.get_full_name() or user.username,
            'allocated_cny': f'{amount:.2f}', 'paid_cny': f'{received:.2f}',
            'pending_cny': f'{amount - received:.2f}',
        })
    return {
        'partners': partners,
        'allocated_cny': f'{sum(allocated.values(), Decimal("0.00")):.2f}',
        'paid_cny': f'{sum(paid.values(), Decimal("0.00")):.2f}',
        'pending_cny': f'{sum(allocated.values(), Decimal("0.00")) - sum(paid.values(), Decimal("0.00")):.2f}',
    }
