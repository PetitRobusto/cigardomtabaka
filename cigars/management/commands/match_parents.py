"""
管理命令：匹配特别款的 parent 关系 v2
- 从原始爬虫 JSON 读取 release_name，为同组子雪茄创建父条目
- 不再将任何 Special Release 匹配到 Current 常规款
用法：python manage.py match_parents
"""
import json, glob
from django.core.management.base import BaseCommand
from cigars.models import Cigar, Brand


class Command(BaseCommand):
    help = '从原始 JSON 读取 release_name，创建父条目，匹配子雪茄'

    def handle(self, *args, **options):
        # 1. 清空所有 parent
        cleared = Cigar.objects.exclude(parent=None).update(parent=None)
        self.stdout.write(f'🧹 清空 {cleared} 条 parent 关系')

        # 2. 读取所有品牌 JSON
        json_dir = '/home/jason/.hermes/cigar_inventory/'
        created = 0
        linked = 0

        for fpath in sorted(glob.glob(f'{json_dir}*.json')):
            with open(fpath) as f:
                data = json.load(f)
            results = data.get('results', [])

            # 按 release_name 分组（仅对有 release_name 且 sub_total > 1 的条目）
            # sub_total > 1 表示同一 .entry 块内有多个 .cigarDetailsHead = 真保湿盒
            groups = {}
            for item in results:
                rn = (item.get('release_name') or '').strip()
                if not rn or item.get('status') != 'Special Releases':
                    continue
                st = item.get('sub_total', 1)
                if not st or st <= 1:
                    continue  # 跳过单雪茄条目（sub_total=1 或 null）
                groups.setdefault(rn, []).append(item)

            for rn, items in groups.items():
                if len(items) <= 1:
                    continue  # 单个条目不创建父条目

                brand_name = data.get('brand', '')
                brand_obj = Brand.objects.filter(english_name=brand_name).first()

                # 创建或找到父条目
                parent, pc = Cigar.objects.get_or_create(
                    brand=brand_name,
                    english_name=rn,
                    release_type='',
                    release_name=rn,
                    defaults={
                        'status': 'Special Releases',
                        'name': rn,
                        'origin': 'Cuban',
                    }
                )
                if pc:
                    created += 1
                    self.stdout.write(f'  ✨ 新建父条目: {rn}')

                # 匹配子雪茄 — 用 release_name 精准定位，解决同名跨保湿盒冲突
                for item in items:
                    child_name = item.get('name', '')
                    child_rt = item.get('release_type', '')
                    child_rn = rn  # 子雪茄的 release_name = 父条目名称
                    child = Cigar.objects.filter(
                        brand=brand_name,
                        english_name=child_name,
                        release_type=child_rt,
                        release_name=child_rn,
                    ).first()
                    if child and not child.parent_id:
                        child.parent = parent
                        child.save(update_fields=['parent'])
                        linked += 1
                        self.stdout.write(f'    └─ {child_name} [{child_rt}] ← {rn}')
                    elif child and child.parent_id:
                        self.stdout.write(f'    ⚠️ {child_name} [{child_rt}] ← 已有parent,跳过')

        # 统计
        orphans = Cigar.objects.filter(
            status='Special Releases', parent__isnull=True
        ).count()
        children = Cigar.objects.exclude(parent=None).count()

        self.stdout.write(self.style.SUCCESS(
            f'\n✅ 完成: {created} 个父条目, {linked} 个子雪茄,'
            f' {children} 条有parent, {orphans} 条独立特别款'
        ))
