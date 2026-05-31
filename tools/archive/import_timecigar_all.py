#!/usr/bin/env python3
"""
TimeCigar 小雪茄导入脚本 — 将爬取的5品牌78款小雪茄导入 cigars_cigar 表
用法: DJANGO_DEBUG=True python3 manage.py shell < import_timecigar_all.py
     或: python3 import_timecigar_all.py
"""
import os, sys, json, django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cigardomtabaka_backend.settings')
os.environ.setdefault('DJANGO_DEBUG', 'True')
sys.path.insert(0, '/home/jason/cigardomtabaka')
django.setup()

from cigars.models import Cigar

# 已知规格映射（基于已验证的TimeCigar详情页数据）
# 格式: 品牌_类型 → (length_mm, ring_gauge, vitola)
SPEC_MAP = {
    # Cohiba (已验证)
    'cohiba_mini': (82, 20, 'Mini'),
    'cohiba_mini_white': (82, 20, 'Mini'),
    'cohiba_club': (96.5, 22, 'Club'),
    'cohiba_club_white': (96.5, 22, 'Club'),
    'cohiba_short': (82, 27, 'Short'),
    'cohiba_wide_short': (100, 32, 'Wide Short'),
    # Guantanamera
    'guantanamera_mini': (82, 20, 'Mini'),
    'guantanamera_puritos': (109, 27, 'Puritos'),
    'guantanamera_decimos': (134, 38, 'Decimos'),
    'guantanamera_cristales': (150, 41, 'Cristales'),
    'guantanamera_minutos': (116, 38, 'Minutos'),
    'guantanamera_coronas': (142, 42, 'Coronas'),
    # Montecristo
    'montecristo_mini': (82, 20, 'Mini'),
    'montecristo_club': (96.5, 22, 'Club'),
    'montecristo_open_mini': (82, 20, 'Mini'),
    'montecristo_open_club': (96.5, 22, 'Club'),
    'montecristo_short': (82, 27, 'Short'),
    'montecristo_puritos': (109, 27, 'Puritos'),
    # Partagas
    'partagas_mini': (82, 20, 'Mini'),
    'partagas_club': (96.5, 22, 'Club'),
    'partagas_serie_mini': (82, 20, 'Mini'),
    'partagas_serie_club': (96.5, 22, 'Club'),
    'partagas_serie_puritos': (109, 27, 'Puritos'),
    'partagas_chicos': (106, 29, 'Chicos'),
    # Romeo y Julieta
    'romeo_mini': (82, 20, 'Mini'),
    'romeo_club': (96.5, 22, 'Club'),
    'romeo_puritos': (109, 27, 'Puritos'),
    # Trinidad
    'trinidad_short': (82, 27, 'Short'),
    'trinidad_wide_short': (100, 32, 'Wide Short'),
}

# 品牌名映射: TimeCigar → Django
BRAND_MAP = {
    'Guantanamera': 'Guantanamera',
    'Montecristo': 'Montecristo',
    'Partagas': 'Partagás',
    'Romeo y Julieta': 'Romeo y Julieta',
    'Trinidad': 'Trinidad',
}

def guess_specs(brand, name):
    """根据产品名猜测规格"""
    brand_lower = brand.lower().replace(' ', '_').replace('á', 'a')
    name_lower = name.lower()
    
    # 尝试匹配
    checks = [
        'wide_short', 'serie_mini', 'serie_club', 'serie_puritos',
        'open_mini', 'open_club', 'mini_white', 'club_white',
        'mini', 'club', 'short', 'puritos', 'chicos',
        'decimos', 'cristales', 'minutos', 'coronas',
    ]
    
    for check in checks:
        if check in name_lower:
            key = f'{brand_lower.split("_")[0]}_{check}'
            if key in SPEC_MAP:
                return SPEC_MAP[key]
    
    # 品牌级 fallback
    for fallback in ['mini', 'club', 'short']:
        key = f'{brand_lower.split("_")[0]}_{fallback}'
        if key in SPEC_MAP and fallback in name_lower:
            return SPEC_MAP[key]
    
    return (82, 20, 'Mini')  # ultimate fallback

