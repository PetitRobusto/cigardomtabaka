"""快照去重测试"""
import pytest
from django.utils import timezone
from datetime import timedelta
from price_tracker.models import PriceSource, PriceSnapshot
from price_tracker.scraper import run_scrape_sync, ScrapedItem, BaseScraper
from cigars.models import Cigar, Brand


@pytest.mark.django_db
class TestSnapshotDedup:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.brand = Brand.objects.create(name='Dedup Brand', english_name='Dedup Brand')
        self.cigar = Cigar.objects.create(brand='Dedup Brand', english_name='Dedup Cigar')
        self.source = PriceSource.objects.create(
            name='Dedup Source', slug='dedup-test',
            base_url='https://test.com', scraper_class='dedup_test', currency='USD',
        )

    def _register_mock_scraper(self, items):
        """Register a mock scraper that returns given items"""
        from price_tracker.scrapers import register_scraper

        class MockScraper(BaseScraper):
            source_slug = 'dedup-test'
            def scrape_catalog(self):
                return items

        # register_scraper is a decorator factory: register_scraper(slug)(cls)
        register_scraper('dedup-test')(MockScraper)

    def _make_historical_snapshot(self, cigar, box_size=25, in_stock=True,
                                   price=100.0, days_ago=1, **kwargs):
        """Create a snapshot with a past scraped_date to avoid uq_snapshot_per_day."""
        scraped_at = timezone.now() - timedelta(days=days_ago)
        snap = PriceSnapshot(
            source=self.source, cigar=cigar,
            price=price, currency='USD',
            box_size=box_size, in_stock=in_stock,
            scraped_at=scraped_at, scraped_date=scraped_at.date(),
            **kwargs,
        )
        snap.save()
        PriceSnapshot.objects.filter(pk=snap.pk).update(
            scraped_date=scraped_at.date(), scraped_at=scraped_at,
        )
        return PriceSnapshot.objects.get(pk=snap.pk)

    def test_new_product_creates(self):
        """New product -> creates snapshot"""
        items = [ScrapedItem(name='Dedup Cigar', price=100, box_size=25, currency='USD')]
        self._register_mock_scraper(items)
        result = run_scrape_sync('dedup-test')
        assert result['created'] == 1

    def test_same_price_skips(self):
        """Price unchanged -> skips"""
        self._make_historical_snapshot(self.cigar, price=100, in_stock=True)
        before = PriceSnapshot.objects.count()
        items = [ScrapedItem(name='Dedup Cigar', price=100, box_size=25, currency='USD')]
        self._register_mock_scraper(items)
        result = run_scrape_sync('dedup-test')
        assert result['created'] == 0
        assert PriceSnapshot.objects.count() == before

    def test_price_changed_creates(self):
        """Price changed -> creates new snapshot"""
        self._make_historical_snapshot(self.cigar, price=100, in_stock=True)
        items = [ScrapedItem(name='Dedup Cigar', price=120, box_size=25, currency='USD')]
        self._register_mock_scraper(items)
        result = run_scrape_sync('dedup-test')
        assert result['created'] == 1

    def test_price_change_under_one_cent_skips(self):
        """Price delta <= 0.01 -> skips as duplicate"""
        self._make_historical_snapshot(self.cigar, price=100.0, in_stock=True)
        before = PriceSnapshot.objects.count()
        items = [ScrapedItem(name='Dedup Cigar', price=100.009, box_size=25, currency='USD')]
        self._register_mock_scraper(items)
        result = run_scrape_sync('dedup-test')
        assert result['created'] == 0
        assert PriceSnapshot.objects.count() == before

    def test_price_change_over_one_cent_creates(self):
        """Price delta > 0.01 -> creates a new snapshot"""
        self._make_historical_snapshot(self.cigar, price=100.0, in_stock=True)
        items = [ScrapedItem(name='Dedup Cigar', price=100.011, box_size=25, currency='USD')]
        self._register_mock_scraper(items)
        result = run_scrape_sync('dedup-test')
        assert result['created'] == 1

    def test_relisted_creates(self):
        """Was delisted, now reappears -> creates relisted snapshot"""
        self._make_historical_snapshot(
            self.cigar, price=100, in_stock=False,
            raw_data={'delisted': True, 'delisted_at': '2026-05-27'},
        )
        items = [ScrapedItem(name='Dedup Cigar', price=100, box_size=25, currency='USD')]
        self._register_mock_scraper(items)
        result = run_scrape_sync('dedup-test')
        assert result['created'] == 1
        snap = PriceSnapshot.objects.filter(
            source=self.source, cigar=self.cigar, in_stock=True
        ).order_by('-scraped_at').first()
        assert snap is not None
        assert snap.raw_data.get('relisted') is True

    def test_delisting_detection_integration(self):
        """Old product not in today's scrape -> marked OOS"""
        # Create an old in-stock snapshot for a DIFFERENT cigar
        cigar2 = Cigar.objects.create(brand='Dedup Brand', english_name='Other Cigar')
        self._make_historical_snapshot(cigar2, price=50, box_size=10, in_stock=True)
        # Only scrape the original cigar, not cigar2
        items = [ScrapedItem(name='Dedup Cigar', price=100, box_size=25, currency='USD')]
        self._register_mock_scraper(items)
        result = run_scrape_sync('dedup-test')
        assert result['marked_oos'] >= 1  # cigar2 should be marked delisted
