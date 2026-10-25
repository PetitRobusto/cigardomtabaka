import io
import json
from copy import deepcopy
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import SimpleTestCase, TestCase
from django.test.utils import CaptureQueriesContext

from cigars.models import Cigar
from storefront.management.commands.check_storefront_seo import audit_pages
from storefront.models import StorePage, StoreSettings, StoreTranslation


def page(path, *, kind="home", **changes):
    return {
        "path": path, "locale": "zh", "kind": kind,
        "title": "莫斯科雪茄门店", "description": "查看门店品牌和商品规格。",
        "body": "请联系门店确认到店安排和具体商品信息。",
        "site": {"name": "CigarDomTabaka", "address": "Moscow", "phone": "+7 999 000 0000",
                 "map_url": "https://maps.example/store", "photo": "/media/store.jpg", "hours": "10:00–18:00"},
        "pagination": {"page": 1}, "products": [], **changes,
    }


class SeoAuditTests(SimpleTestCase):
    def test_scoped_audit_blocks_missing_and_noindex_targets_without_requiring_home(self):
        pages = {'/brand/cohiba': page('/brand/cohiba', kind='brand', indexable=False)}
        result = self.audit(pages, paths=['/brand/cohiba', '/brand/missing'])
        self.assertFalse(result['ready'])
        self.assertEqual({row['code'] for row in result['issues']}, {'missing_target', 'target_not_indexable'})
        pages['/brand/cohiba']['indexable'] = True
        self.assertTrue(self.audit(pages, paths=['/brand/cohiba'])['ready'])

    def test_visible_products_count_as_internal_links(self):
        target = '/cigar/1/model'
        for field in ('products', 'latest_products'):
            pages = {'/': page('/'), '/brand/cohiba': page('/brand/cohiba', kind='brand', **{field: [{'path': target}]}),
                     target: page(target, kind='product', product={'name': 'Model'})}
            self.assertNotIn('orphan_product', {row['code'] for row in self.audit(pages)['issues']})

    def audit(self, pages, **kwargs):
        return audit_pages(pages, details_verified=True, **kwargs)

    def test_complete_content_passes_and_input_is_unchanged(self):
        pages = {"/": page("/")}
        before = deepcopy(pages)
        report = self.audit(pages)
        self.assertTrue(report["ready"])
        self.assertEqual(report["issues"], [])
        self.assertEqual(pages, before)

    def test_all_three_preview_markers_are_blockers(self):
        for marker in ("【测试预览】", "TEST PREVIEW（合成占位）", "[ТЕСТОВЫЙ ПРЕДПРОСМОТР]"):
            with self.subTest(marker=marker):
                report = self.audit({"/": page("/", body=marker)})
                self.assertFalse(report["ready"])
                self.assertEqual(report["issues"][0]["code"], "placeholder_content")
                self.assertEqual(report["issues"][0]["samples"], [{"path": "/", "fields": ["body"]}])

    def test_missing_metadata_and_home_body_block_but_missing_shop_details_do_not(self):
        report = self.audit({"/": page("/", title=" ", body="", site={})})
        self.assertFalse(report["ready"])
        codes = {issue["code"] for issue in report["issues"]}
        self.assertEqual(codes, {"missing_metadata", "missing_home_body", "missing_store_details"})
        warnings_only = audit_pages({"/": page("/", site={})}, details_verified=False)
        self.assertTrue(warnings_only["ready"])
        self.assertEqual(warnings_only["counts"]["error"], 0)

    def test_empty_brand_and_unlinked_directory_product_are_warnings(self):
        paths = {
            "/": page("/"),
            "/brand/cohiba": page("/brand/cohiba", kind="brand", body=""),
            "/cigar/1/robustos": page("/cigar/1/robustos", kind="product", product={"name": "Robustos"}),
        }
        report = self.audit(paths)
        self.assertTrue(report["ready"])
        codes = {issue["code"] for issue in report["issues"]}
        self.assertEqual(codes, {"empty_brand", "orphan_product"})

    def test_optional_brand_body_does_not_require_an_introduction(self):
        paths = {"/": page("/"), "/brand/cohiba": page("/brand/cohiba", kind="brand", body="", total_products=1)}
        self.assertEqual(self.audit(paths)["issues"], [])

    def test_noindex_list_does_not_make_indexable_product_discoverable(self):
        product_path = "/en/cigar/1/robustos"
        paths = {
            "/": page("/"),
            product_path: page(product_path, locale="en", kind="product", indexable=True),
            "/en/catalog": page("/en/catalog", locale="en", view="catalog", indexable=False,
                                translation_complete=False, products=[{"path": product_path}]),
        }
        report = self.audit(paths)
        orphan = next(issue for issue in report["issues"] if issue["code"] == "orphan_product")
        self.assertEqual(orphan["samples"], [{"path": product_path, "fields": []}])
        paths["/en/catalog"]["indexable"] = True
        paths["/en/catalog"]["translation_complete"] = True
        self.assertNotIn("orphan_product", {issue["code"] for issue in self.audit(paths)["issues"]})

    def test_fallback_pages_are_counted_and_warned_without_orphan_or_blocker(self):
        product_path = "/ru/cigar/1/robustos"
        paths = {
            "/": page("/", indexable=True, translation_complete=True),
            product_path: page(product_path, locale="ru", kind="product", indexable=False, translation_complete=False),
            "/ru/catalog": page("/ru/catalog", locale="ru", view="catalog", indexable=False, translation_complete=False),
            "/ru/catalog?page=2": page("/ru/catalog?page=2", locale="ru", view="catalog", indexable=False,
                                       translation_complete=False, pagination={"page": 2}),
        }
        report = self.audit(paths)
        self.assertTrue(report["ready"])
        self.assertEqual(report["page_count"], 4)
        self.assertEqual(report["indexable_page_count"], 1)
        self.assertEqual(report["locales"], {
            "ru": {"page_count": 3, "indexable_page_count": 0, "fallback_page_count": 3},
            "zh": {"page_count": 1, "indexable_page_count": 1, "fallback_page_count": 0},
        })
        self.assertEqual([issue["code"] for issue in report["issues"]], ["translation_fallback"])
        self.assertEqual(report["issues"][0]["count"], 3)

    def test_product_linked_on_second_page_is_discoverable_but_filtered_link_does_not_count(self):
        product_path = "/cigar/1/robustos"
        paths = {
            product_path: page(product_path, kind="product", product={"name": "Robustos"}),
            "/catalog?page=2": page("/catalog?page=2", view="catalog", pagination={"page": 2},
                                    products=[{"path": product_path}]),
        }
        self.assertNotIn("orphan_product", {issue["code"] for issue in self.audit(paths)["issues"]})
        paths["/catalog?page=2"]["filters"] = {"brand": "cohiba"}
        self.assertIn("orphan_product", {issue["code"] for issue in self.audit(paths)["issues"]})

    def test_deterministic_counts_and_bounded_samples(self):
        paths = {f"/brand/{i}": page(f"/brand/{i}", kind="brand", body="") for i in range(10)}
        report = self.audit(paths, sample_limit=2)
        issue = next(issue for issue in report["issues"] if issue["code"] == "empty_brand")
        self.assertEqual(issue["count"], 10)
        self.assertEqual(len(issue["samples"]), 2)
        self.assertEqual(report, self.audit(dict(reversed(list(paths.items()))), sample_limit=2))


