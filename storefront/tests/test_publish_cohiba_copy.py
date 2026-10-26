import hashlib
import io
import json
from copy import deepcopy
from unittest.mock import patch

from django.contrib.admin.models import LogEntry
from django.contrib.contenttypes.models import ContentType
from django.core.management import CommandError, call_command
from django.db import transaction
from django.test import TestCase, override_settings
from django.utils import timezone

from cigars.models import Brand, Cigar, CigarPrice, PurchaseBatch, StockMovement
from storefront.management.commands.prepare_cohiba_content import COPY_FIELDS
from storefront.management.commands.publish_cohiba_copy import Command, LOCALES, SCOPE
from storefront.management.commands.publish_cohiba_russian_copy import PRODUCT_IDS, SOURCE, SCOPE as RUSSIAN_SCOPE
from storefront.models import ProductListing, StoreTranslation
from storefront.tests.test_publish_cohiba_russian_copy import CohibaCopyCommandFixture


@override_settings(DEBUG=True)
class PublishCohibaCopyTests(CohibaCopyCommandFixture, TestCase):
    command_name = 'publish_cohiba_copy'

    def setUp(self):
        super().setUp()
        # Model production after the prior Russian release, without changing its
        # timestamps or adding audit records to this fixture.
        for row in StoreTranslation.objects.filter(pk__in=self.targets):
            entry = self.content['brand'] if row.kind == 'brand' else next(
                item for item in self.content['products'] if str(item['id']) == row.key)
            StoreTranslation.objects.filter(pk=row.pk).update(**entry['translations']['ru'])
        unrelated = Cigar.objects.create(pk=120, brand='Cohiba', english_name='Other model')
        for locale in LOCALES:
            StoreTranslation.objects.create(kind='product', key=str(unrelated.pk), locale=locale,
                                            title='Other model', description='Keep description',
                                            body='Keep body', published=True)

    def invoke_legacy(self, **options):
        out = io.StringIO()
        call_command('publish_cohiba_russian_copy', stdout=out, **options)
        return json.loads(out.getvalue())

    def desired(self, row):
        entry = self.content['brand'] if row['kind'] == 'brand' else next(
            item for item in self.content['products'] if str(item['id']) == row['key'])
        return entry['translations'][row['locale']]

    def test_fixed_fifteen_row_preview_is_read_only_with_ten_changes(self):
        before = self.state()
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            with patch.object(ContentType.objects, 'get_for_model', side_effect=AssertionError('dry-run write')):
                report = self.invoke()
        self.assertEqual(self.state(), before)
        self.assertEqual(callbacks, [])
        self.assertEqual(report['scope'], SCOPE)
        self.assertEqual(report['source'], SOURCE)
        self.assertEqual(report['changed_rows'], 10)
        self.assertEqual(len(report['translations']), 15)
        self.assertEqual({(row['kind'], row['key'], row['locale']) for row in report['translations']},
                         {(kind, key, locale) for kind, key in [('brand', 'cohiba'),
                          *[('product', str(pk)) for pk in PRODUCT_IDS]] for locale in LOCALES})
        for row in report['translations']:
            self.assertEqual(row['action'], 'unchanged' if row['locale'] == 'ru' else 'update')
            for field in COPY_FIELDS:
                self.assertEqual(row['after'][field], self.desired(row)[field])
        self.assertEqual(report['expected_digest'], self.invoke()['expected_digest'])
        parser = Command().create_parser('manage.py', self.command_name)
        for option in ('--locale', '--locales', '--key', '--id', '--scope'):
            self.assertNotIn(option, parser._option_string_actions)

    @override_settings(DEBUG=False)
    def test_ten_updates_audit_and_idempotency_preserve_russian_and_business_facts(self):
        preview = self.invoke()
        before = self.state()
        options = self.apply_options(preview)
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            applied = self.invoke(**options)
        self.assertEqual(applied['changed_rows'], 10)
        self.assertEqual(len(callbacks), 10)
        after = self.state()
        for model in (Brand, Cigar, CigarPrice, PurchaseBatch, StockMovement, ProductListing):
            self.assertEqual(before[model._meta.label], after[model._meta.label])
        changed_ids = {row['id'] for row in preview['translations'] if row['action'] == 'update'}
        self.assertEqual([row for row in before['storefront.StoreTranslation'] if row['id'] not in changed_ids],
                         [row for row in after['storefront.StoreTranslation'] if row['id'] not in changed_ids])
        for row in applied['translations']:
            for field in ('id', 'kind', 'key', 'cigar_id', 'locale', 'hours', 'published'):
                self.assertEqual(row['before'][field], row['after'][field])
            if row['action'] == 'unchanged':
                self.assertEqual(row['before'], row['after'])
            for field in COPY_FIELDS:
                self.assertEqual(row['after'][field], self.desired(row)[field])
        logs = list(LogEntry.objects.order_by('pk'))
        self.assertEqual(len(logs), 10)
        changed = [row for row in applied['translations'] if row['action'] == 'update']
        for log, row in zip(logs, changed):
            audit = json.loads(log.change_message)[0]['seo_release']
            self.assertEqual(log.user_id, self.actor.pk)
            self.assertEqual(log.object_id, str(row['id']))
            self.assertEqual(audit['source'], SOURCE)
            self.assertEqual(audit['scope'], SCOPE)
            self.assertEqual(audit['operation_id'], options['operation_id'])
            self.assertEqual(audit['commit_sha'], options['commit_sha'])
            self.assertEqual(audit['business_date'], timezone.localdate().isoformat())
            self.assertEqual(audit['before'], row['before'])
            self.assertEqual(audit['after'], row['after'])
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            repeated = self.invoke(**options)
        self.assertEqual(repeated['changed_rows'], 0)
        self.assertEqual(callbacks, [])
        self.assertEqual(after, self.state())

    def test_all_fifteen_rows_can_change_when_russian_copy_also_differs(self):
        StoreTranslation.objects.filter(pk__in=self.targets).update(body='Previous Russian body')
        options = self.apply_options()
        self.assertEqual(self.invoke()['changed_rows'], 15)
        result = self.invoke(**options)
        self.assertEqual(result['changed_rows'], 15)
        self.assertEqual(LogEntry.objects.count(), 15)
        self.assertEqual(self.invoke(**options)['changed_rows'], 0)

    def test_missing_or_draft_brand_or_product_in_any_language_rejects_batch(self):
        for locale in LOCALES:
            for kind, key in [('brand', 'cohiba'), ('product', '98')]:
                for missing in (True, False):
                    with self.subTest(locale=locale, kind=kind, missing=missing), transaction.atomic():
                        options = self.apply_options()
                        target = StoreTranslation.objects.filter(kind=kind, key=key, locale=locale)
                        if missing:
                            target.delete()
                        else:
                            target.update(published=False)
                        before = self.state()
                        with self.captureOnCommitCallbacks(execute=True) as callbacks:
                            with self.assertRaisesMessage(CommandError, f'{kind}/{key}/{locale}'):
                                self.invoke(**options)
                        self.assertEqual(before, self.state())
                        self.assertEqual(callbacks, [])
                        transaction.set_rollback(True)

    def test_cas_covers_each_language_including_current_russian_metadata(self):
        for locale in LOCALES:
            with self.subTest(locale=locale), transaction.atomic():
                options = self.apply_options()
                StoreTranslation.objects.filter(kind='product', key='98', locale=locale).update(
                    hours=f'Concurrent edit in {locale}')
                before = self.state()
                with self.assertRaisesMessage(CommandError, 'expected-digest'):
                    self.invoke(**options)
                self.assertEqual(before, self.state())
                transaction.set_rollback(True)
        for locale in ('zh', 'en'):
            with self.subTest(manifest_locale=locale):
                options = self.apply_options()
                altered = deepcopy(self.content)
                altered['products'][-1]['translations'][locale]['body'] += ' Different manifest.'
                before = self.state()
                with patch('storefront.management.commands.publish_cohiba_russian_copy.read_content', return_value=altered):
                    with self.assertRaisesMessage(CommandError, 'expected-digest'):
                        self.invoke(**options)
                self.assertEqual(before, self.state())

    def test_missing_manifest_translation_rejects_without_writes(self):
        for locale in LOCALES:
            with self.subTest(locale=locale):
                options = self.apply_options()
                altered = deepcopy(self.content)
                del altered['products'][-1]['translations'][locale]
                before = self.state()
                with patch('storefront.management.commands.publish_cohiba_russian_copy.read_content', return_value=altered):
                    with self.assertRaises(CommandError):
                        self.invoke(**options)
                self.assertEqual(before, self.state())

    def test_late_english_save_or_audit_failure_rolls_back_ten_updates(self):
        last = StoreTranslation.objects.get(kind='product', key='98', locale='en')
        options = self.apply_options()
        original_save = StoreTranslation.save
        original_log = LogEntry.objects.create
        visited = []

        def fail_last_save(row, *args, **kwargs):
            visited.append(row.pk)
            if row.pk == last.pk:
                raise RuntimeError('last English save failed')
            return original_save(row, *args, **kwargs)

        def fail_last_log(**kwargs):
            visited.append(int(kwargs['object_id']))
            if kwargs['object_id'] == str(last.pk):
                raise RuntimeError('last English audit failed')
            return original_log(**kwargs)

        for failure in [patch.object(StoreTranslation, 'save', fail_last_save),
                        patch.object(LogEntry.objects, 'create', side_effect=fail_last_log)]:
            visited.clear()
            before = self.state()
            with self.captureOnCommitCallbacks(execute=True) as callbacks:
                with failure, self.assertRaises(CommandError):
                    self.invoke(**options)
            self.assertEqual(len(visited), 10)
            self.assertEqual(before, self.state())
            self.assertEqual(callbacks, [])

    def test_operation_id_cannot_cross_scopes_and_legacy_retry_remains_valid(self):
        StoreTranslation.objects.filter(pk__in=self.targets).update(body='Before the Russian release')
        old_preview = self.invoke_legacy()
        old_options = self.apply_options(old_preview, operation_id='prior-russian-release')
        self.assertEqual(self.invoke_legacy(**old_options)['changed_rows'], 5)
        original_logs = list(LogEntry.objects.order_by('pk').values())
        before = self.state()
        with self.assertRaisesMessage(CommandError, '不同的范围'):
            self.invoke(**self.apply_options(operation_id=old_options['operation_id']))
        self.assertEqual(before, self.state())
        options = self.apply_options(operation_id='new-trilingual-release')
        self.assertEqual(self.invoke(**options)['changed_rows'], 10)
        before = self.state()
        with self.assertRaisesMessage(CommandError, '不同的范围'):
            self.invoke_legacy(**{**options, 'expected_digest': self.invoke_legacy()['expected_digest']})
        self.assertEqual(before, self.state())
        self.assertEqual(self.invoke_legacy(**old_options)['changed_rows'], 0)
        self.assertEqual(before, self.state())
        self.assertEqual(original_logs, list(LogEntry.objects.order_by('pk').values())[:5])
        self.assertEqual({json.loads(row['change_message'])[0]['seo_release']['scope'] for row in original_logs},
                         {RUSSIAN_SCOPE})

    def test_legacy_russian_digest_format_and_fixed_scope_are_unchanged(self):
        report = self.invoke_legacy()
        self.assertEqual(report['scope'], 'cohiba-russian-copy-v1')
        self.assertEqual(len(report['translations']), 5)
        self.assertEqual([row['locale'] for row in report['translations']], ['ru'] * 5)
        self.assertEqual([row['key'] for row in report['translations']], ['cohiba', '102', '103', '97', '98'])

        def original_digest(value):
            return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                             separators=(',', ':')).encode()).hexdigest()

        content_digest = original_digest([{'kind': row['kind'], 'key': row['key'], 'locale': 'ru',
                                          'copy': self.desired(row)} for row in report['translations']])
        identities = [{'kind': 'brand', 'id': self.brand.pk, 'english_name': 'Cohiba', 'slug': 'cohiba'}]
        for pk in PRODUCT_IDS:
            cigar = Cigar.objects.get(pk=pk)
            identities.append({'kind': 'product', 'id': pk, 'brand': cigar.brand,
                               **{field: getattr(cigar, field) for field in
                                  ('english_name', 'length', 'ring_gauge', 'release_type', 'release_name')}})
        self.assertEqual(report['content_digest'], content_digest)
        self.assertEqual(report['expected_digest'], original_digest({
            'scope': RUSSIAN_SCOPE, 'identities': identities,
            'before': [row['before'] for row in report['translations']], 'content_digest': content_digest}))

    def test_trilingual_apply_keeps_required_credentials_and_idempotency_conflicts(self):
        options = self.apply_options()
        for field in ('expected_digest', 'actor', 'operation_id', 'commit_sha'):
            before = self.state()
            with self.subTest(missing=field), self.assertRaises(CommandError):
                self.invoke(**{**options, field: ''})
            self.assertEqual(before, self.state())
        self.actor.is_staff = False
        self.actor.save(update_fields=['is_staff'])
        before = self.state()
        with self.assertRaisesMessage(CommandError, 'active staff'):
            self.invoke(**options)
        self.assertEqual(before, self.state())
        self.actor.is_staff = True
        self.actor.save(update_fields=['is_staff'])
        self.invoke(**options)
        StoreTranslation.objects.filter(kind='product', key='98', locale='en').update(body='Later correction')
        before = self.state()
        with self.assertRaisesMessage(CommandError, '已执行'):
            self.invoke(**self.apply_options(operation_id=options['operation_id']))
        self.assertEqual(before, self.state())
        self.assertEqual(self.invoke(**self.apply_options(operation_id='fresh-review'))['changed_rows'], 1)
