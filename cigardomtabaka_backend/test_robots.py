from urllib.robotparser import RobotFileParser

from django.test import SimpleTestCase, override_settings

from cigardomtabaka_backend.urls import STAFF_PAGE_PREFIXES


class RobotsTests(SimpleTestCase):
    def test_anonymous_request_returns_plain_text_in_both_environments(self):
        for debug in (False, True):
            with self.subTest(debug=debug), override_settings(DEBUG=debug):
                response = self.client.get('/robots.txt')

                self.assertEqual(response.status_code, 200)
                self.assertEqual(response['Content-Type'], 'text/plain; charset=utf-8')
                self.assertContains(response, 'User-agent: *')
                self.assertNotContains(response, '<html')
                self.assertNotContains(response, '<style')
                self.assertFalse(response.cookies)

    def test_head_request_returns_plain_text_without_body(self):
        response = self.client.head('/robots.txt')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/plain; charset=utf-8')
        self.assertEqual(response.content, b'')

    def test_public_pages_are_crawlable_and_generic_private_paths_are_disallowed(self):
        response = self.client.get('/robots.txt')
        rules = RobotFileParser()
        rules.parse(response.content.decode().splitlines())

        allowed = (
            '/', '/ru/', '/en/', '/catalog', '/catalog?page=2',
            '/brand/cohiba', '/cigar/1/cohiba', '/ru/catalog', '/en/brand/cohiba',
            '/ru/cigar/1/cohiba', '/sitemap-storefront.xml',
            '/static/frontend/assets/app.js', '/media/cigars/cohiba.jpg',
            '/yandex_b944c5e69a8995a8.html',
            '/login', '/login/',
        )
        disallowed = (
            '/admin', '/admin/', '/admin/login/', '/api', '/api/brands/', '/p/customer-token',
        )
        for agent in ('YandexBot', 'Googlebot', 'ExampleBot'):
            for path in allowed:
                with self.subTest(agent=agent, allowed=path):
                    self.assertTrue(rules.can_fetch(agent, path))
            for path in disallowed:
                with self.subTest(agent=agent, disallowed=path):
                    self.assertFalse(rules.can_fetch(agent, path))

    def test_robots_does_not_publish_internal_business_paths(self):
        response = self.client.get('/robots.txt')
        for path in STAFF_PAGE_PREFIXES:
            with self.subTest(path=path):
                self.assertNotContains(response, path)

    @override_settings(STOREFRONT_ENABLED=True, STOREFRONT_ORIGIN='https://shop.example/')
    def test_robots_lists_only_the_public_storefront_sitemap(self):
        rules = RobotFileParser()
        rules.parse(self.client.get('/robots.txt').content.decode().splitlines())
        self.assertEqual(rules.site_maps(), ['https://shop.example/sitemap-storefront.xml'])
        with override_settings(STOREFRONT_ENABLED=False):
            self.assertNotContains(self.client.get('/robots.txt'), 'Sitemap:')
