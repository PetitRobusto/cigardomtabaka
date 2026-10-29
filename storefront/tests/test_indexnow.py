import io
import json
from datetime import timedelta
from unittest.mock import patch

import requests
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command, CommandError
from django.test import TestCase, override_settings
from django.utils import timezone

from storefront.indexnow import MIN_INTERVAL, configuration, send_pending, sync_changes
from storefront.models import IndexNowState, IndexNowURL, RefreshState, StorePage


@override_settings(STOREFRONT_ENABLED=True, STOREFRONT_ORIGIN='https://store.example',
                   INDEXNOW_ENABLED=True, INDEXNOW_KEY='test-key-12345678')
class IndexNowTests(TestCase):
    def setUp(self):
        self.snapshot = {'/': 'home-v1', '/ru/catalog': 'catalog-v1'}
        self.snapshot_patch = patch('storefront.indexnow._public_snapshot', side_effect=lambda: self.snapshot)
        self.snapshot_patch.start()
        self.addCleanup(self.snapshot_patch.stop)
        self.calls = []

    def accept(self, payload):
        self.calls.append(payload)
        return 200, None

    def changed(self):
        sync_changes()
        self.snapshot['/'] = 'home-v2'
        sync_changes()

    def test_initial_baseline_does_not_submit_history(self):
        result = send_pending(transport=self.accept)
        self.assertEqual(result['status'], 'idle')
        self.assertEqual(self.calls, [])
        self.assertEqual(IndexNowURL.objects.count(), 2)
        self.assertTrue(IndexNowState.objects.get().initialized_at)

    def test_new_changed_and_removed_pages_are_coalesced_and_not_resent(self):
        sync_changes()
        self.snapshot = {'/': 'home-v2', '/en/': 'english-home'}
        result = send_pending(transport=self.accept)
        self.assertEqual(result['sent'], 3)
        self.assertCountEqual(self.calls[0]['urlList'], [
            'https://store.example/', 'https://store.example/en/', 'https://store.example/ru/catalog',
        ])
        self.assertEqual(self.calls[0]['host'], 'store.example')
        self.assertEqual(self.calls[0]['keyLocation'], 'https://store.example/test-key-12345678.txt')
        self.assertEqual(send_pending(transport=self.accept)['sent'], 0)
        self.assertEqual(len(self.calls), 1)

    def test_revision_or_renderer_failure_defers_notification(self):
        self.changed()
        state = RefreshState.objects.create(pk=1, revision=2, processed_revision=1)
        self.assertEqual(send_pending(transport=self.accept)['status'], 'publication_pending')
        state.processed_revision = 2
        state.save()
        StorePage.objects.create(path='/', desired_hash='new-build', rendered_hash='old-build')
        self.assertEqual(send_pending(transport=self.accept)['status'], 'publication_pending')
        self.assertFalse(self.calls)
        StorePage.objects.update(rendered_hash='new-build')
        self.assertEqual(send_pending(transport=self.accept)['sent'], 1)

    def test_no_content_change_does_not_notify_new_build(self):
        sync_changes()
        StorePage.objects.create(path='/', desired_hash='new-build', rendered_hash='new-build')
        self.assertEqual(send_pending(transport=self.accept)['sent'], 0)
        self.assertFalse(self.calls)

    def test_reverted_change_is_not_sent(self):
        self.changed()
        self.snapshot['/'] = 'home-v1'
        self.assertEqual(send_pending(transport=self.accept)['sent'], 0)
        self.assertIsNone(IndexNowURL.objects.get(path='/').retry_at)

    def test_withdrawal_then_republication_tracks_delivered_state(self):
        sync_changes()
        del self.snapshot['/']
        self.assertEqual(send_pending(transport=self.accept)['sent'], 1)
        self.snapshot['/'] = 'home-v1'
        self.assertEqual(send_pending(transport=self.accept)['sent'], 0)
        row = IndexNowURL.objects.get(path='/')
        self.assertGreaterEqual(row.retry_at, row.last_attempt_at + MIN_INTERVAL)
        with patch('storefront.indexnow.timezone.now', return_value=timezone.now() + MIN_INTERVAL):
            self.assertEqual(send_pending(transport=self.accept)['sent'], 1)

    def test_429_backoff_honors_retry_after(self):
        self.changed()
        before = timezone.now()
        self.assertEqual(send_pending(transport=lambda p: (429, '1800'))['sent'], 0)
        row = IndexNowURL.objects.get(path='/')
        self.assertEqual(row.attempts, 1)
        self.assertGreaterEqual(row.retry_at, before + timedelta(seconds=1800))
        self.assertEqual(send_pending(transport=self.accept)['sent'], 0)
        self.assertFalse(self.calls)
        IndexNowURL.objects.filter(pk=row.pk).update(retry_at=timezone.now())
        self.assertEqual(send_pending(transport=self.accept)['sent'], 1)

    def test_network_timeout_persists_safe_error_without_key(self):
        self.changed()
        def broken(payload):
            raise requests.Timeout('secret test-key-12345678')
        self.assertEqual(send_pending(transport=broken)['sent'], 0)
        row = IndexNowURL.objects.get(path='/')
        self.assertEqual(row.error, 'Timeout')
        self.assertIsNotNone(row.retry_at)

    def test_retry_limit_stops_transient_failures(self):
        self.changed()
        IndexNowURL.objects.filter(path='/').update(attempts=5)
        send_pending(transport=lambda p: (503, None))
        row = IndexNowURL.objects.get(path='/')
        self.assertEqual(row.attempts, 6)
        self.assertIsNone(row.retry_at)
        self.assertEqual(send_pending(transport=self.accept)['sent'], 0)

    def test_permanent_errors_wait_for_explicit_retry_or_corrected_key(self):
        self.changed()
        send_pending(transport=lambda p: (403, None))
        row = IndexNowURL.objects.get(path='/')
        self.assertIsNone(row.retry_at)
        self.assertEqual(send_pending(transport=self.accept)['sent'], 0)
        with override_settings(INDEXNOW_KEY='corrected-key-12345678'):
            self.assertEqual(send_pending(transport=self.accept)['sent'], 0)
            with patch('storefront.indexnow.timezone.now', return_value=timezone.now() + MIN_INTERVAL):
                self.assertEqual(send_pending(transport=self.accept)['sent'], 1)

    def test_manual_retry_preserves_per_url_cooldown(self):
        self.changed()
        send_pending(transport=lambda p: (403, None))
        call_command('notify_indexnow', retry_failed=True, stdout=io.StringIO())
        self.assertEqual(send_pending(transport=self.accept)['sent'], 0)
        with patch('storefront.indexnow.timezone.now', return_value=timezone.now() + MIN_INTERVAL):
            self.assertEqual(send_pending(transport=self.accept)['sent'], 1)

    def test_202_records_acceptance_and_pending_key_validation(self):
        self.changed()
        self.assertEqual(send_pending(transport=lambda p: (202, None))['sent'], 1)
        output = io.StringIO()
        call_command('notify_indexnow', stdout=output)
        result = json.loads(output.getvalue())
        self.assertEqual(result['key_validation_pending'], 1)
        self.assertEqual(result['pending'], 0)

    def test_redirect_is_not_success_and_transport_does_not_follow_redirects(self):
        self.changed()
        with patch('storefront.indexnow.requests.post') as post:
            post.return_value.status_code = 302
            post.return_value.headers = {}
            self.assertEqual(send_pending()['sent'], 0)
            self.assertFalse(post.call_args.kwargs['allow_redirects'])
        self.assertIsNone(IndexNowURL.objects.get(path='/').retry_at)

    def test_active_worker_lease_prevents_duplicate_send(self):
        self.changed()
        IndexNowState.objects.update(lease_until=timezone.now() + timedelta(minutes=1), lease_token='other')
        self.assertEqual(send_pending(transport=self.accept)['status'], 'busy')
        self.assertFalse(self.calls)

    def test_expired_lease_recovers(self):
        self.changed()
        IndexNowState.objects.update(lease_until=timezone.now() - timedelta(minutes=1), lease_token='dead')
        self.assertEqual(send_pending(transport=self.accept)['sent'], 1)
        self.assertEqual(IndexNowState.objects.get().lease_token, '')

    def test_inflight_response_does_not_acknowledge_a_newer_version(self):
        self.changed()
        def change_during_send(payload):
            self.snapshot['/'] = 'home-v3'
            sync_changes()
            return 200, None
        send_pending(transport=change_during_send)
        row = IndexNowURL.objects.get(path='/')
        self.assertEqual(row.desired_hash, 'home-v3')
        self.assertNotEqual(row.desired_hash, row.notified_hash)
        self.assertIsNotNone(row.last_attempt_at)
        self.assertGreaterEqual(row.retry_at, row.last_attempt_at + MIN_INTERVAL)
        self.assertEqual(send_pending(transport=self.accept)['sent'], 0)
        with patch('storefront.indexnow.timezone.now', return_value=timezone.now() + MIN_INTERVAL):
            self.assertEqual(send_pending(transport=self.accept)['sent'], 1)
        row.refresh_from_db()
        self.assertEqual(row.notified_hash, 'home-v3')
        self.assertEqual(IndexNowState.objects.get().lease_token, '')

    def test_interrupted_send_preserves_attempt_and_cooldown(self):
        self.changed()
        def interrupted(payload):
            raise SystemExit('worker stopped')
        with self.assertRaises(SystemExit):
            send_pending(transport=interrupted)
        row = IndexNowURL.objects.get(path='/')
        self.assertEqual(row.attempts, 1)
        self.assertIsNone(row.last_status)
        self.assertEqual(send_pending(transport=self.accept)['sent'], 0)
        with patch('storefront.indexnow.timezone.now', return_value=timezone.now() + MIN_INTERVAL):
            self.assertEqual(send_pending(transport=self.accept)['sent'], 1)

    def test_key_endpoint_only_serves_exact_configured_key(self):
        response = self.client.get('/test-key-12345678.txt')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b'test-key-12345678')
        self.assertIn('text/plain', response['Content-Type'])
        self.assertIn('noindex', response['X-Robots-Tag'])
        self.assertEqual(self.client.get('/other-key-12345678.txt').status_code, 404)
        self.assertEqual(self.client.post('/test-key-12345678.txt').status_code, 405)
        self.assertEqual(self.client.head('/test-key-12345678.txt').content, b'')

    def test_disabled_configuration_does_not_track_or_send(self):
        with override_settings(INDEXNOW_ENABLED=False):
            self.assertIsNone(sync_changes())
            self.assertEqual(send_pending(transport=self.accept)['status'], 'disabled')
            self.assertEqual(self.client.get('/test-key-12345678.txt').status_code, 404)
        self.assertFalse(IndexNowState.objects.exists())
        self.assertFalse(self.calls)

    def test_invalid_origin_and_key_are_rejected(self):
        for origin in ('http://store.example', 'https://user:pass@store.example',
                       'https://store.example/path', 'https://store.example:443',
                       'https://store.example:invalid', 'https://[broken'):
            with self.subTest(origin=origin), override_settings(STOREFRONT_ORIGIN=origin):
                with self.assertRaises(ImproperlyConfigured):
                    configuration()
        with override_settings(INDEXNOW_KEY='../not-safe'):
            with self.assertRaises(ImproperlyConfigured):
                configuration()

    def test_status_command_is_read_only(self):
        output = io.StringIO()
        call_command('notify_indexnow', stdout=output)
        self.assertFalse(json.loads(output.getvalue())['initialized'])
        self.assertFalse(IndexNowState.objects.exists())

    def test_notify_command_sync_does_not_send(self):
        with patch('storefront.indexnow.requests.post', side_effect=AssertionError('network')):
            call_command('notify_indexnow', sync=True, stdout=io.StringIO())
        self.assertTrue(IndexNowState.objects.get().initialized_at)

    def test_per_url_status_never_syncs_or_sends_and_rejects_mutating_options(self):
        self.changed()
        before = list(IndexNowURL.objects.order_by('pk').values())
        with patch('storefront.indexnow.requests.post', side_effect=AssertionError('network')):
            output = io.StringIO()
            call_command('notify_indexnow', path='/', stdout=output)
            status = json.loads(output.getvalue())['url_status']
            self.assertEqual(status['path'], '/')
            self.assertTrue(status['pending'])
            self.assertEqual(status['attempts'], 0)
            self.assertIsNone(status['last_status'])
            self.assertNotIn('test-key-12345678', output.getvalue())
            output = io.StringIO()
            call_command('notify_indexnow', path='/never-public', stdout=output)
            self.assertIsNone(json.loads(output.getvalue())['url_status'])
            for action in ('send', 'sync', 'retry_failed'):
                with self.subTest(action=action), self.assertRaises(CommandError):
                    call_command('notify_indexnow', path='/', **{action: True})
        self.assertEqual(list(IndexNowURL.objects.order_by('pk').values()), before)


