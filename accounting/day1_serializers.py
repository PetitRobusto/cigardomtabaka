"""Stable JSON read models for the one-time Day 1 workflow."""


def _serialize_draft(initialization):
    """Keep editable draft data separate from the frozen completion summary."""
    accounts = initialization.draft_payload.get('accounts')
    inventory = initialization.draft_payload.get('inventory')
    return {
        'accounts': accounts if isinstance(accounts, list) else [],
        'inventory': inventory if isinstance(inventory, list) else [],
    }


def serialize_day1_state(initialization):
    """Expose only one of the editable draft or immutable completed snapshot."""
    if initialization is None:
        return {
            'status': 'not_started',
            'version': 0,
            'business_date': None,
            'draft': None,
            'completion_summary': None,
        }
    completed = initialization.status == initialization.Status.COMPLETED
    draft_business_date = (
        initialization.draft_payload.get('business_date')
        if initialization.draft_payload else None
    )
    return {
        'status': initialization.status,
        'version': initialization.version,
        'business_date': (
            draft_business_date
            if not completed and isinstance(draft_business_date, str)
            else initialization.business_date.isoformat()
            if initialization.business_date else None
        ),
        'draft': None if completed else _serialize_draft(initialization),
        # This JSON value was frozen by confirm_day1 and must not be rebuilt.
        'completion_summary': (
            initialization.completion_summary if completed else None
        ),
    }
