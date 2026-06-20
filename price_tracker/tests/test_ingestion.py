"""Price Snapshot ingestion module tests."""
from datetime import timedelta

import pytest
from django.test import override_settings
from django.utils import timezone

from cigars.models import Brand, Cigar
from price_tracker.models import PriceSnapshot, PriceSource
from price_tracker.scraper import BaseScraper, ScrapedItem


@pytest.mark.django_db
class TestIngestItems:
    @pytest.fixture(autouse=True)
    def setup(self):
        Brand.objects.create(name='Ingestion Brand', english_name='Ingestion Brand')
        self.source = PriceSource.objects.create(
            name='Ingestion Source',
            slug='ingestion-test',
            base_url='https://ingestion.example',
            scraper_class='ingestion_test',
            currency='USD',
        )
        self.cigar = Cigar.objects.create(
            brand='Ingestion Brand',
            english_name='Ingestion Cigar',
        )

    def _patch_matcher(self, monkeypatch):
        def fake_match(scraper, item):
            return Cigar.objects.filter(english_name=item.name).first()

        monkeypatch.setattr(BaseScraper, 'match_cigar', fake_match)

    def _snapshot(self, cigar=None, days_ago=1, **kwargs):
        cigar = cigar or self.cigar
        scraped_at = timezone.now() - timedelta(days=days_ago)
        defaults = {
            'source': self.source,
            'cigar': cigar,
            'price': 100,
            'currency': 'USD',
            'price_cny': 700,
            'box_size': 25,
            'in_stock': True,
            'scraped_at': scraped_at,
            'scraped_date': scraped_at.date(),
        }
        defaults.update(kwargs)
        snap = PriceSnapshot.objects.create(**defaults)
        PriceSnapshot.objects.filter(pk=snap.pk).update(
            scraped_at=scraped_at,
            scraped_date=scraped_at.date(),
        )
        return PriceSnapshot.objects.get(pk=snap.pk)

    def test_new_item_creates_snapshot(self, monkeypatch):
        """new matched item creates a PriceSnapshot"""
        from price_tracker.ingestion import ingest_items

        self._patch_matcher(monkeypatch)

        result = ingest_items(
            self.source,
            [ScrapedItem(name='Ingestion Cigar', price=100, box_size=25, currency='USD')],
            mode='scrape',
            run_delisting=False,
        )

        assert result.total_items == 1
        assert result.matched == 1
        assert result.created == 1
        snap = PriceSnapshot.objects.get(source=self.source, cigar=self.cigar)
        assert snap.price == 100
        assert snap.price_cny == 700

    def test_duplicate_price_skips(self, monkeypatch):
        """same original price, CNY price and stock state skips"""
        from price_tracker.ingestion import ingest_items

        self._patch_matcher(monkeypatch)
        self._snapshot()

        result = ingest_items(
            self.source,
            [ScrapedItem(name='Ingestion Cigar', price=100, box_size=25, currency='USD')],
            mode='scrape',
            run_delisting=False,
        )

        assert result.created == 0
        assert result.skipped == 1
        assert PriceSnapshot.objects.filter(source=self.source, cigar=self.cigar).count() == 1

    def test_price_cny_change_creates_snapshot(self, monkeypatch):
        """same original price creates when pushed CNY price changes"""
        from price_tracker.ingestion import ingest_items

        self._patch_matcher(monkeypatch)
        self._snapshot()
        item = ScrapedItem(name='Ingestion Cigar', price=100, box_size=25, currency='USD')
        item.price_cny = 777

        result = ingest_items(
            self.source,
            [item],
            mode='push',
            run_delisting=False,
        )

        assert result.created == 1
        assert PriceSnapshot.objects.filter(
            source=self.source,
            cigar=self.cigar,
            price_cny=777,
        ).exists()

    def test_url_cache_hit_skips_matcher(self, monkeypatch):
        """cached URL/product match avoids calling the matcher"""
        from price_tracker.ingestion import ingest_items

        self._snapshot(
            url='https://ingestion.example/cached',
            raw_data={'product': 'Cached Product'},
        )

        def fail_match(scraper, item):
            raise AssertionError('matcher should not run on cache hit')

        monkeypatch.setattr(BaseScraper, 'match_cigar', fail_match)

        result = ingest_items(
            self.source,
            [
                ScrapedItem(
                    name='Unmatched Name',
                    price=120,
                    box_size=25,
                    currency='USD',
                    url='https://ingestion.example/cached',
                    raw_data={'product': 'Cached Product'},
                )
            ],
            mode='scrape',
            run_delisting=False,
        )

        assert result.matched == 1
        assert result.created == 1
        assert result.cache_hits == 1
        assert result.cache_misses == 0

    def test_missing_box_size_infers_unique_historical_size(self, monkeypatch):
        """scrape mode infers a missing box_size from one historical size"""
        from price_tracker.ingestion import ingest_items

        self._patch_matcher(monkeypatch)
        self._snapshot(price=100, price_cny=700, box_size=10)

        result = ingest_items(
            self.source,
            [ScrapedItem(name='Ingestion Cigar', price=120, box_size=None, currency='USD')],
            mode='scrape',
            run_delisting=False,
        )

        assert result.created == 1
        assert PriceSnapshot.objects.filter(
            source=self.source,
            cigar=self.cigar,
            price=120,
            box_size=10,
        ).exists()

    def test_push_mode_keeps_missing_box_size_uninferred(self, monkeypatch):
        """push mode preserves None box_size instead of inferring from history"""
        from price_tracker.ingestion import ingest_items

        self._patch_matcher(monkeypatch)
        self._snapshot(price=100, price_cny=700, box_size=10)

        result = ingest_items(
            self.source,
            [ScrapedItem(name='Ingestion Cigar', price=120, box_size=None, currency='USD')],
            mode='push',
            run_delisting=False,
        )

        assert result.created == 1
        snap = PriceSnapshot.objects.filter(
            source=self.source,
            cigar=self.cigar,
            price=120,
        ).order_by('-scraped_at').first()
        assert snap is not None
        assert snap.box_size is None

    def test_price_cny_from_raw_data_creates_snapshot(self, monkeypatch):
        """ingestion uses raw_data price_cny when item attribute is absent"""
        from price_tracker.ingestion import ingest_items

        self._patch_matcher(monkeypatch)

        item = ScrapedItem(
            name='Ingestion Cigar',
            price=120,
            box_size=25,
            currency='USD',
            raw_data={'price_cny': 888},
        )

        result = ingest_items(
            self.source,
            [item],
            mode='push',
            run_delisting=False,
        )

        assert result.created == 1
        snap = PriceSnapshot.objects.filter(
            source=self.source,
            cigar=self.cigar,
            price_cny=888,
        ).first()
        assert snap is not None

    def test_normalized_same_url_display_currency_does_not_create_snapshot(self, monkeypatch):
        """Same canonical URL/price skips even when raw display currency changed."""
        from price_tracker.ingestion import ingest_items

        self._patch_matcher(monkeypatch)
        url = 'https://ingestion.example/nyon-product/'
        self._snapshot(
            price=2850.0,
            currency='CHF',
            price_cny=24000,
            box_size=20,
            url=url,
            raw_data={
                'display_currency': 'CHF',
                'display_price': 2850.0,
                'canonical_currency': 'CHF',
            },
        )

        result = ingest_items(
            self.source,
            [
                ScrapedItem(
                    name='Ingestion Cigar',
                    price=2850.0,
                    box_size=20,
                    currency='CHF',
                    url=url,
                    raw_data={
                        'display_currency': 'EUR',
                        'display_price': 3163.5,
                        'canonical_currency': 'CHF',
                    },
                )
            ],
            mode='scrape',
            run_delisting=False,
        )

        assert result.created == 0
        assert result.skipped == 1
        assert PriceSnapshot.objects.filter(source=self.source, cigar=self.cigar).count() == 1

    def test_delisting_compares_only_last_scrape_date(self, monkeypatch):
        """delisting compares today with the latest previous scrape only"""
        from price_tracker.ingestion import ingest_items

        self._patch_matcher(monkeypatch)
        old_only = Cigar.objects.create(
            brand='Ingestion Brand',
            english_name='Older Only Cigar',
        )
        missing = Cigar.objects.create(
            brand='Ingestion Brand',
            english_name='Missing Cigar',
        )
        present = Cigar.objects.create(
            brand='Ingestion Brand',
            english_name='Present Cigar',
        )
        self._snapshot(cigar=old_only, days_ago=2, box_size=25)
        self._snapshot(cigar=missing, days_ago=1, box_size=25)
        self._snapshot(cigar=present, days_ago=1, box_size=25)

        result = ingest_items(
            self.source,
            [ScrapedItem(name='Present Cigar', price=100, box_size=25, currency='USD')],
            mode='scrape',
            run_delisting=True,
        )

        assert result.delisted == 1
        assert PriceSnapshot.objects.filter(
            source=self.source,
            cigar=missing,
            in_stock=False,
            raw_data__delisted=True,
        ).exists()
        assert not PriceSnapshot.objects.filter(
            source=self.source,
            cigar=old_only,
            in_stock=False,
        ).exists()

    def test_empty_scrape_does_not_mark_everything_delisted(self, monkeypatch):
        """empty scrape results are treated as a failed/blocked run, not all-OOS."""
        from price_tracker.ingestion import ingest_items

        self._snapshot(cigar=self.cigar, days_ago=1, box_size=25)

        result = ingest_items(
            self.source,
            [],
            mode='scrape',
            run_delisting=True,
        )

        assert result.total_items == 0
        assert result.delisted == 0
        assert not PriceSnapshot.objects.filter(
            source=self.source,
            cigar=self.cigar,
            in_stock=False,
            raw_data__delisted=True,
        ).exists()

    @override_settings(USE_TZ=True, TIME_ZONE='Asia/Shanghai')
    def test_delisting_uses_local_scrape_date(self, monkeypatch):
        """delisting compares against the same local date ingestion writes."""
        from price_tracker.ingestion import ingest_items

        self._patch_matcher(monkeypatch)
        missing = Cigar.objects.create(
            brand='Ingestion Brand',
            english_name='Missing Local Date Cigar',
        )
        self._snapshot(cigar=missing, days_ago=1, box_size=25)

        result = ingest_items(
            self.source,
            [ScrapedItem(name='Ingestion Cigar', price=100, box_size=25, currency='USD')],
            mode='scrape',
            run_delisting=True,
        )

        assert result.delisted == 1
        assert PriceSnapshot.objects.filter(
            source=self.source,
            cigar=missing,
            in_stock=False,
            scraped_date=timezone.localdate(),
            raw_data__delisted=True,
        ).exists()

    def test_error_summary_records_unmatched_items(self, monkeypatch):
        """unmatched items are counted and surfaced in result.unmatched"""
        from price_tracker.ingestion import ingest_items

        monkeypatch.setattr(BaseScraper, 'match_cigar', lambda scraper, item: None)

        result = ingest_items(
            self.source,
            [ScrapedItem(name='Unknown Cigar', price=120, box_size=25, currency='USD')],
            mode='scrape',
            run_delisting=False,
        )

        assert result.created == 0
        assert result.errors == 1
        assert result.error_summary == {'unmatched': 1}
        assert result.unmatched == ['Unknown Cigar']

    def test_anomaly_detection_runs_for_created_groups_only(self, monkeypatch):
        """created groups are sent to IQR anomaly recalculation"""
        from price_tracker.ingestion import ingest_items

        self._patch_matcher(monkeypatch)
        calls = []

        def fake_detect(cigar_id, box_size):
            calls.append((cigar_id, box_size))
            return 0

        monkeypatch.setattr('price_tracker.anomaly.detect_and_mark_group', fake_detect)

        result = ingest_items(
            self.source,
            [ScrapedItem(name='Ingestion Cigar', price=100, box_size=25, currency='USD')],
            mode='scrape',
            run_delisting=False,
        )

        assert result.created == 1
        assert calls == [(self.cigar.id, 25)]
