from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.http import Http404
from django.test import SimpleTestCase, override_settings


@override_settings(DEBUG=False, STOREFRONT_ENABLED=True)
class NotFoundResponseTests(SimpleTestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.static_root = Path(self.temporary.name)
        error_dir = self.static_root / "frontend" / "errors"
        error_dir.mkdir(parents=True)
        for locale, heading in (("zh", "ZH ERROR ARTIFACT"), ("ru", "RU ERROR ARTIFACT"), ("en", "EN ERROR ARTIFACT")):
            (error_dir / f"404-{locale}.html").write_text(
                f"<!doctype html><html lang='{locale}'><head><meta name='robots' content='noindex, nofollow'>"
                f"<title>{heading}</title></head><body><h1>{heading}</h1></body></html>",
                encoding="utf-8",
            )

    def test_html_404_uses_localized_artifact_and_keeps_http_404(self):
        with override_settings(STATIC_ROOT=self.static_root):
            with patch("storefront.views.build_pages", return_value={}):
                for path, marker in (
                    ("/missing", "ZH ERROR ARTIFACT"),
                    ("/zh/missing", "ZH ERROR ARTIFACT"),
                    ("/ru/missing", "RU ERROR ARTIFACT"),
                    ("/en/missing", "EN ERROR ARTIFACT"),
                    ("/russian/missing", "ZH ERROR ARTIFACT"),
                ):
                    with self.subTest(path=path):
                        response = self.client.get(path)
                        self.assertEqual(response.status_code, 404)
                        self.assertEqual(response["Content-Type"], "text/html; charset=utf-8")
                        self.assertEqual(response["X-Robots-Tag"], "noindex, nofollow")
                        self.assertEqual(response["Cache-Control"], "no-store")
                        self.assertContains(response, marker, status_code=404)
                        self.assertNotContains(response, "rel=\"canonical\"", status_code=404)

    def test_missing_artifact_uses_safe_localized_fallback_without_request_path(self):
        from cigardomtabaka_backend.error_views import not_found
        from django.test import RequestFactory

        request = RequestFactory().get("/ru/<script>alert(1)</script>")
        with patch("cigardomtabaka_backend.error_views._artifact_path", return_value=self.static_root / "absent.html"):
            response = not_found(request, Http404())

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response["X-Robots-Tag"], "noindex, nofollow")
        self.assertContains(response, "Страница не найдена", status_code=404)
        self.assertNotContains(response, "<script>alert(1)</script>", status_code=404)
        self.assertNotContains(response, "rel=\"canonical\"", status_code=404)

    def test_api_route_misses_and_storefront_page_misses_stay_json_404(self):
        with override_settings(STOREFRONT_ENABLED=False):
            for path in (
                "/api", "/api/no-such-endpoint",
                "/privnote/api", "/privnote/api/no-such-endpoint",
            ):
                with self.subTest(path=path):
                    response = self.client.get(path, HTTP_ACCEPT="application/json")
                    self.assertEqual(response.status_code, 404)
                    self.assertEqual(response["Content-Type"], "application/json")
                    self.assertEqual(response.json(), {"error": "not_found"})
                    self.assertEqual(response["X-Robots-Tag"], "noindex, nofollow")

        with patch("storefront.views.build_pages", return_value={}):
            response = self.client.get(
                "/api/storefront/page/?path=%2Fmissing",
                HTTP_ACCEPT="application/json",
            )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertEqual(response.json(), {"error": "not_found"})

    @override_settings(STOREFRONT_ENABLED=False)
    def test_valid_spa_route_keeps_existing_success_response(self):
        response = self.client.get("/login")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<div id="root"></div>')
