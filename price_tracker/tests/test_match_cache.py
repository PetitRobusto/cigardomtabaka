"""URL/product match cache tests."""
import pytest

from cigars.models import Brand, Cigar
from price_tracker.models import PriceSnapshot, PriceSource
from price_tracker.scraper import ScrapedItem


@pytest.mark.django_db
class TestMatchCache:
    @pytest.fixture(autouse=True)
    def setup(self):
        Brand.objects.create(name='Cache Brand', english_name='Cache Brand')
        self.source = PriceSource.objects.create(
            name='Cache Source',
            slug='cache-test',
            base_url='https://cache.example',
            scraper_class='cache_test',
            currency='USD',
        )
        self.cigar_a = Cigar.objects.create(
            brand='Cache Brand',
            english_name='Cache Cigar A',
        )
        self.cigar_b = Cigar.objects.create(
            brand='Cache Brand',
            english_name='Cache Cigar B',
        )

    def _snapshot(self, cigar, url, raw_data):
        return PriceSnapshot.objects.create(
            source=self.source,
            cigar=cigar,
            price=100,
            currency='USD',
            box_size=25,
            url=url,
            raw_data=raw_data,
        )

    def test_same_url_with_different_products_does_not_cross_match(self):
        """same URL is safe when product name differs"""
        from price_tracker.match_cache import MatchCache

        url = 'https://cache.example/brand-page'
        self._snapshot(self.cigar_a, url, {'product': 'Cache Product A'})
        self._snapshot(self.cigar_b, url, {'product': 'Cache Product B'})

        cache = MatchCache.for_source(self.source)

        assert cache.get(ScrapedItem(
            name='Cache Cigar A',
            url=url,
            raw_data={'product': 'Cache Product A'},
        )) == self.cigar_a
        assert cache.get(ScrapedItem(
            name='Cache Cigar B',
            url=url,
            raw_data={'product': 'Cache Product B'},
        )) == self.cigar_b
        assert cache.get(ScrapedItem(
            name='Unknown',
            url=url,
            raw_data={'product': 'Unknown Product'},
        )) is None
        assert cache.hits == 2
        assert cache.misses == 1

    def test_stale_cigar_id_is_ignored(self, monkeypatch):
        """stale cache entries do not crash callers"""
        from price_tracker.match_cache import MatchCache

        self._snapshot(
            self.cigar_a,
            'https://cache.example/stale',
            {'product': 'Stale Product'},
        )
        real_get = Cigar.objects.get

        def fake_get(*args, **kwargs):
            if kwargs.get('id') == self.cigar_a.id:
                raise Cigar.DoesNotExist
            return real_get(*args, **kwargs)

        monkeypatch.setattr(Cigar.objects, 'get', fake_get)

        cache = MatchCache.for_source(self.source)

        assert cache.get(ScrapedItem(
            name='Stale Product',
            url='https://cache.example/stale',
            raw_data={'product': 'Stale Product'},
        )) is None
        assert cache.hits == 0
        assert cache.misses == 1

    def test_legacy_url_cache_only_hits_when_unambiguous(self):
        """legacy rows without product use URL only when one cigar is possible"""
        from price_tracker.match_cache import MatchCache

        one_url = 'https://cache.example/one-product'
        shared_url = 'https://cache.example/shared'
        self._snapshot(self.cigar_a, one_url, {})
        self._snapshot(self.cigar_a, shared_url, {})
        self._snapshot(self.cigar_b, shared_url, {})

        cache = MatchCache.for_source(self.source)

        assert cache.get(ScrapedItem(name='Legacy A', url=one_url)) == self.cigar_a
        assert cache.get(ScrapedItem(name='Ambiguous', url=shared_url)) is None
        assert cache.hits == 1
        assert cache.misses == 1
