"""Verify deploy service restart behavior without invoking a real service manager."""
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest


class StorefrontWorkerDeployTests(unittest.TestCase):
    def test_existing_worker_restarts_without_enabling_or_installing_service(self):
        workflow = Path(__file__).resolve().parents[1] / '.github/workflows/deploy.yml'
        proposed = workflow.read_text()
        start = proposed.index('if sudo systemctl is-enabled --quiet storefront-worker.service')
        block = proposed[start:proposed.index('\n', proposed.index('fi', start))]
        mock = '''sudo() {
          case "$*" in
            "systemctl is-enabled --quiet storefront-worker.service") return "$ENABLED_STATUS" ;;
            "systemctl is-active --quiet storefront-worker.service") return "$ACTIVE_STATUS" ;;
            "systemctl restart storefront-worker.service") printf 'restart\\n' >> "$CALLS"; return "$RESTART_STATUS" ;;
            *) return 99 ;;
          esac
        }
        '''
        for enabled, active, restart, expected_call, expected_status in (
            (0, 1, 0, True, 0), (1, 0, 0, True, 0), (1, 1, 0, False, 0), (0, 1, 7, True, 7),
        ):
            with self.subTest(enabled=enabled, active=active, restart=restart), TemporaryDirectory() as directory:
                calls = Path(directory) / 'calls'
                env = {**os.environ, 'CALLS': str(calls), 'ENABLED_STATUS': str(enabled), 'ACTIVE_STATUS': str(active), 'RESTART_STATUS': str(restart)}
                result = subprocess.run(['bash', '-e', '-c', mock + block], env=env, capture_output=True, text=True)
                self.assertEqual(result.returncode, expected_status, result.stderr)
                self.assertEqual(calls.exists(), expected_call)


if __name__ == '__main__':
    unittest.main()
