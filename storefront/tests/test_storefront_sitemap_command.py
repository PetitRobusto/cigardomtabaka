import io
from unittest.mock import patch

from django.core.management import CommandError, call_command
from django.http import HttpResponse
from django.test import TestCase, override_settings


@override_settings(STOREFRONT_ORIGIN="https://store.example")
class StorefrontSitemapCommandTests(TestCase):
    module = "storefront.management.commands.check_storefront_sitemap"

    def setUp(self):
        self.pages = {
            "/": {"path": "/", "indexable": True},
            "/cigar/12/test-cigar": {"path": "/cigar/12/test-cigar", "indexable": True},
            # A translation fallback is served to visitors but intentionally noindex.
            "/en/cigar/12/test-cigar": {"path": "/en/cigar/12/test-cigar", "indexable": False},
        }
        self.locations = ["https://store.example/", "https://store.example/cigar/12/test-cigar"]
        self.xml_body = None

    def run_check(self, *required):
        from xml.etree.ElementTree import Element, SubElement, tostring

        root = Element("urlset", xmlns="http://www.sitemaps.org/schemas/sitemap/0.9")
        for location in self.locations:
            url = SubElement(root, "url")
            SubElement(url, "loc").text = location
        response = HttpResponse(self.xml_body or tostring(root), content_type="application/xml; charset=utf-8")
        client = type("FakeClient", (), {"get": lambda self, *args, **kwargs: response})()
        output = io.StringIO()
        with patch(self.module + ".build_pages", return_value=self.pages), \
             patch(self.module + ".Client", return_value=client):
            call_command("check_storefront_sitemap", *[
                arg for path in required for arg in ("--require-path", path)
            ], stdout=output)
        return output.getvalue()

    def test_current_indexable_pages_pass_and_noindex_fallback_is_excluded(self):
        self.assertIn("2 个", self.run_check())

    def test_newly_published_missing_url_fails(self):
        self.pages["/cigar/13/new-product"] = {"path": "/cigar/13/new-product", "indexable": True}
        with self.assertRaisesMessage(CommandError, "缺少 1 个可索引页面"):
            self.run_check()

    def test_unwanted_url_fails_even_when_it_looks_public(self):
        self.locations.append("https://store.example/en/cigar/12/test-cigar")
        with self.assertRaisesMessage(CommandError, "不应收录页面"):
            self.run_check()

    def test_required_path_must_be_published_and_indexable(self):
        with self.assertRaisesMessage(CommandError, "未发布或不可索引"):
            self.run_check("/en/cigar/12/test-cigar")
        self.assertIn("通过", self.run_check("/cigar/12/test-cigar"))

    def test_malformed_duplicate_and_off_origin_urls_fail(self):
        self.xml_body = b"<urlset>"
        with self.assertRaisesMessage(CommandError, "XML 无效"):
            self.run_check()
        self.xml_body = None

        self.locations.append("https://store.example/")
        with self.assertRaisesMessage(CommandError, "重复 URL"):
            self.run_check()
        self.locations.pop()

        self.locations[0] = "https://other.example/"
        with self.assertRaisesMessage(CommandError, "非规范或非本站 URL"):
            self.run_check()
