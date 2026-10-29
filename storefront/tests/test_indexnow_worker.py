import io
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from storefront.models import RefreshState


@override_settings(STOREFRONT_ENABLED=True, INDEXNOW_ENABLED=True,
                   INDEXNOW_KEY='test-key-12345678', STOREFRONT_ORIGIN='https://store.example')
class IndexNowWorkerTests(TestCase):
    def setUp(self):
        RefreshState.objects.create(pk=1, revision=1, processed_revision=1, reconciled_at=timezone.now())
        for name, value in [('build_assets', {}), ('reconcile', None), ('publish_pending', 0)]:
            mock = patch(f'storefront.management.commands.render_storefront.{name}', return_value=value)
            setattr(self, name, mock.start())
            self.addCleanup(mock.stop)

    def watch(self, **kwargs):
        with patch('storefront.management.commands.render_storefront.time.sleep',
                   side_effect=[None, KeyboardInterrupt]), \
                patch('storefront.management.commands.render_storefront.time.monotonic', return_value=100):
            with self.assertRaises(KeyboardInterrupt):
                call_command('render_storefront', watch=True, **kwargs)

    def test_one_shot_deploy_render_never_submits_urls(self):
        with patch('storefront.indexnow.process_changes') as notify:
            call_command('render_storefront', stdout=io.StringIO())
        notify.assert_not_called()
        self.publish_pending.assert_called_once()

    def test_notification_failures_do_not_fail_or_repeat_publication(self):
        self.publish_pending.side_effect = [3, 0]
        output, errors = io.StringIO(), io.StringIO()
        with patch('storefront.indexnow.process_changes', side_effect=RuntimeError('external failure')) as notify:
            self.watch(stdout=output, stderr=errors)
        self.assertEqual(notify.call_count, 1)
        self.assertEqual(self.publish_pending.call_count, 2)
        self.assertIn('已更新 3 个公开页面', output.getvalue())
        self.assertIn('IndexNow 通知暂缓：RuntimeError', errors.getvalue())
        self.assertNotIn('商城刷新失败', errors.getvalue())

    def test_new_publication_triggers_notification_without_waiting_for_retry_poll(self):
        order = []
        def published(**kwargs):
            order.append('published')
            return 1
        self.publish_pending.side_effect = published
        with patch('storefront.indexnow.process_changes', side_effect=lambda: order.append('notify')):
            self.watch(stdout=io.StringIO())
        self.assertEqual(order, ['published', 'notify', 'published', 'notify'])

    def test_pending_retry_is_polled_after_one_minute_without_a_new_publication(self):
        with patch('storefront.indexnow.process_changes') as notify, \
                patch('storefront.management.commands.render_storefront.time.sleep',
                      side_effect=[None, KeyboardInterrupt]), \
                patch('storefront.management.commands.render_storefront.time.monotonic',
                      side_effect=[100, 161, 161]):
            with self.assertRaises(KeyboardInterrupt):
                call_command('render_storefront', watch=True, stdout=io.StringIO())
        self.assertEqual(notify.call_count, 2)
