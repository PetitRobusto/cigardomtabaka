import hashlib
import io
import json
from pathlib import Path
import tarfile
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.test import SimpleTestCase

from deploy.frontend_artifact import install, pack, verify


class FrontendArtifactTests(SimpleTestCase):
    sha = 'a' * 40

    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / 'build'
        (self.source / '.vite').mkdir(parents=True)
        (self.source / 'assets').mkdir()
        (self.source / 'assets/app.js').write_text('app')
        (self.source / '.vite/manifest.json').write_text(json.dumps({
            'index.html': {'file': 'assets/app.js', 'isEntry': True},
        }))
        self.artifact = self.root / 'artifact'
        pack(self.source, self.artifact, self.sha)
        self.destination = self.root / 'live'
        self.destination.mkdir()
        (self.destination / 'old.js').write_text('previous build')

    def assert_old_build(self):
        self.assertEqual((self.destination / 'old.js').read_text(), 'previous build')
        self.assertFalse((self.destination / '.vite').exists())

    def test_installs_hidden_manifest_and_replaces_old_build(self):
        verify(self.artifact, self.sha)
        install(self.artifact, self.sha, self.destination)
        self.assertEqual((self.destination / 'assets/app.js').read_text(), 'app')
        self.assertTrue((self.destination / '.vite/manifest.json').is_file())
        self.assertFalse((self.destination / 'old.js').exists())

    def test_wrong_commit_or_corrupt_archive_preserves_old_build(self):
        with self.assertRaisesRegex(ValueError, 'commit'):
            install(self.artifact, 'b' * 40, self.destination)
        self.assert_old_build()
        (self.artifact / 'frontend.tar.gz').write_bytes(b'corrupted')
        with self.assertRaisesRegex(ValueError, 'checksum'):
            install(self.artifact, self.sha, self.destination)
        self.assert_old_build()

    def rewrite_archive(self, members):
        archive = self.artifact / 'frontend.tar.gz'
        with tarfile.open(archive, 'w:gz') as bundle:
            for name, content in members.items():
                info = tarfile.TarInfo(name)
                info.size = len(content)
                bundle.addfile(info, io.BytesIO(content))
        (self.artifact / 'metadata.json').write_text(json.dumps({
            'commit': self.sha, 'sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
        }))

    def test_missing_manifest_or_asset_preserves_old_build(self):
        for members in ({'app.js': b'app'}, {
            '.vite/manifest.json': b'{"index.html":{"file":"missing.js","isEntry":true}}',
        }):
            with self.subTest(members=members):
                self.rewrite_archive(members)
                with self.assertRaises((FileNotFoundError, ValueError)):
                    install(self.artifact, self.sha, self.destination)
                self.assert_old_build()

    def test_path_traversal_is_rejected_before_install(self):
        self.rewrite_archive({'../escape.js': b'escape'})
        with self.assertRaisesRegex(ValueError, 'Unsafe'):
            install(self.artifact, self.sha, self.destination)
        self.assert_old_build()
        self.assertFalse((self.destination.parent / 'escape.js').exists())

    def test_failed_replacement_restores_previous_build(self):
        original = Path.rename

        def fail_release(path, target):
            if path.name == 'release':
                raise OSError('simulated rename failure')
            return original(path, target)

        with patch.object(Path, 'rename', fail_release):
            with self.assertRaisesRegex(OSError, 'simulated'):
                install(self.artifact, self.sha, self.destination)
        self.assert_old_build()

    def private_pages(self):
        source = self.root / 'private-build'
        source.mkdir()
        name = 'a' * 64 + '.html'
        body = b'<h1>Public catalogue</h1>'
        (source / name).write_bytes(body)
        (source / 'manifest.json').write_text(json.dumps({'schemaVersion': 1, 'pages': {
            '/': {'file': name, 'sha256': hashlib.sha256(body).hexdigest()},
        }}))
        pack(self.source, self.artifact, self.sha, seo_source=source)
        return name

    def test_private_html_installs_outside_static_assets(self):
        name = self.private_pages()
        target = self.root / 'private-live'
        verify(self.artifact, self.sha)
        install(self.artifact, self.sha, self.destination, seo_destination=target)
        self.assertTrue((target / name).exists())
        self.assertFalse((self.destination / '__seo_private__').exists())
        self.assertFalse((self.destination / name).exists())

    def test_missing_private_destination_preserves_public_assets(self):
        self.private_pages()
        with self.assertRaisesRegex(ValueError, 'private SEO destination'):
            install(self.artifact, self.sha, self.destination)
        self.assert_old_build()

    def test_private_install_failure_rolls_back_both_outputs(self):
        self.private_pages()
        target = self.root / 'private-live'
        target.mkdir()
        (target / 'old.html').write_text('old page')
        original = Path.rename

        def fail_private(path, destination):
            if path.name == 'seo-release':
                raise OSError('simulated private install failure')
            return original(path, destination)

        with patch.object(Path, 'rename', fail_private):
            with self.assertRaisesRegex(OSError, 'private install failure'):
                install(self.artifact, self.sha, self.destination, seo_destination=target)
        self.assert_old_build()
        self.assertEqual((target / 'old.html').read_text(), 'old page')
