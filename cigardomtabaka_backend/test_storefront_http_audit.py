"""Exercise the read-only release smoke check without contacting production."""

from email.message import Message
import json
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from deploy.verify_storefront_http import PRIVATE_PATHS, ROBOTS_DISALLOWED_PATHS, Response, audit, fetch, public_indexable_url


class StorefrontHttpAuditTests(SimpleTestCase):
    origin = "https://shop.example"

    def payload(self, path):
        return json.dumps({'page': {
            'path': path, 'locale': 'ru' if path.startswith('/ru/') else 'en' if path.startswith('/en/') else 'zh',
            'kind': 'product' if '/cigar/' in path else 'brand' if '/brand/' in path else 'home',
            'view': 'catalog' if '/catalog' in path else None,
            'indexable': True,
        }})

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
                <body><h1>Store catalogue</h1><script id="store-data" type="application/json">{self.payload(path)}</script>
                <script src="/static/frontend/startup-loader.js?v=test" defer></script></body></html>''')
        locations = "".join(f"<url><loc>{url}</loc></url>" for url in pages)
        pages[self.origin + "/sitemap-storefront.xml"] = Response(200, {"content-type": "application/xml"},
            f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{locations}</urlset>')
        pages[self.origin + "/robots.txt"] = Response(200, {"content-type": "text/plain"},
            "User-agent: *\n" + "".join(f"Disallow: {path}\n" for path in ROBOTS_DISALLOWED_PATHS)
            + f"Sitemap: {self.origin}/sitemap-storefront.xml\n")
        pages[self.origin + '/login'] = Response(200, {'x-robots-tag': 'noindex, nofollow'}, 'login')
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
        self.assertEqual(len(report["checked_urls"]), 11)

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
                         {"invalid_sitemap", "robots_blocks_pages", "robots_blocks_resources", "robots_blocks_login_noindex"})

    def test_network_failures_are_reported_and_no_automatic_repair_is_attempted(self):
        requested = []

        def unavailable(url):
            requested.append(url)
            raise TimeoutError("Timed out")

        report = audit(self.origin, request=unavailable)
        self.assertFalse(report["ready"])
        self.assertEqual(len(requested), 7)
        self.assertTrue(all(issue["code"] == "request_failed" for issue in report["issues"]))

    def test_sitemap_rejects_private_filtered_and_noncanonical_urls(self):
        for path in (*PRIVATE_PATHS, '/catalog?q=test', '/catalog?page=1',
                     '/?page=2', '/ru/?page=3', '/en/?page=2',
                     '/en/cigar/1/cohiba?page=2', '/brand/cohiba#private',
                     '/brand/%2e%2e', '/unknown', '/en/catalog/'):
            with self.subTest(path=path):
                responses = self.responses()
                sitemap = responses[self.origin + '/sitemap-storefront.xml']
                sitemap.body = sitemap.body.replace('</urlset>', f'<url><loc>{self.origin}{path}</loc></url></urlset>')
                report = audit(self.origin, request=responses.__getitem__)
                self.assertFalse(report['ready'])
                self.assertEqual({issue['code'] for issue in report['issues']}, {'sitemap_nonpublic_url'})
        for path in ('/', '/en/', '/ru/', '/brand/cohiba?page=2', '/en/catalog?page=10', '/brand/cohiba', '/ru/cigar/12/cohiba-robustos'):
            with self.subTest(public_path=path):
                self.assertTrue(public_indexable_url(self.origin + path, self.origin))

    def test_robots_must_exclude_generic_private_paths_and_allow_rendering_resources(self):
        responses = self.responses()
        robots = responses[self.origin + '/robots.txt']
        robots.body = robots.body.replace('Disallow: /api/\n', '')
        robots.body += 'Disallow: /static/\n'
        report = audit(self.origin, request=responses.__getitem__)
        self.assertFalse(report['ready'])
        self.assertEqual({issue['code'] for issue in report['issues']},
                         {'robots_allows_private_paths', 'robots_blocks_resources'})

    def test_login_requires_readable_noindex(self):
        responses = self.responses()
        responses[self.origin + '/login'].headers = {}
        responses[self.origin + '/robots.txt'].body += 'Disallow: /login\n'
        report = audit(self.origin, request=responses.__getitem__)
        self.assertEqual({issue['code'] for issue in report['issues']},
                         {'login_indexable', 'robots_blocks_login_noindex'})

    def test_invalid_origins_and_off_site_sample_paths_fail_before_requests(self):
        def unexpected_request(url):
            self.fail(f"Unexpected request: {url}")

        for origin in ("file:///tmp/test", "https://user:password@shop.example", "https://shop.example/path"):
            with self.subTest(origin=origin), self.assertRaises(ValueError):
                audit(origin, request=unexpected_request)
        with self.assertRaises(ValueError):
            audit(self.origin, extra_paths=["//other.example/product"], request=unexpected_request)

    def representative_responses(self):
        pages = self.responses()
        locations = []
        for prefix in ('/', '/ru/', '/en/'):
            template = pages[self.origin + prefix]
            for suffix in ('catalog', 'brand/cohiba', 'cigar/99/cohiba-magicos'):
                url = self.origin + prefix + suffix
                pages[url] = Response(200, dict(template.headers), template.body.replace(
                    f'href="{self.origin}{prefix}"', f'href="{url}"').replace(
                        self.payload(prefix), self.payload(prefix + suffix)))
                locations.append(f'<url><loc>{url}</loc></url>')
            language = {'/': 'zh-CN', '/ru/': 'ru-RU', '/en/': 'en'}[prefix]
            pages[self.origin + prefix + '__seo_audit_missing_page__'] = Response(
                404, {'content-type': 'text/html'},
                f'<html lang="{language}"><title>404</title><h1>Page not found</h1></html>')
        pages[self.origin + '/sitemap-storefront.xml'].body = pages[
            self.origin + '/sitemap-storefront.xml'].body.replace('</urlset>', ''.join(locations) + '</urlset>')
        pages[self.origin + '/api/storefront/page/?path=%2F__seo_audit_missing_page__'] = Response(
            404, {'content-type': 'application/json'}, '{"error":"not_found"}')
        return pages

    def test_representatives_cover_all_languages_page_types_and_true_errors(self):
        responses = self.representative_responses()
        report = audit(self.origin, representative_pages=True, request=responses.__getitem__)
        self.assertTrue(report['ready'], report['issues'])
        for prefix in ('/', '/ru/', '/en/'):
            for suffix in ('', 'catalog', 'brand/cohiba', 'cigar/99/cohiba-magicos', '__seo_audit_missing_page__'):
                self.assertIn(self.origin + prefix + suffix, report['checked_urls'])
        self.assertEqual(report['sitemap_url_count'], 13)

    def test_representatives_follow_current_sitemap_after_a_listing_changes(self):
        responses = self.representative_responses()
        sitemap = responses[self.origin + '/sitemap-storefront.xml']
        sitemap.body = sitemap.body.replace('/cigar/99/cohiba-magicos', '/cigar/778/another-public-product')
        for prefix in ('/', '/ru/', '/en/'):
            previous = responses.pop(self.origin + prefix + 'cigar/99/cohiba-magicos')
            url = self.origin + prefix + 'cigar/778/another-public-product'
            responses[url] = Response(200, previous.headers, previous.body.replace(
                '/cigar/99/cohiba-magicos', '/cigar/778/another-public-product'))
        report = audit(self.origin, representative_pages=True, request=responses.__getitem__)
        self.assertTrue(report['ready'], report['issues'])
        self.assertFalse(any('/cigar/99/' in url for url in report['checked_urls']))

    def test_missing_language_product_sample_fails_instead_of_silently_skipping(self):
        responses = self.representative_responses()
        sitemap = responses[self.origin + '/sitemap-storefront.xml']
        sitemap.body = sitemap.body.replace(f'<url><loc>{self.origin}/en/cigar/99/cohiba-magicos</loc></url>', '')
        report = audit(self.origin, representative_pages=True, request=responses.__getitem__)
        self.assertFalse(report['ready'])
        self.assertEqual([(issue['code'], issue['detail']) for issue in report['issues']],
                         [('representative_page_missing', '/en/cigar/')])

    def test_representative_metadata_and_prerender_regressions_fail(self):
        responses = self.representative_responses()
        responses[self.origin + '/en/brand/cohiba'].headers['x-robots-tag'] = 'noindex'
        product = responses[self.origin + '/ru/cigar/99/cohiba-magicos']
        product.body = product.body.replace('id="store-data"', 'id="old-shell"').replace(
            'href="' + self.origin + '/ru/cigar/99/cohiba-magicos"', 'href="' + self.origin + '/ru/"')
        report = audit(self.origin, representative_pages=True, request=responses.__getitem__)
        self.assertEqual({issue['code'] for issue in report['issues']},
                         {'unexpected_noindex', 'canonical_mismatch', 'prerender_missing'})

    def test_empty_malformed_or_other_page_payload_cannot_pass_as_prerendered(self):
        path = '/ru/cigar/99/cohiba-magicos'
        for payload in ('{}', 'invalid JSON', self.payload('/ru/'),
                        self.payload(path).replace('"indexable": true', '"indexable": false')):
            with self.subTest(payload=payload):
                responses = self.representative_responses()
                product = responses[self.origin + path]
                product.body = product.body.replace(self.payload(path), payload)
                report = audit(self.origin, representative_pages=True, request=responses.__getitem__)
                self.assertEqual({issue['code'] for issue in report['issues']}, {'prerender_missing'})

    def test_home_and_catalog_payloads_must_use_their_correct_view(self):
        for path, replacement in (('/ru/catalog', None), ('/ru/', 'catalog')):
            with self.subTest(path=path):
                responses = self.representative_responses()
                payload = json.loads(self.payload(path))
                payload['page']['view'] = replacement
                response = responses[self.origin + path]
                response.body = response.body.replace(self.payload(path), json.dumps(payload))
                report = audit(self.origin, representative_pages=True, request=responses.__getitem__)
                self.assertEqual({issue['code'] for issue in report['issues']}, {'prerender_missing'})

    def test_localized_and_api_soft_404_regressions_fail(self):
        responses = self.representative_responses()
        responses[self.origin + '/ru/__seo_audit_missing_page__'].status = 200
        responses[self.origin + '/en/__seo_audit_missing_page__'].body = '<h1>Missing</h1>'
        responses[self.origin + '/api/storefront/page/?path=%2F__seo_audit_missing_page__'].body = '<html>SPA</html>'
        report = audit(self.origin, representative_pages=True, request=responses.__getitem__)
        self.assertEqual({issue['code'] for issue in report['issues']},
                         {'soft_404', 'localized_404_missing', 'api_404_contract'})

    def test_only_network_and_transient_statuses_are_retried(self):
        responses = self.representative_responses()
        attempts, sleeps = [], []
        def transient(url):
            attempts.append(url)
            if url == self.origin + '/' and attempts.count(url) == 1:
                raise TimeoutError('still restarting')
            if url == self.origin + '/' and attempts.count(url) == 2:
                return Response(503, {}, 'unavailable')
            return responses[url]
        report = audit(self.origin, representative_pages=True, request=transient,
                       retries=2, retry_delay=1, sleep=sleeps.append)
        self.assertTrue(report['ready'], report['issues'])
        self.assertEqual(sleeps, [1, 1])
        self.assertEqual(len(report['retries']), 2)
        self.assertEqual(attempts.count(self.origin + '/'), 3)

    def test_broken_metadata_and_404_are_not_retried_until_they_pass(self):
        responses = self.responses()
        responses[self.origin + '/ru/'].headers['x-robots-tag'] = 'noindex'
        responses[self.origin + '/en/'].status = 404
        requested = []
        def request(url):
            requested.append(url)
            return responses[url]
        report = audit(self.origin, request=request, retries=2, sleep=lambda delay: self.fail('unexpected sleep'))
        self.assertFalse(report['ready'])
        self.assertEqual(len(requested), len(set(requested)))
        self.assertEqual(report['retries'], [])

    def test_retry_exhaustion_and_invalid_limits(self):
        responses = self.responses()
        responses[self.origin + '/ru/'].status = 503
        report = audit(self.origin, request=responses.__getitem__, retries=2, sleep=lambda delay: None)
        self.assertFalse(report['ready'])
        self.assertEqual(len(report['retries']), 2)
        self.assertEqual({issue['code'] for issue in report['issues']}, {'page_status'})
        for options in ({'retries': 4}, {'retries': -1}, {'retry_delay': 11}, {'retry_delay': -1}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                audit(self.origin, **options)
