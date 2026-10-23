"""每日汇率抓取 — open.er-api.com (免费，无需 Key)"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from price_tracker.models import ExchangeRate
from datetime import date, datetime, timezone as datetime_timezone
import math


class Command(BaseCommand):
    help = '从 open.er-api.com 抓取 USD/CHF/EUR/RUB 对 CNY 展示汇率'

    CURRENCIES = ['USD', 'CHF', 'EUR', 'RUB']

    def handle(self, *args, **options):
        import json, urllib.request

        # DateField(auto_now_add=True) uses date.today(), not the UTC date.
        # Keep the upsert key identical around the local/UTC midnight boundary.
        today = date.today()

        for currency in self.CURRENCIES:
            url = f'https://open.er-api.com/v6/latest/{currency}'
            try:
                with urllib.request.urlopen(url, timeout=15) as resp:
                    data = json.loads(resp.read())
                rate = data.get('rates', {}).get('CNY')
                if not isinstance(rate, (int, float)) or isinstance(rate, bool) or not math.isfinite(rate) or rate <= 0:
                    self.stderr.write(f'  ❌ {currency}: no CNY rate in response')
                    continue

                updated = data.get('time_last_update_unix')
                source_updated = datetime.fromtimestamp(updated, datetime_timezone.utc) if isinstance(updated, (int, float)) else None
                if source_updated and source_updated > timezone.now():
                    raise ValueError('来源汇率时间不能在未来')

                # Upsert: 同一天同一货币只存一条
                entry, created = ExchangeRate.objects.update_or_create(
                    currency=currency,
                    date=today,
                    defaults={
                        'rate': round(rate, 8 if currency == 'RUB' else 4),
                        'fetched_at': timezone.now(),
                        'source_updated_at': source_updated,
                    },
                )
                action = '🆕' if created else '🔄'
                self.stdout.write(f'  {action} 1 {currency} = {entry.rate:.4f} CNY')
            except Exception as e:
                self.stderr.write(f'  ❌ {currency}: {e}')

        self.stdout.write(self.style.SUCCESS(f'\n✅ 汇率更新完成 ({today})'))
