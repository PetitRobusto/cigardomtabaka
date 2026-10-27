from decimal import Decimal
from django.db import IntegrityError, transaction
from django.http import QueryDict

from django.test import TestCase, override_settings
from unittest.mock import patch

from cigars.models import Brand, Cigar, CigarPrice
from storefront.catalog import allowed_payload, browse_page, build_pages
from storefront.models import ProductListing, StoreTranslation


@override_settings(STOREFRONT_ENABLED=True)
class StorefrontSeoPayloadAdditionTests(TestCase):
    def setUp(self):
        self.cohiba = Brand.objects.create(english_name="Cohiba", name="高希霸", slug="cohiba")
        self.trinidad = Brand.objects.create(english_name="Trinidad", name="特立尼达", slug="trinidad")
        StoreTranslation.objects.create(kind="home", key="home", locale="zh", title="Home",
                                        description="Home description", body="Home body", published=True)

    def add_product(self, brand, english_name, *, published=True, withdrawn=False, retail_price=None,
                    release_type="", release_name=""):
        cigar = Cigar.objects.create(brand=brand.english_name, english_name=english_name,
                                     release_type=release_type, release_name=release_name)
        ProductListing.objects.create(cigar=cigar, published=published, withdrawn=withdrawn)
        if retail_price is not None:
            CigarPrice.objects.create(cigar=cigar, box_size=25, wholesale_price=100,
                                      retail_price_rub=Decimal(retail_price))
        return cigar

    def test_hero_links_resolve_fixed_official_identities_in_each_locale(self):
        cigars = [
            self.add_product(self.cohiba, "BHK 56"),
            self.add_product(self.cohiba, "Siglo VI"),
            self.add_product(self.trinidad, "Casilda", release_type="Habanos Collection Series",
                             release_name="Casilda"),
            self.add_product(self.cohiba, "BHK 52"),
            self.add_product(self.trinidad, "Ingenios", release_type="Limited Edition Series",
                             release_name="Ingenios"),
        ]
        pages = build_pages()
        for locale, prefix in (("zh", ""), ("ru", "/ru"), ("en", "/en")):
            with self.subTest(locale=locale):
                links = pages[prefix + "/"]["hero_links"]
                self.assertEqual(list(links), ["bhk56", "siglo", "casilda", "bhk52", "ingenios"])
                for cigar, slot in zip(cigars, links):
                    target = links[slot]
                    self.assertTrue(target.startswith(f"{prefix}/cigar/{cigar.pk}/"))
                    self.assertEqual(pages[target]["product"]["id"], cigar.pk)

    def test_hero_falls_back_for_unpublished_withdrawn_and_missing_models(self):
        hidden = self.add_product(self.cohiba, "BHK 56", published=False)
        self.add_product(self.cohiba, "Other Cohiba")
        self.add_product(self.trinidad, "Other Trinidad")
        pages = build_pages()
        self.assertEqual(pages["/"]["hero_links"]["bhk56"], "/brand/cohiba")
        self.assertNotIn(f"/cigar/{hidden.pk}/cohiba-bhk-56", pages)

        ProductListing.objects.filter(cigar__brand="Cohiba").update(withdrawn=True)
        pages = build_pages()
        self.assertEqual(pages["/"]["hero_links"]["bhk56"], "/catalog")
        self.assertFalse(allowed_payload({**build_pages()["/"], "hero_links": {"bhk56": "/brand/cohiba"}}))

    def test_same_name_public_special_release_does_not_replace_missing_hero_version(self):
        self.add_product(self.cohiba, "BHK 56", release_type="Commemorative Release",
                         release_name="Anniversary")
        self.add_product(self.cohiba, "Siglo VI", release_type="Duty Free and Travel Retail Series",
                         release_name="Siglo VI")
        pages = build_pages()
        self.assertEqual(pages["/"]["hero_links"]["bhk56"], "/brand/cohiba")
        self.assertEqual(pages["/"]["hero_links"]["siglo"], "/brand/cohiba")

    def test_casilda_and_ingenios_use_the_matching_release_identity(self):
        self.add_product(self.trinidad, "Casilda", release_type="Other Series", release_name="Casilda")
        self.add_product(self.trinidad, "Casilda", release_type="Habanos Collection Series",
                         release_name="Casilda")
        self.add_product(self.trinidad, "Ingenios", release_type="Other Series", release_name="Ingenios")
        self.add_product(self.trinidad, "Ingenios", release_type="Limited Edition Series",
                         release_name="Ingenios")
        pages = build_pages()
        self.assertIn("trinidad-casilda-habanos-collection-series-casilda",
                      pages["/"]["hero_links"]["casilda"])
        self.assertIn("trinidad-ingenios-limited-edition-series-ingenios",
                      pages["/"]["hero_links"]["ingenios"])

    def test_withdrawn_hero_target_invalidates_old_cached_home_payload(self):
        cigar = self.add_product(self.cohiba, "BHK 56")
        cached = build_pages()["/ru/"]
        self.assertTrue(allowed_payload(cached))
        ProductListing.objects.filter(cigar=cigar).update(withdrawn=True)
        self.assertFalse(allowed_payload(cached))

    def test_catalog_price_filter_option_uses_all_public_offers_across_pages(self):
        first = self.add_product(self.cohiba, "No price")
        priced = self.add_product(self.trinidad, "Public price", retail_price="0.01")
        self.add_product(self.trinidad, "No price 2")
        with patch("storefront.catalog.PAGE_SIZE", 1):
            pages = build_pages()
        self.assertEqual(pages["/catalog"]["products"][0]["id"], first.pk)
        self.assertTrue(pages["/catalog"]["filter_options"]["has_prices"])
        self.assertTrue(pages["/brand/trinidad"]["filter_options"]["has_prices"])
        # The option is based on the complete catalog, even when the current page has no priced card.
        self.assertTrue(pages["/catalog?page=2"]["filter_options"]["has_prices"])
        self.assertIn(priced.pk, {p["id"] for page in pages.values()
                                  if page["path"].split("?", 1)[0] == "/catalog"
                                  for p in page["products"]})
        empty = browse_page(pages["/catalog"], QueryDict("q=zzzzzz"), pages)
        self.assertEqual(empty["products"], [])
        self.assertTrue(empty["filter_options"]["has_prices"])
        price_filtered = browse_page(pages["/catalog"], QueryDict("price_min=.01"), pages)
        self.assertTrue(price_filtered["filter_options"]["has_prices"])
        self.assertEqual(price_filtered["filters"]["price_min"], ".01")
        self.assertEqual([p["id"] for p in price_filtered["products"]], [priced.pk])

    def test_catalog_price_filter_option_is_false_without_a_public_price(self):
        self.add_product(self.cohiba, "Only unpriced")
        pages = build_pages()
        self.assertFalse(pages["/catalog"]["filter_options"]["has_prices"])

    def test_zero_ruble_price_remains_invalid_under_current_contract(self):
        cigar = self.add_product(self.cohiba, "Zero is not a public price")
        with self.assertRaises(IntegrityError), transaction.atomic():
            CigarPrice.objects.create(cigar=cigar, box_size=25, wholesale_price=100,
                                      retail_price_rub=Decimal("0.00"))
