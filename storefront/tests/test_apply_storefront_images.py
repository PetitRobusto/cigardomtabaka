import hashlib
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.core.management import call_command, CommandError
from django.test import TestCase, override_settings

from cigars.models import Cigar, CigarImage


class ApplyStorefrontImagesTests(TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.media = self.root / "media"
        self.media.mkdir()
        self.manifest_path = self.root / "manifest.json"
        self.cigar = Cigar.objects.create(brand="Cohiba", english_name="Espléndidos")

    def asset(self, *, cigar=None, image_type="single", box_size=1, slug="single", hash_override=None):
        cigar = cigar or self.cigar
        detail = f"storefront/{slug}-detail.webp"
        listing = f"storefront/{slug}-list.webp"
        for relative, contents in ((detail, b"detail image"), (listing, b"list image")):
            path = self.media / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(contents)
        detail_hash = hashlib.sha256((self.media / detail).read_bytes()).hexdigest()
        list_hash = hashlib.sha256((self.media / listing).read_bytes()).hexdigest()
        if hash_override:
            detail_hash = hash_override
        return {
            "status": "approved",
            "cigar_id": cigar.pk,
            "brand": cigar.brand,
            "english_name": cigar.english_name,
            "image_type": image_type,
            "box_size": box_size,
            "detail": {"media_path": detail, "sha256": detail_hash},
            "list": {"media_path": listing, "sha256": list_hash},
        }

    def run_manifest(self, assets, *, apply=False):
        self.manifest_path.write_text(json.dumps({"assets": assets}), encoding="utf-8")
        options = {}
        if apply:
            options["apply"] = True
        with override_settings(MEDIA_ROOT=self.media):
            call_command("apply_storefront_images", str(self.manifest_path), **options)

    def test_default_is_dry_run_and_apply_is_idempotent_with_correct_primary(self):
        legacy = CigarImage.objects.create(
            cigar=self.cigar, image="legacy/product.jpg", image_type="cigar", is_primary=True,
        )
        assets = [
            self.asset(image_type="box", box_size=25, slug="box"),
            self.asset(image_type="single", box_size=1, slug="single"),
        ]

        self.run_manifest(assets)
        self.assertEqual(CigarImage.objects.count(), 1)
        self.assertTrue(CigarImage.objects.get(pk=legacy.pk).is_primary)

        with override_settings(DEBUG=True):
            self.run_manifest(assets, apply=True)
            self.run_manifest(assets, apply=True)

        self.assertEqual(CigarImage.objects.count(), 3)
        legacy.refresh_from_db()
        self.assertFalse(legacy.is_primary)
        primary = CigarImage.objects.get(cigar=self.cigar, is_primary=True)
        self.assertEqual(primary.image, "storefront/single-detail.webp")
        self.assertIsNone(primary.box_size)
        self.assertEqual(primary.order, -200)
        box = CigarImage.objects.get(image="storefront/box-detail.webp")
        self.assertEqual((box.image_type, box.box_size, box.is_primary), ("packaging", 25, False))
        self.assertEqual(box.order, -190)

    def test_same_brand_and_name_with_another_release_matches_exact_id(self):
        Cigar.objects.create(
            brand=self.cigar.brand, english_name=self.cigar.english_name,
            release_type="Edición Limitada", release_name="2024",
        )
        self.run_manifest([self.asset()])
        self.assertFalse(CigarImage.objects.exists())

        wrong_release = self.asset()
        wrong_release["release_type"] = "Edición Limitada"
        wrong_release["release_name"] = "2024"
        with self.assertRaises(CommandError):
            self.run_manifest([wrong_release])
        self.assertFalse(CigarImage.objects.exists())

    def test_identity_failure_prevents_all_changes(self):
        valid = self.asset(slug="valid")
        other = Cigar.objects.create(brand="Romeo y Julieta", english_name="Churchills")
        invalid = self.asset(cigar=other, slug="invalid")
        invalid["cigar_id"] = self.cigar.pk
        before = CigarImage.objects.count()

        with override_settings(DEBUG=True), self.assertRaises(CommandError):
            self.run_manifest([valid, invalid], apply=True)

        self.assertEqual(CigarImage.objects.count(), before)

    def test_conflicting_release_evidence_prevents_all_changes(self):
        for field in ("release_type", "release_name"):
            with self.subTest(field=field):
                asset = self.asset()
                asset[field] = getattr(self.cigar, field)
                asset["source_evidence"] = {field: "different release"}
                with override_settings(DEBUG=True), self.assertRaises(CommandError):
                    self.run_manifest([asset], apply=True)
                self.assertFalse(CigarImage.objects.exists())

    def test_hash_mismatch_and_path_traversal_are_rejected(self):
        bad_hash = self.asset(hash_override="0" * 64)
        with self.assertRaises(CommandError):
            self.run_manifest([bad_hash])

        traversal = self.asset(slug="traversal")
        outside = self.root / "outside.webp"
        outside.write_bytes(b"real outside file")
        traversal["detail"]["media_path"] = "../outside.webp"
        with self.assertRaises(CommandError):
            self.run_manifest([traversal])

        escape = self.asset(slug="symlink")
        symlink = self.media / "storefront" / "escape.webp"
        symlink.symlink_to(outside)
        escape["detail"]["media_path"] = "storefront/escape.webp"
        with self.assertRaises(CommandError):
            self.run_manifest([escape])
        self.assertFalse(CigarImage.objects.exists())

    def test_apply_refuses_debug_false(self):
        asset = self.asset()
        before = CigarImage.objects.count()
        with override_settings(DEBUG=False), self.assertRaises(CommandError):
            self.run_manifest([asset], apply=True)
        self.assertEqual(CigarImage.objects.count(), before)

    def test_apply_refuses_database_named_cigars_db(self):
        asset = self.asset()
        before = CigarImage.objects.count()
        fake_connection = SimpleNamespace(settings_dict={"NAME": "/srv/app/cigars.db"})
        with (override_settings(DEBUG=True),
              patch("storefront.management.commands.apply_storefront_images.connection", fake_connection),
              self.assertRaises(CommandError)):
            self.run_manifest([asset], apply=True)
        self.assertEqual(CigarImage.objects.count(), before)
