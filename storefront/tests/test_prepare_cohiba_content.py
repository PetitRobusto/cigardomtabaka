import io
import json
import shutil
import tempfile
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest import skipUnless
from unittest.mock import patch

from bs4 import BeautifulSoup
from django.conf import settings
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings

from cigars.models import Brand, Cigar, CigarPrice, PurchaseBatch, StockMovement
from cigars.tests.inventory_fixtures import create_purchase_batch
from storefront.catalog import build_pages
from storefront.languages import HOME_COPY
from storefront.management.commands.prepare_cohiba_content import Command, read_content
from storefront.management.commands.prepare_storefront_localizations import _brand_translation, _product_translation
from storefront.models import ProductListing, StoreTranslation
from storefront.publishing import build_assets, render_batch


@override_settings(DEBUG=True)
class PrepareCohibaContentTests(TestCase):
    def setUp(self):
        self.content = read_content()
        self.brand = Brand.objects.create(english_name="Cohiba", name="高希霸", slug="cohiba")
        self.cigars = {}
        for entry, name, vitola in zip(self.content["products"],
                                      ["天才", "魔术师", "世纪 2 号", "世纪 3 号"],
                                      ["Genios 5", "Mágicos", "Marevas", "Coronas Grandes"]):
            cigar = Cigar.objects.create(pk=entry["id"], brand="Cohiba", name=name,
                                         english_name=entry["english_name"], length=entry["length"],
                                         ring_gauge=entry["ring_gauge"], vitola=vitola)
            self.cigars[cigar.pk] = cigar
            ProductListing.objects.create(cigar=cigar, published=True)
            if cigar.pk != 102:
                CigarPrice.objects.create(cigar=cigar, box_size=entry["box_size"],
                                          wholesale_price=2345, retail_price=3456, can_preorder=True)
            for locale in ("ru", "zh", "en"):
                StoreTranslation.objects.create(kind="product", key=str(cigar.pk), locale=locale,
                                                published=True, **_product_translation(cigar, locale))
        for locale in ("ru", "zh", "en"):
            StoreTranslation.objects.create(kind="brand", key="cohiba", locale=locale,
                                            published=True, **_brand_translation(self.brand, locale))

    def run_command(self, apply=False):
        out = io.StringIO()
        call_command("prepare_cohiba_content", apply=apply, stdout=out)
        return json.loads(out.getvalue())

    def snapshot(self):
        return {
            model._meta.label: list(model.objects.order_by("pk").values())
            for model in (Cigar, CigarPrice, ProductListing, StoreTranslation, PurchaseBatch, StockMovement)
        }

    def test_dry_run_reports_exact_scope_and_writes_nothing(self):
        before = self.snapshot()
        report = self.run_command()
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(report["changed_rows"], 19)
        self.assertEqual(len(report["translations"]), 15)
        genios = report["prices"][0]
        self.assertEqual((genios["id"], genios["box_size"], genios["action"]), (102, 10, "create"))
        self.assertEqual(genios["created_wholesale_cny_per_box"], 11000)
        self.assertEqual(genios["after_rub_per_box"], "130000.00")

    def test_content_only_never_reads_or_writes_prices_and_is_idempotent(self):
        before = self.snapshot()
        out = io.StringIO()
        with patch('storefront.management.commands.prepare_cohiba_content.CigarPrice.objects.select_for_update',
                   side_effect=AssertionError('Content-only must not access prices')):
            call_command('prepare_cohiba_content', content_only=True, apply=True, stdout=out)
        report = json.loads(out.getvalue())
        self.assertEqual(report['prices'], [])
        self.assertEqual(report['changed_rows'], 15)
        after = self.snapshot()
        for model in (Cigar, CigarPrice, ProductListing, PurchaseBatch, StockMovement):
            self.assertEqual(before[model._meta.label], after[model._meta.label])
        out = io.StringIO()
        call_command('prepare_cohiba_content', content_only=True, apply=True, stdout=out)
        self.assertEqual(json.loads(out.getvalue())['changed_rows'], 0)

    def test_supporting_articles_are_explicit_and_preserve_business_data(self):
        for pk, name, length, ring in [(105, 'BHK 52', 119, 52), (107, 'BHK 56', 166, 56)]:
            Cigar.objects.create(pk=pk, brand='Cohiba', english_name=name, length=length, ring_gauge=ring)
        before = self.snapshot()
        call_command('prepare_cohiba_content', content_only=True, include_supporting=True,
                     apply=True, stdout=io.StringIO())
        self.assertEqual(StoreTranslation.objects.filter(cigar_id__in=[105,107], published=False).count(), 6)
        call_command('prepare_cohiba_content', content_only=True, include_supporting=True,
                     publish_supporting=True, apply=True, stdout=io.StringIO())
        self.assertEqual(StoreTranslation.objects.filter(cigar_id__in=[105,107], published=True).count(), 6)
        after = self.snapshot()
        for model in (Cigar, CigarPrice, ProductListing, PurchaseBatch, StockMovement):
            self.assertEqual(before[model._meta.label], after[model._meta.label])
        # A changed identity aborts the entire batch without overwriting copy.
        Cigar.objects.filter(pk=107).update(length=1)
        before = self.snapshot()
        with self.assertRaises(CommandError):
            call_command('prepare_cohiba_content', content_only=True, include_supporting=True,
                         apply=True, stdout=io.StringIO())
        self.assertEqual(self.snapshot(), before)

    def test_apply_exact_prices_preserves_business_facts_and_second_apply_is_noop(self):
        unrelated = CigarPrice.objects.create(cigar=self.cigars[102], box_size=25,
                                               wholesale_price=9999, retail_price_rub=222222)
        before = self.snapshot()
        report = self.run_command(apply=True)
        self.assertEqual(report["changed_rows"], 19)
        for entry in self.content["products"]:
            price = CigarPrice.objects.get(cigar_id=entry["id"], box_size=entry["box_size"])
            self.assertEqual(price.retail_price_rub, Decimal(entry["retail_price_rub"]))
            self.assertEqual(price.wholesale_price, 11000 if entry["id"] == 102 else 2345)
            self.assertEqual(price.retail_price, None if entry["id"] == 102 else 3456)
            self.assertEqual(price.can_preorder, entry["id"] != 102)
        unrelated.refresh_from_db()
        self.assertEqual(unrelated.retail_price_rub, Decimal(222222))
        after = self.snapshot()
        for model in (Cigar, ProductListing, PurchaseBatch, StockMovement):
            self.assertEqual(before[model._meta.label], after[model._meta.label])
        self.assertEqual(self.run_command(apply=True)["changed_rows"], 0)
        self.assertEqual(self.snapshot(), after)  # Includes every updated_at.

    def test_existing_genios_cny_is_preserved_and_inactive_is_not_enabled(self):
        price = CigarPrice.objects.create(cigar=self.cigars[102], box_size=10,
                                          wholesale_price=8765, retail_price=9876, is_active=False)
        listing = ProductListing.objects.get(cigar_id=102)
        listing.published, listing.withdrawn = False, True
        listing.save()
        report = self.run_command(apply=True)
        price.refresh_from_db()
        listing.refresh_from_db()
        self.assertEqual((price.wholesale_price, price.retail_price, price.is_active), (8765, 9876, False))
        self.assertEqual((listing.published, listing.withdrawn), (False, True))
        self.assertFalse(report["prices"][0]["price_active"])
        self.assertTrue(report["prices"][0]["listing_withdrawn"])

    def test_last_price_conflict_aborts_entire_batch_including_genios_creation(self):
        CigarPrice.objects.filter(cigar_id=98).update(retail_price_rub=1)
        before = self.snapshot()
        with self.assertRaisesMessage(CommandError, "不同 RUB"):
            self.run_command(apply=True)
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(CigarPrice.objects.filter(cigar_id=102, box_size=10).exists())

    def test_custom_copy_alias_or_hours_is_never_overwritten(self):
        for field in ("title", "description", "body", "aliases", "hours"):
            with self.subTest(field=field):
                row = StoreTranslation.objects.get(kind="product", key="98", locale="zh")
                original = getattr(row, field)
                setattr(row, field, "用户自定义")
                row.save()
                before = self.snapshot()
                with self.assertRaisesMessage(CommandError, "自定义"):
                    self.run_command(apply=True)
                self.assertEqual(self.snapshot(), before)
                setattr(row, field, original)
                row.save()

    def test_other_missing_packaging_cannot_borrow_genios_wholesale(self):
        price = CigarPrice.objects.get(cigar_id=98)
        price.box_size = 10
        price.save()
        before = self.snapshot()
        with self.assertRaisesMessage(CommandError, "缺少 25 支盒"):
            self.run_command(apply=True)
        self.assertEqual(self.snapshot(), before)

    def test_deleted_or_wrong_identity_aborts(self):
        cigar = self.cigars[98]
        for field, changed in (("brand", "Other"), ("english_name", "Other"),
                               ("length", 140), ("ring_gauge", 52),
                               ("release_type", "limited"), ("release_name", "2024")):
            with self.subTest(field=field):
                original = getattr(cigar, field)
                Cigar.objects.filter(pk=cigar.pk).update(**{field: changed})
                before = self.snapshot()
                with self.assertRaisesMessage(CommandError, "身份或尺寸"):
                    self.run_command(apply=True)
                self.assertEqual(self.snapshot(), before)
                Cigar.objects.filter(pk=cigar.pk).update(**{field: original})
        from django.utils import timezone
        Cigar.objects.filter(pk=98).update(deleted_at=timezone.now())
        with self.assertRaisesMessage(CommandError, "身份或尺寸"):
            self.run_command(apply=True)

    def test_missing_translation_is_draft_and_existing_draft_stays_draft(self):
        StoreTranslation.objects.filter(kind="product", key="102", locale="ru").delete()
        StoreTranslation.objects.filter(kind="product", key="103", locale="zh").update(published=False)
        self.run_command(apply=True)
        for key, locale in (("102", "ru"), ("103", "zh")):
            self.assertFalse(StoreTranslation.objects.get(kind="product", key=key, locale=locale).published)

    def test_exception_during_save_rolls_back_earlier_content_and_price_writes(self):
        original = CigarPrice.save
        def fail_last(row, *args, **kwargs):
            if row.cigar_id == 98:
                raise RuntimeError("write failed")
            return original(row, *args, **kwargs)
        before = self.snapshot()
        with patch.object(CigarPrice, "save", fail_last), self.assertRaises(RuntimeError):
            self.run_command(apply=True)
        self.assertEqual(self.snapshot(), before)

    def test_apply_requires_debug_and_rejects_production_paths_and_links(self):
        with override_settings(DEBUG=False), self.assertRaises(CommandError):
            self.run_command(apply=True)
        module = "storefront.management.commands.prepare_cohiba_content.connection"
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            production = root / "cigars.db"
            production.touch()
            symlink = root / "cigars_dev.db"
            symlink.symlink_to(production)
            hardlink = root / "alias.db"
            hardlink.hardlink_to(production)
            for name, vendor in ((str(production), "sqlite"), (str(symlink), "sqlite"),
                                  (str(hardlink), "sqlite"), ("file:/srv/cigars.db?mode=rw", "sqlite"),
                                  ("file:memorydb_alias?marker=mode=memory&mode=rw", "sqlite"),
                                  ("file:memorydb_alias?mode=memory&mode=rw", "sqlite"),
                                  (":memory:", "postgresql")):
                with self.subTest(name=name), override_settings(BASE_DIR=root), patch(
                    module, SimpleNamespace(settings_dict={"NAME": name}, vendor=vendor),
                ), self.assertRaises(CommandError):
                    Command()._guard_apply()

    @skipUnless(shutil.which("node") and Path(settings.STOREFRONT_RENDERER).is_file(), "Build React renderer first")
    def test_real_html_contains_all_fifteen_pages_copy_prices_canonicals_and_language_links(self):
        for locale in ("ru", "zh", "en"):
            StoreTranslation.objects.create(kind="home", key="home", locale=locale,
                                            published=True, **HOME_COPY[locale])
        for entry in self.content["products"]:
            # Real catalog regression: Magicos has stock in an unpriced 25-box,
            # while the owner approved the price only for its out-of-stock 10-box.
            stock_box = 25 if entry["id"] == 103 else entry["box_size"]
            create_purchase_batch(source="opening", cigar=self.cigars[entry["id"]],
                                  quantity=stock_box, remaining=stock_box,
                                  physical_remaining=stock_box, box_size=stock_box,
                                  unit_cost_cny=Decimal("1"))
        self.run_command(apply=True)
        pages = build_pages()
        targets = {path: page for path, page in pages.items()
                   if page["locale"] in ("ru", "zh", "en") and page["kind"] in ("brand", "product")}
        self.assertEqual(len(targets), 15)
        rendered = render_batch([SimpleNamespace(path=p, payload=v) for p, v in targets.items()], build_assets())
        for path, page in targets.items():
            with self.subTest(path=path):
                html = rendered[path]
                visible = html.split('<script id="store-data"')[0]
                document = BeautifulSoup(visible, 'html.parser')
                self.assertEqual([heading.get_text() for heading in document.select('h1')], [page['title']])
                self.assertEqual(document.title.get_text(), page['seo_title'])
                if page['kind'] == 'brand':
                    self.assertIsNotNone(document.select_one('h1 img.store-brand-logo'))
                    self.assertIsNone(document.select_one('.store-brand-browser'))
                    links = {link['href'].split('?')[0] for link in document.select('a[href]')}
                    for product_path, product_page in targets.items():
                        if product_page['kind'] == 'product' and product_page['locale'] == page['locale']:
                            self.assertIn(product_path, links)
                self.assertIn(page["body"], visible)
                self.assertIn('rel="canonical"', visible)
                self.assertIn(f'href="{settings.STOREFRONT_ORIGIN}{path}"', visible)
                self.assertIn('hreflang="ru"', visible)
                self.assertIn('hreflang="zh-CN"', visible)
                self.assertIn('hreflang="en"', visible)
                self.assertNotIn('name="robots" content="noindex', visible)
                self.assertNotIn("wholesale_price", html)
                self.assertNotIn("unit_cost_cny", html)
                if page["kind"] == "product":
                    entry = next(e for e in self.content["products"] if e["id"] == page["product"]["id"])
                    self.assertIn(f'data-price-rub="{entry["retail_price_rub"]}"', visible)
                    self.assertEqual(page["product"]["offers"][0]["box_size"], entry["box_size"])
