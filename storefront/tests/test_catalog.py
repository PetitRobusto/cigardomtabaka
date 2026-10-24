from datetime import date, timedelta
from decimal import Decimal
import json

from django.db import IntegrityError, transaction
from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone

from accounting.models import Day1Initialization, FundAccount, LedgerPosting
from accounting.purchase_actions import (
    pay_purchase_order, receive_paid_purchase_order, reverse_received_purchase_order,
)
from accounting.services import record_opening_balance
from cigars.models import (
    Brand, Cigar, CigarImage, CigarPrice, PurchaseBatch, PurchaseOrder,
    PurchaseOrderItem, Supplier, User,
)
from cigars.tests.inventory_fixtures import create_purchase_batch, force_inventory_update
from price_tracker.models import ExchangeRate

from storefront.catalog import _product_data, allowed_payload, build_pages, public_dependencies, resolve_path, search_products, semantic_hash
from storefront.models import ProductListing, StorePage, StoreSettings, StoreTranslation
from storefront.public_details import PUBLIC_DETAILS
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

    def receive_purchase(self, cigar, business_date, *, key):
        """Create a real posted receipt so the test exercises its business date."""
        operator = getattr(self, "receipt_operator", None)
        if operator is None:
            operator = User.objects.create_user(
                username=f"storefront-receipt-{User.objects.count()}", is_staff=True,
            )
            self.receipt_operator = operator
            Day1Initialization.objects.create(
                singleton_key="company", status=Day1Initialization.Status.COMPLETED,
                business_date=date(2026, 8, 10), completed_by=operator,
            )
            self.receipt_account = FundAccount.objects.create(
                name="商城测试卢布账户", currency=FundAccount.Currency.RUB,
                creation_idempotency_key="storefront-receipt-fund", custodian=operator,
            )
            record_opening_balance(
                self.receipt_account, Decimal("100000.00"), Decimal("12000.00"),
                LedgerPosting.Category.OPENING_CAPITAL, date(2026, 8, 10), operator,
                "storefront-receipt-opening",
            )
        supplier, _ = Supplier.objects.get_or_create(name="商城测试供应商")
        order = PurchaseOrder.objects.create(
            supplier=supplier, rub_total=Decimal("100.00"), operator=operator,
            draft_business_date=business_date,
        )
        PurchaseOrderItem.objects.create(
            purchase_order=order, cigar=cigar, quantity=25, box_size=25,
            box_quantity=1, unit_price_rub_per_box=Decimal("100.00"),
            packaging_status=PurchaseOrderItem.PackagingStatus.UNREPRESENTABLE,
        )
        pay_purchase_order(
            purchase_order_id=order.pk, rub_account_id=self.receipt_account.pk,
            business_date=business_date, operator=operator, idempotency_key=f"{key}-payment",
        )
        batches = receive_paid_purchase_order(
            purchase_order_id=order.pk, business_date=business_date, operator=operator,
            idempotency_key=f"{key}-receipt",
        )
        return order, batches

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

    def test_missing_product_translation_keeps_locale_page_with_safe_fallback(self):
        path = f"/en/cigar/{self.cigar.pk}/test-brand-test-cigar"
        fallback = build_pages()[path]
        self.assertEqual(fallback["product"]["name"], self.cigar.english_name)
        self.assertEqual(fallback["product"]["description"], "Robusto")
        self.assertFalse(fallback["translation_complete"])
        self.assertEqual(fallback["content_locale"], "en")
        self.assertFalse(fallback["indexable"])
        self.assertTrue(allowed_payload(fallback))
        self.assertNotIn("en", {row["locale"] for row in fallback["alternates"]})
        self.assertEqual({row["locale"] for row in fallback["browsing_alternates"]}, {"zh", "ru", "en"})
        pages = build_pages()
        locale_products = {
            locale: {page["product"]["id"] for page in pages.values()
                     if page["locale"] == locale and page["kind"] == "product"}
            for locale in ("zh", "ru", "en")
        }
        self.assertEqual(locale_products["zh"], locale_products["ru"])
        self.assertEqual(locale_products["zh"], locale_products["en"])
        StorePage.objects.create(
            path=path, payload=fallback, rendered_payload=fallback,
            desired_hash=semantic_hash(fallback), rendered_hash=semantic_hash(fallback),
            html="<html><body>fallback product</body></html>",
        )
        response = page(self.factory.get(path))
        self.assertEqual(response["X-Robots-Tag"], "noindex, nofollow")
        sitemap = self.client.get("/sitemap-storefront.xml")
        self.assertNotContains(sitemap, path)
        self.add_home_translation("en")
        self.add_brand_translation("en")
        self.add_product_translation("en")
        payload = build_pages()[path]
        self.assertEqual(payload["locale"], "en")
        self.assertEqual(payload["product"]["description"], "Reviewed cigar description")
        self.assertEqual(payload["product"]["brand"], "Reviewed en brand")
        self.assertTrue(payload["translation_complete"])
        self.assertTrue(payload["indexable"])

    def test_published_english_translation_revocation_invalidates_cached_english_fallback(self):
        self.add_home_translation("en")
        self.add_brand_translation("en")
        translation = self.add_product_translation("en")
        path = f"/en/cigar/{self.cigar.pk}/test-brand-test-cigar"
        payload = build_pages()[path]
        self.assertTrue(allowed_payload(payload))
        translation.published = False
        translation.save(update_fields=["published"])
        self.assertFalse(allowed_payload(payload))

    def test_store_translation_brand_body_may_be_empty(self):
        row = StoreTranslation.objects.create(
            kind="brand", key=self.brand.slug, locale="en", title=self.brand.english_name,
            description=self.brand.english_name, body="", published=True,
        )
        row.full_clean()
        self.add_home_translation("en")
        payload = build_pages()[f"/en/brand/{self.brand.slug}"]
        self.assertEqual(payload["body"], "")
        self.assertEqual(payload["title"], self.brand.english_name)

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

    def test_image_variants_keep_exact_box_metadata_and_unknown_legacy_box_sizes(self):
        ten = CigarImage.objects.create(
            cigar=self.cigar, image="cigars/box-10.jpg", thumbnail="cigars/box-10-thumb.jpg",
            image_type=CigarImage.ImageType.PACKAGING, box_size=10,
        )
        twenty_five = CigarImage.objects.create(
            cigar=self.cigar, image="cigars/box-25.jpg", thumbnail="cigars/box-25-thumb.jpg",
            image_type=CigarImage.ImageType.SPECIAL, box_size=25,
        )
        legacy = CigarImage.objects.create(
            cigar=self.cigar, image="cigars/legacy-box.jpg", image_type=CigarImage.ImageType.PACKAGING,
        )

        product = build_pages()[f"/cigar/{self.cigar.pk}/test-brand-test-cigar"]["product"]
        variants = {variant["url"]: variant for variant in product["image_variants"]}
        self.assertEqual(variants["/media/cigars/box-10.jpg"], {
            "url": "/media/cigars/box-10.jpg",
            "thumbnail_url": "/media/cigars/box-10-thumb.jpg",
            "image_type": "packaging",
            "box_size": 10,
        })
        self.assertEqual(variants["/media/cigars/box-25.jpg"]["box_size"], 25)
        self.assertIsNone(variants["/media/cigars/legacy-box.jpg"]["box_size"])
        self.assertEqual(ten.box_size, 10)
        self.assertEqual(twenty_five.box_size, 25)
        self.assertIsNone(legacy.box_size)

    def test_image_box_size_constraint_requires_positive_packaging_image(self):
        invalid_values = [
            (CigarImage.ImageType.CIGAR, 10),
            (CigarImage.ImageType.PACKAGING, 0),
        ]
        for index, (image_type, box_size) in enumerate(invalid_values):
            with self.subTest(image_type=image_type, box_size=box_size):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    CigarImage.objects.create(
                        cigar=self.cigar, image=f"cigars/invalid-{index}.jpg",
                        image_type=image_type, box_size=box_size,
                    )

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
        for cigar in translated_cigars[1:]:
            create_purchase_batch(
                source=PurchaseBatch.Source.OPENING, cigar=cigar,
                quantity=1, remaining=1, physical_remaining=1, box_size=None,
                unit_cost_cny=Decimal("1.00"),
            )
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
        self.assertTrue(allowed_payload(zh_page_two))

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

    def test_home_latest_products_use_effective_receipt_dates_and_public_listing_rules(self):
        self.add_home_translation()
        received = []
        dates = [date(2026, 8, 10), date(2026, 8, 11), date(2026, 8, 12),
                 date(2026, 8, 13), date(2026, 8, 14), date(2026, 8, 15),
                 date(2026, 8, 16)]
        for index, receipt_date in enumerate(dates):
            cigar = Cigar.objects.create(
                brand=self.brand.english_name, english_name=f"Receipt Cigar {index}",
                name=f"进货雪茄 {index}",
            )
            self.receive_purchase(cigar, receipt_date, key=f"storefront-order-{index}")
            ProductListing.objects.create(cigar=cigar, published=True)
            received.append(cigar)

        # Current stock is not required for the new-arrivals shelf once a
        # product has a valid public listing and receipt history.
        sold_out = received[1]
        force_inventory_update(
            PurchaseBatch.objects.filter(cigar=sold_out), remaining=0,
            available_box_quantity=0, available_stick_quantity=0,
            remaining_cost_cny=Decimal("0.00"),
        )
        # Deliberately make row creation time disagree with the receipt date.
        for index, cigar in enumerate(received):
            force_inventory_update(PurchaseBatch.objects.filter(cigar=cigar),
                purchased_at=timezone.now() + timedelta(days=len(received) - index),
            )

        unpublished = Cigar.objects.create(brand=self.brand.english_name, english_name="Unpublished")
        self.receive_purchase(unpublished, date(2026, 8, 20), key="storefront-unpublished")
        ProductListing.objects.create(cigar=unpublished, published=False)
        withdrawn = Cigar.objects.create(brand=self.brand.english_name, english_name="Withdrawn")
        self.receive_purchase(withdrawn, date(2026, 8, 21), key="storefront-withdrawn")
        ProductListing.objects.create(cigar=withdrawn, published=False, withdrawn=True)
        deleted = Cigar.objects.create(brand=self.brand.english_name, english_name="Deleted")
        self.receive_purchase(deleted, date(2026, 8, 22), key="storefront-deleted")
        ProductListing.objects.create(cigar=deleted, published=True)
        deleted.deleted_at = timezone.now()
        deleted.save(update_fields=["deleted_at"])
        reversed_cigar = Cigar.objects.create(brand=self.brand.english_name, english_name="Reversed")
        reversed_order, _ = self.receive_purchase(
            reversed_cigar, date(2026, 8, 24), key="storefront-reversed",
        )
        ProductListing.objects.create(cigar=reversed_cigar, published=True)
        reverse_received_purchase_order(
            purchase_order_id=reversed_order.pk, business_date=date(2026, 8, 25),
            operator=self.receipt_operator, idempotency_key="storefront-reversed-action",
            reason="测试撤销",
        )

        home = build_pages()["/"]
        expected = [received[i].pk for i in (6, 5, 4, 3, 2, 1)]
        self.assertEqual([row["id"] for row in home["latest_products"]], expected)
        self.assertEqual(home["latest_products"][5]["availability"], "out_of_stock")
        self.assertNotIn(unpublished.pk, [row["id"] for row in home["latest_products"]])
        self.assertNotIn(withdrawn.pk, [row["id"] for row in home["latest_products"]])
        self.assertNotIn(reversed_cigar.pk, [row["id"] for row in home["latest_products"]])
        self.assertNotIn(deleted.pk, [row["id"] for row in home["latest_products"]])

    def test_home_latest_only_product_translation_is_a_live_cache_dependency(self):
        self.add_home_translation()
        self.add_home_translation("en")
        self.add_home_translation("ru")
        self.add_brand_translation("en")
        self.add_brand_translation("ru")
        latest = Cigar.objects.create(
            brand=self.brand.english_name, english_name="Latest Translation Only",
            name="最新翻译依赖",
        )
        self.receive_purchase(latest, date(2026, 8, 23), key="storefront-latest-translation")
        ProductListing.objects.create(cigar=latest, published=True)
        force_inventory_update(
            PurchaseBatch.objects.filter(cigar=latest), remaining=0,
            available_box_quantity=0, available_stick_quantity=0,
            remaining_cost_cny=Decimal("0.00"),
        )
        translation = StoreTranslation.objects.create(
            kind="product", key=str(latest.pk), locale="zh", title="新上架翻译",
            description="已审核摘要", body="已审核正文", published=True,
        )
        for locale in ("en", "ru"):
            StoreTranslation.objects.create(
                kind="product", key=str(latest.pk), locale=locale,
                title=f"Latest product {locale}", description=f"Reviewed {locale} summary",
                body=f"Reviewed {locale} content", published=True,
            )

        home = build_pages()["/"]
        latest_ids = [row["id"] for row in home["latest_products"]]
        self.assertIn(latest.pk, latest_ids)
        self.assertNotIn(latest.pk, [row["id"] for row in home["products"]])
        self.assertIn(["product", str(latest.pk), "zh"], home["translation_dependencies"])
        self.assertTrue(allowed_payload(home))

        catalog_pages = build_pages()
        self.assertEqual(catalog_pages["/catalog"]["latest_products"], [])
        self.assertTrue(allowed_payload(catalog_pages["/catalog"]))
        self.assertTrue(allowed_payload(catalog_pages["/en/catalog"]))

        stocked = Cigar.objects.bulk_create([
            Cigar(brand=self.brand.english_name, english_name=f"Paged Product {index:02}")
            for index in range(25)
        ])
        for cigar in stocked:
            create_purchase_batch(
                source=PurchaseBatch.Source.OPENING, cigar=cigar,
                quantity=1, remaining=1, physical_remaining=1, box_size=None,
                unit_cost_cny=Decimal("1.00"),
            )
            ProductListing.objects.create(cigar=cigar, published=True)
        paginated_home = build_pages()["/?page=2"]
        self.assertNotIn("latest_products", paginated_home)
        self.assertTrue(allowed_payload(paginated_home))

        english_translation = StoreTranslation.objects.get(
            kind="product", key=str(latest.pk), locale="en",
        )
        english_translation.published = False
        english_translation.save(update_fields=["published"])
        untranslated_home = build_pages()["/en/"]
        self.assertFalse(untranslated_home["translation_complete"])
        self.assertTrue(allowed_payload(untranslated_home))
        english_translation.published = True
        english_translation.save(update_fields=["published"])

        translation.published = False
        translation.save(update_fields=["published"])
        self.assertFalse(allowed_payload(home))
        translation.published = True
        translation.save(update_fields=["published"])
        refreshed_home = build_pages()["/"]
        self.assertTrue(allowed_payload(refreshed_home))
        listing = ProductListing.objects.get(cigar=latest)
        listing.published = False
        listing.withdrawn = True
        listing.save(update_fields=["published", "withdrawn"])
        self.assertFalse(allowed_payload(refreshed_home))

    def test_pagination_urls_are_explicit_and_use_canonical_self_paths(self):
        cigars = Cigar.objects.bulk_create([
            Cigar(brand=self.brand.english_name, english_name=f"Catalog Cigar {index}")
            for index in range(25)
        ])
        for cigar in cigars:
            create_purchase_batch(
                source=PurchaseBatch.Source.OPENING, cigar=cigar,
                quantity=1, remaining=1, physical_remaining=1, box_size=None,
                unit_cost_cny=Decimal("1.00"),
            )
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
        store.map_url = "https://maps.example/custom-store"
        store.save()
        site = build_pages()["/"]["site"]
        self.assertEqual(site["address"], PUBLIC_DETAILS["address"]["zh"])
        self.assertEqual(site["phone"], PUBLIC_DETAILS["phone"])
        self.assertEqual(site["map_url"], PUBLIC_DETAILS["map_url"])
        self.assertEqual(site["hours"], PUBLIC_DETAILS["hours"]["zh"])
        store.details_verified = True
        store.save()
        site = build_pages()["/"]["site"]
        self.assertEqual(site["address"], "Private draft address")
        self.assertEqual(site["phone"], "+7 999 123 45 67")
        self.assertEqual(site["map_url"], "https://maps.example/custom-store")
        self.assertEqual(site["hours"], "Daily 10–18")

    def test_confirmed_details_are_public_in_all_locales_without_verifying_other_drafts(self):
        StoreSettings.objects.create(address="Draft address", phone="Private phone", map_url="https://maps.example/draft", details_verified=False)
        for locale in ("zh", "ru", "en"):
            self.add_home_translation(locale)
        pages = build_pages()
        dependencies = public_dependencies()
        for path, payload in pages.items():
            with self.subTest(path=path):
                locale = payload["locale"]
                self.assertEqual(payload["site"]["address"], PUBLIC_DETAILS["address"][locale])
                self.assertEqual(payload["site"]["hours"], PUBLIC_DETAILS["hours"][locale])
                self.assertEqual(payload["site"]["phone"], PUBLIC_DETAILS["phone"])
                self.assertEqual(payload["site"]["map_url"], PUBLIC_DETAILS["map_url"])
                self.assertTrue(allowed_payload(payload, dependencies))
        for field in ("address", "hours", "phone", "map_url"):
            payload = json.loads(json.dumps(pages["/"]))
            payload["site"][field] = "Unverified draft"
            with self.subTest(field=field):
                self.assertFalse(allowed_payload(payload, dependencies))

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
        self.assertEqual(catalog["title"], "商品目录")
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

    def test_new_filter_parameters_trigger_live_catalog_filtering(self):
        self.add_home_translation()
        ProductListing.objects.create(cigar=self.cigar, published=True)
        for criteria, expected in [
            ({"length_min": "124", "length_max": "124", "ring_min": "50", "ring_max": "50", "price_min": "12345.67", "price_max": "12345.67", "stock_only": "1"}, [self.cigar.pk]),
            ({"length_min": "125"}, []), ({"ring_max": "49"}, []),
            ({"price_max": "12345.66"}, []), ({"stock_only": "1"}, [self.cigar.pk]),
        ]:
            with self.subTest(criteria=criteria):
                response = page_data(self.factory.get("/api/storefront/page/", {"path": "/catalog", **criteria}))
                self.assertEqual(response.status_code, 200)
                self.assertEqual([p["id"] for p in json.loads(response.content)["products"]], expected)
                self.assertIn("noindex", response["X-Robots-Tag"])

    def test_brand_search_stays_within_brand_and_sorts_before_pagination(self):
        self.add_home_translation()
        cigars = Cigar.objects.bulk_create([
            Cigar(brand=self.brand.english_name, english_name=f"Match {i:02}", length=200-i)
            for i in range(30)
        ])
        for cigar in cigars:
            create_purchase_batch(source=PurchaseBatch.Source.OPENING, cigar=cigar,
                                  quantity=1, remaining=0, physical_remaining=0, box_size=None,
                                  unit_cost_cny=Decimal("1.00"))
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

            for path in ("/catalog", "/catalog?page=2"):
                payload = pages[path]
                StorePage.objects.create(path=path, payload=payload, rendered_payload=payload,
                    desired_hash=semantic_hash(payload), rendered_hash=semantic_hash(payload),
                    html=f'<html><link rel="canonical" href="https://shop.example{path}"></html>')
            for filters in ({"box": "25"}, {"brand": self.brand.slug}, {"sort": "length"}):
                with self.subTest(filters=filters):
                    response = self.client.get("/catalog", {**filters, "page": "2"})
                    self.assertContains(response, 'href="https://shop.example/catalog"')
                    self.assertEqual(response["X-Robots-Tag"], "noindex, nofollow")
                    data_response = page_data(self.factory.get("/api/storefront/page/", {"path": "/catalog", **filters, "page": "2"}))
                    self.assertEqual(json.loads(data_response.content)["path"], "/catalog")
                    cached = self.client.get("/catalog", {**filters, "page": "2"}, HTTP_IF_NONE_MATCH=response["ETag"])
                    self.assertEqual(cached.status_code, 304)
                    self.assertEqual(cached["X-Robots-Tag"], "noindex, nofollow")
            response = self.client.get("/catalog", {"page": "2"})
            self.assertContains(response, 'href="https://shop.example/catalog?page=2"')
            self.assertNotIn("X-Robots-Tag", response)
            for filters in ({"box": "25", "page": "99"}, {"q": "absent", "page": "2"}):
                self.assertEqual(self.client.get("/catalog", filters).status_code, 404)

    def test_translated_search_recognizes_chinese_brand_and_vitola_without_changing_output_language(self):
        self.add_home_translation("en")
        self.add_brand_translation("en")
        self.add_product_translation("en")
        for query in ("测试品牌", "罗布图", "robusto"):
            with self.subTest(query=query):
                rows = search_products(query, locale="en")
                self.assertEqual([p["id"] for p in rows], [self.cigar.pk])
                self.assertEqual(rows[0]["brand"], "Reviewed en brand")

    def test_priority_brand_filters_require_valid_stock_history(self):
        from storefront.catalog import PRIORITY_BRANDS
        for index, english_name in enumerate(reversed(PRIORITY_BRANDS)):
            brand = Brand.objects.create(english_name=english_name, name=f"品牌 {index}")
            cigar = Cigar.objects.create(brand=brand.english_name, english_name=f"历史商品 {index}")
            create_purchase_batch(source=PurchaseBatch.Source.OPENING, cigar=cigar,
                                  quantity=1, remaining=0, physical_remaining=0, box_size=None,
                                  unit_cost_cny=Decimal("1.00"))
        Brand.objects.create(english_name="Never Stocked Brand", name="未入库品牌")
        self.add_home_translation()
        pages = build_pages()
        home = pages["/"]
        navigation = home["navigation"]["brands"]
        self.assertEqual([b["english_name"] for b in navigation[:6]], list(PRIORITY_BRANDS))
        self.assertNotIn("Never Stocked Brand", {b["english_name"] for b in navigation})
        self.assertTrue(allowed_payload(home))
        self.assertEqual(navigation[1]["path"], "/brand/montecristo")
        self.assertIn(navigation[1]["path"], pages)
        response = page_data(self.factory.get("/api/storefront/page/", {"path": "/catalog", "brand": "montecristo"}))
        filtered = json.loads(response.content)["products"]
        self.assertEqual([product["id"] for product in filtered], [
            cigar.pk for cigar in Cigar.objects.filter(brand="Montecristo").order_by("english_name")
        ])

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
        cigar.image_url = "https://images.example/unknown-pack.jpg"
        cigar.save(update_fields=["image_url"])
        product = next(p["product"] for p in build_pages().values()
                       if p.get("product") and p["product"]["id"] == cigar.pk)
        self.assertEqual(product["image_variants"], [{
            "url": "https://images.example/unknown-pack.jpg",
            "thumbnail_url": "https://images.example/unknown-pack.jpg",
            "image_type": None,
            "box_size": None,
        }])
        self.assertEqual([p["id"] for p in pages["/"]["products"]], [cigar.pk])
        self.assertEqual({p["id"] for p in pages["/catalog"]["products"]}, {self.cigar.pk, cigar.pk})
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
        self.assertEqual({p["id"] for p in pages["/catalog"]["products"]},
                         {self.cigar.pk, hidden[1].pk, hidden[3].pk})
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
        catalog_product = next(p for p in pages["/catalog"]["products"] if p["id"] == cigar.pk)
        self.assertEqual(catalog_product["availability"], "catalog")
        self.assertEqual(catalog_product["offers"], [])
        product = next(p["product"] for p in pages.values() if p.get("product") and p["product"]["id"] == cigar.pk)
        self.assertEqual(product["offers"], [])
        self.assertEqual(product["availability"], "catalog")
        listing.published = True
        listing.withdrawn = True
        listing.save(update_fields=["published", "withdrawn"])
        self.assertFalse(allowed_payload(cached))
        self.assertFalse(any(p.get("product", {}).get("id") == cigar.pk for p in build_pages().values() if p.get("product")))


