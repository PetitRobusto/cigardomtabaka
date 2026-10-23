"""Exercise the read-only release smoke check without contacting production."""

from email.message import Message
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from deploy.verify_storefront_http import PRIVATE_PATHS, Response, audit, fetch, public_indexable_url


class StorefrontHttpAuditTests(SimpleTestCase):
    origin = "https://shop.example"

    def test_repeated_robot_headers_preserve_noindex_and_fail_audit(self):
        responses = self.responses()
        raw = MagicMock()
        raw.__enter__.return_value = raw
        raw.code = 200
        raw.headers = Message()
        raw.headers['Content-Type'] = 'text/html'
        raw.headers['X-Robots-Tag'] = 'noindex'
        raw.headers['X-Robots-Tag'] = 'nosnippet'
        raw.read.return_value = responses[self.origin + '/'].body.encode()
        with patch('deploy.verify_storefront_http.build_opener') as opener:
            opener.return_value.open.return_value = raw
            response = fetch(self.origin + '/')
        self.assertEqual(response.headers['x-robots-tag'], 'noindex, nosnippet')
        responses[self.origin + '/'] = response
        report = audit(self.origin, request=responses.__getitem__)
        self.assertFalse(report['ready'])
        self.assertEqual({issue['code'] for issue in report['issues']}, {'unexpected_noindex'})

    def responses(self):
        pages = {}
        for path, language in (("/", "zh-CN"), ("/ru/", "ru-RU"), ("/en/", "en"), ("/catalog?page=2", "zh-CN")):
            pages[self.origin + path] = Response(200, {"content-type": "text/html; charset=utf-8"}, f'''
                <html lang="{language}"><head><title>Store catalogue</title>
                <meta name="description" content="Reviewed catalogue">
                <link rel="canonical" href="{self.origin}{path}">
                <link rel="icon" href="/static/frontend/favicon-96.png"></head>
                <body><h1>Store catalogue</h1><script id="store-data" type="application/json">{{}}</script>
                <script src="/static/frontend/startup-loader.js?v=test" defer></script></body></html>''')
        locations = "".join(f"<url><loc>{url}</loc></url>" for url in pages)
        pages[self.origin + "/sitemap-storefront.xml"] = Response(200, {"content-type": "application/xml"},
            f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{locations}</urlset>')
        pages[self.origin + "/robots.txt"] = Response(200, {"content-type": "text/plain"},
            "User-agent: *\n" + "".join(f"Disallow: {path}\n" for path in PRIVATE_PATHS)
            + f"Sitemap: {self.origin}/sitemap-storefront.xml\n")
        pages[self.origin + "/static/frontend/favicon-96.png"] = Response(200, {"content-type": "image/png"}, "image")
        pages[self.origin + "/static/frontend/startup-loader.js?v=test"] = Response(200, {"content-type": "application/javascript"}, "script")
        pages[self.origin + "/__seo_audit_missing_page__"] = Response(404, {"content-type": "text/html"}, "missing")
        pages["https://www.shop.example/"] = Response(301, {"location": self.origin + "/"}, "")
        return pages

    def test_complete_public_site_passes_with_an_explicit_paginated_sample(self):
        responses = self.responses()
        report = audit(self.origin, www_origin="https://www.shop.example", extra_paths=["/catalog?page=2"], request=responses.__getitem__)
        self.assertTrue(report["ready"])
        self.assertEqual(report["issues"], [])
        self.assertEqual(report["sitemap_url_count"], 4)
        self.assertEqual(len(report["checked_urls"]), 10)

    def test_old_spa_with_200_for_every_url_cannot_pass_release_checks(self):
        old_spa = Response(200, {"content-type": "text/html"}, '<html><head><title>Store</title></head><body><div id="root"></div></body></html>')
        report = audit(self.origin, www_origin="https://www.shop.example", request=lambda url: old_spa)
        codes = {issue["code"] for issue in report["issues"]}
        self.assertFalse(report["ready"])
        self.assertTrue({"prerender_missing", "canonical_mismatch", "h1_missing", "invalid_sitemap", "robots_sitemap_missing", "soft_404", "www_redirect"} <= codes)

    def test_canonical_language_indexing_and_resource_errors_are_reported_together(self):
        responses = self.responses()
        ru = responses[self.origin + "/ru/"]
        ru.body = ru.body.replace('lang="ru-RU"', 'lang="en"').replace(self.origin + "/ru/", "https://preview.example/ru/")
        ru.headers["x-robots-tag"] = "noindex, nofollow"
        responses[self.origin + "/static/frontend/startup-loader.js?v=test"] = Response(200, {"content-type": "text/html"}, "old SPA")
        report = audit(self.origin, request=responses.__getitem__)
        self.assertEqual({issue["code"] for issue in report["issues"]},
                         {"canonical_mismatch", "language_mismatch", "unexpected_noindex", "resource_response"})

    def test_cross_origin_sitemap_and_crawler_block_are_rejected(self):
        responses = self.responses()
        sitemap = responses[self.origin + "/sitemap-storefront.xml"]
        sitemap.body = sitemap.body.replace(self.origin + "/en/", "https://preview.example/en/")
        robots = responses[self.origin + "/robots.txt"]
        robots.body = robots.body.replace("Disallow: /api/", "Disallow: /")
        report = audit(self.origin, request=responses.__getitem__)
        self.assertFalse(report["ready"])
        self.assertEqual({issue["code"] for issue in report["issues"]},
                         {"invalid_sitemap", "robots_blocks_pages", "robots_blocks_resources"})

    def test_network_failures_are_reported_and_no_automatic_repair_is_attempted(self):
        requested = []

        def unavailable(url):
            requested.append(url)
            raise TimeoutError("Timed out")

        report = audit(self.origin, request=unavailable)
        self.assertFalse(report["ready"])
        self.assertEqual(len(requested), 6)
        self.assertTrue(all(issue["code"] == "request_failed" for issue in report["issues"]))

    def test_sitemap_rejects_private_filtered_and_noncanonical_urls(self):
        for path in (*PRIVATE_PATHS, '/catalog?q=test', '/catalog?page=1',
                     '/en/cigar/1/cohiba?page=2', '/brand/cohiba#private',
                     '/brand/%2e%2e', '/unknown', '/en/catalog/'):
            with self.subTest(path=path):
                responses = self.responses()
                sitemap = responses[self.origin + '/sitemap-storefront.xml']
                sitemap.body = sitemap.body.replace('</urlset>', f'<url><loc>{self.origin}{path}</loc></url></urlset>')
                report = audit(self.origin, request=responses.__getitem__)
                self.assertFalse(report['ready'])
                self.assertEqual({issue['code'] for issue in report['issues']}, {'sitemap_nonpublic_url'})
        for path in ('/', '/en/', '/ru/', '/?page=2', '/en/catalog?page=10', '/brand/cohiba', '/ru/cigar/12/cohiba-robustos'):
            with self.subTest(public_path=path):
                self.assertTrue(public_indexable_url(self.origin + path, self.origin))

    def test_robots_must_exclude_staff_and_allow_rendering_resources(self):
        responses = self.responses()
        robots = responses[self.origin + '/robots.txt']
        robots.body = robots.body.replace('Disallow: /library\n', '')
        robots.body += 'Disallow: /static/\n'
        report = audit(self.origin, request=responses.__getitem__)
        self.assertFalse(report['ready'])
        self.assertEqual({issue['code'] for issue in report['issues']},
                         {'robots_allows_private_paths', 'robots_blocks_resources'})

    def test_invalid_origins_and_off_site_sample_paths_fail_before_requests(self):
        def unexpected_request(url):
            self.fail(f"Unexpected request: {url}")

        for origin in ("file:///tmp/test", "https://user:password@shop.example", "https://shop.example/path"):
            with self.subTest(origin=origin), self.assertRaises(ValueError):
                audit(origin, request=unexpected_request)
        with self.assertRaises(ValueError):
            audit(self.origin, extra_paths=["//other.example/product"], request=unexpected_request)
