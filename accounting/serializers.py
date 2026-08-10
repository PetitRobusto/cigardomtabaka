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
        'account_id': snapshot.account_id,
        'currency': snapshot.currency,
        'original_balance': format(snapshot.original_balance, 'f'),
        'cny_book_cost': format(snapshot.cny_book_cost, 'f'),
        'moving_average_cny': None if moving_average is None else format(moving_average, 'f'),
    }


def serialize_transaction(ledger_transaction):
    postings = list(ledger_transaction.postings.all())
    return {
        'id': ledger_transaction.pk,
        'type': ledger_transaction.transaction_type,
        'status': ledger_transaction.status,
        'date': ledger_transaction.business_date.isoformat(),
        'sequence': ledger_transaction.effective_sequence,
        'description': ledger_transaction.description,
        'operator_id': ledger_transaction.operator_id,
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
