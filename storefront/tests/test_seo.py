from copy import deepcopy

from django.test import SimpleTestCase

from storefront.seo import enrich_page_metadata


class StorefrontSeoTests(SimpleTestCase):
    def page(self, **overrides):
        return {
            "locale": "en", "kind": "product", "path": "/en/cigar/1/cohiba-genios",
            "title": "Genios", "description": "Reviewed product description.",
            "body": "Reviewed body.", "site": {"name": "CigarDomTabaka"},
            "product": {"name": "Genios", "english_name": "Genios", "brand": "Cohiba",
                        "vitola": "Robusto", "length": 140, "ring_gauge": 52,
                        "availability": "out_of_stock", "offers": []},
            "breadcrumbs": [{"label": "Genios", "path": "/en/cigar/1/cohiba-genios"}],
            "pagination": {"page": 1},
            **overrides,
        }

    def enrich(self, page):
        enrich_page_metadata({page["path"]: page})
        return page

    def test_product_titles_use_local_moscow_wording_without_changing_display_or_reviewed_content(self):
        expected_by_locale = {
            "zh": "Cohiba Genios — 莫斯科雪茄 | CigarDomTabaka",
            "ru": "Cohiba Genios — сигары в Москве | CigarDomTabaka",
            "en": "Cohiba Genios — Cigars in Moscow | CigarDomTabaka",
        }
        for locale, expected in expected_by_locale.items():
            with self.subTest(locale=locale):
                page = self.page(locale=locale)
                original = deepcopy(page)
                self.enrich(page)
                self.assertEqual(page["seo_title"], expected)
                self.assertEqual({key: value for key, value in page.items() if key != "seo_title"}, original)

    def test_product_search_title_is_independent_of_specs_price_and_stock(self):
        expected = "Cohiba Genios — Cigars in Moscow | CigarDomTabaka"
        variants = [
            {"vitola": "Robusto", "length": 140, "ring_gauge": 52,
             "offers": [], "availability": "out_of_stock"},
            {"vitola": "", "length": None, "ring_gauge": None,
             "offers": [{"price_rub": "123.45", "in_stock": True}], "availability": "in_stock"},
            {"vitola": "Churchill", "length": 200, "ring_gauge": 60,
             "offers": [{"price_rub": "0", "in_stock": False}], "availability": "out_of_stock"},
        ]
        for product_data in variants:
            with self.subTest(product_data=product_data):
                page = self.page()
                page["product"].update(product_data)
                self.enrich(page)
                self.assertEqual(page["seo_title"], expected)

    def test_brand_is_not_duplicated_for_existing_case_or_punctuation_variants(self):
        page = self.page()
        page["product"].update(name="H. UPMANN No. 2", brand="H Upmann")
        self.enrich(page)
        self.assertEqual(page["seo_title"], "H. UPMANN No. 2 — Cigars in Moscow | CigarDomTabaka")

    def test_brand_matching_does_not_confuse_partial_words(self):
        page = self.page()
        page["product"].update(name="Cohibana", brand="Cohiba")
        self.enrich(page)
        self.assertEqual(page["seo_title"], "Cohiba Cohibana — Cigars in Moscow | CigarDomTabaka")

    def test_chinese_brand_without_separating_whitespace_is_not_duplicated(self):
        page = self.page(locale="zh")
        page["product"].update(name="高希霸世纪二号", brand="高希霸")
        self.enrich(page)
        self.assertEqual(page["seo_title"], "高希霸世纪二号 — 莫斯科雪茄 | CigarDomTabaka")

    def test_product_names_with_accents_and_embedded_brand_are_not_duplicated(self):
        page = self.page()
        page["product"].update(name="Cohiba Mágicos Maduro 5", brand="Cohiba")
        self.enrich(page)
        self.assertEqual(page["seo_title"], "Cohiba Mágicos Maduro 5 — Cigars in Moscow | CigarDomTabaka")

    def test_home_preserves_reviewed_title_without_repeating_site(self):
        for title in ["Cigars in Moscow | CigarDomTabaka", "Cigars in Moscow"]:
            with self.subTest(title=title):
                page = self.page(kind="home", title=title, product=None)
                self.enrich(page)
                self.assertEqual(page["seo_title"], "Cigars in Moscow | CigarDomTabaka")
                self.assertEqual(page["title"], title)
                self.assertEqual(page["description"], "Reviewed product description.")

    def test_brand_titles_and_pagination_are_localized_without_rewriting_paths(self):
        for locale, title, number_label in [("zh", "Cohiba雪茄 — 莫斯科", "第 2 页"), ("ru", "Сигары Cohiba в Москве", "Страница 2"), ("en", "Cohiba cigars in Moscow", "Page 2")]:
            with self.subTest(locale=locale):
                page = self.page(locale=locale, kind="brand", title="Cohiba", product=None,
                                 path="/brand/cohiba?page=2", pagination={"page": 2})
                self.enrich(page)
                self.assertEqual(page["seo_title"], f"{title} — {number_label} | CigarDomTabaka")
                self.assertEqual(page["path"], "/brand/cohiba?page=2")
                self.assertEqual(page["description"], "Reviewed product description.")

    def test_russian_brand_local_title_preserves_visible_content_and_other_page_types(self):
        for brand in ["Cohiba", "H. Upmann"]:
            with self.subTest(brand=brand):
                page = self.page(locale="ru", kind="brand", title=brand, product=None)
                original = deepcopy(page)
                self.enrich(page)
                self.assertEqual(page["seo_title"], f"Сигары {brand} в Москве | CigarDomTabaka")
                self.assertEqual({key: value for key, value in page.items() if key != "seo_title"}, original)
        product = self.enrich(self.page(locale="ru"))
        self.assertEqual(product["seo_title"], "Cohiba Genios — сигары в Москве | CigarDomTabaka")

    def test_catalogue_has_own_description_and_paginated_search_title(self):
        for locale, label, number_label in [("zh", "雪茄目录", "第 3 页"), ("ru", "Каталог сигар", "Страница 3"), ("en", "Cigar catalogue", "Page 3")]:
            with self.subTest(locale=locale):
                page = self.page(locale=locale, kind="home", view="catalog", title="Display catalogue",
                                 product=None, path="/catalog?page=3", pagination={"page": 3})
                self.enrich(page)
                self.assertEqual(page["seo_title"], f"{label} — {number_label} | CigarDomTabaka")
                self.assertIn("CigarDomTabaka", page["description"])
                self.assertNotEqual(page["description"], "Reviewed product description.")
                self.assertEqual(page["title"], "Display catalogue")

    def test_incomplete_product_uses_localized_title_and_fallback_site(self):
        page = self.page(product={"english_name": "Genios"}, site={})
        self.enrich(page)
        self.assertEqual(page["seo_title"], "Genios — Cigars in Moscow | CigarDomTabaka")

    def test_new_products_receive_localized_title_without_a_product_specific_override(self):
        for locale, expected in [
            ("zh", "H. Upmann Half Corona — 莫斯科雪茄 | CigarDomTabaka"),
            ("ru", "H. Upmann Half Corona — сигары в Москве | CigarDomTabaka"),
            ("en", "H. Upmann Half Corona — Cigars in Moscow | CigarDomTabaka"),
        ]:
            with self.subTest(locale=locale):
                page = self.page(locale=locale, title="Half Corona", product={
                    "name": "Half Corona", "english_name": "Half Corona", "brand": "H. Upmann",
                })
                self.enrich(page)
                self.assertEqual(page["seo_title"], expected)

    def test_enrichment_is_idempotent(self):
        page = self.page(kind="brand", title="Cohiba", product=None, pagination={"page": 2})
        self.enrich(page)
        original = deepcopy(page)
        self.enrich(page)
        self.assertEqual(page, original)

    def test_reviewed_override_only_changes_search_title_for_all_page_kinds(self):
        for kind in ('home', 'brand', 'product'):
            with self.subTest(kind=kind):
                page = self.page(kind=kind, seo_title_override='Cohiba Mágicos in Moscow')
                original = deepcopy(page)
                self.enrich(page)
                self.assertEqual(page['seo_title'], 'Cohiba Mágicos in Moscow | CigarDomTabaka')
                self.assertEqual({k: v for k, v in page.items() if k != 'seo_title'}, original)
                self.enrich(page)
                self.assertEqual(page['seo_title'], 'Cohiba Mágicos in Moscow | CigarDomTabaka')

    def test_override_normalizes_suffix_before_pagination_and_empty_uses_fallback(self):
        page = self.page(seo_title_override='Mágicos | cigardomtabaka | CigarDomTabaka', pagination={'page': 2})
        self.enrich(page)
        self.assertEqual(page['seo_title'], 'Mágicos — Page 2 | CigarDomTabaka')
        for value in ('', '  '):
            page = self.enrich(self.page(seo_title_override=value))
            self.assertEqual(page['seo_title'], 'Cohiba Genios — Cigars in Moscow | CigarDomTabaka')

    def test_derived_catalog_does_not_inherit_home_override(self):
        page = self.enrich(self.page(kind='home', view='catalog', seo_title_override='Homepage only'))
        self.assertEqual(page['seo_title'], 'Cigar catalogue | CigarDomTabaka')
