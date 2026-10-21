from urllib.robotparser import RobotFileParser

from django.test import SimpleTestCase, override_settings


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

    def test_public_pages_are_crawlable_and_internal_paths_are_disallowed(self):
        response = self.client.get('/robots.txt')
        rules = RobotFileParser()
        rules.parse(response.content.decode().splitlines())

        allowed = (
            '/', '/brand/cohiba', '/cigar/1/cohiba', '/prices',
            '/static/frontend/assets/app.js', '/media/cigars/cohiba.jpg',
            '/yandex_b944c5e69a8995a8.html',
        )
        disallowed = (
            '/admin/', '/api/brands/', '/privnote', '/privnote/api/access/',
            '/p/customer-token', '/login', '/inventory', '/inventory/purchases',
            '/sales', '/sales/customers', '/accounting', '/accounting/day1',
            '/accounting/reports/monthly', '/reports/monthly', '/help',
        )
        for agent in ('YandexBot', 'Googlebot', 'ExampleBot'):
            for path in allowed:
                with self.subTest(agent=agent, allowed=path):
                    self.assertTrue(rules.can_fetch(agent, path))
            for path in disallowed:
                with self.subTest(agent=agent, disallowed=path):
                    self.assertFalse(rules.can_fetch(agent, path))
