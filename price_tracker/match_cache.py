"""URL/product match cache for Price Snapshot ingestion."""
import logging
from collections import defaultdict
from typing import TYPE_CHECKING

from cigars.models import Cigar

from .models import PriceSnapshot, PriceSource

if TYPE_CHECKING:
    from .scraper import ScrapedItem

logger = logging.getLogger(__name__)


class MatchCache:
    """Cache historical URL/product matches for one price source."""

    def __init__(self, cache: dict[tuple[str, str], int]):
        self._cache = cache
        self._hits = 0
        self._misses = 0

    @classmethod
    def for_source(cls, source: PriceSource) -> "MatchCache":
        """Build a cache from historical snapshots for one source."""
        cache: dict[tuple[str, str], int] = {}
        ids_by_url: dict[str, set[int]] = defaultdict(set)

        snapshots = PriceSnapshot.objects.filter(source=source, url__gt='').values(
            'url',
            'raw_data',
            'cigar_id',
        )
        for snap in snapshots:
            url = snap['url']
            cigar_id = snap['cigar_id']
            ids_by_url[url].add(cigar_id)

            raw_data = snap['raw_data'] or {}
            product = raw_data.get('product', '') if isinstance(raw_data, dict) else ''
            if product:
                cache[(url, product)] = cigar_id

        # Legacy rows may not have raw_data["product"].  Only expose a pure URL
        # key when the URL maps to exactly one cigar; otherwise it can cross-match
        # brand/category pages that contain multiple products.
        for url, cigar_ids in ids_by_url.items():
            if len(cigar_ids) == 1:
                cache.setdefault((url, ''), next(iter(cigar_ids)))

        logger.info(
            '[match-cache] loaded %d URL/product mappings for %s',
            len(cache),
            source.slug,
        )
        return cls(cache)

    def get(self, item: "ScrapedItem") -> Cigar | None:
        """Return cached cigar for an item, or None on miss/stale entries."""
        if not item.url:
            self._misses += 1
            return None

        product = item.raw_data.get('product', '') if isinstance(item.raw_data, dict) else ''
        key = (item.url, product or '')
        cigar_id = self._cache.get(key)
        if cigar_id is None:
            self._misses += 1
            return None

        try:
            cigar = Cigar.objects.get(id=cigar_id)
        except Cigar.DoesNotExist:
            self._cache.pop(key, None)
            self._misses += 1
            logger.debug('[match-cache] stale cigar_id=%s for key=%s', cigar_id, key)
            return None

        self._hits += 1
        return cigar

    @property
    def hits(self) -> int:
        return self._hits

    @property
    def misses(self) -> int:
        return self._misses
