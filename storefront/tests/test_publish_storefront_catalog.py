import hashlib
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from django.core.management import call_command, CommandError
from django.test import TestCase, override_settings

from cigars.models import Brand, Cigar, CigarImage, CigarPrice, PurchaseBatch, StockMovement
from storefront.management.commands.publish_storefront_catalog import Command, ImageCommand
from storefront.models import ProductListing, StoreTranslation


MODULE = 'storefront.management.commands.publish_storefront_catalog'


class PublishStorefrontCatalogTests(TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.media = self.base / 'media'
        self.media.mkdir()
        self.manifest = self.base / 'docs/data/storefront-images-20261023.json'
        self.manifest.parent.mkdir(parents=True)
        self.production_path = self.base / 'cigars.db'
        self.production_path.touch()
        self.connection = SimpleNamespace(vendor='sqlite', settings_dict={'NAME': str(self.production_path)})
        self.brand = Brand.objects.create(english_name='Cohiba', name='高希霸', slug='cohiba')
        self.cigars = [Cigar.objects.create(brand='Cohiba', english_name=f'Model {number}',
                                          length=124, ring_gauge=50) for number in range(2)]
        self.assets = []
        for cigar in self.cigars:
            images = {}
            for kind in ('detail', 'list'):
                name = f'{cigar.pk}-{kind}.webp'
                content = name.encode()
                (self.media / name).write_bytes(content)
                images[kind] = {'media_path': name, 'sha256': hashlib.sha256(content).hexdigest()}
            self.assets.append({'status': 'approved', 'cigar_id': cigar.pk, 'brand': cigar.brand,
                                'english_name': cigar.english_name, 'release_type': '', 'release_name': '',
                                'image_type': 'single', 'box_size': None, **images})
        self.write_manifest()

    def write_manifest(self):
        self.manifest.write_text(json.dumps({'assets': self.assets}))

    def run_command(self, apply=False):
        output = io.StringIO()
        # The command guard sees a production-shaped path, while all ORM work
        # stays in Django's isolated test DB. Production still requires 60 IDs.
        with (override_settings(BASE_DIR=self.base, MEDIA_ROOT=self.media, DEBUG=False),
              patch(f'{MODULE}.connection', self.connection),
              patch('storefront.management.commands.prepare_storefront_localizations.EXPECTED_PRODUCT_COUNT', 2)):
            call_command('publish_storefront_catalog', apply=apply, confirm_production=apply, stdout=output)
        return json.loads(output.getvalue())

    def test_default_preview_does_not_write(self):
        report = self.run_command()
        self.assertEqual(report['mode'], 'dry-run')
        self.assertEqual((report['products'], report['translations_create'], report['listings_create']), (2, 12, 2))
        self.assertFalse(StoreTranslation.objects.exists())
        self.assertFalse(ProductListing.objects.exists())
        self.assertFalse(CigarImage.objects.exists())

    def test_publish_preserves_content_withdrawals_prices_and_legacy_images_and_is_idempotent(self):
        home = StoreTranslation.objects.create(kind='home', key='home', locale='en',
                                               title='My draft', description='Custom', body='Keep', published=False)
        listing = ProductListing.objects.create(cigar=self.cigars[0], published=False, withdrawn=True)
        legacy = CigarImage.objects.create(cigar=self.cigars[0], image='legacy.jpg', image_type='cigar', is_primary=True)
        CigarPrice.objects.create(cigar=self.cigars[1], box_size=25, wholesale_price=1234, retail_price=2345)
        business_models = (Cigar, CigarPrice, PurchaseBatch, StockMovement)
        before = {model: list(model.objects.order_by('pk').values()) for model in business_models}
        first = self.run_command(apply=True)
        self.assertEqual((first['translations_create'], first['listings_create']), (11, 1))
        home.refresh_from_db()
        listing.refresh_from_db()
        self.assertEqual((home.title, home.description, home.body, home.published), ('My draft', 'Custom', 'Keep', False))
        self.assertEqual((listing.published, listing.withdrawn), (False, True))
        self.assertTrue(ProductListing.objects.get(cigar=self.cigars[1]).published)
        self.assertTrue(CigarImage.objects.filter(pk=legacy.pk, image='legacy.jpg').exists())
        self.assertEqual(CigarImage.objects.count(), 3)
        self.assertFalse(StoreTranslation.objects.filter(kind='brand').exclude(body='').exists())
        second = self.run_command(apply=True)
        self.assertEqual((second['translations_create'], second['listings_create'], second['images_create']), (0, 0, 0))
        self.assertEqual(CigarImage.objects.count(), 3)
        self.assertEqual(before, {model: list(model.objects.order_by('pk').values()) for model in business_models})

    def test_identity_hash_and_missing_checksum_fail_before_publishing(self):
        original = json.loads(json.dumps(self.assets))
        for failure in ('identity', 'hash', 'missing_checksum'):
            with self.subTest(failure=failure):
                self.assets = json.loads(json.dumps(original))
                if failure == 'identity':
                    self.assets[-1]['english_name'] = 'Different model'
                elif failure == 'hash':
                    self.assets[-1]['detail']['sha256'] = '0' * 64
                else:
                    self.assets[-1]['detail'].pop('sha256')
                self.write_manifest()
                with self.assertRaises(CommandError):
                    self.run_command(apply=True)
                self.assertFalse(StoreTranslation.objects.exists())
                self.assertFalse(ProductListing.objects.exists())
                self.assertFalse(CigarImage.objects.exists())

    def test_existing_image_cannot_be_rebound_to_another_product(self):
        original = CigarImage.objects.create(cigar=self.cigars[1], image=self.assets[0]['detail']['media_path'], image_type='cigar')
        with self.assertRaises(CommandError):
            self.run_command(apply=True)
        original.refresh_from_db()
        self.assertEqual(original.cigar_id, self.cigars[1].pk)
        self.assertFalse(StoreTranslation.objects.exists())
        self.assertFalse(ProductListing.objects.exists())

    def test_late_image_failure_rolls_back_the_whole_publication(self):
        legacy = CigarImage.objects.create(cigar=self.cigars[0], image='legacy.jpg', image_type='cigar', is_primary=True)
        original_apply = ImageCommand._apply

        def fail_after_images(entries):
            original_apply(entries)
            raise CommandError('Simulated image import failure')

        with patch.object(ImageCommand, '_apply', side_effect=fail_after_images), self.assertRaises(CommandError):
            self.run_command(apply=True)
        self.assertFalse(StoreTranslation.objects.exists())
        self.assertFalse(ProductListing.objects.exists())
        self.assertEqual(CigarImage.objects.count(), 1)
        legacy.refresh_from_db()
        self.assertTrue(legacy.is_primary)

    def test_production_guard_requires_confirmation_real_path_and_debug_false(self):
        command = Command()
        with override_settings(DEBUG=False), patch(f'{MODULE}.connection', self.connection):
            command._guard_apply(True)
            with self.assertRaises(CommandError):
                command._guard_apply(False)
            with override_settings(DEBUG=True), self.assertRaises(CommandError):
                command._guard_apply(True)
            for name in ('', ':memory:', str(self.base / 'cigars_dev.db'), str(self.base / 'missing/cigars.db')):
                with self.subTest(name=name):
                    self.connection.settings_dict['NAME'] = name
                    with self.assertRaises(CommandError):
                        command._guard_apply(True)
            target = self.base / 'development.db'
            target.touch()
            self.production_path.unlink()
            self.production_path.symlink_to(target)
            self.connection.settings_dict['NAME'] = str(self.production_path)
            with self.assertRaises(CommandError):
                command._guard_apply(True)

    def test_real_manifest_requires_all_sixty_reviewed_identities(self):
        with override_settings(BASE_DIR=self.base, MEDIA_ROOT=self.media), self.assertRaisesMessage(CommandError, '60'):
            call_command('publish_storefront_catalog', stdout=io.StringIO())
