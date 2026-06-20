"""Snapshot creation decision tests."""
from datetime import timedelta

import pytest
from django.utils import timezone

from cigars.models import Brand, Cigar
from price_tracker.models import PriceSnapshot, PriceSource
from price_tracker.scraper import ScrapedItem


@pytest.mark.django_db
class TestSnapshotDecision:
    @pytest.fixture(autouse=True)
    def setup(self):
        Brand.objects.create(name='Decision Brand', english_name='Decision Brand')
        self.source = PriceSource.objects.create(
            name='Decision Source',
            slug='decision-source',
            base_url='https://decision.example',
            scraper_class='decision_test',
            currency='CHF',
        )
        self.cigar = Cigar.objects.create(
            brand='Decision Brand',
            english_name='Decision Cigar',
        )

    def _snapshot(self, days_ago=1, **kwargs):
        scraped_at = timezone.now() - timedelta(days=days_ago)
        defaults = {
            'source': self.source,
            'cigar': self.cigar,
            'price': 2850.0,
            'currency': 'CHF',
            'price_cny': 24000.0,
            'box_size': 20,
            'url': 'https://decision.example/product/',
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

    def test_same_url_same_price_skips(self):
        from price_tracker.snapshot_decision import decide_snapshot

        latest = self._snapshot()
        item = ScrapedItem(
            name='Decision Cigar',
            price=2850.0,
            currency='CHF',
            box_size=20,
            url='https://decision.example/product/',
        )

        decision = decide_snapshot(
            source=self.source,
            cigar=self.cigar,
            box_size=20,
            item=item,
            price_cny=23900.0,
        )

        assert decision.latest == latest
        assert decision.should_create is False
        assert decision.raw_data == {}

    def test_same_url_price_change_creates(self):
        from price_tracker.snapshot_decision import decide_snapshot

        self._snapshot()
        item = ScrapedItem(
            name='Decision Cigar',
            price=2900.0,
            currency='CHF',
            box_size=20,
            url='https://decision.example/product/',
        )

        decision = decide_snapshot(
            source=self.source,
            cigar=self.cigar,
            box_size=20,
            item=item,
            price_cny=24300.0,
        )

        assert decision.should_create is True
        assert decision.raw_data == {}

    def test_stock_change_marks_raw_data_update(self):
        from price_tracker.snapshot_decision import decide_snapshot

        self._snapshot(in_stock=True)
        item = ScrapedItem(
            name='Decision Cigar',
            price=2850.0,
            currency='CHF',
            box_size=20,
            url='https://decision.example/product/',
            in_stock=False,
        )

        decision = decide_snapshot(
            source=self.source,
            cigar=self.cigar,
            box_size=20,
            item=item,
            price_cny=24000.0,
        )

        assert decision.should_create is True
        assert decision.raw_data['went_oos'] is True
        assert 'went_oos_at' in decision.raw_data

    def test_box_info_preferred_over_url_fallback(self):
        from price_tracker.snapshot_decision import decide_snapshot

        old_variant = self._snapshot(
            days_ago=2,
            price=100.0,
            raw_data={'box_info': '5x4 Box'},
        )
        self._snapshot(
            days_ago=1,
            price=200.0,
            raw_data={'box_info': '20 Box'},
        )
        item = ScrapedItem(
            name='Decision Cigar',
            price=100.0,
            currency='CHF',
            box_size=20,
            url='https://decision.example/product/',
            raw_data={'box_info': '5x4 box'},
        )

        decision = decide_snapshot(
            source=self.source,
            cigar=self.cigar,
            box_size=20,
            item=item,
            price_cny=840.0,
        )

        assert decision.latest == old_variant
        assert decision.should_create is False
