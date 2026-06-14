"""价格推送 API 测试"""
import json

import pytest
from django.test import RequestFactory, override_settings

from cigars.models import Cigar, Brand
from price_tracker.models import PriceSource, PriceSnapshot
from price_tracker.push_api import push_bulk


@pytest.mark.django_db
class TestPushBulk:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.factory = RequestFactory()
        Brand.objects.create(name='Push Brand', english_name='Push Brand')
        self.cigar = Cigar.objects.create(brand='Push Brand', english_name='Known Cigar')
        self.source = PriceSource.objects.create(
            name='Push Source',
            slug='push-test',
            base_url='https://push.example',
            scraper_class='push_test',
            currency='USD',
        )
        PriceSnapshot.objects.create(
            source=self.source,
            cigar=self.cigar,
            price=100,
            currency='USD',
            price_cny=700,
            box_size=25,
            url='https://push.example/known-cigar',
            raw_data={'product': 'Known Cigar'},
        )

    def _post_push(self, items):
        return self.factory.post(
            '/api/prices/push-bulk/',
            data=json.dumps({'source_slug': self.source.slug, 'items': items}),
            content_type='application/json',
            HTTP_X_API_KEY='secret',
        )

    @override_settings(DEBUG=False)
    def test_uses_pushed_price_cny_without_reconverting(self, monkeypatch):
        """push preserves caller-provided price_cny when creating a snapshot"""
        monkeypatch.setenv('PRICE_PUSH_API_KEY', 'secret')
        item = {
            'name': 'Known Cigar',
            'price': 100,
            'price_cny': 777,
            'box_size': 25,
            'currency': 'USD',
            'url': 'https://push.example/known-cigar',
            'raw_data': {'product': 'Known Cigar'},
        }

        response = push_bulk(self._post_push([item]))
        payload = json.loads(response.content)

        assert response.status_code == 200
        assert payload['created'] == 1
        latest = PriceSnapshot.objects.filter(
            source=self.source, cigar=self.cigar, price_cny=777
        ).order_by('-scraped_at').first()
        assert latest is not None

    @override_settings(DEBUG=False)
    def test_success_response_shape_stays_compatible(self, monkeypatch):
        """push response keeps the public API field set stable"""
        monkeypatch.setenv('PRICE_PUSH_API_KEY', 'secret')
        item = {
            'name': 'Known Cigar',
            'price': 100,
            'price_cny': 700,
            'box_size': 25,
            'currency': 'USD',
            'url': 'https://push.example/known-cigar',
            'raw_data': {'product': 'Known Cigar'},
        }

        response = push_bulk(self._post_push([item]))
        payload = json.loads(response.content)

        assert response.status_code == 200
        assert set(payload) == {
            'ok',
            'source',
            'received',
            'matched',
            'created',
            'skipped',
            'delisted',
            'errors',
            'error_summary',
            'cache_hits',
            'cache_misses',
        }

    @override_settings(DEBUG=False)
    def test_uses_fallback_cny_when_payload_does_not_include_price_cny(self, monkeypatch):
        """push fills price_cny from local conversion when caller omits it"""
        monkeypatch.setenv('PRICE_PUSH_API_KEY', 'secret')
        item = {
            'name': 'Known Cigar',
            'price': 120,
            'box_size': 25,
            'currency': 'USD',
            'url': 'https://push.example/known-cigar',
            'raw_data': {'product': 'Known Cigar'},
        }

        response = push_bulk(self._post_push([item]))
        payload = json.loads(response.content)

        assert response.status_code == 200
        assert payload['created'] == 1
        snap = PriceSnapshot.objects.filter(
            source=self.source,
            cigar=self.cigar,
        ).order_by('-scraped_at').first()
        assert snap is not None
        assert snap.price_cny == 840

    @override_settings(DEBUG=False)
    def test_error_summary_rolls_extra_error_types_into_other(self, monkeypatch):
        """push keeps only five classified error buckets and rolls the rest into other"""
        monkeypatch.setenv('PRICE_PUSH_API_KEY', 'secret')

        items = [
            {'name': '', 'price': 100, 'box_size': 25, 'currency': 'USD', 'raw_data': {}},
            {'name': '', 'price': 100, 'box_size': 25, 'currency': 'USD', 'raw_data': {}},
            {'name': '', 'price': 100, 'box_size': 25, 'currency': 'USD', 'raw_data': {}},
            {'name': '', 'price': 100, 'box_size': 25, 'currency': 'USD', 'raw_data': {}},
            {'name': '', 'price': 100, 'box_size': 25, 'currency': 'USD', 'raw_data': {}},
            {'name': '', 'price': 100, 'box_size': 25, 'currency': 'USD', 'raw_data': {}},
        ]

        response = push_bulk(self._post_push(items))
        payload = json.loads(response.content)

        assert response.status_code == 200
        assert payload['errors'] == 6
        assert payload['error_summary'] == {'missing_name': 5, 'other': 1}

    @override_settings(DEBUG=False)
    def test_error_summary_groups_processing_errors_and_remaining_samples(self, monkeypatch):
        """push response includes grouped error counts and sampled overflow as other"""
        monkeypatch.setenv('PRICE_PUSH_API_KEY', 'secret')

        bad_item = {
            'name': 'Known Cigar',
            'price': 'bad-price',
            'box_size': 25,
            'currency': 'USD',
            'url': 'https://push.example/known-cigar',
            'raw_data': {'product': 'Known Cigar'},
        }
        items = [bad_item.copy() for _ in range(6)]

        response = push_bulk(self._post_push(items))
        payload = json.loads(response.content)

        assert response.status_code == 200
        assert payload['errors'] == 6
        assert payload['error_summary'] == {'TypeError': 5, 'other': 1}
