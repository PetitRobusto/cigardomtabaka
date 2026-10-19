import json

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from cigardomtabaka_backend.seo_catalog import FRONTEND, build_catalog, page_definitions


class Command(BaseCommand):
    help = 'Export the public catalogue build snapshot from the explicit development database.'

    def add_arguments(self, parser):
        parser.add_argument('--public-origin', help='Refresh from the configured public website using anonymous GET requests.')

    def handle(self, *args, **options):
        origin = options.get('public_origin')
        if not origin and (not settings.DEBUG or str(settings.DATABASES['default']['NAME']).endswith('/cigars.db')):
            raise CommandError('Use DJANGO_DEBUG=True and the development database; production export is not supported.')
        catalog = build_catalog(origin=origin)
        output = FRONTEND / 'seo'
        output.mkdir(exist_ok=True)
        (output / 'catalog.json').write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        pages = page_definitions(catalog['brands'], catalog['cigars'])
        (output / 'pages.json').write_text(json.dumps(pages, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        self.stdout.write(self.style.SUCCESS(f'Exported public build input for {len(pages)} pages.'))
