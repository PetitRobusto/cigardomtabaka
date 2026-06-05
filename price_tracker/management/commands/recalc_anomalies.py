"""全量重算所有 snapshot 的 IQR 异常标记"""
from django.core.management.base import BaseCommand
from price_tracker.anomaly import recalc_all


class Command(BaseCommand):
    help = '全量重算所有 (cigar_id, box_size) 组的 IQR 异常标记'

    def handle(self, **options):
        self.stdout.write('正在重算异常标记...')
        total = recalc_all()
        self.stdout.write(self.style.SUCCESS(f'完成，共标记 {total} 条异常'))
