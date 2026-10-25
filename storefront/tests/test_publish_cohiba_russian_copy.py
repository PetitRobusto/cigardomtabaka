import io
import json
from copy import deepcopy
from decimal import Decimal
from unittest.mock import patch

from django.contrib.admin.models import LogEntry
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from cigars.models import Brand, Cigar, CigarPrice, PurchaseBatch, StockMovement
from cigars.tests.inventory_fixtures import create_purchase_batch
from storefront.management.commands.prepare_cohiba_content import COPY_FIELDS, read_content
from storefront.management.commands.publish_cohiba_russian_copy import SOURCE
from storefront.models import ProductListing, RefreshState, StoreTranslation


@override_settings(DEBUG=True)
class PublishCohibaRussianCopyTests(TestCase):
    def setUp(self):
        self.content = read_content()
        self.actor = get_user_model().objects.create_user(username='seo-owner', is_staff=True)
        self.brand = Brand.objects.create(english_name='Cohiba', name='高希霸', slug='cohiba')
        self.cigars = {}
        for entry in self.content['products']:
            cigar = Cigar.objects.create(pk=entry['id'], brand='Cohiba', english_name=entry['english_name'],
                                         length=entry['length'], ring_gauge=entry['ring_gauge'])
            self.cigars[cigar.pk] = cigar
            CigarPrice.objects.create(cigar=cigar, box_size=entry['box_size'], wholesale_price=123,
                                      retail_price_rub=None, can_preorder=False)
            ProductListing.objects.create(cigar=cigar, published=True)
        create_purchase_batch(source='opening', cigar=self.cigars[102], quantity=10, remaining=10,
                              physical_remaining=10, box_size=10, unit_cost_cny=Decimal('1'))
        self.targets = []
        for locale in ('ru', 'en', 'zh'):
            for kind, key in [('brand', 'cohiba'), *[('product', str(pk)) for pk in self.cigars]]:
                row = StoreTranslation.objects.create(
                    kind=kind, key=key, locale=locale, title=f'{locale} prior {key}',
                    description='Prior reviewed summary', body='Prior reviewed body',
                    aliases='prior-alias', hours='preserved-hours', published=True)
                if locale == 'ru':
                    self.targets.append(row.pk)
        StoreTranslation.objects.create(kind='home', key='home', locale='ru', title='Home',
                                        description='Home summary', body='Home body', published=True)
        RefreshState.objects.get_or_create(pk=1)

    def invoke(self, **options):
        out = io.StringIO()
        call_command('publish_cohiba_russian_copy', stdout=out, **options)
        return json.loads(out.getvalue())

    def apply_options(self, preview=None, **overrides):
        preview = preview or self.invoke()
        return {'apply': True, 'expected_digest': preview['expected_digest'], 'actor': self.actor.username,
                'operation_id': 'seo05-release-1', 'commit_sha': 'a' * 40, **overrides}

    def state(self):
        return {model._meta.label: list(model.objects.order_by('pk').values())
                for model in (Brand, Cigar, CigarPrice, PurchaseBatch, StockMovement, ProductListing,
                              StoreTranslation, RefreshState, LogEntry, ContentType)}

    def test_dry_run_is_read_only_and_reports_complete_approved_diff(self):
        before = self.state()
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            with patch.object(ContentType.objects, 'get_for_model', side_effect=AssertionError('dry-run must not create content types')):
                report = self.invoke()
        self.assertEqual(before, self.state())
        self.assertEqual(callbacks, [])
        self.assertEqual(report['mode'], 'dry-run')
        self.assertEqual(report['changed_rows'], 5)
        self.assertEqual(report['expected_digest'], self.invoke()['expected_digest'])
        self.assertEqual({(r['kind'], r['key'], r['locale']) for r in report['translations']},
                         {('brand', 'cohiba', 'ru'), *[('product', str(pk), 'ru') for pk in self.cigars]})
        self.assertEqual(report['translations'][0]['before']['title'], 'ru prior cohiba')
        self.assertEqual(report['translations'][0]['after']['title'], self.content['brand']['translations']['ru']['title'])
        self.assertIn('updated_at', report['translations'][0]['before'])

    @override_settings(DEBUG=False)
    def test_apply_audits_five_rows_preserves_business_facts_and_is_idempotent(self):
        preview = self.invoke()
        before = self.state()
        options = self.apply_options(preview)
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            report = self.invoke(**options)
        self.assertEqual(report['changed_rows'], 5)
        self.assertEqual(len(callbacks), 5)
        after = self.state()
        for model in (Brand, Cigar, CigarPrice, PurchaseBatch, StockMovement, ProductListing):
            self.assertEqual(before[model._meta.label], after[model._meta.label])
        untouched_before = [r for r in before['storefront.StoreTranslation'] if r['id'] not in self.targets]
        untouched_after = [r for r in after['storefront.StoreTranslation'] if r['id'] not in self.targets]
        self.assertEqual(untouched_before, untouched_after)
        for expected, actual in zip(preview['translations'], report['translations']):
            for field in ('id', 'kind', 'key', 'cigar_id', 'locale', 'hours', 'published'):
                self.assertEqual(expected['before'][field], actual['after'][field])
            for field in COPY_FIELDS:
                self.assertEqual(expected['after'][field], actual['after'][field])
        logs = list(LogEntry.objects.order_by('pk'))
        self.assertEqual(len(logs), 5)
        for log, row in zip(logs, report['translations']):
            metadata = json.loads(log.change_message)[0]['seo_release']
            self.assertEqual(log.user_id, self.actor.pk)
            self.assertEqual(log.object_id, str(row['id']))
            self.assertEqual(metadata['source'], SOURCE)
            self.assertEqual(metadata['operation_id'], options['operation_id'])
            self.assertEqual(metadata['commit_sha'], options['commit_sha'])
            self.assertEqual(metadata['before'], row['before'])
            self.assertEqual(metadata['after'], row['after'])
            self.assertEqual(metadata['business_date'], timezone.localdate().isoformat())
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            repeat = self.invoke(**options)
        self.assertEqual(repeat['changed_rows'], 0)
        self.assertEqual(callbacks, [])
        self.assertEqual(after, self.state())

    def test_preview_detects_copy_metadata_and_target_content_drift(self):
        for field, value in [('body', 'Concurrent custom copy'), ('hours', 'Concurrent hours'),
                             ('updated_at', timezone.now())]:
            with self.subTest(field=field):
                preview = self.invoke()
                StoreTranslation.objects.filter(pk=self.targets[-1]).update(**{field: value})
                before = self.state()
                with self.assertRaisesMessage(CommandError, 'expected-digest'):
                    self.invoke(**self.apply_options(preview))
                self.assertEqual(before, self.state())
        preview = self.invoke()
        changed_content = deepcopy(self.content)
        changed_content['products'][-1]['translations']['ru']['body'] += ' Changed manifest.'
        before = self.state()
        with patch('storefront.management.commands.publish_cohiba_russian_copy.read_content', return_value=changed_content):
            with self.assertRaisesMessage(CommandError, 'expected-digest'):
                self.invoke(**self.apply_options(preview))
        self.assertEqual(before, self.state())

    def test_missing_draft_or_wrong_identity_aborts_whole_batch(self):
        preview = self.invoke()
        last = self.targets[-1]
        StoreTranslation.objects.filter(pk=last).update(published=False)
        before = self.state()
        with self.assertRaisesMessage(CommandError, '未发布'):
            self.invoke(**self.apply_options(preview))
        self.assertEqual(before, self.state())
        StoreTranslation.objects.filter(pk=last).update(published=True)
        self.cigars[98].length = 1
        self.cigars[98].save(update_fields=['length'])
        before = self.state()
        with self.assertRaisesMessage(CommandError, '身份、尺寸或版本'):
            self.invoke(**self.apply_options(preview))
        self.assertEqual(before, self.state())
        self.cigars[98].length = 155
        self.cigars[98].save(update_fields=['length'])
        StoreTranslation.objects.filter(pk=last).delete()
        before = self.state()
        with self.assertRaisesMessage(CommandError, '缺失'):
            self.invoke(**self.apply_options(preview))
        self.assertEqual(before, self.state())

    def test_soft_deleted_or_different_release_is_rejected(self):
        for changes in [{'deleted_at': timezone.now()}, {'release_name': 'Different edition'}, {'brand': 'Other brand'}]:
            with self.subTest(changes=changes):
                original = Cigar.objects.get(pk=98)
                Cigar.objects.filter(pk=98).update(**changes)
                before = self.state()
                with self.assertRaises(CommandError):
                    self.invoke()
                self.assertEqual(before, self.state())
                Cigar.objects.filter(pk=98).update(**{field: getattr(original, field) for field in changes})

    def test_all_apply_credentials_and_option_formats_are_required(self):
        options = self.apply_options()
        invalid = [{name: ''} for name in ('expected_digest', 'actor', 'operation_id', 'commit_sha')]
        invalid += [{'expected_digest': 'x' * 64}, {'commit_sha': 'abc'}, {'operation_id': 'id\nline'},
                    {'operation_id': 'a' * 121}, {'actor': ' seo-owner'}, {'actor': 'x' * 151}]
        for overrides in invalid:
            with self.subTest(overrides=overrides):
                before = self.state()
                with self.assertRaises(CommandError):
                    self.invoke(**{**options, **overrides})
                self.assertEqual(before, self.state())

    def test_missing_inactive_or_nonstaff_actor_cannot_apply(self):
        options = self.apply_options()
        for username, active, staff in [('absent', True, True), ('seo-owner', False, True), ('seo-owner', True, False)]:
            with self.subTest(username=username, active=active, staff=staff):
                get_user_model().objects.filter(pk=self.actor.pk).update(is_active=active, is_staff=staff)
                before = self.state()
                with self.assertRaisesMessage(CommandError, 'active staff'):
                    self.invoke(**{**options, 'actor': username})
                self.assertEqual(before, self.state())

    def test_reusing_an_operation_cannot_overwrite_later_changes(self):
        options = self.apply_options()
        self.invoke(**options)
        StoreTranslation.objects.filter(pk=self.targets[-1]).update(body='Subsequent manual correction')
        fresh = self.invoke()
        before = self.state()
        with self.assertRaisesMessage(CommandError, '已执行'):
            self.invoke(**{**options, 'expected_digest': fresh['expected_digest']})
        self.assertEqual(before, self.state())
        result = self.invoke(**{**options, 'expected_digest': fresh['expected_digest'], 'operation_id': 'seo05-release-2'})
        self.assertEqual(result['changed_rows'], 1)

    def test_reusing_operation_with_another_commit_or_actor_fails_even_when_already_current(self):
        options = self.apply_options()
        self.invoke(**options)
        other = get_user_model().objects.create_user(username='other-owner', is_staff=True)
        before = self.state()
        for overrides in [{'commit_sha': 'b' * 40}, {'actor': other.username}]:
            with self.subTest(overrides=overrides):
                with self.assertRaisesMessage(CommandError, 'operation-id'):
                    self.invoke(**{**options, **overrides})
                self.assertEqual(before, self.state())

    def test_late_save_or_audit_failure_rolls_back_prior_changes_and_callbacks(self):
        original_save = StoreTranslation.save
        original_log = LogEntry.objects.create
        options = self.apply_options()

        def fail_last_save(row, *args, **kwargs):
            if row.pk == self.targets[-1]:
                raise RuntimeError('injected save failure')
            return original_save(row, *args, **kwargs)

        def fail_last_log(**kwargs):
            if kwargs['object_id'] == str(self.targets[-1]):
                raise RuntimeError('injected audit failure')
            return original_log(**kwargs)

        patches = [patch.object(StoreTranslation, 'save', fail_last_save),
                   patch.object(LogEntry.objects, 'create', side_effect=fail_last_log)]
        for failure in patches:
            before = self.state()
            with self.captureOnCommitCallbacks(execute=True) as callbacks:
                with failure, self.assertRaises(CommandError):
                    self.invoke(**options)
            self.assertEqual(callbacks, [])
            self.assertEqual(before, self.state())
