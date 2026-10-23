"""Run the deployment gate against disposable real SQLite files."""

from pathlib import Path
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory

from django.test import SimpleTestCase


class DatabaseDeployGuardTests(SimpleTestCase):
    def test_valid_or_orphaned_database_is_never_modified(self):
        for orphan in (False, True):
            with self.subTest(orphan=orphan), TemporaryDirectory() as directory:
                path = Path(directory) / 'database.sqlite3'
                connection = sqlite3.connect(path)
                connection.executescript('''
                    CREATE TABLE parent (id INTEGER PRIMARY KEY);
                    CREATE TABLE child (id INTEGER PRIMARY KEY, parent_id INTEGER REFERENCES parent(id));
                    INSERT INTO parent VALUES (1);
                ''')
                connection.execute('INSERT INTO child VALUES (1, ?)', (2 if orphan else 1,))
                connection.commit()
                connection.close()
                before = path.read_bytes()
                result = self.run_guard(path)
                self.assertEqual(result.returncode, 1 if orphan else 0, result.stderr)
                self.assertEqual(path.read_bytes(), before)
                if orphan:
                    self.assertIn('no records changed', result.stderr)

    def test_missing_and_invalid_files_fail_without_creating_or_changing_them(self):
        with TemporaryDirectory() as directory:
            missing = Path(directory) / 'missing.sqlite3'
            self.assertEqual(self.run_guard(missing).returncode, 1)
            self.assertFalse(missing.exists())
            invalid = Path(directory) / 'invalid.sqlite3'
            invalid.write_bytes(b'not a database')
            self.assertEqual(self.run_guard(invalid).returncode, 1)
            self.assertEqual(invalid.read_bytes(), b'not a database')

    def test_committed_wal_orphans_are_detected(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'wal.sqlite3'
            connection = sqlite3.connect(path)
            try:
                connection.execute('PRAGMA journal_mode=WAL')
                connection.executescript('''
                    CREATE TABLE parent (id INTEGER PRIMARY KEY);
                    CREATE TABLE child (parent_id INTEGER REFERENCES parent(id));
                    INSERT INTO child VALUES (99);
                ''')
                self.assertTrue(Path(str(path) + '-wal').exists())
                result = self.run_guard(path)
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertIn('foreign-key violations', result.stderr)
                self.assertEqual(connection.execute('SELECT * FROM child').fetchall(), [(99,)])
            finally:
                connection.close()

    def run_guard(self, path):
        script = Path(__file__).resolve().parents[1] / 'deploy/check_database_integrity.py'
        return subprocess.run([sys.executable, str(script), str(path)], capture_output=True, text=True)
