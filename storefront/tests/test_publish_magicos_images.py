import io
import hashlib
import json
import tempfile
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from django.contrib.admin.models import LogEntry
from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings

from cigars.models import Cigar, CigarImage
from storefront.management.commands import publish_magicos_images as publish


@override_settings(DEBUG=True)
class PublishMagicosImagesTests(TestCase):
    def setUp(self):
        self.media_tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.media_tmp.cleanup)
        self.media_root = Path(self.media_tmp.name)
        self.media_override = override_settings(MEDIA_ROOT=self.media_root)
        self.media_override.enable()
        self.addCleanup(self.media_override.disable)
        self.manifest = publish.MANIFEST
        self.manifest_before = self.manifest.read_bytes()
        self.fixture_assets = json.loads(self.manifest_before.decode('utf-8'))['product_assets']
        pinned_fixture = {}
        for asset in self.fixture_assets:
            slot = (asset['image_type'], None if asset['image_type'] == 'single' else asset['box_size'])
            paths_hashes = []
            for key in ('detail', 'list'):
                relative = asset[key]['media_path']
                file_path = self.media_root / relative
                file_path.parent.mkdir(parents=True, exist_ok=True)
                fixture_bytes = f'fixture image {relative}'.encode()
                file_path.write_bytes(fixture_bytes)
                file_hash = hashlib.sha256(fixture_bytes).hexdigest()
                asset[key]['sha256'] = file_hash
                paths_hashes.extend((relative, file_hash))
            pinned_fixture[slot] = tuple(paths_hashes)
        self.assets_patch = patch.object(publish, 'ASSETS', pinned_fixture)
        self.assets_patch.start()
        self.addCleanup(self.assets_patch.stop)
        fixture_payload = json.dumps(self.fixture_assets, sort_keys=True, separators=(',', ':')).encode()
        fixture_digest = hashlib.sha256(fixture_payload).hexdigest()
        self.manifest_patch = patch.object(publish, '_read_fixed_manifest',
                                           return_value=(self.fixture_assets, fixture_digest))
        self.manifest_patch.start()
        self.addCleanup(self.manifest_patch.stop)
        self.cigar = Cigar.objects.create(pk=103, brand='Cohiba', english_name='Magicos',
                                          length=115, ring_gauge=52)
        self.actor = get_user_model().objects.create_user(username='seo-owner', is_staff=True)
        self.legacy = CigarImage.objects.create(cigar=self.cigar, image='legacy/old.webp',
            thumbnail='legacy/old-thumb.webp', image_type='cigar', order=4, is_primary=True)
        self.other = CigarImage.objects.create(cigar=self.cigar, image='legacy/other.webp',
            thumbnail='legacy/other-thumb.webp', image_type='band', order=7, is_primary=False)
    def tearDown(self):
        self.assertEqual(self.manifest.read_bytes(), self.manifest_before)

    def invoke(self, **options):
        output = io.StringIO()
        call_command('publish_magicos_images', stdout=output, **options)
        return json.loads(output.getvalue())

    def state(self):
        return (list(Cigar.objects.order_by('pk').values()),
                list(CigarImage.objects.order_by('pk').values()),
                list(LogEntry.objects.order_by('pk').values()))

    def apply_options(self, preview=None, **overrides):
        preview = preview or self.invoke()
        return {'apply': True, 'confirm_production': True,
                'expected_digest': preview['expected_digest'], 'actor': self.actor.username,
                'operation_id': 'seo13-magicos-1', 'commit_sha': 'a' * 40, **overrides}

    def test_dry_run_validates_assets_without_writing(self):
        before = self.state()
        result = self.invoke()
        self.assertEqual(before, self.state())
        self.assertEqual(result['mode'], 'dry-run')
        self.assertEqual(result['changed_rows'], 3)  # two inserts and the former primary demotion
        self.assertEqual({row['after']['image_type'] for row in result['images'] if row['action'] == 'create'},
                         {'cigar', 'packaging'})

    def test_apply_creates_exact_images_demotes_only_primary_and_audits(self):
        before_other = self.other.__dict__.copy()
        preview = self.invoke()
        cigar_before = list(Cigar.objects.filter(pk=103).values())[0]
        legacy_before = CigarImage.objects.filter(pk=self.legacy.pk).values().first()
        other_before = CigarImage.objects.filter(pk=self.other.pk).values().first()
        result = self.invoke(**self.apply_options(preview))
        self.assertEqual(result['changed_rows'], 3)
        rows = {row.image: row for row in CigarImage.objects.filter(cigar_id=103)}
        single_path = publish.ASSETS[('single', None)][0]
        box_path = publish.ASSETS[('box', 10)][0]
        self.assertEqual(rows[single_path].image_type, 'cigar')
        self.assertIsNone(rows[single_path].box_size)
        self.assertTrue(rows[single_path].is_primary)
        self.assertEqual(rows[box_path].image_type, 'packaging')
        self.assertEqual(rows[box_path].box_size, 10)
        self.assertFalse(rows[box_path].is_primary)
        self.assertFalse(CigarImage.objects.get(pk=self.legacy.pk).is_primary)
        self.assertEqual(CigarImage.objects.get(pk=self.other.pk).image, before_other['image'])
        self.assertFalse(CigarImage.objects.get(pk=self.other.pk).is_primary)
        self.assertEqual(list(Cigar.objects.filter(pk=103).values())[0], cigar_before)
        legacy_after = CigarImage.objects.filter(pk=self.legacy.pk).values().first()
        other_after = CigarImage.objects.filter(pk=self.other.pk).values().first()
        self.assertEqual({k: v for k, v in legacy_before.items() if k != 'is_primary'},
                         {k: v for k, v in legacy_after.items() if k != 'is_primary'})
        self.assertEqual(other_after, other_before)
        logs = list(LogEntry.objects.order_by('pk'))
        self.assertEqual(len(logs), 3)
        for log in logs:
            metadata = json.loads(log.change_message)[0]['seo_release']
            self.assertEqual(log.user_id, self.actor.pk)
            self.assertEqual(metadata['source'], 'codex-seo13')
            self.assertEqual(metadata['scope'], 'magicos-images-v1')
            self.assertEqual(metadata['operation_id'], 'seo13-magicos-1')
            self.assertEqual(metadata['commit_sha'], 'a' * 40)
            self.assertEqual(metadata['business_date'], __import__('django.utils.timezone', fromlist=['localdate']).localdate().isoformat())
            self.assertIn('before', metadata)
            self.assertIn('after', metadata)
        current = self.state()
        repeated = self.invoke(**self.apply_options(preview))
        self.assertEqual(repeated['changed_rows'], 0)
        self.assertEqual(current, self.state())

    def test_stale_cas_rejects_concurrent_image_changes(self):
        preview = self.invoke()
        CigarImage.objects.filter(pk=self.other.pk).update(order=81)
        before = self.state()
        with self.assertRaisesMessage(CommandError, 'expected-digest'):
            self.invoke(**self.apply_options(preview))
        self.assertEqual(before, self.state())

    def test_apply_options_actor_and_operation_reuse_are_checked(self):
        opts = self.apply_options()
        inactive = get_user_model().objects.create_user(username='inactive', is_staff=True, is_active=False)
        for invalid in [{'confirm_production': False}, {'expected_digest': 'x' * 64},
                        {'operation_id': 'bad\nvalue'}, {'commit_sha': 'abc'},
                        {'actor': 'missing'}, {'actor': inactive.username}]:
            with self.subTest(invalid=invalid):
                before = self.state()
                with self.assertRaises(CommandError):
                    self.invoke(**{**opts, **invalid})
                self.assertEqual(before, self.state())
        self.invoke(**opts)
        before = self.state()
        other_actor = get_user_model().objects.create_user(username='different', is_staff=True)
        for changed in [{'commit_sha': 'b' * 40}, {'actor': other_actor.username}]:
            with self.assertRaisesMessage(CommandError, 'operation-id'):
                self.invoke(**{**opts, **changed})
            self.assertEqual(before, self.state())
        current_preview = self.invoke()
        with self.assertRaisesMessage(CommandError, 'operation-id'):
            self.invoke(**{**opts, 'expected_digest': current_preview['expected_digest']})
        CigarImage.objects.filter(pk=self.other.pk).update(order=91)
        preview = self.invoke()
        with self.assertRaisesMessage(CommandError, '已执行'):
            self.invoke(**{**opts, 'expected_digest': preview['expected_digest']})

    def test_manifest_identity_hash_slots_and_owner_conflicts_are_rejected(self):
        altered = {'product_assets': deepcopy(self.fixture_assets)}
        altered['product_assets'][0]['source_evidence']['english_name'] = 'Wrong'
        with patch.object(publish, '_read_fixed_manifest', return_value=(altered['product_assets'], 'a' * 64)):
            with self.assertRaises(CommandError):
                self.invoke()
        altered = {'product_assets': deepcopy(self.fixture_assets)}
        altered['product_assets'][0]['detail']['sha256'] = '0' * 64
        with patch.object(publish, '_read_fixed_manifest', return_value=(altered['product_assets'], 'b' * 64)):
            with self.assertRaisesMessage(CommandError, 'SHA-256'):
                self.invoke()
        altered = {'product_assets': deepcopy(self.fixture_assets)}
        altered['product_assets'][1] = altered['product_assets'][0]
        with patch.object(publish, '_read_fixed_manifest', return_value=(altered['product_assets'], 'c' * 64)):
            with self.assertRaises(CommandError):
                self.invoke()
        with patch.object(publish, '_read_fixed_manifest', side_effect=CommandError('bad digest')):
            with self.assertRaises(CommandError):
                self.invoke()
        paths = [publish.ASSETS[('single', None)][0], publish.ASSETS[('single', None)][2]]
        for path, field in [(paths[0], 'image'), (paths[1], 'image'), (paths[1], 'thumbnail')]:
            with self.subTest(path=path, field=field):
                owner = Cigar.objects.create(pk=104, brand='Other', english_name='Other')
                kwargs = {'cigar': owner, 'image': 'other/owned.webp', 'thumbnail': '' if field == 'image' else path,
                          'image_type': 'cigar'}
                if field == 'image':
                    kwargs['image'] = path
                CigarImage.objects.create(**kwargs)
                with self.assertRaisesMessage(CommandError, '另一商品'):
                    self.invoke()
                CigarImage.objects.filter(cigar=owner).delete()
                owner.delete()
        Cigar.objects.filter(pk=103).update(length=116)
        with self.assertRaisesMessage(CommandError, '身份或规格'):
            self.invoke()

    def test_stale_digest_is_rejected_even_when_plan_has_no_writes(self):
        first_preview = self.invoke()
        self.invoke(**self.apply_options(first_preview, operation_id='seo13-initial'))
        no_op_preview = self.invoke()
        self.assertEqual(no_op_preview['changed_rows'], 0)
        CigarImage.objects.filter(pk=self.other.pk).update(image_url='https://example.test/changed')
        with self.assertRaisesMessage(CommandError, 'expected-digest'):
            self.invoke(**self.apply_options(no_op_preview, operation_id='seo13-next'))

    def test_write_or_audit_failure_rolls_back(self):
        opts = self.apply_options()
        original = LogEntry.objects.create
        calls = {'n': 0}

        def fail_second(**kwargs):
            calls['n'] += 1
            if calls['n'] == 2:
                raise RuntimeError('audit failure')
            return original(**kwargs)

        before = self.state()
        with patch.object(LogEntry.objects, 'create', side_effect=fail_second):
            with self.assertRaises(CommandError):
                self.invoke(**opts)
        self.assertEqual(before, self.state())
        original_image_create = CigarImage.objects.create
        create_calls = {'n': 0}

        def fail_second_write(**kwargs):
            create_calls['n'] += 1
            if create_calls['n'] == 2:
                raise RuntimeError('image write failure')
            return original_image_create(**kwargs)

        with patch.object(CigarImage.objects, 'create', side_effect=fail_second_write):
            with self.assertRaises(CommandError):
                self.invoke(**opts)
        self.assertEqual(before, self.state())

    @override_settings(DEBUG=False)
    def test_debug_false_must_point_to_real_production_database(self):
        options = self.apply_options()
        dev_path = str(Path(publish.settings.BASE_DIR) / 'cigars_dev.db')
        with patch.dict(publish.connection.settings_dict, {'NAME': dev_path}):
            with self.assertRaisesMessage(CommandError, '项目根目录的正式数据库'):
                self.invoke(**options)

    @override_settings(DEBUG=False)
    def test_canonical_production_database_is_eligible_only_with_confirmation(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base / 'cigars.db').touch()
            canonical = str(base / 'cigars.db')
            with patch.object(publish.settings, 'BASE_DIR', base):
                with patch.dict(publish.connection.settings_dict, {'NAME': canonical}):
                    publish.Command()._check_database(confirm_production=True)
                    with self.assertRaisesMessage(CommandError, 'confirm-production'):
                        publish.Command()._check_database(confirm_production=False)

    @override_settings(DEBUG=False)
    def test_missing_canonical_database_fails_before_opening_transaction(self):
        options = self.apply_options()
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            with patch.object(publish.settings, 'BASE_DIR', base):
                with patch.dict(publish.connection.settings_dict, {'NAME': str(base / 'cigars.db')}):
                    before = self.state()
                    with patch('storefront.management.commands.publish_magicos_images.transaction.atomic',
                               side_effect=AssertionError('transaction must not start')):
                        with self.assertRaisesMessage(CommandError, '不存在'):
                            self.invoke(**options)
                    self.assertFalse((base / 'cigars.db').exists())
                    self.assertEqual(before, self.state())

    def test_debug_database_must_not_resolve_to_production_database(self):
        production_db = Path(publish.settings.BASE_DIR) / 'cigars.db'
        with patch.dict(publish.connection.settings_dict, {'NAME': str(production_db)}):
            with self.assertRaisesMessage(CommandError, 'DEBUG=True 指向正式数据库'):
                publish.Command()._check_database(confirm_production=True)

    def test_symlink_alias_to_cigars_db_is_rejected_even_when_debug_enabled(self):
        production_db = Path(publish.settings.BASE_DIR) / 'cigars.db'
        with tempfile.TemporaryDirectory() as directory:
            alias = Path(directory) / 'alias.sqlite3'
            alias.symlink_to(production_db)
            with patch.dict(publish.connection.settings_dict, {'NAME': str(alias)}):
                with self.assertRaisesMessage(CommandError, '正式数据库'):
                    publish.Command()._check_database(confirm_production=True)

    def test_file_uri_that_could_alias_production_database_is_rejected(self):
        encoded_alias = f"file:{Path(publish.settings.BASE_DIR)}/cigars.db%3Fmode=ro"
        with patch.dict(publish.connection.settings_dict, {'NAME': encoded_alias}):
            with self.assertRaisesMessage(CommandError, 'file: URI'):
                publish.Command()._check_database(confirm_production=True)
