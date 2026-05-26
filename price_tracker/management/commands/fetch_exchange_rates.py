"""每日汇率抓取 — open.er-api.com (免费，无需 Key)"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from price_tracker.models import ExchangeRate


class Command(BaseCommand):
    help = '从 open.er-api.com 抓取 USD/CHF/EUR 对 CNY 汇率'

    CURRENCIES = ['USD', 'CHF', 'EUR']

    def handle(self, *args, **options):
        import json, urllib.request

        today = timezone.now().date()

        for currency in self.CURRENCIES:
            url = f'https://open.er-api.com/v6/latest/{currency}'
            try:
                with urllib.request.urlopen(url, timeout=15) as resp:
                    data = json.loads(resp.read())
                rate = data.get('rates', {}).get('CNY')
                if not rate:
                    self.stderr.write(f'  ❌ {currency}: no CNY rate in response')
                    continue

                # Upsert: 同一天同一货币只存一条
                entry, created = ExchangeRate.objects.update_or_create(
                    currency=currency,
                    date=today,
                    defaults={'rate': round(rate, 4)},
                )
                action = '🆕' if created else '🔄'
                self.stdout.write(f'  {action} 1 {currency} = {entry.rate:.4f} CNY')
            except Exception as e:
                self.stderr.write(f'  ❌ {currency}: {e}')

        self.stdout.write(self.style.SUCCESS(f'\n✅ 汇率更新完成 ({today})'))
