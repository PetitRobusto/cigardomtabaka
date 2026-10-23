import io
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.core.management import call_command, CommandError
from django.test import TestCase, override_settings

from cigars.models import Brand, Cigar
from storefront.languages import HOME_COPY
from storefront.models import StoreTranslation


class PrepareStorefrontLocalizationsTests(TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.manifest_path = self.base / "docs/data/storefront-images-20261023.json"
        self.manifest_path.parent.mkdir(parents=True)
        self.brand = Brand.objects.create(english_name="Cohiba", name="高希霸")
        self.cigar = Cigar.objects.create(
            brand=self.brand.english_name,
            english_name="Genios",
            name="天才",
            vitola="Robusto",
            length=124,
            ring_gauge=50,
            release_type="Edición Limitada",
            release_name="2024",
        )
        self.write_manifest()

    def write_manifest(self, *, brand=None):
        self.manifest_path.write_text(json.dumps({
            "assets": [{
                "status": "approved",
                "cigar_id": self.cigar.pk,
                "brand": brand or self.cigar.brand,
                "english_name": self.cigar.english_name,
                "release_type": self.cigar.release_type,
                "release_name": self.cigar.release_name,
            }],
        }), encoding="utf-8")

    def run_command(self, *, apply=False, stdout=None):
        with override_settings(BASE_DIR=self.base, DEBUG=True), patch(
            "storefront.management.commands.prepare_storefront_localizations.EXPECTED_PRODUCT_COUNT", 1,
        ):
            call_command("prepare_storefront_localizations", apply=apply,
                         stdout=stdout or io.StringIO())

    def test_default_is_dry_run(self):
        output = io.StringIO()
        self.run_command(stdout=output)
        self.assertIn("dry-run", output.getvalue())
        self.assertFalse(StoreTranslation.objects.exists())

    def test_identity_mismatch_aborts_before_creating_any_translation(self):
        self.write_manifest(brand="Romeo y Julieta")
        with self.assertRaises(CommandError):
            self.run_command(apply=True)
        self.assertFalse(StoreTranslation.objects.exists())

    def test_apply_refuses_production_database_even_when_debug_is_true(self):
        connection = SimpleNamespace(settings_dict={"NAME": "/srv/app/cigars.db"})
        with (override_settings(BASE_DIR=self.base, DEBUG=True),
              patch("storefront.management.commands.prepare_storefront_localizations.connection", connection),
              patch("storefront.management.commands.prepare_storefront_localizations.EXPECTED_PRODUCT_COUNT", 1),
              self.assertRaises(CommandError)):
            call_command("prepare_storefront_localizations", apply=True, stdout=io.StringIO())
        self.assertFalse(StoreTranslation.objects.exists())

    def test_apply_refuses_debug_false(self):
        with (override_settings(BASE_DIR=self.base, DEBUG=False),
              patch("storefront.management.commands.prepare_storefront_localizations.EXPECTED_PRODUCT_COUNT", 1),
              self.assertRaises(CommandError)):
            call_command("prepare_storefront_localizations", apply=True, stdout=io.StringIO())
        self.assertFalse(StoreTranslation.objects.exists())

    def test_user_edits_are_preserved_and_only_exact_home_copy_is_published(self):
        exact_home = StoreTranslation.objects.create(
            kind="home", key="home", locale="en", **HOME_COPY["en"], published=False,
        )
        custom_home = StoreTranslation.objects.create(
            kind="home", key="home", locale="ru", title="User title",
            description="User summary", body="User body", published=False,
        )
        custom_product = StoreTranslation.objects.create(
            kind="product", key=str(self.cigar.pk), locale="ru", title="User model name",
            description="User specification", body="User specification body", published=False,
        )

        self.run_command(apply=True)

        exact_home.refresh_from_db()
        custom_home.refresh_from_db()
        custom_product.refresh_from_db()
        self.assertTrue(exact_home.published)
        self.assertFalse(custom_home.published)
        self.assertEqual((custom_home.title, custom_home.description, custom_home.body),
                         ("User title", "User summary", "User body"))
        self.assertFalse(custom_product.published)
        self.assertEqual((custom_product.title, custom_product.description, custom_product.body),
                         ("User model name", "User specification", "User specification body"))

    def test_rerun_is_idempotent_and_brand_body_stays_empty(self):
        first_output = io.StringIO()
        self.run_command(apply=True, stdout=first_output)
        count_after_first_run = StoreTranslation.objects.count()
        second_output = io.StringIO()
        self.run_command(apply=True, stdout=second_output)

        self.assertEqual(StoreTranslation.objects.count(), count_after_first_run)
        self.assertIn("新建 0 条", second_output.getvalue())
        for locale in ("zh", "ru", "en"):
            brand_translation = StoreTranslation.objects.get(
                kind="brand", key=self.brand.slug, locale=locale,
            )
            self.assertTrue(brand_translation.published)
            self.assertEqual(brand_translation.body, "")
            self.assertEqual(brand_translation.description, brand_translation.title)

    def test_product_text_uses_only_existing_name_and_specification_facts(self):
        self.run_command(apply=True)
        zh = StoreTranslation.objects.get(kind="product", key=str(self.cigar.pk), locale="zh")
        en = StoreTranslation.objects.get(kind="product", key=str(self.cigar.pk), locale="en")
        ru = StoreTranslation.objects.get(kind="product", key=str(self.cigar.pk), locale="ru")

        self.assertEqual(zh.title, "天才")
        self.assertEqual(en.title, "Genios")
        self.assertEqual(ru.title, "Genios")
        self.assertEqual(zh.description, zh.body)
        self.assertEqual(en.description, en.body)
        self.assertEqual(ru.description, ru.body)
        self.assertIn("Robusto", en.description)
        self.assertIn("Робусто", ru.description)
        self.assertIn("124 mm", en.description)
        self.assertIn("Диаметр кольца: 50", ru.description)
        for phrase in ("Browse", "Discover", "Explore", "品牌故事", "介绍"):
            self.assertNotIn(phrase, " ".join([zh.body, en.body, ru.body]))
