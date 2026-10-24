"""Sitemap eligibility, revalidation and bounded catalog work."""

from copy import deepcopy
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch
from xml.etree.ElementTree import fromstring

from django.core.cache import cache
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from cigars.models import Brand, Cigar, PurchaseBatch
from cigars.tests.inventory_fixtures import create_purchase_batch, force_inventory_update
from storefront.catalog import build_pages, public_dependencies, public_page_paths, semantic_hash
from storefront.models import ProductListing, StorePage, StoreTranslation


@override_settings(STOREFRONT_ENABLED=True, STOREFRONT_ORIGIN="https://store.example")
class SitemapTests(TestCase):
    url = '/sitemap-storefront.xml'

    def setUp(self):
        cache.clear()
        self.brand = Brand.objects.create(english_name='Test Brand', name='测试品牌')
        self.home = StoreTranslation.objects.create(
            kind='home', key='home', locale='zh', title='首页',
            description='介绍', body='正文', published=True,
        )
        self.cigar = Cigar.objects.create(brand=self.brand.english_name, english_name='Test Cigar')
        self.listing = ProductListing.objects.create(cigar=self.cigar, published=True)
        self.batch(self.cigar)

    def batch(self, cigar):
        return create_purchase_batch(
            source=PurchaseBatch.Source.OPENING, cigar=cigar, quantity=1,
            remaining=1, physical_remaining=1, box_size=None, unit_cost_cny=Decimal('1'),
        )

    def publish(self):
        pages = build_pages()
        for path, payload in pages.items():
            StorePage.objects.update_or_create(path=path, defaults={
                'active': True, 'payload': payload, 'rendered_payload': payload,
                'desired_hash': semantic_hash(payload), 'rendered_hash': semantic_hash(payload),
                'html': '<html>Rendered content</html>', 'rendered_changed_at': timezone.now(),
            })
        return pages

    def paths(self, response):
        self.assertEqual(response.status_code, 200)
        return {node.text.removeprefix('https://store.example')
                for node in fromstring(response.content).iter() if node.tag.endswith('}loc')}

    def test_request_skips_full_page_build_images_and_prices(self):
        pages = self.publish()
        with patch('storefront.views.build_pages', side_effect=AssertionError('Full page rebuild')):
            with CaptureQueriesContext(connection) as queries:
                response = self.client.get(self.url)
        expected = {path for path, payload in pages.items() if payload['indexable']}
        self.assertEqual(self.paths(response), expected)
        # Adding directory products must not introduce image/price queries.
        sql = '\n'.join(query['sql'].lower() for query in queries)
        self.assertNotIn('cigars_cigarimage', sql)
        self.assertNotIn('cigars_cigarprice', sql)
        self.assertLessEqual(len(queries), 12)

    def test_path_catalog_matches_full_build_across_stock_and_publication_changes(self):
        Brand.objects.create(english_name='Empty Brand')
        Cigar.objects.create(brand='Unregistered Brand', english_name='Directory Only')
        items = Cigar.objects.bulk_create([
            Cigar(brand=self.brand.english_name, english_name=f'Extra {number}') for number in range(25)
        ])
        for cigar in items:
            self.batch(cigar)
        ProductListing.objects.bulk_create([ProductListing(cigar=cigar, published=True) for cigar in items])
        self.assertEqual(public_page_paths(public_dependencies()), set(build_pages()))
        self.assertIn('/?page=2', public_page_paths(public_dependencies()))
        self.listing.withdrawn = True
        self.listing.save(update_fields=['withdrawn'])
        Cigar.objects.filter(pk=items[0].pk).update(deleted_at=timezone.now())
        self.home.published = False
        self.home.save(update_fields=['published'])
        self.assertEqual(public_page_paths(public_dependencies()), set(build_pages()))
        self.assertNotIn('/', public_page_paths(public_dependencies()))

    def test_revalidation_supports_head_weak_and_multiple_etags(self):
        self.publish()
        first = self.client.get(self.url)
        self.assertEqual(first['Cache-Control'], 'no-cache')
        for validator in (first['ETag'], 'W/' + first['ETag'], '"other", ' + first['ETag'], '*'):
            with self.subTest(validator=validator):
                response = self.client.get(self.url, HTTP_IF_NONE_MATCH=validator)
                self.assertEqual(response.status_code, 304)
                self.assertEqual(response.content, b'')
                self.assertEqual(response['ETag'], first['ETag'])
                self.assertEqual(response['Cache-Control'], 'no-cache')
        head = self.client.head(self.url)
        self.assertEqual(head.status_code, 200)
        self.assertEqual(head.content, b'')
        self.assertEqual(head['ETag'], first['ETag'])
        self.assertEqual(self.client.get(self.url, HTTP_IF_NONE_MATCH='"other"').content, first.content)

    def test_withdrawal_bypasses_warm_xml_cache_and_old_validator(self):
        pages = self.publish()
        product_path = next(path for path, page in pages.items() if page['kind'] == 'product' and page['locale'] == 'zh')
        first = self.client.get(self.url)
        self.assertIn(product_path, self.paths(first))
        # Bulk updates deliberately bypass model signals.
        ProductListing.objects.filter(pk=self.listing.pk).update(withdrawn=True)
        current = self.client.get(self.url, HTTP_IF_NONE_MATCH=first['ETag'])
        self.assertNotIn(product_path, self.paths(current))
        self.assertNotEqual(current['ETag'], first['ETag'])

    def test_translation_revocation_and_slug_changes_bypass_cache(self):
        self.publish()
        first = self.client.get(self.url)
        StoreTranslation.objects.filter(pk=self.home.pk).update(published=False)
        current = self.client.get(self.url, HTTP_IF_NONE_MATCH=first['ETag'])
        self.assertNotIn('/', self.paths(current))
        self.assertNotIn('/catalog', self.paths(current))
        Cigar.objects.filter(pk=self.cigar.pk).update(english_name='Renamed')
        current = self.client.get(self.url, HTTP_IF_NONE_MATCH=current['ETag'])
        self.assertFalse(any(path.startswith('/cigar/') for path in self.paths(current)))

    def test_out_of_range_and_noncanonical_cached_pagination_is_excluded(self):
        items = Cigar.objects.bulk_create([
            Cigar(brand=self.brand.english_name, english_name=f'Extra {number}') for number in range(24)
        ])
        for cigar in items:
            self.batch(cigar)
        ProductListing.objects.bulk_create([ProductListing(cigar=cigar, published=True) for cigar in items])
        pages = self.publish()
        first = self.client.get(self.url)
        self.assertIn('/?page=2', self.paths(first))
        for path in ('/?page=1', '/?page=02', '/?page=999', '/catalog?q=test'):
            payload = deepcopy(pages['/'])
            payload['path'] = path
            StorePage.objects.create(path=path, active=True, rendered_payload=payload,
                                     html='old page', rendered_hash='rendered', desired_hash='rendered')
        # Exhaust stock while preserving inventory history: the old page's
        # dependencies still exist, but home pagination must shrink immediately.
        force_inventory_update(PurchaseBatch.objects.all(), available_stick_quantity=0)
        current = self.client.get(self.url, HTTP_IF_NONE_MATCH=first['ETag'])
        paths = self.paths(current)
        self.assertNotIn('/?page=2', paths)
        self.assertIn('/catalog?page=2', paths)
        for path in ('/?page=1', '/?page=02', '/?page=999', '/catalog?q=test'):
            self.assertNotIn(path, paths)

    def test_cache_tracks_origin_and_content_date_and_respects_disabled_storefront(self):
        self.publish()
        first = self.client.get(self.url)
        StorePage.objects.filter(path='/').update(rendered_changed_at=timezone.now() - timedelta(days=2))
        changed = self.client.get(self.url, HTTP_IF_NONE_MATCH=first['ETag'])
        self.assertEqual(changed.status_code, 200)
        self.assertNotEqual(changed['ETag'], first['ETag'])
        with override_settings(STOREFRONT_ORIGIN='https://other.example'):
            other = self.client.get(self.url, HTTP_IF_NONE_MATCH=changed['ETag'])
        self.assertEqual(other.status_code, 200)
        self.assertNotContains(other, 'https://store.example')
        self.assertContains(other, 'https://other.example')
        with override_settings(STOREFRONT_ENABLED=False):
            self.assertEqual(self.client.get(self.url, HTTP_IF_NONE_MATCH=first['ETag']).status_code, 404)
