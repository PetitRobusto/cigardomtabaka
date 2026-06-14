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
        'short_name': 'iHavanas',
    },
    {
        'name': 'EGM Cigars',
        'slug': 'egm',
        'base_url': 'https://egmcigars.com',
        'scraper_class': 'egm',
        'currency': 'USD',
        'exchange_rate': 7.25,
        'short_name': 'EGM',
    },
    {
        'name': 'COH Cigars',
        'slug': 'coh',
        'base_url': 'https://www.cohcigars.com',
        'scraper_class': 'coh',
        'currency': 'USD',
        'exchange_rate': 7.25,
        'short_name': 'COH',
    },
    {
        'name': 'COH Cigars China',
        'slug': 'coh_china',
        'base_url': 'https://www.cohcigars.com',
        'scraper_class': 'coh_china',
        'currency': 'USD',
        'exchange_rate': 7.25,
        'short_name': 'COH中国',
    },
    {
        'name': 'CigarOne',
        'slug': 'cigarone',
        'base_url': 'https://www.cigarone.com',
        'scraper_class': 'cigarone',
        'currency': 'CHF',
        'exchange_rate': 8.5,
        'short_name': 'CigarOne',
    },
    {
        'name': 'HYHPURO',
        'slug': 'hyhpuro',
        'base_url': 'https://hyhpuro.com',
        'scraper_class': 'hyhpuro',
        'currency': 'EUR',
        'exchange_rate': 7.8,
        'short_name': 'HYH',
    },
    {
        'name': 'LCDH Brussels',
        'slug': 'lcdh_brussels',
        'base_url': 'https://lacasadelhabano.brussels',
        'scraper_class': 'lcdh_brussels',
        'currency': 'EUR',
        'exchange_rate': 7.8,
        'short_name': 'LCDH布鲁塞尔',
    },
    {
        'name': 'LCDH Dusseldorf',
        'slug': 'lcdh_dl',
        'base_url': 'https://www.lacasadelhabano-dl.ch',
        'scraper_class': 'lcdh_dl',
        'currency': 'CHF',
        'exchange_rate': 8.5,
        'short_name': 'LCDH杜塞',
    },
    {
        'name': 'LCDH Nyon',
        'slug': 'lcdh_nyon',
        'base_url': 'https://la-casa-del-habano-nyon.com',
        'scraper_class': 'lcdh_nyon',
        'currency': 'CHF',
        'exchange_rate': 8.5,
        'short_name': 'LCDH尼翁',
    },
    {
        'name': 'VIP Cigars',
        'slug': 'vipcigars',
        'base_url': 'https://www.vipcigars.com',
        'scraper_class': 'vipcigars',
        'currency': 'EUR',
        'exchange_rate': 7.8,
        'short_name': 'VIP',
    },
]


class Command(BaseCommand):
    help = '创建默认价格来源（iHavanas, EGM, COH）'

    def handle(self, *args, **options):
        created = 0
        updated = 0
        for src in DEFAULT_SOURCES:
            _, is_new = PriceSource.objects.update_or_create(
                slug=src['slug'],
                defaults=src,
            )
            if is_new:
                created += 1
                self.stdout.write(
                    self.style.SUCCESS(f'  ✅ {src["name"]}')
                )
            else:
                updated += 1
                self.stdout.write(f'  ↻ {src["name"]} (已更新)')

        self.stdout.write(
            self.style.SUCCESS(f'\n🎉 完成！创建 {created} 个，更新 {updated} 个价格来源')
        )
