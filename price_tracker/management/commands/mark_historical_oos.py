"""标记历史缺货 — 首次运行：为所有以前有货但近期无记录的雪茄创建缺货快照

用法：
  python manage.py mark_historical_oos --source coh --days 30 --dry-run
  python manage.py mark_historical_oos --source coh
"""
import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from price_tracker.models import PriceSnapshot
from django.db.models import Max

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = '标记历史缺货：为近期无新记录的雪茄创建缺货快照'

    def add_arguments(self, parser):
        parser.add_argument('--source', '-s', required=True, help='来源 slug')
        parser.add_argument('--days', type=int, default=30,
                            help='超过多少天无新记录视为缺货（默认30）')
        parser.add_argument('--dry-run', action='store_true',
                            help='只预览不写入')

    def handle(self, *args, **options):
        source_slug = options['source']
        days = options['days']
        dry_run = options['dry_run']

        from price_tracker.models import PriceSource
        source = PriceSource.objects.filter(slug=source_slug).first()
        if not source:
            self.stderr.write(f'❌ 来源 "{source_slug}" 不存在')
            return

        cutoff = timezone.now() - timedelta(days=days)
        today = timezone.now().date()

        # 获取每个 (cigar, box_size) 最新的 in_stock=True 快照
        subquery = (
            PriceSnapshot.objects
            .filter(source=source, in_stock=True)
            .values('cigar_id', 'box_size')
            .annotate(latest_id=Max('id'))
            .values_list('latest_id', flat=True)
        )
        latest_in_stock = PriceSnapshot.objects.filter(
            id__in=subquery,
            source=source,
            scraped_date__lt=cutoff.date(),
        ).select_related('cigar')

        count = 0
        for snap in latest_in_stock:
            # 确保当日还没缺货记录
            existing = PriceSnapshot.objects.filter(
                source=source, cigar=snap.cigar,
                box_size=snap.box_size, scraped_date=today,
                in_stock=False,
            ).exists()
            if existing:
                continue

            count += 1
            if dry_run:
                self.stdout.write(
                    f'  📦 [{count}] {snap.cigar} (box={snap.box_size}) — '
                    f'最后有货: {snap.scraped_date}, 价格: ${snap.price}'
                )
            else:
                PriceSnapshot.objects.create(
                    source=source,
                    cigar=snap.cigar,
                    price=snap.price,
                    currency=snap.currency,
                    price_cny=snap.price_cny,
                    box_size=snap.box_size,
                    box_price=snap.box_price,
                    url=snap.url,
                    in_stock=False,
                    raw_data={
                        'oos_detected': True,
                        'last_seen': str(snap.scraped_date),
                        'historical_oos_sweep': True,
                    },
                )

        if dry_run:
            self.stdout.write(self.style.SUCCESS(
                f'\n🔍 Dry-run: 将标记 {count} 条为缺货（来源: {source.name}）'
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f'\n✅ 已标记 {count} 条缺货记录（来源: {source.name}）'
            ))
