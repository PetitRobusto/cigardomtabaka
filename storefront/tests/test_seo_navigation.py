from decimal import Decimal

from django.test import TestCase, override_settings

from cigars.models import Brand, Cigar
from cigars.tests.inventory_fixtures import create_purchase_batch
from storefront.catalog import allowed_payload, build_pages, public_dependencies
from storefront.models import StoreTranslation, ProductListing, StorePage


@override_settings(STOREFRONT_ENABLED=True)
class BrandLandingNavigationTests(TestCase):
    def setUp(self):
        self.brand = Brand.objects.create(english_name="Cohiba", name="高希霸", slug="cohiba")
        self.cigar = Cigar.objects.create(brand="Cohiba", english_name="Genios", name="天才")
        ProductListing.objects.create(cigar=self.cigar, published=True)
        create_purchase_batch(
            source="opening", cigar=self.cigar, quantity=25, remaining=0,
            physical_remaining=0, box_size=25, unit_cost_cny=Decimal("1"),
        )
        for locale in ("zh", "ru", "en"):
            for kind, key, title in (("home", "home", "CigarDomTabaka"),
                                     ("brand", "cohiba", "Cohiba"),
                                     ("product", str(self.cigar.pk), "Genios")):
                StoreTranslation.objects.create(
                    kind=kind, key=key, locale=locale, title=title,
                    description="Reviewed description", body="Reviewed body", published=True,
                )

    def test_each_language_links_to_its_indexable_brand_landing_page(self):
        pages = build_pages()
        for locale, prefix in (("zh", ""), ("ru", "/ru"), ("en", "/en")):
            home = pages[prefix + "/"]
            link = home["navigation"]["brands"][0]
            self.assertEqual(link["path"], prefix + "/brand/cohiba")
            target = pages[link["path"]]
            self.assertEqual(target["locale"], locale)
            self.assertEqual(target["kind"], "brand")
            self.assertTrue(allowed_payload(home))
            self.assertTrue(allowed_payload(target))
            self.assertEqual(target["products"][0]["id"], self.cigar.pk)
            # Retain the reviewed name in visible product cards while enriching metadata.
            product = pages[f"{prefix}/cigar/{self.cigar.pk}/cohiba-genios"]
            self.assertEqual(product["title"], "Genios")
            self.assertEqual(product["product"]["name"], "Genios")
            self.assertIn("高希霸" if locale == "zh" else "Cohiba", product["seo_title"])
            self.assertIn("Genios", product["seo_title"])

    def test_revoked_translation_invalidates_cached_canonical_brand_navigation(self):
        cached = build_pages()["/ru/"]
        StoreTranslation.objects.filter(kind="brand", key="cohiba", locale="ru").update(published=False)
        self.assertFalse(allowed_payload(cached))
        pages = build_pages()
        navigation_brand = pages["/ru/"]["navigation"]["brands"][0]
        self.assertEqual(navigation_brand["name"], "Cohiba")
        self.assertFalse(navigation_brand["translation_complete"])
        self.assertEqual(navigation_brand["content_locale"], "en")
        self.assertFalse(pages["/ru/"]["indexable"])
        self.assertIn("/ru/brand/cohiba", pages)
        self.assertFalse(pages["/ru/brand/cohiba"]["indexable"])

    def test_hreflang_only_targets_final_indexable_pages_when_related_translation_is_missing(self):
        # The main Russian product is translated, but its related stock is not.
        related = Cigar.objects.create(brand="Cohiba", english_name="Siglo II")
        create_purchase_batch(source="opening", cigar=related, quantity=25, remaining=25,
                              physical_remaining=25, box_size=25, unit_cost_cny=Decimal("1"))
        ProductListing.objects.create(cigar=related, published=True)
        StoreTranslation.objects.create(kind="product", key=str(related.pk), locale="en",
                                        title="Siglo II", description="Reviewed description",
                                        body="Reviewed body", published=True)
        pages = build_pages()
        path = f"/cigar/{self.cigar.pk}/cohiba-genios"
        self.assertFalse(pages["/ru" + path]["indexable"])
        self.assertNotIn("ru", {row["locale"] for row in pages[path]["alternates"]})
        dependencies = public_dependencies()
        for current_path, payload in pages.items():
            with self.subTest(path=current_path):
                self.assertTrue(allowed_payload(payload, dependencies))
                for alternate in payload["alternates"]:
                    self.assertTrue(pages[alternate["path"]]["indexable"])

    def test_missing_english_brand_translation_is_browsable_but_not_indexable(self):
        StoreTranslation.objects.filter(kind="brand", key="cohiba", locale="en").update(published=False)
        pages = build_pages()
        dependencies = public_dependencies()
        for path in ("/en/", "/en/catalog", "/en/brand/cohiba",
                     f"/en/cigar/{self.cigar.pk}/cohiba-genios"):
            with self.subTest(path=path):
                payload = pages[path]
                self.assertFalse(payload["indexable"])
                self.assertTrue(allowed_payload(payload, dependencies))
                self.assertNotIn("en", {row["locale"] for row in payload["alternates"]})
        fallback = pages[f"/en/cigar/{self.cigar.pk}/cohiba-genios"]
        self.assertEqual(fallback["product"]["brand"], "Cohiba")
        StorePage.objects.create(path=fallback["path"], payload=fallback, rendered_payload=fallback,
                                 desired_hash="fallback", rendered_hash="fallback",
                                 html="<h1>Genios</h1>")
        response = self.client.get(fallback["path"])
        self.assertEqual(response.status_code, 200)
        self.assertIn("noindex", response["X-Robots-Tag"])
        self.assertNotContains(self.client.get("/sitemap-storefront.xml"), fallback["path"])
        StoreTranslation.objects.filter(kind="brand", key="cohiba", locale="en").update(published=True)
        self.assertFalse(allowed_payload(fallback))
        published = build_pages()[fallback["path"]]
        self.assertTrue(published["indexable"])
        self.assertTrue(allowed_payload(published))
