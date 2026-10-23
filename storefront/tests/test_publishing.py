import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.db import transaction
from django.test import TestCase, override_settings
from django.utils import timezone

from storefront.models import RefreshState, StorePage, StoreTranslation
from storefront.publishing import publish_pending, reconcile, request_refresh


class PublishingTests(TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.renderer = Path(self.tmp.name) / 'render.mjs'
        self.renderer.write_text('// test renderer')
        self.settings_override = override_settings(STOREFRONT_RENDERER=self.renderer)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        self.assets = {'js': ['/static/app.js'], 'css': []}
        self.payload = {'path': '/', 'title': '现货', 'body': '商品', 'locale': 'zh'}
        self.pages = {'/': self.payload}
        self.catalog_patch = patch('storefront.catalog.build_pages', side_effect=lambda: self.pages)
        self.catalog_patch.start()
        self.addCleanup(self.catalog_patch.stop)

    @staticmethod
    def render(pages, assets):
        return {p.path: '<h1>' + p.payload['title'] + '</h1>' for p in pages}

    def sync(self):
        reconcile(assets=self.assets)

    def test_refresh_registered_only_after_successful_transaction(self):
        with self.captureOnCommitCallbacks(execute=True):
            StoreTranslation.objects.create(kind='home', key='home', locale='zh', title='a', description='b', body='c')
            self.assertFalse(RefreshState.objects.exists())
        self.assertGreater(RefreshState.objects.get(pk=1).revision, 0)
        previous = RefreshState.objects.get(pk=1).revision
        with self.captureOnCommitCallbacks(execute=True):
            try:
                with transaction.atomic():
                    StoreTranslation.objects.create(kind='home', key='home', locale='en', title='a', description='b', body='c')
                    raise ValueError('rollback')
            except ValueError:
                pass
        self.assertEqual(RefreshState.objects.get(pk=1).revision, previous)

    def test_content_unchanged_does_not_rerender_or_fake_lastmod(self):
        self.sync()
        self.assertEqual(publish_pending(assets=self.assets, renderer=self.render), 1)
        before = StorePage.objects.get(path='/')
        request_refresh()
        self.sync()
        self.assertEqual(publish_pending(assets=self.assets, renderer=self.render), 0)
        after = StorePage.objects.get(path='/')
        self.assertEqual(after.changed_at, before.changed_at)
        self.assertEqual(after.rendered_at, before.rendered_at)

    def test_failed_generation_preserves_old_html_and_retries(self):
        self.sync()
        publish_pending(assets=self.assets, renderer=self.render)
        published = StorePage.objects.get(path='/')
        old = published.html
        self.pages = {'/': dict(self.payload, title='新价格')}
        request_refresh()
        self.sync()
        def broken(*args):
            raise RuntimeError('renderer unavailable')
        self.assertEqual(publish_pending(assets=self.assets, renderer=broken), 0)
        row = StorePage.objects.get(path='/')
        self.assertEqual(row.html, old)
        self.assertEqual(row.rendered_changed_at, published.changed_at)
        self.assertNotEqual(row.changed_at, row.rendered_changed_at)
        self.assertEqual(row.attempts, 1)
        self.assertIn('renderer unavailable', row.error)
        self.assertEqual(publish_pending(assets=self.assets, renderer=self.render), 0)
        StorePage.objects.update(retry_at=timezone.now())
        self.assertEqual(publish_pending(assets=self.assets, renderer=self.render), 1)
        self.assertIn('新价格', StorePage.objects.get(path='/').html)
        row.refresh_from_db()
        self.assertEqual(row.rendered_changed_at, row.changed_at)

    def test_mutation_during_render_does_not_publish_stale_generation(self):
        self.sync()
        def racing_renderer(pages, assets):
            request_refresh()
            return self.render(pages, assets)
        self.assertEqual(publish_pending(assets=self.assets, renderer=racing_renderer), 0)
        self.assertEqual(StorePage.objects.get(path='/').html, '')

    def test_stale_reconcile_cannot_withdraw_a_newer_published_generation(self):
        newest = {}

        def stale_snapshot():
            request_refresh()
            current_pages = {'/': dict(self.payload, title='最新页面')}
            with patch('storefront.catalog.build_pages', return_value=current_pages):
                self.sync()
                self.assertEqual(publish_pending(assets=self.assets, renderer=self.render), 1)
            newest['page'] = StorePage.objects.get(path='/')
            newest['state'] = RefreshState.objects.get(pk=1)
            return {}

        with patch('storefront.catalog.build_pages', side_effect=stale_snapshot):
            self.sync()

        page = StorePage.objects.get(path='/')
        state = RefreshState.objects.get(pk=1)
        self.assertTrue(page.active)
        self.assertEqual(page.html, newest['page'].html)
        self.assertEqual(page.desired_hash, newest['page'].desired_hash)
        self.assertEqual(state.processed_revision, newest['state'].processed_revision)
        self.assertEqual(state.reconciled_at, newest['state'].reconciled_at)

    def test_withdrawal_removes_old_artifact(self):
        self.sync()
        publish_pending(assets=self.assets, renderer=self.render)
        self.pages = {}
        request_refresh()
        self.sync()
        row = StorePage.objects.get(path='/')
        self.assertFalse(row.active)
        self.assertEqual(row.html, '')

    def test_stale_reconcile_cannot_replace_same_revision_compensation(self):
        self.sync()
        publish_pending(assets=self.assets, renderer=self.render)
        revision = RefreshState.objects.get(pk=1).revision
        newest = {}

        def stale_snapshot():
            # Periodic compensation can discover a missed refresh signal without
            # incrementing revision, so the completed reconciliation also matters.
            current_pages = {'/': dict(self.payload, title='补偿后的页面')}
            with patch('storefront.catalog.build_pages', return_value=current_pages):
                self.sync()
                self.assertEqual(publish_pending(assets=self.assets, renderer=self.render), 1)
            newest['page'] = StorePage.objects.get(path='/')
            newest['state'] = RefreshState.objects.get(pk=1)
            return {}

        with patch('storefront.catalog.build_pages', side_effect=stale_snapshot):
            self.sync()

        page = StorePage.objects.get(path='/')
        state = RefreshState.objects.get(pk=1)
        self.assertTrue(page.active)
        self.assertEqual(page.html, newest['page'].html)
        self.assertEqual(page.desired_hash, newest['page'].desired_hash)
        self.assertEqual(state.revision, revision)
        self.assertEqual(state.reconciled_at, newest['state'].reconciled_at)

    def test_older_failed_render_cannot_mark_a_successful_publication_failed(self):
        self.sync()
        published = {}

        def slow_failure(pages, assets):
            self.assertEqual(publish_pending(assets=assets, renderer=self.render), 1)
            published['page'] = StorePage.objects.get(path='/')
            raise RuntimeError('older renderer attempt failed')

        self.assertEqual(publish_pending(assets=self.assets, renderer=slow_failure), 0)
        page = StorePage.objects.get(path='/')
        self.assertEqual(page.html, published['page'].html)
        self.assertEqual(page.rendered_hash, page.desired_hash)
        self.assertEqual(page.error, '')
        self.assertEqual(page.attempts, 0)
        self.assertEqual(page.retry_at, published['page'].retry_at)
        self.assertEqual(publish_pending(assets=self.assets, renderer=self.render), 0)

    def test_older_failed_render_cannot_add_a_retry_to_withdrawn_page(self):
        self.sync()
        withdrawn = {}

        def withdrawn_during_render(pages, assets):
            self.pages = {}
            request_refresh()
            self.sync()
            withdrawn['page'] = StorePage.objects.get(path='/')
            raise RuntimeError('renderer failed after withdrawal')

        self.assertEqual(publish_pending(assets=self.assets, renderer=withdrawn_during_render), 0)
        page = StorePage.objects.get(path='/')
        self.assertFalse(page.active)
        self.assertEqual(page.html, '')
        self.assertEqual(page.rendered_hash, '')
        self.assertEqual(page.error, '')
        self.assertEqual(page.attempts, 0)
        self.assertEqual(page.retry_at, withdrawn['page'].retry_at)

    def test_new_build_refreshes_html_without_changing_content_lastmod(self):
        self.sync()
        publish_pending(assets=self.assets, renderer=self.render)
        before = StorePage.objects.get(path='/')
        self.renderer.write_text('// second build')
        self.sync()
        after = StorePage.objects.get(path='/')
        self.assertEqual(after.changed_at, before.changed_at)
        self.assertNotEqual(after.desired_hash, before.desired_hash)

    def test_stale_assets_do_not_publish_new_build_and_schedule_reconciliation(self):
        self.pages['/other'] = dict(self.payload, path='/other')
        self.sync()
        self.assertEqual(publish_pending(assets=self.assets, renderer=self.render), 2)
        previous = {page.path: page for page in StorePage.objects.all()}
        new_assets = {'js': ['/static/new-build.js'], 'css': []}
        reconcile(assets=new_assets)
        render_calls = []

        def stale_worker(pages, assets):
            render_calls.append(pages)
            return self.render(pages, assets)

        self.assertEqual(publish_pending(assets=self.assets, renderer=stale_worker), 0)
        self.assertEqual(render_calls, [])
        for page in StorePage.objects.all():
            self.assertEqual(page.html, previous[page.path].html)
            self.assertEqual(page.rendered_hash, previous[page.path].rendered_hash)
            self.assertNotEqual(page.rendered_hash, page.desired_hash)
        state = RefreshState.objects.get(pk=1)
        self.assertGreater(state.revision, state.processed_revision)

        reconcile(assets=new_assets)
        self.assertEqual(publish_pending(assets=new_assets, renderer=self.render), 2)
        for page in StorePage.objects.all():
            self.assertEqual(page.rendered_hash, page.desired_hash)
            self.assertEqual(page.changed_at, previous[page.path].changed_at)

    def test_renderer_replaced_during_render_keeps_old_html_and_reconciles(self):
        self.sync()
        publish_pending(assets=self.assets, renderer=self.render)
        published = StorePage.objects.get(path='/')
        self.pages = {'/': dict(self.payload, title='等待新构建的页面')}
        request_refresh()
        self.sync()
        pending = StorePage.objects.get(path='/')

        def replaced_renderer(pages, assets):
            self.renderer.write_text('// deployed while render was running')
            return self.render(pages, assets)

        self.assertEqual(publish_pending(assets=self.assets, renderer=replaced_renderer), 0)
        page = StorePage.objects.get(path='/')
        self.assertEqual(page.html, published.html)
        self.assertEqual(page.rendered_hash, published.rendered_hash)
        self.assertEqual(page.error, '')
        self.assertEqual(page.attempts, 0)
        state = RefreshState.objects.get(pk=1)
        self.assertGreater(state.revision, state.processed_revision)

        self.sync()
        self.assertEqual(publish_pending(assets=self.assets, renderer=self.render), 1)
        page.refresh_from_db()
        self.assertIn('等待新构建的页面', page.html)
        self.assertEqual(page.rendered_hash, page.desired_hash)
        self.assertNotEqual(page.desired_hash, pending.desired_hash)
        self.assertEqual(page.changed_at, pending.changed_at)

    def test_bad_renderer_output_does_not_publish(self):
        from storefront.publishing import render_batch
        self.sync()
        with patch('storefront.publishing.subprocess.run') as run:
            run.return_value.stdout = json.dumps([{'path': '/', 'html': '<div>Loading</div>'}])
            with self.assertRaises(ValueError):
                render_batch(list(StorePage.objects.all()), self.assets)