class SeoCommandTests(TestCase):
    def test_existing_legacy_product_does_not_replace_unpublished_home(self):
        Cigar.objects.create(brand="Cohiba", english_name="Robustos")
        StoreTranslation.objects.create(kind="home", key="home", locale="zh", title="门店",
                                        description="门店简介", body="待核实介绍", published=False)
        output = io.StringIO()
        with self.assertRaises(CommandError):
            call_command("check_storefront_seo", json=True, strict=True, stdout=output)
        report = json.loads(output.getvalue())
        self.assertGreater(report["page_count"], 0)
        self.assertIn("missing_home", {issue["code"] for issue in report["issues"]})

    def test_command_reads_database_without_writes_or_publishing(self):
        StoreSettings.objects.create(details_verified=True)
        StoreTranslation.objects.create(kind="home", key="home", locale="zh", title="门店",
                                        description="门店简介", body="核实后的门店介绍", published=True)
        output = io.StringIO()
        with CaptureQueriesContext(connection) as queries:
            call_command("check_storefront_seo", json=True, strict=True, stdout=output)
        report = json.loads(output.getvalue())
        self.assertTrue(report["ready"])
        self.assertGreater(report["page_count"], 0)
        writes = [query["sql"] for query in queries if query["sql"].lstrip().split()[0].upper()
                  in {"INSERT", "UPDATE", "DELETE", "REPLACE", "CREATE", "ALTER", "DROP"}]
        self.assertEqual(writes, [])
        self.assertFalse(StorePage.objects.exists())
        self.assertTrue(StoreTranslation.objects.get(kind="home").published)

    def test_strict_json_outputs_report_before_failing(self):
        output = io.StringIO()
        with patch("storefront.management.commands.check_storefront_seo.build_pages", return_value={}), \
                self.assertRaises(CommandError):
            call_command("check_storefront_seo", json=True, strict=True, stdout=output)
        report = json.loads(output.getvalue())
        self.assertFalse(report["ready"])
        self.assertEqual(report["schema_version"], 1)
        self.assertIn("no_pages", {issue["code"] for issue in report["issues"]})

    def test_strict_mode_allows_intentional_translation_fallback(self):
        paths = {"/": page("/"), "/ru/": page("/ru/", locale="ru", indexable=False, translation_complete=False)}
        output = io.StringIO()
        StoreSettings.objects.create(details_verified=True)
        with patch("storefront.management.commands.check_storefront_seo.build_pages", return_value=paths):
            call_command("check_storefront_seo", json=True, strict=True, stdout=output)
        report = json.loads(output.getvalue())
        self.assertTrue(report["ready"])
        self.assertEqual(report["counts"], {"error": 0, "warning": 1})

    def test_default_reports_blockers_without_failure_and_invalid_sample_limit_fails(self):
        with patch("storefront.management.commands.check_storefront_seo.build_pages", return_value={}):
            call_command("check_storefront_seo", stdout=io.StringIO())
        with self.assertRaises(CommandError):
            call_command("check_storefront_seo", sample_limit=0, stdout=io.StringIO())
