import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from xml.etree import ElementTree

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.utils import timezone

from cigars.models import Brand, Cigar
from .seo_catalog import CONTENT, FRONTEND, _check_public, cigar_path, content_digest, live_fingerprint


@override_settings(DEBUG=False)
class PublicSeoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.brand = Brand.objects.create(english_name='Cohiba', name='高希霸', slug='cohiba')
        cls.cigar = Cigar.objects.create(pk=95, brand='Cohiba', english_name='Robustos', name='罗布图', length=124, ring_gauge=50)

    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.settings_override = override_settings(SEO_BUILD_DIR=self.directory.name)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)

    def install_page(self, path='/brand/cohiba'):
        from .seo_catalog import read_definitions
        page = next(item for item in read_definitions() if item['path'] == path)
        body = '<!doctype html><html><head><title>高希霸资料</title></head><body><h1>高希霸 Cohiba</h1><p>公开目录规格</p></body></html>'
        file = hashlib.sha256(path.encode()).hexdigest() + '.html'
        Path(self.directory.name, file).write_text(body)
        manifest = {'schemaVersion': 1, 'contentDigest': content_digest(),
                    'definitionsDigest': hashlib.sha256((FRONTEND / 'seo/pages.json').read_bytes()).hexdigest(),
                    'pages': {path: {'file': file, 'sha256': hashlib.sha256(body.encode()).hexdigest(), 'fingerprint': live_fingerprint(page)}}}
        Path(self.directory.name, 'manifest.json').write_text(json.dumps(manifest))
        return body, file

    def test_robots_and_sitemap_are_real_files_with_public_urls_only(self):
        robots = self.client.get('/robots.txt')
        self.assertEqual(robots.status_code, 200)
        self.assertTrue(robots['Content-Type'].startswith('text/plain'))
        self.assertContains(robots, 'Sitemap: https://cigardomtabaka.com/sitemap.xml')
        sitemap = self.client.get('/sitemap.xml')
        root = ElementTree.fromstring(sitemap.content)
        urls = [node.text for node in root.findall('{*}url/{*}loc')]
        self.assertIn(CONTENT['origin'] + '/brand/cohiba', urls)
        self.assertIn(CONTENT['origin'] + '/contacts', urls)
        self.assertNotIn(CONTENT['origin'] + '/brand/montecristo', urls)
        self.assertTrue(all('/p/' not in url and '/login' not in url and '/accounting' not in url for url in urls))

    def test_missing_entities_and_unknown_paths_return_404(self):
        for path in ['/brand/missing', '/cigar/99999/nope', '/does-not-exist', '/ru/brand/montecristo']:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 404)
                self.assertIn('noindex', response['X-Robots-Tag'])
                self.assertContains(response, 'noindex,nofollow', status_code=404)
        self.assertEqual(self.client.get('/api/brands/missing/').status_code, 404)
        self.assertEqual(self.client.get('/api/cigars/99999/').status_code, 404)

    def test_canonical_redirects_preserve_query_and_do_not_redirect_api_posts(self):
        response = self.client.get('/cigar/95/outdated?utm_source=test')
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response['Location'], cigar_path(self.cigar) + '?utm_source=test')
        self.assertEqual(self.client.get('/brand/cohiba/')['Location'], '/brand/cohiba')
        response = self.client.get('/brand/cohiba', HTTP_HOST='www.cigardomtabaka.com')
        self.assertEqual(response['Location'], CONTENT['origin'] + '/brand/cohiba')
        self.assertNotEqual(self.client.post('/api/login/', HTTP_HOST='www.cigardomtabaka.com').status_code, 301)

    def test_intact_build_returns_actual_html_without_requiring_javascript(self):
        body, _ = self.install_page()
        response = self.client.get('/brand/cohiba')
        self.assertEqual(response.content.decode(), body)
        self.assertEqual(response['X-Robots-Tag'], 'index, follow')
        self.assertNotIn('private', response['Cache-Control'])

    def test_catalogue_change_or_corrupt_artifact_cannot_serve_old_content(self):
        body, file = self.install_page()
        self.cigar.length = 125
        self.cigar.save(update_fields=['length'])
        self.assertNotEqual(self.client.get('/brand/cohiba').content.decode(), body)
        self.install_page()
        Path(self.directory.name, file).write_text('<h1>tampered</h1>')
        self.assertNotContains(self.client.get('/brand/cohiba'), 'tampered')

    def test_deleted_brand_or_soft_deleted_cigar_does_not_serve_snapshot(self):
        self.install_page(cigar_path(self.cigar))
        self.cigar.deleted_at = timezone.now()
        self.cigar.save(update_fields=['deleted_at'])
        self.assertEqual(self.client.get(cigar_path(self.cigar)).status_code, 404)
        self.assertEqual(self.client.get('/api/cigars/95/').status_code, 404)
        self.install_page('/brand/cohiba')
        self.brand.delete()
        self.assertEqual(self.client.get('/brand/cohiba').status_code, 404)
        self.assertEqual(self.client.get('/ru/brand/cohiba').status_code, 404)

    def test_private_documents_are_noindex_without_opening_note_or_relaxing_api_access(self):
        with patch('privnote.views.api_privnote', side_effect=AssertionError('must not open note')):
            response = self.client.get('/p/test-unopened-token')
        self.assertEqual(response.status_code, 200)
        self.assertIn('noindex', response['X-Robots-Tag'])
        self.assertIn('no-store', response['Cache-Control'])
        self.assertContains(response, 'noindex,nofollow')
        self.assertIn('noindex', self.client.get('/api/inventory/')['X-Robots-Tag'])
        self.assertNotEqual(self.client.get('/api/inventory/').status_code, 200)

    def test_locale_metadata_is_specific_and_missing_translations_are_not_invented(self):
        response = self.client.get('/ru/brand/cohiba')
        self.assertContains(response, 'lang="ru"')
        self.assertContains(response, 'hreflang="zh-CN"')
        self.assertContains(response, 'hreflang="en"')
        self.assertContains(response, 'Сигары Cohiba')
        self.assertNotContains(response, 'Habanos Specialist')
        response = self.client.get('/contacts')
        self.assertNotContains(response, 'habanos-specialist.png')

    def test_build_export_blocks_private_fields_and_production_database(self):
        for payload in [{'data': {'price_ref': 200}}, {'catalog': [{'token': 'secret'}]}, {'cost_cny': 1}]:
            with self.assertRaises(ValueError):
                _check_public(payload)
        _check_public({'name': 'Cohiba', 'length': 124, 'packagings': [{'size': 25}]})
        with self.assertRaises(CommandError):
            call_command('export_public_catalog')

    def test_soft_deleted_children_are_absent_from_public_brand_payload(self):
        child = Cigar.objects.create(brand='Cohiba', english_name='Robustos Special', parent=self.cigar,
                                     deleted_at=timezone.now(), release_type='Special Release')
        response = self.client.get('/api/brands/cohiba/')
        children = [item for section in response.json()['sections'] for cigar in section['cigars'] for item in cigar['children']]
        self.assertNotIn(child.id, [item['id'] for item in children])
        self.assertEqual(response.json()['total'], 1)

    def test_anonymous_remote_refresh_has_a_fixed_origin_and_no_login_dependency(self):
        from .seo_catalog import _public_payload
        with self.assertRaises(ValueError):
            _public_payload('/api/brands/', 'https://unrelated.example')
        with patch('requests.get') as get:
            get.return_value.status_code = 200
            get.return_value.json.return_value = {'sections': [], 'total_brands': 0}
            self.assertEqual(_public_payload('/api/brands/', CONTENT['origin']), {'sections': [], 'total_brands': 0})
            get.assert_called_once_with(CONTENT['origin'] + '/api/brands/', timeout=(3, 20), allow_redirects=False)

    def test_candidate_artifact_is_checked_without_installing_live_files(self):
        from deploy.frontend_artifact import pack
        from .seo_catalog import read_definitions
        page = next(item for item in read_definitions() if item['path'] == '/brand/cohiba')
        body, file = self.install_page()
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            static = root / 'static'
            (static / '.vite').mkdir(parents=True)
            (static / 'entry.js').write_text('')
            (static / '.vite/manifest.json').write_text(json.dumps({'entry': {'file': 'entry.js', 'isEntry': True}}))
            artifact = root / 'artifact'
            pack(static, artifact, 'a' * 40, Path(self.directory.name))
            with patch('cigars.management.commands.check_public_seo.read_definitions', return_value=[page]):
                call_command('check_public_seo', artifact_dir=str(artifact), commit='a' * 40)
                self.cigar.length = 125
                self.cigar.save(update_fields=['length'])
                with self.assertRaisesMessage(CommandError, 'Missing or stale public HTML'):
                    call_command('check_public_seo', artifact_dir=str(artifact), commit='a' * 40)
                with self.assertRaisesMessage(CommandError, 'Invalid candidate artifact'):
                    call_command('check_public_seo', artifact_dir=str(artifact), commit='b' * 40)
            self.assertEqual(Path(self.directory.name, file).read_text(), body)

    def test_candidate_artifact_options_cannot_mix_local_and_remote_checks(self):
        for options in [{'artifact_dir': '/tmp/unopened'}, {'commit': 'a' * 40},
                        {'artifact_dir': '/tmp/unopened', 'commit': 'a' * 40, 'public_origin': CONTENT['origin']}]:
            with self.subTest(options=options), self.assertRaises(CommandError):
                call_command('check_public_seo', **options)

    def test_remote_deployment_check_accepts_prerender_and_rejects_spa_fallback(self):
        from .seo_catalog import read_definitions
        with patch('requests.get') as get:
            get.return_value.status_code = 200
            get.return_value.headers = {'X-CDT-Rendering': 'prerendered'}
            call_command('check_public_seo', public_origin=CONTENT['origin'])
            self.assertEqual(get.call_count, len(read_definitions()))
            get.assert_any_call(CONTENT['origin'] + '/ru/contacts', timeout=(3, 20), allow_redirects=False)
            get.return_value.headers = {'X-CDT-Rendering': 'spa'}
            with self.assertRaisesMessage(CommandError, 'Missing or stale public HTML'):
                call_command('check_public_seo', public_origin=CONTENT['origin'])
