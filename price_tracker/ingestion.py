"""Unified Price Snapshot ingestion pipeline."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Iterable

from django.db.models import Count
from django.utils import timezone

from .match_cache import MatchCache
from .models import PriceSnapshot, PriceSource
from .pricing import convert_to_cny
from .scraper import BaseScraper, ScrapedItem

logger = logging.getLogger(__name__)


@dataclass
class IngestionResult:
    source: str
    total_items: int
    matched: int = 0
    created: int = 0
    skipped: int = 0
    delisted: int = 0
    errors: int = 0
    error_summary: dict[str, int] = field(default_factory=dict)
    cache_hits: int = 0
    cache_misses: int = 0
    unmatched: list[str] = field(default_factory=list)


def ingest_items(
    source: PriceSource,
    items: Iterable[ScrapedItem],
    *,
    mode: str,
    run_delisting: bool = True,
    today: date | None = None,
) -> IngestionResult:
    """Ingest normalized scraped/pushed/imported price items."""
    item_list = list(items)
    result = IngestionResult(source=source.slug, total_items=len(item_list))
    today = today or timezone.localdate()
    matcher = BaseScraper(source)
    match_cache = MatchCache.for_source(source)
    scraped_combos: set[tuple[int, int | None]] = set()
    anomaly_groups: set[tuple[int, int | None]] = set()
    seen_this_run: set[tuple[int, int | None, float | None]] = set()

    for item in item_list:
        try:
            if not item.name:
                result.skipped += 1
                _record_error(result, 'missing_name')
                continue

            cigar = match_cache.get(item)
            if cigar is None:
                cigar = matcher.match_cigar(item)

            if cigar is None:
                result.skipped += 1
                result.unmatched.append(_item_label(item))
                _record_error(result, 'unmatched')
                continue

            result.matched += 1

            box_size = _resolve_box_size(cigar, item, mode, result)
            if box_size is _SKIP_ITEM:
                continue

            scraped_combos.add((cigar.id, box_size))
            price_cny = _get_price_cny(item, source)
            latest = _latest_snapshot(source, cigar, box_size, item)
            raw_data = dict(item.raw_data) if isinstance(item.raw_data, dict) else {}

            should_create = _should_create_snapshot(
                latest=latest,
                item=item,
                price_cny=price_cny,
                raw_data=raw_data,
            )

            if not should_create:
                result.skipped += 1
                continue

            # 本轮去重：同 (cigar, box, price) 只入库一次
            run_combo = (cigar.id, box_size, item.price)
            if run_combo in seen_this_run:
                result.skipped += 1
                continue
            seen_this_run.add(run_combo)

            if item.price is None and item.in_stock:
                result.skipped += 1
                _record_error(result, 'missing_price')
                continue

            PriceSnapshot.objects.create(
                source=source,
                cigar=cigar,
                price=item.price,
                original_price=item.original_price,
                currency=getattr(item, 'currency', None) or source.currency or 'USD',
                price_cny=price_cny,
                box_size=box_size,
                box_price=item.box_price,
                url=item.url,
                in_stock=item.in_stock,
                scraped_date=today,
                scraped_at=timezone.now(),
                raw_data=raw_data,
            )
            result.created += 1
            anomaly_groups.add((cigar.id, box_size))
        except Exception as exc:
            logger.exception('Error ingesting item %s', getattr(item, 'name', '?'))
            result.errors += 1
            _increment_error(result, type(exc).__name__)

    if run_delisting and (mode != 'push' or scraped_combos):
        from .delisting import detect_delistings

        delisting_result = detect_delistings(source, scraped_combos)
        result.delisted = delisting_result['newly_delisted']

    if anomaly_groups:
        from .anomaly import detect_and_mark_group

        for cigar_id, box_size in anomaly_groups:
            detect_and_mark_group(cigar_id, box_size)

    source.last_scraped = timezone.now()
    source.save(update_fields=['last_scraped'])

    result.cache_hits = match_cache.hits
    result.cache_misses = match_cache.misses
    return result


_SKIP_ITEM = object()


def _resolve_box_size(cigar, item: ScrapedItem, mode: str, result: IngestionResult):
    if item.box_size is not None:
        return item.box_size

    if mode == 'push':
        return None

    known_sizes = (
        PriceSnapshot.objects
        .filter(cigar=cigar, box_size__isnull=False)
        .values('box_size')
        .annotate(cnt=Count('id'))
        .order_by('-cnt')
    )
    unique_sizes = [s['box_size'] for s in known_sizes]
    if len(unique_sizes) == 1:
        logger.info(
            '[boxsize-infer] %s -> %s box_size=%s',
            item.name,
            cigar.english_name,
            unique_sizes[0],
        )
        return unique_sizes[0]

    result.skipped += 1
    if not unique_sizes:
        logger.debug('[boxsize-skip] %s: no known box_size in DB', item.name)
    else:
        logger.debug('[boxsize-skip] %s: multiple box_size %s', item.name, unique_sizes)
    return _SKIP_ITEM


def _get_price_cny(item: ScrapedItem, source: PriceSource) -> float | None:
    price_cny = getattr(item, 'price_cny', None)
    if price_cny is None and isinstance(item.raw_data, dict):
        price_cny = item.raw_data.get('price_cny')
    if price_cny is not None:
        return price_cny
    if item.price is None:
        return None
    currency = getattr(item, 'currency', None) or source.currency or 'USD'
    return convert_to_cny(item.price, currency)


def _latest_snapshot(
    source: PriceSource,
    cigar,
    box_size: int | None,
    item: ScrapedItem,
) -> PriceSnapshot | None:
    base_qs = PriceSnapshot.objects.filter(source=source, cigar=cigar, box_size=box_size)
    if item.url:
        latest_for_url = base_qs.filter(url=item.url).order_by('-scraped_at').first()
        if latest_for_url:
            return latest_for_url
        return None
    return base_qs.order_by('-scraped_at').first()


def _should_create_snapshot(
    *,
    latest: PriceSnapshot | None,
    item: ScrapedItem,
    price_cny: float | None,
    raw_data: dict,
) -> bool:
    if latest is None:
        return True

    if latest.in_stock != item.in_stock:
        if not item.in_stock:
            raw_data['went_oos'] = True
            raw_data['went_oos_at'] = timezone.now().isoformat()
        else:
            raw_data['relisted'] = True
            raw_data['relisted_at'] = timezone.now().isoformat()
        return True

    price_same = _same_money(latest.price, item.price)
    return not price_same


def _same_money(left, right) -> bool:
    if left is None or right is None:
        return left is None and right is None
    return abs(float(left) - float(right)) <= 0.01


def _record_error(result: IngestionResult, error_type: str) -> None:
    result.errors += 1
    _increment_error(result, error_type)


def _increment_error(result: IngestionResult, error_type: str) -> None:
    classified = sum(
        count for key, count in result.error_summary.items()
        if key != 'other'
    )
    if classified >= 5:
        result.error_summary['other'] = result.error_summary.get('other', 0) + 1
        return

    result.error_summary[error_type] = result.error_summary.get(error_type, 0) + 1


def _item_label(item: ScrapedItem) -> str:
    if isinstance(item.raw_data, dict):
        brand = item.raw_data.get('brand')
        if brand:
            return f'{brand}: {item.name}'
    return item.name
