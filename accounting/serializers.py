from accounting.selectors import account_snapshot


def serialize_account(account):
    return {
        'id': account.pk,
        'name': account.name,
        'currency': account.currency,
        'custodian_id': account.custodian_id,
        'is_active': account.is_active,
    }


def serialize_snapshot(account):
    snapshot = account_snapshot(account)
    moving_average = snapshot.moving_average_cny
    return {
        **serialize_account(account),
        'original_balance': format(snapshot.original_balance, 'f'),
        'cny_book_cost': format(snapshot.cny_book_cost, 'f'),
        'moving_average_cny': None if moving_average is None else format(moving_average, 'f'),
    }


def serialize_transaction(ledger_transaction):
    postings = list(ledger_transaction.postings.all())
    reversal = getattr(ledger_transaction, 'reversed_by', None)
    return {
        'id': ledger_transaction.pk,
        'transaction_type': ledger_transaction.transaction_type,
        'status': ledger_transaction.status,
        'business_date': ledger_transaction.business_date.isoformat(),
        'effective_sequence': ledger_transaction.effective_sequence,
        'description': ledger_transaction.description,
        'operator_id': ledger_transaction.operator_id,
        'source_type': ledger_transaction.source_type,
        'source_id': ledger_transaction.source_id,
        'reversed_by_id': ledger_transaction.reversed_by_id,
        'reversal_business_date': reversal.business_date.isoformat() if reversal is not None else None,
        'postings': [
            {
                'account_id': posting.account_id,
                'category': posting.category,
                'currency': posting.currency,
                'amount': str(posting.amount),
                'cny_amount': str(posting.cny_amount),
            }
            for posting in postings
        ],
    }
