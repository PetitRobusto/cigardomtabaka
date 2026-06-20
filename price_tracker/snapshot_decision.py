"""Decide whether a scraped item should create a new PriceSnapshot."""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from django.utils import timezone

from .models import PriceSnapshot, PriceSource
from .scraper import ScrapedItem


@dataclass
class SnapshotDecision:
    should_create: bool
    latest: PriceSnapshot | None
    raw_data: dict = field(default_factory=dict)


def decide_snapshot(
    *,
    source: PriceSource,
    cigar,
    box_size: int | None,
    item: ScrapedItem,
    price_cny: float | None,
) -> SnapshotDecision:
    """Return whether this item represents a new price or stock state."""
    latest = latest_snapshot(source, cigar, box_size, item)
    raw_data = dict(item.raw_data) if isinstance(item.raw_data, dict) else {}

    if latest is None:
        return SnapshotDecision(True, latest, raw_data)

    if latest.in_stock != item.in_stock:
        if not item.in_stock:
            raw_data['went_oos'] = True
            raw_data['went_oos_at'] = timezone.now().isoformat()
        else:
            raw_data['relisted'] = True
            raw_data['relisted_at'] = timezone.now().isoformat()
        return SnapshotDecision(True, latest, raw_data)

    price_same = same_money(latest.price, item.price)

    # Only compare CNY when push/import explicitly supplied it.
    explicit_cny = getattr(item, 'price_cny', None)
    if explicit_cny is None and isinstance(item.raw_data, dict):
        explicit_cny = item.raw_data.get('price_cny')
    if explicit_cny is not None:
        cny_same = same_money(latest.price_cny, price_cny)
        return SnapshotDecision(not (price_same and cny_same), latest, raw_data)

    return SnapshotDecision(not price_same, latest, raw_data)


def latest_snapshot(
    source: PriceSource,
    cigar,
    box_size: int | None,
    item: ScrapedItem,
) -> PriceSnapshot | None:
    """Find the historical snapshot that represents the same product variant."""
    base_qs = PriceSnapshot.objects.filter(source=source, cigar=cigar, box_size=box_size)
    if not base_qs.exists():
        return None

    box_info = extract_box_info(item)
    if box_info:
        match = find_by_box_info(base_qs, box_info)
        if match:
            return match

    if item.url:
        match = base_qs.filter(url=item.url).order_by('-scraped_at').first()
        if match:
            return match

    return base_qs.order_by('-scraped_at').first()


def extract_box_info(item: ScrapedItem) -> str | None:
    rd = item.raw_data if isinstance(item.raw_data, dict) else {}
    return rd.get('box_info') or None


def normalize_box_info(text: str) -> str:
    return ' '.join(text.lower().split())


def extract_box_info_from_snapshot(snap: PriceSnapshot) -> str | None:
    rd = snap.raw_data
    if isinstance(rd, str):
        try:
            rd = json.loads(rd)
        except (json.JSONDecodeError, TypeError):
            return None
    if isinstance(rd, dict):
        return rd.get('box_info') or None
    return None


def find_by_box_info(base_qs, box_info: str) -> PriceSnapshot | None:
    target = normalize_box_info(box_info)
    for snap in base_qs.order_by('-scraped_at')[:60]:
        snap_box_info = extract_box_info_from_snapshot(snap)
        if snap_box_info and normalize_box_info(snap_box_info) == target:
            return snap
    return None


def same_money(left, right) -> bool:
    if left is None or right is None:
        return left is None and right is None
    return abs(float(left) - float(right)) <= 0.01
