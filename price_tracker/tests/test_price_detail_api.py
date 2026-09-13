"""Price detail and Dashboard read contracts; all writes target Django's test database."""
from datetime import timedelta
from types import SimpleNamespace

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from cigars.models import Cigar
from price_tracker.models import PriceSnapshot, PriceSource
from price_tracker.serializers import PriceSnapshotSerializer
from price_tracker.views import PriceSnapshotViewSet


class PriceDetailContractTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.cigar = Cigar.objects.create(brand='Test', name='测试产品', english_name='Test Product')
        self.source = PriceSource.objects.create(name='Test Source', slug='detail-test',
                                               currency='USD', exchange_rate=7.1)

    def snapshot(self, days=0, **overrides):
        fields = dict(cigar=self.cigar, source=self.source, price=100, price_cny=700,
                      box_size=10, currency='USD', url='https://example.com/product',
                      in_stock=True, raw_data={'title_original': 'Source product'})
        fields.update(overrides)
        snap = PriceSnapshot.objects.create(**fields)
        PriceSnapshot.objects.filter(pk=snap.pk).update(scraped_at=timezone.now() - timedelta(days=days))
        snap.refresh_from_db()
        return snap

    def request(self, action='history', authenticate=True, **params):
        request = self.factory.get('/', {'cigar_id': self.cigar.id, **params})
        if authenticate:
            force_authenticate(request, user=SimpleNamespace(is_authenticated=True))
        return PriceSnapshotViewSet.as_view({'get': action})(request)

    def test_history_window_excludes_old_points_but_keeps_current_quote(self):
        self.snapshot(days=4000)
        month = self.request(days=30).data['variants'][0]
        self.assertEqual(month['current_price'], 100)
        self.assertEqual(month['points'], [])
        self.assertEqual(month['record_count'], 1)
        self.assertEqual(month['history_record_count'], 0)
        all_history = self.request(days='all').data
        self.assertIsNone(all_history['history_days'])
        self.assertEqual(len(all_history['variants'][0]['points']), 1)

    def test_latest_null_price_name_currency_and_status_are_not_backfilled(self):
        self.snapshot(days=2)
        latest = self.snapshot(price=None, price_cny=None, currency='CHF', in_stock=False,
                               raw_data={'product_name': 'Latest name', 'delisted': True})
        result = self.request().data['variants'][0]
        self.assertEqual(result['snapshot_id'], latest.id)
        self.assertIsNone(result['current_price'])
        self.assertIsNone(result['current_price_cny'])
        self.assertEqual(result['product_name'], 'Latest name')
        self.assertEqual(result['scraped_name'], 'Latest name')
        self.assertEqual(result['currency'], 'CHF')
        self.assertTrue(result['delisted'])
        self.assertFalse(result['in_stock'])
        self.assertTrue(result['points'][0]['in_stock'])
        self.assertFalse(result['points'][0]['delisted'])
        self.assertTrue(result['points'][-1]['delisted'])
        self.assertEqual(result['source_currency'], 'USD')
        self.assertEqual(result['source_exchange_rate'], 7.1)

    def test_latest_is_chronological_with_id_tie_break_and_keeps_anomaly(self):
        current = self.snapshot(is_anomalous=True)
        imported = self.snapshot(days=20, price=20)
        for action in ('history', 'list_aggregated'):
            response = self.request(action).data
            item = response['variants'][0] if action == 'history' else response[0]['sources'][0]
            self.assertEqual(item.get('current_price', item.get('price')), 100)
            self.assertTrue(item['anomaly']['exclude_from_aggregate'])
        PriceSnapshot.objects.filter(pk=imported.pk).update(scraped_at=current.scraped_at)
        self.assertEqual(self.request().data['variants'][0]['current_price'], 20)

    def test_same_source_and_box_different_urls_are_separate_offers(self):
        self.snapshot(url='https://example.com/a')
        self.snapshot(url='https://example.com/b', price=200)
        self.assertEqual(len(self.request().data['variants']), 2)
        self.assertEqual(len(self.request('list_aggregated').data[0]['sources']), 2)

    def test_unknown_box_is_never_inferred(self):
        self.snapshot(box_size=None)
        variant = self.request().data['variants'][0]
        self.assertEqual(variant['box_label'], '未知盒规')
        self.assertIsNone(variant['price_per_stick'])
        self.assertIsNone(self.request('list_aggregated').data[0]['avg_per_stick_cny'])

    def test_null_and_zero_box_are_distinct_offers(self):
        self.snapshot(box_size=None)
        self.snapshot(box_size=0)
        self.assertEqual(len(self.request().data['variants']), 2)
        self.assertEqual(len(self.request('list_aggregated').data[0]['sources']), 2)

    def test_anomaly_is_independent_and_excluded_without_hiding_quote(self):
        self.snapshot(is_anomalous=True)
        variant = self.request().data['variants'][0]
        self.assertTrue(variant['in_stock'])
        self.assertEqual(variant['anomaly']['code'], 'outlier')
        self.assertIn('IQR', variant['anomaly']['reason'])
        self.assertTrue(variant['points'][0]['anomaly']['exclude_from_aggregate'])
        self.assertIsNone(self.request('list_aggregated').data[0]['avg_per_stick_cny'])

    def test_dashboard_average_only_uses_valid_available_quotes(self):
        self.snapshot(price_cny=700, url='https://example.com/a')
        self.snapshot(price_cny=900, url='https://example.com/b')
        cases = [
            {'in_stock': False}, {'raw_data': {'delisted': True}},
            {'price_cny': 0}, {'price_cny': -100}, {'price_cny': None},
            {'box_size': 0}, {'box_size': -1}, {'box_size': None}, {'is_anomalous': True},
        ]
        for index, changes in enumerate(cases):
            self.snapshot(url=f'https://example.com/excluded/{index}', **changes)
        data = self.request('list_aggregated').data[0]
        self.assertEqual(len(data['sources']), 11)
        self.assertEqual(data['avg_per_stick_cny'], 80)

    def test_invalid_range_and_identifier_return_400(self):
        for days in ('bad', '0', '-1', '999999999999999', '1.5'):
            self.assertEqual(self.request(days=days).status_code, 400)
        self.assertEqual(self.request(cigar_id='invalid').status_code, 400)
        for days in (30, 90, 180, 365, 'all'):
            self.assertEqual(self.request(days=days).status_code, 200)

    def test_api_remains_authenticated_and_empty_catalog_keeps_identity(self):
        self.assertIn(self.request(authenticate=False).status_code, (401, 403))
        data = self.request().data
        self.assertEqual(data['cigar_name'], '测试产品')
        self.assertEqual(data['variants'], [])

    def test_serializer_uses_the_same_source_name_semantics_and_does_not_infer_anomalies(self):
        for raw, expected in [
            ({'title_original': ' Original ', 'product': 'fallback'}, 'Original'),
            ({'product_name': 'Product name'}, 'Product name'),
            ({'title': 'Title'}, 'Title'), ({'product': 'Product'}, 'Product'),
            ({'title_original': 123}, ''), ({}, ''),
        ]:
            snap = self.snapshot(raw_data=raw)
            data = PriceSnapshotSerializer(snap).data
            self.assertEqual(data['product_name'], expected)
            self.assertEqual(data['scraped_name'], expected)
            self.assertIsNone(data['anomaly'])
