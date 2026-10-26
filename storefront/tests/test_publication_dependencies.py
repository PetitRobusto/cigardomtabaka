from copy import deepcopy
from decimal import Decimal
from html import escape
from xml.etree.ElementTree import fromstring

from django.test import TestCase, override_settings

from cigars.models import Brand, Cigar, PurchaseBatch
from cigars.tests.inventory_fixtures import create_purchase_batch
from storefront.catalog import allowed_payload, build_pages, public_dependencies, semantic_hash
from storefront.models import ProductListing, StorePage, StoreSettings, StoreTranslation
from storefront.public_details import PUBLIC_DETAILS


@override_settings(STOREFRONT_ENABLED=True, STOREFRONT_ORIGIN="http://testserver")
class TranslationPublicationDependenciesTests(TestCase):
    def setUp(self):
        self.brand = Brand.objects.create(english_name="Test Brand", name="历史品牌")
        self.cigar = Cigar.objects.create(
            brand=self.brand.english_name, english_name="Test Cigar", name="历史商品",
        )
        create_purchase_batch(
            source=PurchaseBatch.Source.OPENING, cigar=self.cigar,
            quantity=25, remaining=25, physical_remaining=25, box_size=25,
            unit_cost_cny=Decimal("1.00"),
        )
        ProductListing.objects.create(cigar=self.cigar, published=True)
        self.home = self.translation("home", "home")
        self.product_path = f"/cigar/{self.cigar.pk}/test-brand-test-cigar"
        self.brand_path = f"/brand/{self.brand.slug}"

    def translation(self, kind, key, **overrides):
        return StoreTranslation.objects.create(
            kind=kind, key=str(key), locale="zh", title=f"审核标题 {kind}",
            description=f"审核摘要 {kind}", body=f"审核正文 {kind}",
            published=True, **overrides,
        )

    def cache(self, path, payload=None):
        payload = payload if payload is not None else build_pages()[path]
        text = [payload["title"], payload["body"], payload["site"].get("hours", "")]
        text.extend(product["name"] for product in payload["products"])
        if payload["product"]:
            text.append(payload["product"]["name"])
        text.extend(brand["name"] for brand in payload["brands"])
        StorePage.objects.update_or_create(path=path, defaults={
            "active": True, "payload": payload, "rendered_payload": payload,
            "desired_hash": semantic_hash(payload), "rendered_hash": semantic_hash(payload),
            "html": "<html><body>" + escape(" / ".join(text)) + "</body></html>",
        })
        return payload

    def sitemap_paths(self):
        response = self.client.get("/sitemap-storefront.xml")
        self.assertEqual(response.status_code, 200)
        return {
            element.text.removeprefix("http://testserver")
            for element in fromstring(response.content).iter()
            if element.tag.endswith("}loc")
        }

    def assert_unservable(self, paths, *, status=503):
        for path in paths:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, status)
                self.assertNotIn("审核正文".encode(), response.content)
                self.assertNotIn(path, self.sitemap_paths())

    def test_sitemap_ignores_internal_unknown_filtered_and_unrendered_cache_rows(self):
        public_paths = {'/', self.brand_path, self.product_path}
        for path in public_paths:
            self.cache(path)
        # Even active cached HTML is insufficient: the URL must be a current
        # public catalogue page, never a staff page or a customer secret link.
        payload = build_pages()['/']
        for path in ('/admin/', '/login', '/library', '/prices', '/inventory',
                     '/sales', '/accounting', '/reports/monthly', '/help',
                     '/api/brands/', '/privnote', '/p/customer-secret',
                     '/unknown', '/?q=test', self.brand_path + '?box=25'):
            self.cache(path, deepcopy(payload))
        self.assertEqual(self.sitemap_paths(), public_paths)
        for missing_field in ('active', 'html', 'rendered_hash'):
            with self.subTest(missing_field=missing_field):
                self.cache(self.product_path)
                StorePage.objects.filter(path=self.product_path).update(
                    **{missing_field: False if missing_field == 'active' else ''})
                self.assertEqual(self.sitemap_paths(), public_paths - {self.product_path})

    def test_product_translation_revocation_hides_detail_and_visible_cards_until_rebuilt(self):
        translation = self.translation("product", self.cigar.pk)
        paths = [self.product_path, self.brand_path, "/"]
        for path in paths:
            self.cache(path)
            self.assertContains(self.client.get(path), translation.title)
            self.assertIn(path, self.sitemap_paths())

        translation.published = False
        translation.save(update_fields=["published"])
        self.assert_unservable(paths)
        for path in paths:
            payload = self.cache(path)
            self.assertNotIn(["product", str(self.cigar.pk), "zh"], payload["translation_dependencies"])
            response = self.client.get(path)
            self.assertContains(response, self.cigar.name)
            self.assertNotContains(response, translation.title)
            self.assertIn(path, self.sitemap_paths())

    def test_brand_translation_deletion_hides_brand_body_and_home_index_until_rebuilt(self):
        translation = self.translation("brand", self.brand.slug)
        paths = [self.brand_path, "/"]
        for path in paths:
            self.cache(path)
            self.assertContains(self.client.get(path), translation.title)
        translation.delete()
        self.assert_unservable(paths)
        for path in paths:
            self.cache(path)
            self.assertContains(self.client.get(path), self.brand.name)
            self.assertIn(path, self.sitemap_paths())

    def test_home_translation_hours_revocation_hides_other_pages_until_hours_removed(self):
        StoreSettings.objects.create(details_verified=True)
        self.home.hours = "Reviewed opening hours"
        self.home.save(update_fields=["hours"])
        for path in ["/", self.product_path, self.brand_path]:
            payload = self.cache(path)
            self.assertIn(["home", "home", "zh"], payload["translation_dependencies"])
            self.assertContains(self.client.get(path), self.home.hours)
        self.home.published = False
        self.home.save(update_fields=["published"])
        self.assert_unservable(["/"], status=404)
        self.assert_unservable([self.product_path, self.brand_path])
        for path in [self.product_path, self.brand_path]:
            payload = self.cache(path)
            self.assertEqual(payload["site"]["hours"], PUBLIC_DETAILS["hours"]["zh"])
            self.assertNotContains(self.client.get(path), self.home.hours)
            self.assertIn(path, self.sitemap_paths())

    def test_never_translated_legacy_pages_remain_public_without_translation_dependencies(self):
        for path in [self.product_path, self.brand_path]:
            payload = self.cache(path)
            self.assertEqual(payload["translation_dependencies"], [])
            self.assertEqual(self.client.get(path).status_code, 200)
        self.home.delete()
        for path in [self.product_path, self.brand_path]:
            self.assertEqual(self.client.get(path).status_code, 200)
            self.assertIn(path, self.sitemap_paths())

    def test_old_or_malformed_dependency_metadata_is_rejected_until_rebuilt(self):
        original = build_pages()[self.product_path]
        for invalid in ["missing", None, {}, ["bad"], [["product", self.cigar.pk, "zh"]]]:
            with self.subTest(metadata=invalid):
                payload = deepcopy(original)
                if invalid == "missing":
                    payload.pop("translation_dependencies")
                else:
                    payload["translation_dependencies"] = invalid
                self.cache(self.product_path, payload)
                self.assert_unservable([self.product_path])
        self.cache(self.product_path)
        self.assertEqual(self.client.get(self.product_path).status_code, 200)

    def test_whitespace_invalidates_each_required_reviewed_field_in_both_read_paths(self):
        translation = self.translation("product", self.cigar.pk)
        for field in ["title", "description", "body"]:
            with self.subTest(field=field):
                original = getattr(translation, field)
                self.cache(self.product_path)
                setattr(translation, field, " \n\t ")
                translation.save(update_fields=[field])
                dependency = ("product", str(self.cigar.pk), "zh")
                self.assertNotIn(dependency, public_dependencies()["translations"])
                self.assert_unservable([self.product_path])
                current = build_pages()[self.product_path]
                self.assertEqual(current["product"]["name"], self.cigar.name)
                self.assertNotIn(list(dependency), current["translation_dependencies"])
                self.cache(self.product_path, current)
                self.assertEqual(self.client.get(self.product_path).status_code, 200)
                setattr(translation, field, original)
                translation.save(update_fields=[field])

    def test_paginated_page_only_depends_on_translations_it_actually_shows(self):
        cigars = Cigar.objects.bulk_create([
            Cigar(brand=self.brand.english_name, english_name=f"A item {number:02}")
            for number in range(24)
        ])
        ProductListing.objects.bulk_create([ProductListing(cigar=cigar, published=True) for cigar in cigars])
        for cigar in cigars:
            create_purchase_batch(
                source=PurchaseBatch.Source.OPENING, cigar=cigar,
                quantity=1, remaining=0, physical_remaining=0, box_size=None,
                unit_cost_cny=Decimal("1.00"),
            )
        translation = self.translation("product", self.cigar.pk)
        translation.title = "Z translated item"
        translation.save(update_fields=["title"])
        first_path = self.brand_path
        second_path = self.brand_path + "?page=2"
        first = self.cache(first_path)
        second = self.cache(second_path)
        dependency = ["product", str(self.cigar.pk), "zh"]
        shown_path = next(path for path, payload in ((first_path, first), (second_path, second))
                          if any(item["id"] == self.cigar.pk for item in payload["products"]))
        hidden_path, hidden = (second_path, second) if shown_path == first_path else (first_path, first)
        shown = first if shown_path == first_path else second
        self.assertIn(dependency, shown["translation_dependencies"])
        self.assertNotIn(dependency, hidden["translation_dependencies"])
        self.assertEqual(shown["translation_dependencies"], sorted(shown["translation_dependencies"]))
        self.assertEqual(len(shown["translation_dependencies"]), len({tuple(row) for row in shown["translation_dependencies"]}))
        translation.published = False
        translation.save(update_fields=["published"])
        self.assertTrue(allowed_payload(hidden))
        self.assertEqual(self.client.get(hidden_path).status_code, 200)
        self.assert_unservable([shown_path])
