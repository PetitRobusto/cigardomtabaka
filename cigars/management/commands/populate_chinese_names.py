"""
批量填充品牌和雪茄中文名
用法: python manage.py populate_chinese_names
"""
import json, os
from django.core.management.base import BaseCommand
from cigars.models import Brand, Cigar

# 与搜索及客户报价展示共用品牌译名，避免重新填充时恢复旧译名。
from cigars.constants import BRAND_CN_MAP as BRAND_CHINESE


class Command(BaseCommand):
    help = '填充品牌和雪茄的中文名'

    def handle(self, **options):
        # 1. 填品牌中文名
        brand_updated = 0
        for brand in Brand.objects.all():
            cn = BRAND_CHINESE.get(brand.english_name, '')
            if cn and brand.name != cn:
                brand.name = cn
                brand.save()
                brand_updated += 1
                self.stdout.write(f'  🏷️  {brand.english_name} → {cn}')

        self.stdout.write(self.style.SUCCESS(
            f'品牌中文名: {brand_updated} 个已更新'
        ))

        # 2. 雪茄中文名（从预爬JSON加载）
        cigar_json = os.path.join(os.path.dirname(__file__), '..', '..', '..',
                                   'cigar_chinese_names.json')
        if os.path.exists(cigar_json):
            with open(cigar_json) as f:
                cigar_data = json.load(f)

            cigar_updated = 0
            for brand_en, cigars in cigar_data.items():
                for en_name, cn_name in cigars.items():
                    updated = Cigar.objects.filter(
                        brand=brand_en, english_name=en_name
                    ).update(name=cn_name)
                    if updated:
                        cigar_updated += updated
                        self.stdout.write(f'  🚬 {brand_en} {en_name} → {cn_name}')

            self.stdout.write(self.style.SUCCESS(
                f'雪茄中文名: {cigar_updated} 条已更新'
            ))
        else:
            self.stdout.write('⚠️ cigar_chinese_names.json 不存在，跳过雪茄中文名')