@override_settings(STOREFRONT_ENABLED=True)
class StockHistoryDiscoveryTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.brand = Brand.objects.create(english_name="History Brand", name="历史品牌")
        self.home = StoreTranslation.objects.create(
            kind="home", key="home", locale="zh", title="首页",
            description="首页介绍", body="首页正文", published=True,
        )

    def cigar(self, name, *, deleted=False):
        return Cigar.objects.create(
            brand=self.brand.english_name, english_name=name,
            deleted_at=timezone.now() if deleted else None,
        )

    def batch(self, cigar, *, quantity, remaining=0, reversed=False, **extra):
        return create_purchase_batch(
            source=PurchaseBatch.Source.OPENING, cigar=cigar,
            quantity=quantity, remaining=remaining, physical_remaining=remaining,
            box_size=None, unit_cost_cny=Decimal("1.00"),
            reversed_at=timezone.now() if reversed else None,
            reversed_quantity=quantity if reversed else 0,
            **extra,
        )

    def product_ids(self, rows):
        return {row["id"] for row in rows}

    def test_never_stocked_stays_directly_accessible_but_is_not_discoverable(self):
        historical = self.cigar("Previously stocked")
        self.batch(historical, quantity=10, remaining=0)
        never_stocked = self.cigar("Directory only")
        ProductListing.objects.create(cigar=never_stocked, published=True)

        pages = build_pages()
        brand_page = pages[f"/brand/{self.brand.slug}"]
        catalog = pages["/catalog"]
        direct_path = f"/cigar/{never_stocked.pk}/history-brand-directory-only"
        self.assertIn(direct_path, pages)
        self.assertEqual(self.product_ids(brand_page["products"]), {historical.pk})
        self.assertEqual(self.product_ids(catalog["products"]), {historical.pk})
        self.assertEqual(search_products("Directory only", pages=pages), [])
        self.assertNotIn(never_stocked.pk, public_dependencies()["known_inventory"])

    def test_unlisted_and_positive_adjustment_only_history_appears_without_offers(self):
        adjusted = self.cigar("Adjusted stock history")
        self.batch(adjusted, quantity=0, positive_adjustment_quantity=5)

        pages = build_pages()
        catalog_product = next(row for row in pages["/catalog"]["products"] if row["id"] == adjusted.pk)
        brand_product = next(row for row in pages[f"/brand/{self.brand.slug}"]["products"] if row["id"] == adjusted.pk)
        self.assertEqual(catalog_product["availability"], "catalog")
        self.assertEqual(catalog_product["offers"], [])
        self.assertEqual(brand_product["availability"], "catalog")
        self.assertEqual(brand_product["offers"], [])

    def test_catalog_includes_current_stock_for_cigar_with_unregistered_brand(self):
        cigar = Cigar.objects.create(brand="Unregistered Brand", english_name="Current stock")
        self.batch(cigar, quantity=5, remaining=5)
        ProductListing.objects.create(cigar=cigar, published=True)

        pages = build_pages()
        self.assertEqual(pages["/catalog"]["total_products"], 1)
        self.assertEqual(self.product_ids(pages["/catalog"]["products"]), {cigar.pk})
        self.assertFalse(any(page["kind"] == "brand" and page["products"] for page in pages.values()))

    def test_cached_discovery_page_is_rejected_when_its_history_is_reversed(self):
        cigar = self.cigar("Reversal invalidates discovery")
        batch = self.batch(cigar, quantity=5)
        ProductListing.objects.create(cigar=cigar, published=True)
        cached = build_pages()["/catalog"]
        self.assertTrue(allowed_payload(cached))

        force_inventory_update(PurchaseBatch.objects.filter(pk=batch.pk),
                               reversed_at=timezone.now(), reversed_quantity=5,
                               reversed_cost_cny=batch.original_cost_cny)
        self.assertFalse(allowed_payload(cached))
        self.assertEqual(build_pages()["/catalog"]["products"], [])

    def test_zero_reversed_and_deleted_batches_do_not_create_discoverable_history(self):
        zero = self.cigar("Zero quantity")
        self.batch(zero, quantity=0)
        reversed_cigar = self.cigar("Reversed stock")
        self.batch(reversed_cigar, quantity=5, reversed=True)
        deleted = self.cigar("Deleted stock", deleted=True)
        self.batch(deleted, quantity=5)

        pages = build_pages()
        visible_ids = self.product_ids(pages[f"/brand/{self.brand.slug}"]["products"])
        self.assertEqual(visible_ids, set())
        self.assertEqual(pages["/catalog"]["products"], [])
        self.assertEqual(search_products("stock", pages=pages), [])

    def test_currently_stocked_brands_precede_priority_and_historical_brands(self):
        cohiba = Brand.objects.create(english_name="Cohiba", name="高希霸")
        zulu = Brand.objects.create(english_name="Zulu Brand", name="祖鲁")
        alpha = Brand.objects.create(english_name="Alpha Brand", name="阿尔法")
        for brand, name, quantity, remaining in (
            (cohiba, "Old Cohiba", 5, 0),
            (zulu, "Old Zulu", 5, 0),
            (alpha, "Current Alpha", 5, 5),
        ):
            cigar = Cigar.objects.create(brand=brand.english_name, english_name=name)
            self.batch(cigar, quantity=quantity, remaining=remaining)
            ProductListing.objects.create(cigar=cigar, published=True)

        pages = build_pages()
        nav_slugs = [row["slug"] for row in pages["/catalog"]["navigation"]["brands"]]
        self.assertLess(nav_slugs.index(alpha.slug), nav_slugs.index(cohiba.slug))
        self.assertLess(nav_slugs.index(cohiba.slug), nav_slugs.index(zulu.slug))
        home_slugs = [row["slug"] for row in pages["/"]["brands"]]
        self.assertEqual(set(home_slugs), {cohiba.slug, zulu.slug, alpha.slug})
