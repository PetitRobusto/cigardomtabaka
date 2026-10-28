"""Exercise the workflow's storefront gates and service order with a fake service manager."""
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from textwrap import dedent
import unittest


class StorefrontWorkerDeployTests(unittest.TestCase):
    def test_missing_image_sources_prevent_frontend_switch(self):
        workflow = (Path(__file__).resolve().parents[1] / '.github/workflows/deploy.yml').read_text()
        preparation = dedent(workflow[workflow.index('            echo "=== generate responsive home images'):
                                     workflow.index('            echo "=== collectstatic ==="')])
        with TemporaryDirectory() as directory:
            calls = Path(directory) / 'calls'
            shell = '''
            sudo() { printf 'images\\n' >> "$CALLS"; return "$IMAGE_STATUS"; }
            python() { printf 'install\\n' >> "$CALLS"; }
            '''
            for image_status, expected in [('7', ['images']), ('0', ['images', 'install'])]:
                with self.subTest(image_status=image_status):
                    calls.write_text('')
                    result = subprocess.run(['bash', '-e', '-c', dedent(shell) + preparation],
                                            env={**os.environ, 'CALLS': str(calls), 'IMAGE_STATUS': image_status},
                                            capture_output=True, text=True)
                    self.assertEqual(result.returncode, int(image_status))
                    self.assertEqual(calls.read_text().splitlines(), expected)

    def run_workflow(self, **overrides):
        workflow = Path(__file__).resolve().parents[1] / '.github/workflows/deploy.yml'
        proposed = workflow.read_text()
        pause = proposed[proposed.index('            DEPLOY_STAGE=pause-storefront-worker'):
                         proposed.index('            DEPLOY_STAGE=install-code-and-migrations')]
        finish = proposed[proposed.index('            # A successful render command'):
                          proposed.index('            echo "=== reload nginx ==="')]
        self.assertLess(proposed.index('DEPLOY_STAGE=pause-storefront-worker'),
                        proposed.index('git reset --hard "$DEPLOY_SHA"'))
        mock = '''
        STOREFRONT_DEPLOY=false
        check_count=0
        sudo() {
          case "$*" in
            "systemctl is-enabled --quiet storefront-worker.service") return "$ENABLED_STATUS" ;;
            "systemctl is-active --quiet storefront-worker.service") return "$ACTIVE_STATUS" ;;
            "systemctl stop storefront-worker.service") printf 'stop\\n' >> "$CALLS"; return "$STOP_STATUS" ;;
            *"manage.py render_storefront") printf 'render\\n' >> "$CALLS"; return "$RENDER_STATUS" ;;
            *"manage.py check_storefront_cache")
              printf 'check\\n' >> "$CALLS"
              check_count=$((check_count + 1))
              test "$check_count" -gt "$CHECK_FAILURES" ;;
            *"manage.py check_storefront_sitemap") printf 'sitemap\\n' >> "$CALLS"; return "$SITEMAP_STATUS" ;;
            "systemctl restart gunicorn") printf 'web\\n' >> "$CALLS"; return "$WEB_STATUS" ;;
            "systemctl restart storefront-worker.service") printf 'worker\\n' >> "$CALLS"; return "$WORKER_STATUS" ;;
            *) return 99 ;;
          esac
        }
        '''
        with TemporaryDirectory() as directory:
            calls = Path(directory) / 'calls'
            controls = dict(ENABLED_STATUS='0', ACTIVE_STATUS='0', STOP_STATUS='0', RENDER_STATUS='0',
                            CHECK_FAILURES='0', SITEMAP_STATUS='0', WEB_STATUS='0', WORKER_STATUS='0')
            controls.update({key: str(value) for key, value in overrides.items()})
            env = {**os.environ, **controls, 'CALLS': str(calls)}
            result = subprocess.run(['bash', '-e', '-c', dedent(mock) + dedent(pause) + dedent(finish)],
                                    env=env, capture_output=True, text=True)
            return result.returncode, calls.read_text().splitlines() if calls.exists() else []

    def test_enabled_or_active_worker_is_paused_verified_and_restored(self):
        for enabled, active in [(0, 0), (0, 1), (1, 0)]:
            with self.subTest(enabled=enabled, active=active):
                self.assertEqual(self.run_workflow(ENABLED_STATUS=enabled, ACTIVE_STATUS=active),
                                 (0, ['stop', 'render', 'check', 'sitemap', 'web', 'worker']))

    def test_disabled_inactive_worker_is_not_enabled_or_started(self):
        self.assertEqual(self.run_workflow(ENABLED_STATUS=1, ACTIVE_STATUS=1), (0, ['web']))

    def test_failures_do_not_blindly_restore_worker_or_continue_switching(self):
        for controls, expected in [
            ({'STOP_STATUS': 7}, (7, ['stop'])),
            ({'RENDER_STATUS': 7}, (7, ['stop', 'render'])),
            ({'SITEMAP_STATUS': 7}, (7, ['stop', 'render', 'check', 'sitemap'])),
            ({'WEB_STATUS': 7}, (7, ['stop', 'render', 'check', 'sitemap', 'web'])),
            ({'WORKER_STATUS': 7}, (7, ['stop', 'render', 'check', 'sitemap', 'web', 'worker'])),
        ]:
            with self.subTest(controls=controls):
                self.assertEqual(self.run_workflow(**controls), expected)

    def test_stale_generations_retry_whole_render_and_never_bypass_gate(self):
        attempts = ['render', 'check'] * 3
        self.assertEqual(self.run_workflow(CHECK_FAILURES=2),
                         (0, ['stop', *attempts, 'sitemap', 'web', 'worker']))
        self.assertEqual(self.run_workflow(CHECK_FAILURES=99), (1, ['stop', *attempts]))


if __name__ == '__main__':
    unittest.main()
