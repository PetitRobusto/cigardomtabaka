"""
批量填充品牌和雪茄中文名
用法: python manage.py populate_chinese_names
"""
import json, os
from django.core.management.base import BaseCommand
from cigars.models import Brand, Cigar

# 从 cubancigarwebsite.com 中文版爬取的品牌中文名
BRAND_CHINESE = {
    'Belinda': '贝琳达',
    'Bolívar': '玻利瓦',
    'Cabañas': '卡班纳',
    'Caney': '凯尼',
    'Cifuentes': '西福恩特斯',
    'Cohiba': '高希霸',
    'Cuaba': '库阿巴',
    'Cubatabaco': '古巴雪茄',
    'Davidoff': '大卫杜夫',
    'Diplomáticos': '外交官',
    'Don Alfredo': '唐、阿尔佛',
    'Don Cándido': '唐、坎迪多',
    'Dunhill': '登喜路',
    'Edmundo Dantes': '艾蒙度但丁',
    'El Rey del Mundo': '世界之王',
    'Flor del Punto': '繁花',
    'Fonseca': '科塞卡',
    'Gispert': '基斯伯',
    'Guantanamera': '关达拉美拉',
    'H. Upmann': '乌普曼',
    'Habanos': '哈伯纳斯',
    'Hoyo de Monterrey': '好友',
    'J. J. Fox Exclusives': 'J.J·福克斯 专享',
    'José L. Piedra': '荷西比雅达',
    'Juan López': '胡安佩洛斯',
    'La Corona': '皇冠雪茄',
    'La Escepción': '拉雅仕帕西安',
    'La Flor de Cano': '卡诺之花',
    'La Flor del Caney': '拉弗洛德卡妮',
    'La Gloria Cubana': '古巴荣耀',
    'Los Statos de Luxe': '劳斯登徒',
    'María Guerrero': '玛丽亚 格雷多',
    'Montecristo': '蒙特',
    'Multi-Brand Releases': '精选品牌系列',
    'Partagás': '帕特加斯',
    'Por Larrañaga': '波尔拉腊尼加',
    'Punch': '潘趣',
    "Quai d'Orsay": '希多尔赛',
    'Quintero': '金特罗',
    'Rafael González': '拉斐尔',
    'Ramón Allones': '雷蒙阿隆尼',
    'Romeo y Julieta': '罗密欧与朱丽叶',
    'Saint Luis Rey': '圣路易斯雷伊',
    'San Cristóbal': '圣克里斯多',
    'San Cristóbal de la Habana': '圣克里斯多',
    'San Luis Rey': '新路易斯雷伊',
    'Sancho Panza': '桑丘潘萨',
    'Siboney': '西波妮',
    'Small Cigars': '小雪茄',
    'Trinidad': '千里达',
    'Troya': '特洛伊',
    'Vegas Robaina': '瓦格斯陆班纳',
    'Vegueros': '威古洛',
}


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
