import json
import os
from django.core.management.base import BaseCommand
from cigars.models import Cigar, CigarPrice


class Command(BaseCommand):
    help = '导入批发价数据到 CigarPrice 模型（通过 english_name 匹配 Cigar 记录）'

    def add_arguments(self, parser):
        parser.add_argument(
            '--file',
            type=str,
            default='',
            help='JSON 文件路径，包含 [{"english_name": "...", "box_size": 25, "wholesale_price": 10000, ...}]',
        )

    def handle(self, *args, **options):
        file_path = options['file']

        # 如果没有提供文件，尝试使用内置示例数据
        if not file_path:
            self.stdout.write(self.style.WARNING('未提供数据文件，使用内置示例数据（仅用于测试）'))
            data = self._get_sample_data()
        else:
            if not os.path.exists(file_path):
                self.stdout.write(self.style.ERROR(f'文件不存在: {file_path}'))
                return
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

        matched = 0
        unmatched = []

        for entry in data:
            ename = entry.get('english_name', '').strip()
            box_size = entry.get('box_size')
            wholesale_price = entry.get('wholesale_price')
            retail_price = entry.get('retail_price')
            sort_order = entry.get('sort_order', 0)
            is_active = entry.get('is_active', True)

            if not ename or not box_size or not wholesale_price:
                self.stdout.write(self.style.WARNING(f'跳过无效记录: {entry}'))
                continue

            # 大小写不敏感匹配，去除多余空格
            cigars = Cigar.objects.filter(english_name__iexact=ename.strip())
            if not cigars.exists():
                # 尝试去除多余空格后再匹配
                ename_normalized = ' '.join(ename.split())
                cigars = Cigar.objects.filter(english_name__iexact=ename_normalized)

            if cigars.exists():
                cigar = cigars.first()
                cp, created = CigarPrice.objects.update_or_create(
                    cigar=cigar,
                    box_size=box_size,
                    defaults={
                        'wholesale_price': wholesale_price,
                        'retail_price': retail_price,
                        'sort_order': sort_order,
                        'is_active': is_active,
                    }
                )
                action = '创建' if created else '更新'
                self.stdout.write(f'{action}: {cigar} · {box_size}支/盒 · ¥{wholesale_price}')
                matched += 1
            else:
                unmatched.append(ename)
                self.stdout.write(self.style.WARNING(f'未匹配: {ename}'))

        self.stdout.write(self.style.SUCCESS(f'\n导入完成：匹配 {matched} 款，未匹配 {len(unmatched)} 款'))
        if unmatched:
            self.stdout.write(self.style.WARNING(f'未匹配列表: {unmatched}'))

    def _get_sample_data(self):
        """示例数据 — 用于测试结构，生产环境请提供实际数据文件"""
        return [
            # {"english_name": "COHIBA ROBUSTOS", "box_size": 25, "wholesale_price": 17900, "sort_order": 1},
        ]
