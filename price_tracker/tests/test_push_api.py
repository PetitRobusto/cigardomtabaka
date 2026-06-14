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
            box_size=25,
            url='https://push.example/known-cigar',
            raw_data={'product': 'Known Cigar'},
        )

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
        request = self.factory.post(
            '/api/prices/push-bulk/',
            data=json.dumps({'source_slug': self.source.slug, 'items': items}),
            content_type='application/json',
            HTTP_X_API_KEY='secret',
        )

        response = push_bulk(request)
        payload = json.loads(response.content)

        assert response.status_code == 200
        assert payload['errors'] == 6
        assert payload['error_summary'] == {'TypeError': 5, 'other': 1}
