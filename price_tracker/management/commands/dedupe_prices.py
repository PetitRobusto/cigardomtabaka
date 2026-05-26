"""清理 PriceSnapshot 中的重复记录

按 (cigar, source, box_size, scraped_date) 分组，仅保留每组最新的 scraped_at。
"""

from django.core.management.base import BaseCommand
from django.db.models import Count, Max
from price_tracker.models import PriceSnapshot


class Command(BaseCommand):
    help = '清理价格快照中的重复记录，只保留每组最新的一条'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='只统计不删除',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        duplicates = (
            PriceSnapshot.objects.values('cigar', 'source', 'box_size', 'scraped_date')
            .annotate(cnt=Count('id'), latest=Max('scraped_at'))
            .filter(cnt__gt=1)
        )

        total = duplicates.count()
        if total == 0:
            self.stdout.write(self.style.SUCCESS('✅ 没有发现重复记录'))
            return

        self.stdout.write(f'🔍 发现 {total} 组重复，共 {sum(d["cnt"] for d in duplicates)} 条记录')

        if dry_run:
            self.stdout.write('dry-run 模式，未执行删除')
            return

        deleted_total = 0
        for dup in duplicates:
            keep = PriceSnapshot.objects.filter(
                cigar=dup['cigar'], source=dup['source'],
                box_size=dup['box_size'], scraped_date=dup['scraped_date'],
                scraped_at=dup['latest'],
            ).first()

            to_delete = PriceSnapshot.objects.filter(
                cigar=dup['cigar'], source=dup['source'],
                box_size=dup['box_size'], scraped_date=dup['scraped_date'],
            ).exclude(pk=keep.pk)

            count, _ = to_delete.delete()
            deleted_total += count

        self.stdout.write(self.style.SUCCESS(f'✅ 已删除 {deleted_total} 条重复记录'))
