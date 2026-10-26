import io
import json
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.contrib.admin.models import LogEntry
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.management import CommandError, call_command
from django.db import connection
from django.test import TestCase, override_settings

from cigars.models import Brand, Cigar, CigarPrice
from storefront.management.commands.publish_catalog_copy import Command, SOURCE, SCOPE
from storefront.models import ProductListing, RefreshState, StoreTranslation


@override_settings(DEBUG=True)
class PublishCatalogCopyTests(TestCase):
    def setUp(self):
        self.actor = get_user_model().objects.create_user(username='seo-editor', is_staff=True)
        self.scope = {'schema_version': 1, 'products': [], 'brands': [],
                      'spec_corrections': {'1': {'length': 124, 'ring_gauge': 50, 'vitola': 'Robustos', 'vitola_cn': '罗布图'}}}
        self.products, self.brands = {}, {}
        for i in range(1, 21):
            brand = Brand.objects.create(english_name=f'Brand {i}', slug=f'brand-{i}')
            self.scope['brands'].append({'slug': brand.slug, 'english_name': brand.english_name})
            self.brands[brand.slug] = self.copy('brand', brand.slug)
            for n in range(3):
                pk = (i - 1) * 3 + n + 1
                cigar = Cigar.objects.create(pk=pk, brand=brand.english_name, english_name=f'Model {pk}',
                                             length=130, ring_gauge=48, vitola='Old', vitola_cn='旧', name='保留品名')
                ProductListing.objects.create(cigar=cigar, published=True)
                CigarPrice.objects.create(cigar=cigar, box_size=25, wholesale_price=123, retail_price_rub=456)
                self.scope['products'].append({'id': pk, 'brand': cigar.brand, 'english_name': cigar.english_name,
                                               'release_type': '', 'release_name': '',
                                               'expected_specs': {'length': 130, 'ring_gauge': 48, 'vitola': 'Old', 'vitola_cn': '旧'}})
                self.products[pk] = self.copy('product', str(pk))
        StoreTranslation.objects.create(kind='home', key='home', locale='en', title='Home',
                                        description='Keep home', body='Keep home', published=True)
        RefreshState.objects.get_or_create(pk=1)
        self.release = (self.scope, self.products, self.brands)
        self.reader = patch('storefront.management.commands.publish_catalog_copy.read_release', return_value=self.release)
        self.reader.start()
        self.addCleanup(self.reader.stop)

    def copy(self, kind, key):
        values = {'decision': 'update', 'translations': {}}
        for locale in ('zh', 'ru', 'en'):
            StoreTranslation.objects.create(kind=kind, key=key, locale=locale, title=f'Keep {key}',
                                            seo_title=f'Keep search {locale}', aliases='keep aliases', hours='keep hours',
                                            description='Old summary', body='Old body', published=True)
            values['translations'][locale] = {'description': f'{locale} reviewed {key}', 'body': f'{locale} complete body {key}'}
        return values

    def invoke(self, **options):
        out = io.StringIO()
        call_command('publish_catalog_copy', stdout=out, **options)
        return json.loads(out.getvalue())

    def options(self):
        return {'apply': True, 'expected_digest': self.invoke()['expected_digest'], 'actor': self.actor.username,
                'operation_id': 'seo18-test-1', 'commit_sha': 'a' * 40}

    def state(self):
        return {m._meta.label: list(m.objects.order_by('pk').values()) for m in (
            Brand, Cigar, CigarPrice, ProductListing, StoreTranslation, LogEntry, RefreshState, ContentType)}

    def test_preview_is_read_only_and_covers_every_language_and_spec(self):
        before = self.state()
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            result = self.invoke()
        self.assertEqual(result['changed_rows'], 241)
        self.assertEqual(len(result['records']), 300)
        self.assertEqual(before, self.state())
        self.assertEqual(callbacks, [])

    def test_apply_preserves_names_metadata_commerce_and_repeat_is_noop(self):
        before = self.state()
        options = self.options()
        with self.captureOnCommitCallbacks(execute=True):
            result = self.invoke(**options)
        self.assertEqual(result['changed_rows'], 241)
        after = self.state()
        for label in ('cigars.Brand', 'cigars.CigarPrice', 'storefront.ProductListing'):
            self.assertEqual(before[label], after[label])
        for a, b in zip(before['storefront.StoreTranslation'], after['storefront.StoreTranslation']):
            for field in a:
                if field not in ('description', 'body', 'updated_at'):
                    self.assertEqual(a[field], b[field], field)
        for a, b in zip(before['cigars.Cigar'], after['cigars.Cigar']):
            for field in a:
                if a['id'] != 1 or field not in ('length', 'ring_gauge', 'vitola', 'vitola_cn'):
                    self.assertEqual(a[field], b[field], field)
        self.assertEqual(Cigar.objects.get(pk=1).length, 124)
        self.assertEqual(LogEntry.objects.count(), 241)
        for log in LogEntry.objects.all():
            meta = json.loads(log.change_message)[0]['seo_release']
            self.assertEqual(meta['source'], SOURCE)
            self.assertEqual(meta['scope'], SCOPE)
            self.assertEqual(meta['operation_id'], options['operation_id'])
            self.assertIn('business_date', meta)
            self.assertIn('before', meta)
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            repeated = self.invoke(**options)
        self.assertEqual(repeated['changed_rows'], 0)
        self.assertEqual(after, self.state())
        self.assertEqual(callbacks, [])

    def test_stale_preview_detects_translation_identity_spec_and_manifest_edits(self):
        options = self.options()
        StoreTranslation.objects.filter(kind='product', key='60', locale='en').update(body='Concurrent edit')
        before = self.state()
        with self.assertRaisesMessage(CommandError, 'expected-digest'):
            self.invoke(**options)
        self.assertEqual(before, self.state())
        options = self.options()
        self.products[60]['translations']['en']['body'] = 'Changed release'
        with self.assertRaisesMessage(CommandError, 'expected-digest'):
            self.invoke(**options)
        Cigar.objects.filter(pk=60).update(length=131)
        with self.assertRaisesMessage(CommandError, '规格已经变动'):
            self.invoke()
        Cigar.objects.filter(pk=60).update(release_type='Limited Edition')
        with self.assertRaisesMessage(CommandError, '发行版本'):
            self.invoke()

    def test_hidden_extra_or_missing_public_products_stop_whole_batch(self):
        ProductListing.objects.filter(cigar_id=60).update(published=False)
        with self.assertRaisesMessage(CommandError, '公开商品集合'):
            self.invoke()
        ProductListing.objects.filter(cigar_id=60).update(published=True)
        extra = Cigar.objects.create(brand='Brand 1', english_name='New')
        ProductListing.objects.create(cigar=extra, published=True)
        with self.assertRaisesMessage(CommandError, '公开商品集合'):
            self.invoke()

    def test_draft_missing_and_preserved_editorial_rows_stop_batch(self):
        target = StoreTranslation.objects.filter(kind='product', key='60', locale='en')
        target.update(published=False)
        with self.assertRaisesMessage(CommandError, '缺失、草稿'):
            self.invoke()
        target.update(published=True)
        self.products[60]['decision'] = 'preserve'
        with self.assertRaisesMessage(CommandError, '保留资料发生变化'):
            self.invoke()
        self.products[60]['decision'] = 'update'
        target.delete()
        with self.assertRaisesMessage(CommandError, '缺失、草稿'):
            self.invoke()

    def test_late_translation_or_audit_failure_rolls_back_specs_and_all_copy(self):
        options = self.options()
        save = StoreTranslation.save

        def failing_save(row, *args, **kwargs):
            if row.kind == 'product' and row.key == '60' and row.locale == 'en':
                raise RuntimeError('late failure')
            return save(row, *args, **kwargs)

        for fail in (patch.object(StoreTranslation, 'save', failing_save),
                     patch.object(LogEntry.objects, 'create', side_effect=RuntimeError('audit failure'))):
            before = self.state()
            with fail, self.captureOnCommitCallbacks(execute=True) as callbacks:
                with self.assertRaisesMessage(CommandError, '事务未写入'):
                    self.invoke(**options)
            self.assertEqual(before, self.state())
            self.assertEqual(callbacks, [])

    def test_apply_requires_actor_preview_and_explicit_production_guard(self):
        with self.assertRaisesMessage(CommandError, '必须同时提供'):
            self.invoke(apply=True)
        options = self.options()
        options['actor'] = 'missing'
        with self.assertRaisesMessage(CommandError, 'active staff'):
            self.invoke(**options)
        with override_settings(DEBUG=False), self.assertRaisesMessage(CommandError, '生产写入要求'):
            self.invoke(**self.options())
        with self.assertRaisesMessage(CommandError, '生产确认不能'):
            self.invoke(**self.options(), confirm_production=True)

    def test_production_guard_requires_exact_database_path_and_matching_checkout_sha(self):
        command = Command()
        options = {'confirm_production': True, 'commit_sha': 'a' * 40}
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            database = root / 'cigars.db'
            database.touch()
            completed = subprocess.CompletedProcess(
                args=['git', 'rev-parse', 'HEAD'], returncode=0,
                stdout=options['commit_sha'] + '\n', stderr='',
            )
            git = 'storefront.management.commands.publish_catalog_copy.subprocess.run'
            with (override_settings(DEBUG=False, BASE_DIR=root),
                  patch.dict(connection.settings_dict, {'NAME': str(database)}),
                  patch(git, return_value=completed) as run):
                command._guard_apply(options)
                command._guard_commit_sha(options)
            run.assert_called_once_with(
                ['git', '-C', str(root), 'rev-parse', 'HEAD'],
                check=True, capture_output=True, text=True, timeout=10,
            )

            other_dir = root / 'other'
            other_dir.mkdir()
            other_database = other_dir / 'cigars.db'
            other_database.touch()
            with (override_settings(DEBUG=False, BASE_DIR=root),
                  patch.dict(connection.settings_dict, {'NAME': str(other_database)}),
                  patch(git) as run):
                with self.assertRaisesMessage(CommandError, '实际 cigars.db'):
                    command._guard_apply(options)
                run.assert_not_called()

    def test_production_guard_rejects_mismatched_or_unverifiable_checkout_sha(self):
        command = Command()
        options = {'confirm_production': True, 'commit_sha': 'a' * 40}
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            database = root / 'cigars.db'
            database.touch()
            git = 'storefront.management.commands.publish_catalog_copy.subprocess.run'
            with (override_settings(DEBUG=False, BASE_DIR=root),
                  patch.dict(connection.settings_dict, {'NAME': str(database)})):
                mismatched = subprocess.CompletedProcess(
                    args=['git', 'rev-parse', 'HEAD'], returncode=0,
                    stdout='b' * 40 + '\n', stderr='',
                )
                with patch(git, return_value=mismatched):
                    with self.assertRaisesMessage(CommandError, '当前部署代码不一致'):
                        command._guard_commit_sha(options)
                with patch(git, side_effect=subprocess.TimeoutExpired('git', 10)):
                    with self.assertRaisesMessage(CommandError, '无法核验当前部署提交 SHA'):
                        command._guard_commit_sha(options)
        with override_settings(DEBUG=True), patch(
                'storefront.management.commands.publish_catalog_copy.subprocess.run') as run:
            command._guard_commit_sha(options)
            run.assert_not_called()

    def test_operation_reuse_with_other_source_or_changed_copy_is_rejected(self):
        options = self.options()
        LogEntry.objects.create(user=self.actor, content_type=ContentType.objects.get_for_model(StoreTranslation),
                                object_id='1', object_repr='different', action_flag=2,
                                change_message=json.dumps([{'seo_release': {'source': 'other-source',
                                                                          'operation_id': options['operation_id']}}]))
        with self.assertRaisesMessage(CommandError, '不同操作'):
            self.invoke(**options)
        LogEntry.objects.all().delete()
        self.invoke(**options)
        StoreTranslation.objects.filter(kind='product', key='60', locale='en').update(body='Later edit')
        with self.assertRaisesMessage(CommandError, '资料随后变化'):
            self.invoke(**options)
