from unittest.mock import patch

from django.http import QueryDict
from django.test import SimpleTestCase

from storefront.catalog import browse_page


class BrowseFilterTests(SimpleTestCase):
    def setUp(self):
        self.products = [
            {"id": 1, "name": "Mixed", "brand_slug": "cohiba", "length": 150, "ring_gauge": 52,
             "offers": [{"box_size": 10, "price_rub": "100.00", "in_stock": True},
                        {"box_size": 25, "price_rub": "250.00", "in_stock": False}]},
            {"id": 2, "name": "Large", "brand_slug": "cohiba", "length": 166, "ring_gauge": 56,
             "offers": [{"box_size": 25, "price_rub": "500.25", "in_stock": True}]},
            {"id": 3, "name": "Inquiry", "brand_slug": "trinidad", "length": None, "ring_gauge": None,
             "offers": [{"box_size": None, "sale_unit": "stick", "price_rub": None, "in_stock": True}]},
            {"id": 4, "name": "Directory", "brand_slug": "trinidad", "length": 120, "ring_gauge": 40, "offers": []},
        ]
        self.page = {"path": "/catalog", "locale": "en", "products": self.products[:2]}
        self.pages = {"/catalog": self.page, "/catalog?page=2": {**self.page, "path": "/catalog?page=2", "products": self.products[2:]}}

    def browse(self, query):
        return browse_page(self.page, QueryDict(query), self.pages)

    def ids(self, query):
        return [p["id"] for p in self.browse(query)["products"]]

    def test_dimensions_use_inclusive_bounds_and_exclude_unknown_values(self):
        self.assertEqual(self.ids("length_min=150&length_max=166&ring_min=52&ring_max=56"), [1, 2])
        self.assertEqual(self.ids("length_max=150&ring_max=50"), [4])
        self.assertEqual(self.ids("length_min=166&length_max=150"), [])
        self.assertEqual(self.ids("ring_min=56&ring_max=52"), [])

    def test_price_packaging_and_stock_match_one_offer(self):
        self.assertEqual(self.ids("price_min=250&price_max=500.25"), [1, 2])
        self.assertEqual(self.ids("price_min=250&price_max=500.25&stock_only=1"), [2])
        self.assertEqual(self.ids("box=25&stock_only=1"), [2])
        self.assertEqual(self.ids("box=10&price_min=200"), [])
        self.assertEqual(self.ids("box=25&price_max=200"), [])
        self.assertEqual(self.ids("price_min=500.25&price_max=500.25"), [2])
        self.assertEqual(self.ids("price_min=500.26&price_max=500.25"), [])
        self.assertEqual(self.ids("stock_only=1"), [1, 2, 3])
        self.assertEqual(self.ids("stock_only=0"), [1, 2, 3, 4])
        self.assertEqual(self.ids("price_min=0"), [1, 2])
        self.assertEqual(self.ids("box=stick&price_min=0"), [])

    def test_malformed_ranges_are_ignored_without_crashing_or_retaining_invalid_chips(self):
        for value in ("NaN", "Infinity", "-1", "1e5", "abc", "9" * 100, "1.234"):
            with self.subTest(value=value):
                page = self.browse(f"price_min={value}&ring_max={value}&length_min={value}")
                self.assertEqual(page["total_products"], 4)
                self.assertNotIn("price_min", page["filters"])
                self.assertNotIn("length_min", page["filters"])

    def test_filters_apply_before_pagination_and_survive_next_previous_links(self):
        with patch("storefront.catalog.PAGE_SIZE", 1):
            first = self.browse("brand=cohiba&length_min=140&ring_max=56&price_min=0&stock_only=1&sort=length")
            self.assertEqual(first["total_products"], 2)
            self.assertEqual(first["products"][0]["id"], 1)
            next_query = first["pagination"]["next"].split("?", 1)[1]
            second = self.browse(next_query)
            self.assertEqual(second["products"][0]["id"], 2)
            self.assertEqual(first["filters"], second["filters"])
            self.assertIn("stock_only=1", second["pagination"]["previous"])
            self.assertIn("price_min=0", second["pagination"]["previous"])