def parse_name(name_str, brand_name):
    """解析 TimeCigar 产品名: 'Brand Type 中文名' -> english_name, chinese_name"""
    # 格式: 'Guantanamera Mini 關達拉美拉迷你' or 'Partagás Club 2025LE 帕特加斯俱樂部 2025年版'
    parts = name_str.split('  ')
    if len(parts) >= 2:
        english_full = parts[0].strip()
        chinese = parts[1].strip()
    else:
        english_full = name_str
        chinese = ''
    
    # 提取英文简称 (去掉品牌前缀)
    brand_words = english_full.split()
    brand_lower = brand_name.lower().replace('á', 'a')
    skip_words = 1
    # 品牌名可能是多词
    if brand_lower.startswith('romeo y julieta') or brand_lower.startswith('romeo'):
        skip_words = 3
    elif brand_lower.startswith('romeo'):
        skip_words = 3
    
    if len(brand_words) > skip_words:
        english_short = ' '.join(brand_words[skip_words:])
    else:
        english_short = english_full
    
    return english_full, english_short, chinese

def parse_release_type(english_short, tags):
    """检测是否为特别版"""
    rt = ''
    rt_cn = ''
    rn = ''
    
    lower = english_short.lower()
    
    if 'limited edition' in lower or '限量' in ' '.join(tags):
        rt = 'Limited Edition Series'
        rt_cn = '年限'
    
    # 检测年份
    import re
    year_match = re.search(r'(20\d{2})', english_short)
    if year_match:
        rn = year_match.group(1) + ' Edition'
    
    # 检测生肖
    zodiac = {
        'dragon': '龙', 'snake': '蛇', 'horse': '马', 'rabbit': '兔',
        'tiger': '虎', 'ox': '牛', 'rat': '鼠', 'rooster': '鸡',
        'dog': '狗', 'pig': '猪', 'monkey': '猴', 'goat': '羊',
    }
    for en, cn in zodiac.items():
        if en in lower:
            rn = f'Year of the {en.title()} {year_match.group(1) if year_match else ""}'
            break
    
    return rt, rt_cn, rn

def parse_packaging(name_str):
    """从产品名提取包装信息"""
    import re
    packagings = []
    
    # 找支数
    m = re.search(r'(\d+)\s*支', name_str)
    if m:
        size = int(m.group(1))
        packagings.append({'size': size, 'type': f'1套 {size}支'})
    
    # 找保湿盒
    if '保濕盒' in name_str or '保湿盒' in name_str or 'Humidor' in name_str:
        if packagings:
            packagings[0]['type'] = f'保湿盒 {packagings[0]["size"]}支'
    
    return packagings

def import_products(data_file):
    """主导入函数"""
    with open(data_file) as f:
        products = json.load(f)
    
    created = 0
    skipped = 0
    errors = 0
    
    for item in products:
        brand_tc = item['brand_name']
        brand_django = BRAND_MAP.get(brand_tc, brand_tc)
        name_str = item['name']
        
        english_full, english_short, chinese_name = parse_name(name_str, brand_tc)
        length, ring_gauge, vitola = guess_specs(brand_tc, name_str)
        rt, rt_cn, rn = parse_release_type(english_short, item.get('tags', []))
        packagings = parse_packaging(name_str)
        
        # 查重
        existing = Cigar.objects.filter(
            brand=brand_django,
            english_name__iexact=english_short,
            release_type=rt,
            release_name=rn,
        ).first()
        
        if existing:
            if not existing.production_method:
                existing.production_method = 'machine_rolled_short_filler'
                existing.save(update_fields=['production_method'])
                print(f'  ✏️ {existing} → 機捲短芯')
            skipped += 1
            continue
        
        try:
            cigar = Cigar.objects.create(
                brand=brand_django,
                english_name=english_short,
                name=chinese_name or english_short,
                length=length,
                ring_gauge=ring_gauge,
                vitola=vitola,
                origin='Cuban',
                status='Current',
                production_method='machine_rolled_short_filler',
                release_type=rt,
                release_type_cn=rt_cn,
                release_name=rn,
                packagings=json.dumps(packagings, ensure_ascii=False),
                url=f'https://www.timecigar.com/product?view=product&brand={item["brand_id"]}&product_id={item["product_id"]}',
            )
            created += 1
            print(f'  ✅ {brand_django} - {chinese_name or english_short} ({length}×{ring_gauge})')
        except Exception as e:
            errors += 1
            print(f'  ❌ {brand_django} - {english_short}: {e}')
    
    print(f'\n=== 导入完成: 新建 {created} | 跳过 {skipped} | 错误 {errors} ===')
    return created, skipped, errors

if __name__ == '__main__':
    # 数据文件路径
    data_file = '/home/jason/cigardomtabaka/timecigar_minis_full.json'
    if not os.path.exists(data_file):
        print(f'❌ 数据文件不存在: {data_file}')
        print('请先运行 scrape_timecigar_details.py 爬取详情')
        sys.exit(1)
    
    import_products(data_file)
