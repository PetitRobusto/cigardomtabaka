"""Stable JSON read models for the one-time Day 1 workflow."""

from accounting.models import Day1DraftAccount


_SLOT_ORDER = {
    Day1DraftAccount.Slot.OWNER_CNY: 0,
    Day1DraftAccount.Slot.PARTNER_CNY: 1,
    Day1DraftAccount.Slot.RUB: 2,
    Day1DraftAccount.Slot.USDT: 3,
}


def _serialize_draft(initialization):
    """Keep editable draft data separate from the frozen completion summary."""
    accounts = sorted(
        initialization.draft_accounts.all(),
        key=lambda row: (_SLOT_ORDER.get(row.slot, 99), row.pk),
    )
    inventory = sorted(
        initialization.draft_inventory.all(),
        key=lambda row: (row.cigar_id, row.box_size, row.pk),
    )
    return {
        'accounts': [
            {
                'slot': row.slot,
                'name': row.account_name,
                'currency': row.currency,
                'original_amount': format(row.original_amount, '.8f'),
                'cny_book_cost': format(row.cny_book_cost, '.2f'),
            }
            for row in accounts
        ],
        'inventory': [
            {
                'cigar_id': row.cigar_id,
                'box_size': row.box_size,
                'box_quantity': row.box_quantity,
                'loose_sticks': row.loose_sticks,
                'unit_cost_cny': format(row.unit_cost_cny, '.2f'),
            }
            for row in inventory
        ],
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
    return {
        'status': initialization.status,
        'version': initialization.version,
        'business_date': (
            initialization.business_date.isoformat()
            if initialization.business_date else None
        ),
        'draft': None if completed else _serialize_draft(initialization),
        # This JSON value was frozen by confirm_day1 and must not be rebuilt.
        'completion_summary': (
            initialization.completion_summary if completed else None
        ),
    }
