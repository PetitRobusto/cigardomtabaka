import json
from pathlib import Path
from django.core.management.base import BaseCommand
from cigars.models import Cigar


class Command(BaseCommand):
    help = '从 cigars_catalog.json 导入雪茄目录'

    def handle(self, *args, **options):
        catalog_path = Path(__file__).resolve().parent.parent.parent.parent / 'cigars_catalog.json'
        with open(catalog_path) as f:
            catalog = json.load(f)

        created = 0
        updated = 0
        for entry in catalog:
            brand = entry.get('brand', '')
            english_name = entry.get('name', '')
            if not brand or not english_name:
                continue
            release_type = entry.get('release_type', '')
            release_name = entry.get('release_name', '')

            defaults = {
                'vitola': entry.get('vitola', ''),
                'length': entry.get('length_mm'),
                'ring_gauge': entry.get('ring_gauge'),
                'common_name': entry.get('common_name', ''),
                'origin': entry.get('origin', 'Cuban'),
                'status': entry.get('status', 'Current'),
                'url': entry.get('url', ''),
                'release_name': release_name,
                'packagings': json.dumps({
                    'raw': entry.get('packaging_raw', ''),
                    'box_sizes': entry.get('box_sizes', []),
                    'sub_quantity': entry.get('sub_quantity'),
                }) if any([entry.get('packaging_raw'), entry.get('box_sizes')]) else '[]',
            }

            obj, created_flag = Cigar.objects.update_or_create(
                brand=brand,
                english_name=english_name,
                release_type=release_type,
                release_name=release_name,
                defaults=defaults,
            )
            if created_flag:
                created += 1
            else:
                updated += 1

        self.stdout.write(self.style.SUCCESS(
            f'导入完成: 新增 {created} 条，更新 {updated} 条，共 {len(catalog)} 条'
        ))