@override_settings(STOREFRONT_ENABLED=True, STOREFRONT_ORIGIN='https://store.example',
                   INDEXNOW_ENABLED=True, INDEXNOW_KEY='test-key-12345678')
class IndexNowPublicBoundaryTests(TestCase):
    def test_only_successfully_rendered_indexable_public_pages_are_tracked(self):
        from cigars.models import Brand, Cigar
        from storefront.catalog import build_pages, semantic_hash
        from storefront.models import ProductListing, StoreTranslation
        brand = Brand.objects.create(english_name='Cohiba')
        ordinary = Cigar.objects.create(brand=brand.english_name, english_name='Siglo VI')
        private = Cigar.objects.create(brand=brand.english_name, english_name='Siglo VI',
                                       release_type='Commemorative Release', release_name='Siglo X Aniversario Humidor')
        listing = ProductListing.objects.create(cigar=ordinary, published=True)
        StoreTranslation.objects.create(kind='home', key='home', locale='zh', title='首页',
                                        description='介绍', body='正文', published=True)
        pages = build_pages()
        for path, payload in pages.items():
            value = semantic_hash(payload)
            StorePage.objects.create(path=path, payload=payload, rendered_payload=payload,
                                     desired_hash=value, rendered_hash=value, html='<h1>Page</h1>')
        sync_changes()
        expected = {path for path, payload in pages.items() if payload['indexable']}
        self.assertSetEqual(set(IndexNowURL.objects.values_list('path', flat=True)), expected)
        self.assertFalse(any(f'/cigar/{private.pk}/' in path for path in expected))
        self.assertFalse(any(path.startswith('/en/') for path in expected))
        # A bulk withdrawal bypasses signals; public eligibility still removes it.
        ProductListing.objects.filter(pk=listing.pk).update(withdrawn=True, published=False)
        sync_changes()
        product_rows = IndexNowURL.objects.filter(path__contains=f'/cigar/{ordinary.pk}/')
        self.assertTrue(product_rows.exists())
        self.assertTrue(all(row.desired_hash == '' and row.notified_hash for row in product_rows))
