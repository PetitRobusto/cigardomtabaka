"""Anonymous storefront access follows explicit product publication only."""

from decimal import Decimal
from xml.etree.ElementTree import fromstring

from django.test import TestCase, override_settings
from django.utils import timezone

from cigars.models import Brand, Cigar, PurchaseBatch
from cigars.tests.inventory_fixtures import create_purchase_batch
from storefront.catalog import build_pages, semantic_hash
from storefront.models import ProductListing, StorePage, StoreTranslation


@override_settings(STOREFRONT_ENABLED=True, STOREFRONT_ORIGIN="http://testserver")
class PublicCatalogBoundaryTests(TestCase):
    def setUp(self):
        self.brand = Brand.objects.create(english_name="Cohiba", name="高希霸", slug="cohiba")
        StoreTranslation.objects.create(
            kind="home", key="home", locale="zh", title="首页",
            description="商城介绍", body="商城正文", published=True,
        )
        self.unpublished = Cigar.objects.create(brand="Cohiba", english_name="Private directory cigar")
        ProductListing.objects.create(cigar=self.unpublished, published=False)
        StoreTranslation.objects.create(
            kind="product", key=str(self.unpublished.pk), locale="en",
            title="Reviewed private product", description="Private summary",
            body="Private content", published=True,
        )
        create_purchase_batch(source=PurchaseBatch.Source.OPENING, cigar=self.unpublished,
                              quantity=5, remaining=5, physical_remaining=5, box_size=25,
                              unit_cost_cny=Decimal("1.00"))
        self.private_brand = Brand.objects.create(english_name="Private Brand", name="内部品牌", slug="private-brand")
        self.private_only = Cigar.objects.create(brand=self.private_brand.english_name,
                                                 english_name="Private only historical stock")
        create_purchase_batch(source=PurchaseBatch.Source.OPENING, cigar=self.private_only,
                              quantity=5, remaining=5, physical_remaining=5, box_size=25,
                              unit_cost_cny=Decimal("1.00"))
        self.draft = Cigar.objects.create(brand="Cohiba", english_name="Draft listing cigar")
        ProductListing.objects.create(cigar=self.draft, published=False)
        self.sold_out = Cigar.objects.create(brand="Cohiba", english_name="Published sold out")
        ProductListing.objects.create(cigar=self.sold_out, published=True)
        create_purchase_batch(source=PurchaseBatch.Source.OPENING, cigar=self.sold_out,
                              quantity=5, remaining=0, physical_remaining=0, box_size=25,
                              unit_cost_cny=Decimal("1.00"))
        self.no_history = Cigar.objects.create(brand="Cohiba", english_name="Published no history")
        ProductListing.objects.create(cigar=self.no_history, published=True)

    def save_page(self, path, payload):
        StorePage.objects.update_or_create(path=path, defaults={
            "active": True, "payload": payload, "rendered_payload": payload,
            "desired_hash": semantic_hash(payload), "rendered_hash": semantic_hash(payload),
            "html": f"<html><body>{path}</body></html>",
            "rendered_changed_at": timezone.now(),
        })

    def test_published_no_history_and_sold_out_products_are_public_but_directory_rows_are_not(self):
        pages = build_pages()
        expected = {self.sold_out.pk, self.no_history.pk}
        for locale, prefix in (("zh", ""), ("ru", "/ru"), ("en", "/en")):
            catalog = pages[f"{prefix}/catalog"]
            brand = pages[f"{prefix}/brand/cohiba"]
            self.assertEqual({item["id"] for item in catalog["products"]}, expected)
            self.assertEqual({item["id"] for item in brand["products"]}, expected)
            self.assertIn(f"{prefix}/cigar/{self.no_history.pk}/cohiba-published-no-history", pages)
            self.assertEqual(pages[f"{prefix}/cigar/{self.sold_out.pk}/cohiba-published-sold-out"]["product"]["availability"], "out_of_stock")
            self.assertNotIn(f"{prefix}/cigar/{self.unpublished.pk}/cohiba-private-directory-cigar", pages)
            self.assertNotIn(f"{prefix}/cigar/{self.draft.pk}/cohiba-draft-listing-cigar", pages)
            self.assertNotIn(f"{prefix}/cigar/{self.private_only.pk}/private-brand-private-only-historical-stock", pages)
            self.assertNotIn(f"{prefix}/brand/private-brand", pages)

        # Home discovery remains based on current stock, even though the catalog
        # and brand landing pages contain every explicitly published product.
        self.assertEqual([item["id"] for item in pages["/"]["products"]], [])
        self.assertEqual([item["id"] for item in pages["/"]["latest_products"]], [])
        self.assertEqual([item["slug"] for item in pages["/"]["navigation"]["brands"]], ["cohiba"])
        self.assertNotIn(self.private_only.pk, [item["id"] for item in pages["/"]["latest_products"]])

        results = self.client.get("/api/storefront/search/", {"q": "Published", "locale": "en"})
        self.assertEqual(results.status_code, 200)
        self.assertEqual({item["id"] for item in results.json()["products"]}, expected)
        hidden = self.client.get("/api/storefront/search/", {"q": "Private directory", "locale": "en"})
        self.assertEqual(hidden.json()["products"], [])

    def test_unpublished_and_draft_direct_html_and_api_paths_return_404(self):
        for cigar in (self.unpublished, self.draft):
            slug = cigar.english_name.lower().replace(" ", "-")
            path = f"/en/cigar/{cigar.pk}/cohiba-{slug}"
            with self.subTest(path=path):
                self.assertEqual(self.client.get("/api/storefront/page/", {"path": path}).status_code, 404)
                self.assertEqual(self.client.get(path).status_code, 404)

    def test_unpublishing_revokes_cached_detail_and_cards_and_revalidates_warm_sitemap(self):
        pages = build_pages()
        target_path = f"/cigar/{self.no_history.pk}/cohiba-published-no-history"
        paths = [target_path, "/brand/cohiba", "/catalog"]
        for path in paths:
            self.save_page(path, pages[path])
            self.assertEqual(self.client.get(path).status_code, 200)
        before = self.client.get("/sitemap-storefront.xml")
        self.assertEqual(before.status_code, 200)
        self.assertIn(target_path, before.content.decode())

        listing = ProductListing.objects.get(cigar=self.no_history)
        listing.published = False
        listing.save(update_fields=["published"])

        for path in paths:
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 404 if path == target_path else 503)
        after = self.client.get("/sitemap-storefront.xml", HTTP_IF_NONE_MATCH=before["ETag"])
        self.assertEqual(after.status_code, 200)
        urls = {element.text.removeprefix("http://testserver") for element in fromstring(after.content).iter()
                if element.tag.endswith("}loc")}
        self.assertNotIn(target_path, urls)
        self.assertNotIn(target_path, after.content.decode())
