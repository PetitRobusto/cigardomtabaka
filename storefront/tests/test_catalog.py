from datetime import timedelta
from decimal import Decimal
import json

from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone

from cigars.models import Brand, Cigar, CigarImage, CigarPrice, PurchaseBatch
from cigars.tests.inventory_fixtures import create_purchase_batch
from price_tracker.models import ExchangeRate

from storefront.catalog import _product_data, allowed_payload, build_pages, resolve_path, search_products, semantic_hash
from storefront.models import ProductListing, StorePage, StoreSettings, StoreTranslation
from storefront.views import page, page_data, rates


@override_settings(STOREFRONT_ENABLED=True)
class StorefrontCatalogTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.brand = Brand.objects.create(english_name="Test Brand", name="测试品牌")
        self.cigar = Cigar.objects.create(
            brand=self.brand.english_name,
            english_name="Test Cigar",
            name="测试雪茄",
            vitola="Robusto",
            vitola_cn="罗布图",
            length=124,
            ring_gauge=50,
            image_url="https://images.example/cigar.jpg",
        )
        self.batch = create_purchase_batch(
            source=PurchaseBatch.Source.OPENING,
            cigar=self.cigar,
            quantity=50,
            remaining=50,
            physical_remaining=50,
            box_size=25,
            unit_cost_cny=Decimal("999.00"),
        )
        self.price = CigarPrice.objects.create(
            cigar=self.cigar,
            box_size=25,
            wholesale_price=100,
            retail_price=200,
            retail_price_rub=Decimal("12345.67"),
        )

    def add_home_translation(self, locale="zh"):
        return StoreTranslation.objects.create(
            kind="home", key="home", locale=locale, title=f"Home {locale}",
            description=f"Description {locale}", body=f"Body {locale}", published=True,
        )

    def add_product_translation(self, locale="en"):
        return StoreTranslation.objects.create(
            kind="product", key=str(self.cigar.pk), locale=locale,
            title="Test Cigar", description="Reviewed cigar description",
            body="Reviewed cigar body", aliases="sample alias", published=True,
        )

    def add_brand_translation(self, locale="en"):
        return StoreTranslation.objects.create(
            kind="brand", key=self.brand.slug, locale=locale,
            title=f"Reviewed {locale} brand", description="Reviewed brand description",
            body="Reviewed brand body", published=True,
        )

    def test_legacy_chinese_catalog_exposes_no_offer_until_listing_published(self):
        path = f"/cigar/{self.cigar.pk}/test-brand-test-cigar"
        product = build_pages()[path]["product"]
        self.assertEqual(product["name"], "测试雪茄")
        self.assertEqual(product["availability"], "catalog")
        self.assertEqual(product["offers"], [])
        serialized = str(product)
        self.assertNotIn("999", serialized)
        self.assertNotIn("remaining", serialized)
        self.assertNotIn("quantity", serialized)

        listing = ProductListing.objects.create(cigar=self.cigar, published=True)
        product = build_pages()[path]["product"]
        self.assertEqual(product["offers"], [{"box_size": 25, "price_rub": "12345.67", "in_stock": True}])
        self.price.retail_price_rub = None
        self.price.save(update_fields=["retail_price_rub"])
        self.assertIsNone(build_pages()[path]["product"]["offers"][0]["price_rub"])

        listing.withdrawn = True
        listing.published = False
        listing.save()
        self.assertNotIn(path, build_pages())

    def test_translated_product_requires_published_complete_translation(self):
        path = f"/en/cigar/{self.cigar.pk}/test-brand-test-cigar"
        self.assertNotIn(path, build_pages())
        self.add_home_translation("en")
        self.add_brand_translation("en")
        self.add_product_translation("en")
        payload = build_pages()[path]
        self.assertEqual(payload["locale"], "en")
        self.assertEqual(payload["product"]["description"], "Reviewed cigar description")
        self.assertEqual(payload["product"]["brand"], "Reviewed en brand")
        self.assertEqual(payload["alternates"], [{"locale": "zh", "path": f"/cigar/{self.cigar.pk}/test-brand-test-cigar"}, {"locale": "en", "path": path}])

    def test_untranslated_non_chinese_brand_fallback_uses_english_name(self):
        product = _product_data(
            self.cigar, "ru", None, {self.brand.slug: self.brand}, {}, set(), {}, set(), {},
        )
        self.assertEqual(product["brand"], "Test Brand")

    def test_product_card_uses_thumbnail_and_gallery_uses_full_size_image(self):
        CigarImage.objects.create(
            cigar=self.cigar, image="cigars/full-size.jpg",
            thumbnail="cigars/thumb.jpg", image_type="cigar", is_primary=True,
        )
        product = build_pages()[f"/cigar/{self.cigar.pk}/test-brand-test-cigar"]["product"]
        self.assertEqual(product["image_url"], "/media/cigars/thumb.jpg")
        self.assertEqual(product["images"][0], "/media/cigars/full-size.jpg")
        self.assertNotIn("/media/cigars/thumb.jpg", product["images"])

    def test_cached_brand_pages_are_allowed_in_all_locales(self):
        for locale in ("zh", "ru", "en"):
            if locale != "zh":
                self.add_home_translation(locale)
                self.add_brand_translation(locale)
                self.add_product_translation(locale)

        pages = build_pages()
        for locale in ("zh", "ru", "en"):
            path = f"/{locale}/brand/{self.brand.slug}" if locale != "zh" else f"/brand/{self.brand.slug}"
            payload = pages[path]
            StorePage.objects.create(
                path=path,
                payload=payload,
                rendered_payload=payload,
                desired_hash=semantic_hash(payload),
                rendered_hash=semantic_hash(payload),
                html="<html><body>cached brand</body></html>",
            )
            response = page(self.factory.get(path))
            self.assertEqual(response.status_code, 200, locale)
            self.assertEqual(response.content, b"<html><body>cached brand</body></html>", locale)

    def test_paginated_alternates_point_to_matching_locale_page_only(self):
        translated_cigars = [self.cigar]
        translated_cigars.extend(Cigar.objects.bulk_create([
            Cigar(brand=self.brand.english_name, english_name=f"Catalog Cigar {index}")
            for index in range(25)
        ]))
        self.add_home_translation("en")
        self.add_brand_translation("en")
        self.add_product_translation("en")
        self.add_home_translation("ru")
        self.add_brand_translation("ru")
        StoreTranslation.objects.create(
            kind="product", key=str(self.cigar.pk), locale="ru",
            title="Test Cigar RU", description="Reviewed Russian description",
            body="Reviewed Russian body", published=True,
        )
        for cigar in translated_cigars[1:]:
            StoreTranslation.objects.create(
                kind="product", key=str(cigar.pk), locale="en",
                title=cigar.english_name, description="Reviewed description",
                body="Reviewed body", published=True,
            )

        pages = build_pages()
        zh_page_two = pages[f"/brand/{self.brand.slug}?page=2"]
        self.assertEqual(zh_page_two["path"], f"/brand/{self.brand.slug}?page=2")
        self.assertEqual(zh_page_two["alternates"], [
            {"locale": "zh", "path": f"/brand/{self.brand.slug}?page=2"},
            {"locale": "en", "path": f"/en/brand/{self.brand.slug}?page=2"},
        ])
        self.assertNotIn("ru", {alternate["locale"] for alternate in zh_page_two["alternates"]})
        self.assertIn({"locale": "ru", "path": f"/ru/brand/{self.brand.slug}"}, zh_page_two["browsing_alternates"])
        self.assertTrue(allowed_payload(zh_page_two))
        StoreTranslation.objects.filter(kind="home", key="home", locale="ru").update(published=False)
        self.assertFalse(allowed_payload(zh_page_two))

    def test_stock_requires_complete_available_boxes_and_live_batch(self):
        self.batch.available_box_quantity = 0
        self.batch.available_stick_quantity = 24
        self.batch.remaining = 24
        self.batch.physical_box_quantity = 0
        self.batch.physical_stick_quantity = 24
        self.batch.physical_remaining = 24
        # Fixture's inventory guard prevents ordinary updates; this is test setup only.
        from cigars.tests.inventory_fixtures import force_inventory_save
        force_inventory_save(self.batch, update_fields=[
            "available_box_quantity", "available_stick_quantity", "remaining",
            "physical_box_quantity", "physical_stick_quantity", "physical_remaining",
        ])
        path = f"/cigar/{self.cigar.pk}/test-brand-test-cigar"
        product = build_pages()[path]["product"]
        self.assertEqual(product["availability"], "catalog")

    def test_home_requires_approved_translation_and_only_lists_published_stock(self):
        self.assertNotIn("/", build_pages())
        self.add_home_translation()
        home = build_pages()["/"]
        self.assertEqual(home["products"], [])
        ProductListing.objects.create(cigar=self.cigar, published=True)
        home = build_pages()["/"]
        self.assertEqual([row["id"] for row in home["products"]], [self.cigar.pk])

    def test_pagination_urls_are_explicit_and_use_canonical_self_paths(self):
        Cigar.objects.bulk_create([
            Cigar(brand=self.brand.english_name, english_name=f"Catalog Cigar {index}")
            for index in range(25)
        ])
        pages = build_pages()
        brand_path = f"/brand/{self.brand.slug}"
        second_page_path = brand_path + "?page=2"
        self.assertIn(second_page_path, pages)
        self.assertEqual(pages[second_page_path]["path"], second_page_path)
        self.assertEqual(pages[second_page_path]["pagination"]["page"], 2)
        self.assertEqual(resolve_path(brand_path + "/"), brand_path)

    def test_details_are_hidden_until_verified_and_translation_supplies_hours(self):
        translation = self.add_home_translation()
        translation.hours = "Daily 10–18"
        translation.save(update_fields=["hours"])
        store, _ = StoreSettings.objects.get_or_create(pk=1)
        store.address = "Private draft address"
        store.phone = "+7 999 123 45 67"
        store.save()
        site = build_pages()["/"]["site"]
        self.assertEqual(site["address"], "")
        self.assertEqual(site["phone"], "")
        self.assertEqual(site["hours"], "")
        store.details_verified = True
        store.save()
        site = build_pages()["/"]["site"]
        self.assertEqual(site["address"], "Private draft address")
        self.assertEqual(site["phone"], "+7 999 123 45 67")
        self.assertEqual(site["hours"], "Daily 10–18")

    def test_page_data_etag_and_current_publication_guard(self):
        self.add_home_translation()
        listing = ProductListing.objects.create(cigar=self.cigar, published=True)
        payload = build_pages()["/"]
        store_page = StorePage.objects.create(
            path="/", payload=payload, rendered_payload=payload,
            desired_hash=semantic_hash(payload), rendered_hash=semantic_hash(payload), html="<html>ready</html>",
        )
        self.assertTrue(allowed_payload(store_page.rendered_payload))
        response = page(self.factory.get("/"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"<html>ready</html>")
        cached = page(self.factory.get("/", HTTP_IF_NONE_MATCH=response["ETag"]))
        self.assertEqual(cached.status_code, 304)

        data_response = page_data(self.factory.get("/api/storefront/page/", {"path": "/"}))
        self.assertEqual(data_response.status_code, 200)
        data = json.loads(data_response.content)
        self.assertEqual(data, payload)
        self.assertIn("title", data)
        self.assertIn("description", data)

        listing.withdrawn = True
        listing.published = False
        listing.save()
        self.assertFalse(allowed_payload(store_page.rendered_payload))

    def test_search_normalizes_accents_case_and_uses_token_or(self):
        self.add_home_translation("en")
        self.add_brand_translation("en")
        self.add_product_translation("en")
        results = search_products("SAMPLE", locale="en")
        self.assertEqual([item["id"] for item in results], [self.cigar.pk])
        self.assertEqual(search_products("absent", locale="en"), [])

    def test_stock_catalog_has_its_own_routes_and_publication_dependencies(self):
        home = self.add_home_translation()
        ProductListing.objects.create(cigar=self.cigar, published=True)
        pages = build_pages()
        catalog = pages["/catalog"]
        self.assertEqual(catalog["view"], "catalog")
        self.assertEqual(catalog["title"], "现货商品")
        self.assertEqual(catalog["total_products"], 1)
        self.assertEqual(catalog["navigation"]["box_sizes"], [25])
        self.assertEqual(catalog["navigation"]["brands"][0]["slug"], self.brand.slug)
        self.assertEqual(catalog["alternates"], [{"locale": "zh", "path": "/catalog"}])
        self.assertTrue(allowed_payload(catalog))
        home.published = False
        home.save(update_fields=["published"])
        self.assertFalse(allowed_payload(catalog))
        self.assertNotIn("/catalog", build_pages())

    def test_unregistered_brands_are_not_grouped_as_same_brand_recommendations(self):
        self.add_home_translation()
        cigars = [Cigar.objects.create(brand=name, english_name="Unregistered") for name in ("Unknown A", "Unknown B")]
        for cigar in cigars:
            ProductListing.objects.create(cigar=cigar, published=True)
            create_purchase_batch(source=PurchaseBatch.Source.OPENING, cigar=cigar,
                                  quantity=25, remaining=25, physical_remaining=25, box_size=25,
                                  unit_cost_cny=Decimal("1.00"))
        for payload in build_pages().values():
            if payload.get("product") and payload["product"]["id"] in {p.pk for p in cigars}:
                self.assertEqual(payload["products"], [])

    def test_catalog_combines_brand_box_and_vitola_search_with_no_false_results(self):
        self.add_home_translation()
        ProductListing.objects.create(cigar=self.cigar, published=True)
        response = page_data(self.factory.get("/api/storefront/page/", {
            "path": "/catalog", "brand": self.brand.slug, "box": "25", "q": "罗布图", "sort": "length",
        }))
        data = json.loads(response.content)
        self.assertEqual([p["id"] for p in data["products"]], [self.cigar.pk])
        self.assertEqual(data["total_products"], 1)
        self.assertEqual(data["filters"]["boxes"], ["25"])
        self.assertIn("noindex", response["X-Robots-Tag"])
        for invalid in ({"box": "no-number"}, {"box": "10"}, {"brand": "unknown"}, {"q": "absent"}):
            with self.subTest(invalid=invalid):
                response = page_data(self.factory.get("/api/storefront/page/", {"path": "/catalog", **invalid}))
                self.assertEqual(json.loads(response.content)["products"], [])

    def test_brand_search_stays_within_brand_and_sorts_before_pagination(self):
        self.add_home_translation()
        Cigar.objects.bulk_create([
            Cigar(brand=self.brand.english_name, english_name=f"Match {i:02}", length=200-i)
            for i in range(30)
        ])
        other = Brand.objects.create(english_name="Other", name="其他")
        Cigar.objects.create(brand=other.english_name, english_name="Match other", length=1)
        path = f"/brand/{self.brand.slug}"
        response = page_data(self.factory.get("/api/storefront/page/", {"path": path, "q": "Match", "sort": "length", "page": "2"}))
        data = json.loads(response.content)
        self.assertEqual(data["total_products"], 30)
        self.assertEqual(len(data["products"]), 6)
        self.assertEqual([p["length"] for p in data["products"]], list(range(195, 201)))
        self.assertTrue(all(p["brand_slug"] == self.brand.slug for p in data["products"]))
        self.assertIn("q=Match", data["pagination"]["previous"])
        self.assertIn("sort=length", data["pagination"]["previous"])
        with self.assertRaises(Exception) as raised:
            page_data(self.factory.get("/api/storefront/page/", {"path": path, "q": "Match", "page": "99"}))
        from django.http import Http404
        self.assertIsInstance(raised.exception, Http404)

    def test_stock_catalog_paginates_all_filtered_rows_and_language_alternates(self):
        from unittest.mock import patch
        self.add_home_translation()
        ProductListing.objects.create(cigar=self.cigar, published=True)
        second = Cigar.objects.create(brand=self.brand.english_name, english_name="Second", length=110)
        ProductListing.objects.create(cigar=second, published=True)
        create_purchase_batch(source=PurchaseBatch.Source.OPENING, cigar=second,
                              quantity=25, remaining=25, physical_remaining=25, box_size=25,
                              unit_cost_cny=Decimal("1.00"))
        with patch("storefront.catalog.PAGE_SIZE", 1):
            pages = build_pages()
            self.assertEqual(pages["/catalog?page=2"]["alternates"], [{"locale": "zh", "path": "/catalog?page=2"}])
            response = page_data(self.factory.get("/api/storefront/page/", {"path": "/catalog", "box": "25", "sort": "length", "page": "2"}))
            data = json.loads(response.content)
            self.assertEqual(data["total_products"], 2)
            self.assertEqual([p["id"] for p in data["products"]], [self.cigar.pk])
            self.assertEqual(data["pagination"]["previous"], "/catalog?box=25&sort=length")

    def test_translated_search_recognizes_chinese_brand_and_vitola_without_changing_output_language(self):
        self.add_home_translation("en")
        self.add_brand_translation("en")
        self.add_product_translation("en")
        for query in ("测试品牌", "罗布图", "robusto"):
            with self.subTest(query=query):
                rows = search_products(query, locale="en")
                self.assertEqual([p["id"] for p in rows], [self.cigar.pk])
                self.assertEqual(rows[0]["brand"], "Reviewed en brand")

    def test_six_major_brand_filters_precede_other_brands_without_publishing_unreviewed_brand_pages(self):
        from storefront.catalog import PRIORITY_BRANDS
        for index, english_name in enumerate(reversed(PRIORITY_BRANDS)):
            Brand.objects.create(english_name=english_name, name=f"品牌 {index}")
        self.add_home_translation("en")
        self.add_brand_translation("en")
        self.add_product_translation("en")
        ProductListing.objects.create(cigar=self.cigar, published=True)
        pages = build_pages()
        home = pages["/en/"]
        navigation = home["navigation"]["brands"]
        self.assertEqual([b["english_name"] for b in navigation[:6]], list(PRIORITY_BRANDS))
        self.assertEqual([b["name"] for b in navigation[:6]], list(PRIORITY_BRANDS))
        self.assertTrue(allowed_payload(home))
        self.assertNotIn("/en/brand/montecristo", pages)
        self.assertEqual(navigation[1]["path"], "/en/catalog?brand=montecristo")
        response = page_data(self.factory.get("/api/storefront/page/", {"path": "/en/catalog", "brand": "montecristo"}))
        self.assertEqual(json.loads(response.content)["products"], [])

    def test_rates_are_exposed_only_while_both_sources_are_fresh(self):
        fresh_time = timezone.now() - timedelta(minutes=5)
        ExchangeRate.objects.create(currency="RUB", rate=0.12, source_updated_at=fresh_time)
        ExchangeRate.objects.create(currency="USD", rate=90, source_updated_at=fresh_time)
        response = rates(self.factory.get("/api/storefront/rates/"))
        self.assertEqual(response.status_code, 200)
        rates_data = json.loads(response.content)
        self.assertEqual(rates_data["cny_per_rub"], "0.12")
        self.assertEqual(rates_data["usd_per_rub"], str(Decimal("0.12") / Decimal("90.0")))

        old = ExchangeRate.objects.get(currency="RUB")
        old.source_updated_at = timezone.now() - timedelta(hours=49)
        old.save(update_fields=["source_updated_at"])
        expired = rates(self.factory.get("/api/storefront/rates/"))
        self.assertIsNone(json.loads(expired.content)["cny_per_rub"])

    def make_stick_cigar(self, name="Loose", *, published=True, remaining=7, physical=7, reversed=False, deleted=False, box_size=None):
        cigar = Cigar.objects.create(brand=self.brand.english_name, english_name=name,
                                     deleted_at=timezone.now() if deleted else None)
        create_purchase_batch(source=PurchaseBatch.Source.OPENING, cigar=cigar,
                              quantity=physical, remaining=remaining, physical_remaining=physical,
                              box_size=box_size, unit_cost_cny=Decimal("987.00"),
                              reversed_at=timezone.now() if reversed else None,
                              reversed_quantity=physical if reversed else 0)
        if published:
            ProductListing.objects.create(cigar=cigar, published=True)
        return cigar

    def test_loose_sticks_are_stock_without_box_conversion_or_inherited_price(self):
        self.add_home_translation()
        cigar = self.make_stick_cigar(remaining=30, physical=30)
        CigarPrice.objects.create(cigar=cigar, box_size=25, wholesale_price=100,
                                  retail_price_rub=Decimal("5000.00"))
        pages = build_pages()
        product = next(p["product"] for p in pages.values() if p.get("product") and p["product"]["id"] == cigar.pk)
        self.assertEqual(product["availability"], "in_stock")
        self.assertEqual(product["offers"], [
            {"box_size": 25, "price_rub": "5000.00", "in_stock": False},
            {"sale_unit": "stick", "box_size": None, "price_rub": None, "in_stock": True},
        ])
        self.assertEqual([p["id"] for p in pages["/"]["products"]], [cigar.pk])
        self.assertEqual([p["id"] for p in pages["/catalog"]["products"]], [cigar.pk])
        self.assertTrue(pages["/catalog"]["navigation"]["has_sticks"])
        self.assertTrue(pages["/catalog"]["filter_options"]["has_sticks"])
        self.assertEqual(pages["/catalog"]["navigation"]["box_sizes"], [])
        self.assertTrue(allowed_payload(pages["/catalog"]))
        self.assertNotIn("987", json.dumps(product))

    def test_stick_shelf_excludes_reversed_reserved_deleted_and_unpublished(self):
        self.add_home_translation()
        hidden = [self.make_stick_cigar("Reversed", reversed=True),
                  self.make_stick_cigar("Reserved", remaining=0, physical=8),
                  self.make_stick_cigar("Deleted", deleted=True),
                  self.make_stick_cigar("Unpublished", published=False)]
        pages = build_pages()
        self.assertEqual(pages["/catalog"]["products"], [])
        self.assertFalse(pages["/catalog"]["navigation"]["has_sticks"])
        for cigar in hidden:
            products = [p["product"] for p in pages.values() if p.get("product") and p["product"]["id"] == cigar.pk]
            self.assertFalse(any(o.get("sale_unit") == "stick" for p in products for o in p["offers"]))

    def test_stick_filter_combines_brand_query_and_box_or_without_inventing_sticks(self):
        self.add_home_translation()
        ProductListing.objects.create(cigar=self.cigar, published=True)
        loose = self.make_stick_cigar("Loose match")
        mixed = self.make_stick_cigar("Mixed match", remaining=27, physical=27, box_size=25)
        def results(**criteria):
            response = page_data(self.factory.get("/api/storefront/page/", {"path": "/catalog", **criteria}))
            return json.loads(response.content)
        self.assertEqual({p["id"] for p in results(box="stick")["products"]}, {loose.pk, mixed.pk})
        self.assertEqual({p["id"] for p in results(box=["25", "stick"])["products"]}, {self.cigar.pk, loose.pk, mixed.pk})
        self.assertEqual([p["id"] for p in results(box="stick", brand=self.brand.slug, q="Loose")["products"]], [loose.pk])
        self.assertEqual(results(box="stick", brand="unknown")["products"], [])
        self.assertEqual(results(box="None")["products"], [])
        self.assertEqual({p["id"] for p in results(box="25")["products"]}, {self.cigar.pk, mixed.pk})

    def test_unpublishing_stick_listing_hides_stock_and_revokes_cached_payload(self):
        self.add_home_translation()
        cigar = self.make_stick_cigar()
        cached = build_pages()["/catalog"]
        self.assertTrue(allowed_payload(cached))
        listing = ProductListing.objects.get(cigar=cigar)
        listing.published = False
        listing.save(update_fields=["published"])
        self.assertFalse(allowed_payload(cached))
        pages = build_pages()
        self.assertEqual(pages["/catalog"]["products"], [])
        product = next(p["product"] for p in pages.values() if p.get("product") and p["product"]["id"] == cigar.pk)
        self.assertEqual(product["offers"], [])
        self.assertEqual(product["availability"], "catalog")
        listing.published = True
        listing.withdrawn = True
        listing.save(update_fields=["published", "withdrawn"])
        self.assertFalse(allowed_payload(cached))
        self.assertFalse(any(p.get("product", {}).get("id") == cigar.pk for p in build_pages().values() if p.get("product")))
