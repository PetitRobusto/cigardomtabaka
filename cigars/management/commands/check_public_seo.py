"""Read-only pre-render deployment check; exits nonzero on any missing/stale page."""
from contextlib import ExitStack
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management.base import BaseCommand, CommandError
from django.test import RequestFactory, override_settings

from cigardomtabaka_backend.seo_catalog import CONTENT, read_definitions
from cigardomtabaka_backend.seo_views import spa_entry


class Command(BaseCommand):
    help = 'Verify all priority URLs serve the matching pre-rendered public HTML.'

    def add_arguments(self, parser):
        parser.add_argument('--public-origin', help='Check the configured public site after deployment.')
        parser.add_argument('--artifact-dir', help='Validate a verified candidate artifact without installing it.')
        parser.add_argument('--commit', help='Exact CI commit required with --artifact-dir.')

    def handle(self, *args, **options):
        origin = options.get('public_origin')
        if origin and origin.rstrip('/') != CONTENT['origin']:
            raise CommandError('Only the configured public site origin may be checked.')
        artifact, commit = options.get('artifact_dir'), options.get('commit')
        if bool(artifact) != bool(commit) or (artifact and origin):
            raise CommandError('Use --artifact-dir and --commit together, without --public-origin.')
        with ExitStack() as stack:
            if artifact:
                from deploy.frontend_artifact import extract_verified
                directory = Path(stack.enter_context(TemporaryDirectory(prefix='seo-preflight-')))
                try:
                    extract_verified(Path(artifact), commit, directory)
                except (OSError, ValueError, KeyError) as error:
                    raise CommandError(f'Invalid candidate artifact: {error}') from error
                private = directory / '__seo_private__'
                if not private.is_dir():
                    raise CommandError('Candidate artifact is missing private public-page HTML.')
                stack.enter_context(override_settings(SEO_BUILD_DIR=private))
            self.check_pages(origin)

    def check_pages(self, origin):
        failures = []
        for page in read_definitions():
            if origin:
                import requests
                response = requests.get(CONTENT['origin'] + page['path'], timeout=(3, 20), allow_redirects=False)
                ok = response.status_code == 200 and response.headers.get('X-CDT-Rendering') == 'prerendered'
            else:
                response = spa_entry(RequestFactory().get(page['path']))
                ok = response.status_code == 200 and response.get('X-CDT-Rendering') == 'prerendered'
            if not ok:
                failures.append(page['path'])
        if failures:
            raise CommandError('Missing or stale public HTML: ' + ', '.join(failures))
        self.stdout.write(self.style.SUCCESS(f'All {len(read_definitions())} priority pages are pre-rendered.'))
