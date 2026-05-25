"""
批量设置品牌分类和产地
用法: python manage.py update_brand_meta
"""
from django.core.management.base import BaseCommand
from cigars.models import Brand


# 从 cubancigarwebsite.com 抓取的品牌分类
CATEGORY_MAP = {
    # === 全球品牌 ===
    'Cohiba':               'global',
    'H. Upmann':            'global',
    'Hoyo de Monterrey':    'global',
    'Montecristo':          'global',
    'Partagás':             'global',
    'Romeo y Julieta':      'global',
    # === 价值品牌 ===
    'Bolívar':              'value',
    'Punch':                'value',
    "Quai d'Orsay":         'value',
    'Ramón Allones':        'value',
    'Trinidad':             'value',
    # === 走量品牌 ===
    'José L. Piedra':       'volume',
    'Quintero':             'volume',
    'Vegueros':             'volume',
    # === 其他品牌 ===
    'Cuaba':                'other',
    'Diplomáticos':         'other',
    'El Rey del Mundo':     'other',
    'Fonseca':              'other',
    'Juan López':           'other',
    'La Flor de Cano':      'other',
    'La Gloria Cubana':     'other',
    'Por Larrañaga':        'other',
    'Rafael González':      'other',
    'Saint Luis Rey':       'other',
    'San Cristóbal':        'other',
    'San Cristóbal de la Habana': 'other',
    'Sancho Panza':         'other',
    'Vegas Robaina':        'other',
    # === ICT 机制雪茄 ===
    'Belinda':              'ict',
    'Guantanamera':         'ict',
    'Small Cigars':         'ict',
    'Troya':                'ict',
    # === 特殊品牌 ===
    'Cubatabaco':           'special',
    'Edmundo Dantes':       'special',
    'Habanos':              'special',
    'Multi-Brand Releases': 'special',
    # === 已停产 ===
    'Cabañas':              'discontinued',
    'Caney':                'discontinued',
    'Cifuentes':            'discontinued',
    'Davidoff':             'discontinued',
    'Don Alfredo':          'discontinued',
    'Don Cándido':          'discontinued',
    'Dunhill':              'discontinued',
    'Flor del Punto':       'discontinued',
    'Gispert':              'discontinued',
    'J. J. Fox Exclusives': 'discontinued',
    'La Corona':            'discontinued',
    'La Escepción':         'discontinued',
    'La Flor del Caney':    'discontinued',
    'Los Statos de Luxe':   'discontinued',
    'María Guerrero':       'discontinued',
    'San Luis Rey':         'discontinued',
    'Siboney':              'discontinued',
}

# 品牌产地（非古巴的需要标注）
ORIGIN_MAP = {
    # 革命前古巴品牌，现在在多米尼加重生
    'Davidoff':             'Dominican',
    'Dunhill':              'Dominican',
}


class Command(BaseCommand):
    help = '批量设置品牌分类 (category) 和产地 (origin)'

    def handle(self, **options):
        updated_cat = 0
        updated_ori = 0

        for brand in Brand.objects.all():
            name = brand.english_name
            changed = False

            # 设置分类
            if name in CATEGORY_MAP:
                cat = CATEGORY_MAP[name]
                if brand.category != cat:
                    brand.category = cat
                    changed = True
                    updated_cat += 1
                    self.stdout.write(f'  {name} → 分类: {brand.get_category_display()}')

            # 设置产地
            if name in ORIGIN_MAP:
                ori = ORIGIN_MAP[name]
                if brand.origin != ori:
                    brand.origin = ori
                    changed = True
                    updated_ori += 1
                    self.stdout.write(f'  {name} → 产地: {brand.get_origin_display()}')

            if changed:
                brand.save()

        self.stdout.write(self.style.SUCCESS(
            f'\n完成！分类更新 {updated_cat}，产地更新 {updated_ori}'
        ))
