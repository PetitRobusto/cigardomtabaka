"""种子数据 — 创建默认价格来源"""
from django.core.management.base import BaseCommand
from price_tracker.models import PriceSource


DEFAULT_SOURCES = [
    {
        'name': 'iHavanas',
        'slug': 'ihavanas',
        'base_url': 'https://ihavanas.com',
        'scraper_class': 'ihavanas',
        'currency': 'USD',
        'exchange_rate': 7.25,
    },
    {
        'name': 'EGM Cigars',
        'slug': 'egm',
        'base_url': 'https://egmcigars.com',
        'scraper_class': 'egm',
        'currency': 'USD',
        'exchange_rate': 7.25,
    },
    {
        'name': 'Cigars of Habanos',
        'slug': 'coh',
        'base_url': 'https://cigarsofhabanos.com',
        'scraper_class': 'coh',
        'currency': 'USD',
        'exchange_rate': 7.25,
    },
]


class Command(BaseCommand):
    help = '创建默认价格来源（iHavanas, EGM, COH）'

    def handle(self, *args, **options):
        created = 0
        for src in DEFAULT_SOURCES:
            _, is_new = PriceSource.objects.get_or_create(
                slug=src['slug'],
                defaults=src,
            )
            if is_new:
                created += 1
                self.stdout.write(
                    self.style.SUCCESS(f'  ✅ {src["name"]}')
                )
            else:
                self.stdout.write(f'  ⏭️  {src["name"]} (已存在)')

        self.stdout.write(
            self.style.SUCCESS(f'\n🎉 完成！共创建 {created} 个价格来源')
        )
