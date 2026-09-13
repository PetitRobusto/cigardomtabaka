from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from privnote.access import retention_days
from privnote.models import PrivnoteAccessEvent


class Command(BaseCommand):
    help = '清理超过保留期的 Privnote 访问明细；默认仅预览，--apply 执行。'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='执行删除过期访问明细')

    def handle(self, *args, **options):
        expired = PrivnoteAccessEvent.objects.filter(created_at__lt=timezone.now() - timedelta(days=retention_days()))
        if not options['apply']:
            self.stdout.write(f'待清理 {expired.count()} 条访问明细（未修改；使用 --apply 执行）')
            return
        total = 0
        while ids := list(expired.order_by('created_at', 'id').values_list('id', flat=True)[:500]):
            deleted, _ = PrivnoteAccessEvent.objects.filter(id__in=ids).delete()
            total += deleted
        self.stdout.write(self.style.SUCCESS(f'已清理 {total} 条访问明细；累计查看次数不变'))
