"""Shared parsing of catalog packaging declarations.

Display packaging descriptions and accounting box sizes are separate contracts:
the former may be translated text/dicts, while the latter must be stable
positive integers used by Day 1 validation.
"""

import json


def declared_box_sizes(packagings):
    if not packagings:
        return []
    try:
        data = json.loads(packagings) if isinstance(packagings, str) else packagings
    except (TypeError, json.JSONDecodeError):
        return []
    if isinstance(data, dict):
        candidates = data.get('box_sizes', [])
    elif isinstance(data, list):
        candidates = [
            item.get('size') if isinstance(item, dict) else item
            for item in data
        ]
    else:
        return []
    return sorted({
        value for value in candidates
        if isinstance(value, int) and not isinstance(value, bool) and value > 0
    })
