"""列出异常 snapshot 供 Agent 审查：匹配正确 → 清除标记，匹配错误 → 重匹配"""
from django.core.management.base import BaseCommand
from price_tracker.models import PriceSnapshot
from price_tracker.matcher import match_cigar


class Command(BaseCommand):
    help = '列出 IQR 异常 snapshot，Agent 可审查并清除标记'

    def add_arguments(self, parser):
        parser.add_argument('--clear', type=int, nargs='+',
                            help='清除指定 snapshot ID 的异常标记')
        parser.add_argument('--rematch', type=int, nargs='+',
                            help='对指定 snapshot 重新匹配并更新 cigar_id')
        parser.add_argument('--clear-all', action='store_true',
                            help='清除所有异常标记（慎用）')

    def handle(self, **options):
        if options['clear_all']:
            cnt = PriceSnapshot.objects.filter(is_anomalous=True).update(is_anomalous=False)
            self.stdout.write(self.style.SUCCESS(f'已清除全部 {cnt} 条异常标记'))
            return

        if options['clear']:
            for sid in options['clear']:
                PriceSnapshot.objects.filter(id=sid).update(is_anomalous=False)
                self.stdout.write(f'snap={sid} 异常标记已清除')
            return

        if options['rematch']:
            for sid in options['rematch']:
                try:
                    snap = PriceSnapshot.objects.get(id=sid)
                except PriceSnapshot.DoesNotExist:
                    self.stdout.write(f'snap={sid} 不存在')
                    continue
                raw = snap.raw_data or {}
                title = (raw.get('title_original')
                         or raw.get('product_name')
                         or raw.get('title')
                         or raw.get('product', ''))
                brand = raw.get('brand', '')
                new = match_cigar(title, brand_hint=brand or None)
                if new and new.id != snap.cigar_id:
                    old = snap.cigar_id
                    snap.cigar_id = new.id
                    snap.save()  # save() 内部自动触发新旧组异常重算
                    self.stdout.write(f'snap={sid}: cigar_id {old} → {new.id} '
                                      f'[{new.english_name}] release={new.release_type or "常规"}')
                else:
                    self.stdout.write(f'snap={sid}: 匹配无变化 (cigar_id={snap.cigar_id})')
            return

        # 默认：列出所有异常
        snaps = PriceSnapshot.objects.filter(is_anomalous=True).select_related('source', 'cigar')
        if not snaps:
            self.stdout.write('没有异常 snapshot')
            return

        self.stdout.write(f'共 {snaps.count()} 条异常 snapshot:\n')
        for s in snaps:
            raw = s.raw_data or {}
            title = (raw.get('title_original')
                     or raw.get('product_name')
                     or raw.get('title', '?'))
            self.stdout.write(
                f'snap={s.id} cigar_id={s.cigar_id} [{s.cigar.english_name}] '
                f'price={s.price} {s.currency} (¥{s.price_cny:.0f}) '
                f'box={s.box_size} stock={s.in_stock} src={s.source.name}'
            )
            self.stdout.write(f'  title: {title[:100]}')
            self.stdout.write(f'  url: {s.url[:80]}')
            self.stdout.write('')
