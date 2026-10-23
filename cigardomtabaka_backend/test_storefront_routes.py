"""Keep storefront 404s strict without breaking the existing business SPA."""

from unittest.mock import patch

from django.http import HttpResponse
from django.test import SimpleTestCase, override_settings


@override_settings(STOREFRONT_ENABLED=True, DEBUG=True)
class StorefrontSpaRouteTests(SimpleTestCase):
    # These are page routes in App.tsx/businessRoutes.ts, not namespace prefixes.
    fixed_paths = (
        '/inventory', '/inventory/purchases',
        '/sales', '/sales/receipts', '/sales/customers',
        '/accounting', '/accounting/day1',
        '/accounting/reports/monthly', '/accounting/reports/contributions',
        '/reports/monthly', '/reports/contributions',
        '/help', '/prices', '/prices/alerts', '/privnote', '/login',
    )
    parameter_paths = (
        '/prices/cigar/123', '/prices/cigar/123/cohiba-robustos',
        '/p/customer-token_123',
    )
    unknown_paths = (
        '/invented-page', '/pricesfake', '/inventoryfake', '/salesfake',
        '/accountingfake', '/helpful', '/privnotefake', '/loginfake',
        '/catalogfake', '/catalog/not-a-page',
        '/prices/not-a-page', '/inventory/not-a-page',
        '/inventory/purchases/123', '/sales/customers/123',
        '/accounting/reports/not-a-page', '/reports/not-a-page',
        '/help/not-a-page', '/privnote/not-a-page', '/login/not-a-page',
        '/prices/cigar', '/prices/cigar/not-an-id',
        '/prices/cigar/123/slug/extra', '/p', '/p/token/extra',
    )

    def test_existing_pages_and_single_trailing_slash_keep_the_spa(self):
        for base_path in self.fixed_paths + self.parameter_paths:
            for suffix in ('', '/'):
                for method in ('get', 'head'):
                    with self.subTest(path=base_path + suffix, method=method):
                        response = getattr(self.client, method)(base_path + suffix)
                        self.assertEqual(response.status_code, 200)
                        if method == 'get':
                            self.assertContains(response, '<div id="root"></div>')
                        else:
                            self.assertEqual(response.content, b'')

    def test_unknown_paths_return_real_404_instead_of_spa_html(self):
        for base_path in self.unknown_paths:
            for suffix in ('', '/'):
                with self.subTest(path=base_path + suffix):
                    response = self.client.get(base_path + suffix)
                    self.assertEqual(response.status_code, 404)
                    self.assertNotIn(b'<div id="root"></div>', response.content)

    def test_query_strings_do_not_change_page_route_matching(self):
        self.assertEqual(self.client.get('/login/?next=/sales/customers').status_code, 200)
        self.assertEqual(self.client.get('/reports/monthly?month=2026-10').status_code, 200)
        self.assertEqual(self.client.get('/prices/not-a-page?q=Cohiba').status_code, 404)

    def test_public_catalog_routes_still_delegate_to_the_storefront(self):
        with patch('storefront.views.page', return_value=HttpResponse('public catalogue')) as page:
            for path in ('/', '/catalog', '/catalog/', '/ru/', '/en/', '/ru/catalog', '/en/catalog', '/brand/cohiba', '/cigar/123/old-slug'):
                with self.subTest(path=path):
                    response = self.client.get(path)
                    self.assertEqual(response.content, b'public catalogue')
                    self.assertEqual(page.call_args.args[0].path, path)

    @override_settings(STOREFRONT_ENABLED=False)
    def test_disabled_storefront_retains_legacy_spa_catchall(self):
        for path in ('/', '/invented-page', '/pricesfake', '/prices/not-a-page', '/ru/not-a-page'):
            with self.subTest(path=path):
                self.assertContains(self.client.get(path), '<div id="root"></div>')
