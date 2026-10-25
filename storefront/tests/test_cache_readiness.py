import io
from unittest.mock import patch

from django.core.management import CommandError, call_command
from django.test import TestCase

from storefront.models import RefreshState, StorePage
from storefront.publishing import generation_hash


class StorefrontCacheReadinessTests(TestCase):
    def setUp(self):
        RefreshState.objects.create(pk=1, revision=1, processed_revision=1)
        self.pages = {'/ru/': {'path': '/ru/', 'title': 'Сигары в Москве'}}
        self.assets = {'js': ['/static/frontend/assets/current.js'], 'css': []}
        self.build_id = 'renderer-build'
        wanted = generation_hash(self.pages['/ru/'], self.assets, self.build_id)
        self.row = StorePage.objects.create(path='/ru/', active=True, html='<h1>Сигары</h1>',
                                           desired_hash=wanted, rendered_hash=wanted,
                                           rendered_payload=self.pages['/ru/'])

    def run_check(self):
        module = 'storefront.management.commands.check_storefront_cache'
        output = io.StringIO()
        with patch(module + '.build_pages', return_value=self.pages), \
             patch(module + '.build_assets', return_value=self.assets), \
             patch(module + '.renderer_digest', return_value=self.build_id):
            call_command('check_storefront_cache', stdout=output)
        return output.getvalue()

    def snapshot(self):
        return list(StorePage.objects.values()), list(RefreshState.objects.values())

    def test_current_generation_passes_without_writes(self):
        before = self.snapshot()
        self.assertIn('1 页', self.run_check())
        self.assertEqual(before, self.snapshot())

    def test_missing_page_and_empty_catalog_fail_without_writes(self):
        self.pages['/en/'] = {'path': '/en/'}
        before = self.snapshot()
        with self.assertRaisesMessage(CommandError, '1 页待更新'):
            self.run_check()
        self.assertEqual(before, self.snapshot())
        self.pages = {}
        with self.assertRaisesMessage(CommandError, '页面集合为空'):
            self.run_check()

    def test_inactive_empty_failed_or_obsolete_cache_stops_release(self):
        for field, value in [('active', False), ('html', ''), ('error', 'renderer failed'),
                             ('rendered_hash', 'obsolete'), ('desired_hash', 'pending'),
                             ('rendered_payload', {}), ('rendered_payload', {'path': '/ru/', 'title': 'Old'})]:
            with self.subTest(field=field):
                original = getattr(self.row, field)
                StorePage.objects.filter(pk=self.row.pk).update(**{field: value})
                before = self.snapshot()
                with self.assertRaisesMessage(CommandError, '缓存验收未通过'):
                    self.run_check()
                self.assertEqual(before, self.snapshot())
                StorePage.objects.filter(pk=self.row.pk).update(**{field: original})

    def test_changed_content_assets_renderer_or_origin_stops_release(self):
        for change in ['content', 'assets', 'renderer', 'origin']:
            with self.subTest(change=change):
                if change == 'content':
                    with patch.dict(self.pages['/ru/'], title='Updated'):
                        with self.assertRaises(CommandError):
                            self.run_check()
                elif change == 'assets':
                    with patch.dict(self.assets, js=['/static/frontend/assets/new.js']):
                        with self.assertRaises(CommandError):
                            self.run_check()
                elif change == 'renderer':
                    with patch.object(self, 'build_id', 'next-renderer'):
                        with self.assertRaises(CommandError):
                            self.run_check()
                else:
                    with self.settings(STOREFRONT_ORIGIN='https://changed.example'):
                        with self.assertRaises(CommandError):
                            self.run_check()

    def test_pending_or_changing_revision_cannot_pass(self):
        RefreshState.objects.filter(pk=1).update(revision=2)
        with self.assertRaisesMessage(CommandError, '内容仍待校验'):
            self.run_check()
        RefreshState.objects.filter(pk=1).update(revision=1)

        def build_while_content_changes():
            RefreshState.objects.filter(pk=1).update(revision=2)
            return self.pages

        module = 'storefront.management.commands.check_storefront_cache'
        with patch(module + '.build_pages', side_effect=build_while_content_changes), \
             patch(module + '.build_assets', return_value=self.assets), \
             patch(module + '.renderer_digest', return_value=self.build_id):
            with self.assertRaisesMessage(CommandError, '验收期间内容或构建已变化'):
                call_command('check_storefront_cache', stdout=io.StringIO())
