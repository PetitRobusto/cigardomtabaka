"""Requests must not rebuild unrelated legacy details or serve stale stock."""
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, override_settings

from cigars.models import Brand, Cigar, CigarPrice, PurchaseBatch
from cigars.tests.inventory_fixtures import create_purchase_batch, force_inventory_update
from storefront import catalog
from storefront.models import ProductListing, StoreTranslation


@override_settings(STOREFRONT_ENABLED=True)
class RequestCatalogTests(TestCase):
    def setUp(self):
        self.brand = Brand.objects.create(english_name="Cohiba", name="高希霸")
        self.cigars = Cigar.objects.bulk_create([
            Cigar(brand="Cohiba", english_name=f"Stock {i}", name=f"现货 {i}")
            for i in range(3)
        ])
        self.directory = Cigar.objects.bulk_create([
            Cigar(brand="Cohiba", english_name=f"Directory {i}") for i in range(40)
        ])
        for cigar in self.cigars:
            create_purchase_batch(source="opening", cigar=cigar, quantity=25,
                                  remaining=25, physical_remaining=25, box_size=25,
                                  unit_cost_cny=Decimal("1"))
            ProductListing.objects.create(cigar=cigar, published=True)
        for locale in ("zh", "en", "ru"):
            for kind, key in (("home", "home"), ("brand", self.brand.slug)):
                StoreTranslation.objects.create(kind=kind, key=key, locale=locale,
                    title=f"Reviewed {kind}", description="Reviewed description",
                    body="Reviewed body", published=True)
        # Intentionally incomplete translation coverage must keep fallback SEO.
        StoreTranslation.objects.create(kind="product", key=str(self.cigars[0].pk),
            locale="en", title="Reviewed product", description="Reviewed description",
            body="Reviewed body", published=True)

    def test_scoped_build_matches_full_payloads_and_filtered_pagination(self):
        from django.http import QueryDict
        with patch("storefront.catalog.PAGE_SIZE", 1):
            full = catalog.build_pages()
            directory_path = f"/ru/cigar/{self.directory[0].pk}/old-slug"
            for requested in ("/", "/en/catalog", "/ru/brand/cohiba", directory_path,
                              f"/cigar/{self.cigars[0].pk}", "/missing"):
                with self.subTest(requested=requested):
                    scoped = catalog.build_pages(requested_path=requested)
                    self.assertEqual(catalog.resolve_path(requested, scoped),
                                     catalog.resolve_path(requested, full))
                    for path, payload in scoped.items():
                        self.assertEqual(payload, full[path], path)
                    for base in ("/", "/en/catalog", "/ru/brand/cohiba"):
                        params = QueryDict("q=Stock&sort=name&page=2&box=25")
                        self.assertEqual(catalog.browse_page(scoped[base], params, scoped),
                                         catalog.browse_page(full[base], params, full))

    def test_request_never_materializes_unrelated_directory_products(self):
        target = self.directory[0]
        with patch("storefront.catalog._product_data", wraps=catalog._product_data) as build:
            response = self.client.get("/api/storefront/page/", {
                "path": f"/en/cigar/{target.pk}/old-slug",
            })
        self.assertEqual(response.status_code, 404)
        built_ids = {call.args[0].pk for call in build.call_args_list}
        self.assertEqual(built_ids, {c.pk for c in self.cigars})

    def test_requests_read_price_stock_and_withdrawal_changes_immediately(self):
        cigar = self.cigars[0]
        path = f"/cigar/{cigar.pk}/cohiba-stock-0"
        price = CigarPrice.objects.create(cigar=cigar, box_size=25, wholesale_price=1,
                                         retail_price=1,
                                         retail_price_rub=Decimal("100"))
        def product():
            return self.client.get("/api/storefront/page/", {"path": path}).json()["product"]
        self.assertEqual(product()["offers"][0]["price_rub"], "100.00")
        price.retail_price_rub = Decimal("200")
        price.save(update_fields=["retail_price_rub"])
        self.assertEqual(product()["offers"][0]["price_rub"], "200.00")
        force_inventory_update(PurchaseBatch.objects.filter(cigar=cigar),
                               remaining=0, physical_remaining=0,
                               available_box_quantity=0, physical_box_quantity=0)
        self.assertEqual(product()["availability"], "out_of_stock")
        ProductListing.objects.filter(cigar=cigar).update(withdrawn=True, published=False)
        self.assertEqual(self.client.get("/api/storefront/page/", {"path": path}).status_code, 404)
        self.assertEqual(self.client.get(path).status_code, 404)

    def test_oversized_missing_product_id_is_404(self):
        response = self.client.get("/api/storefront/page/", {
            "path": "/en/cigar/" + "9" * 100 + "/missing",
        })
        self.assertEqual(response.status_code, 404)
