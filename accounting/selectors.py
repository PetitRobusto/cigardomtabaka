from dataclasses import dataclass
from decimal import Decimal

from accounting.models import LedgerPosting, LedgerTransaction


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
