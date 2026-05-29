"""爬取所有品牌的中文雪茄名，更新到数据库。
使用 Playwright 访问 cubancigarwebsite.com 中文版。
"""
import json
import os
import re
import sys
import time

# Add Django project
sys.path.insert(0, os.path.expanduser('~/cigardomtabaka'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cigardomtabaka_backend.settings')
import django
django.setup()

from cigars.models import Cigar

# All 27 active brands with their slugs
BRANDS = [
    'bolivar', 'cohiba', 'cuaba', 'diplomaticos', 'el-rey-del-mundo',
    'fonseca', 'h-upmann', 'hoyo-de-monterrey', 'jose-l-piedra',
    'juan-lopez', 'la-flor-de-cano', 'la-gloria-cubana', 'montecristo',
    'partagas', 'por-larranaga', 'punch', 'quai-dorsay', 'quintero',
    'rafael-gonzalez', 'ramon-allones', 'romeo-y-julieta', 'saint-luis-rey',
    'san-cristobal', 'sancho-panza', 'trinidad', 'vegas-robaina', 'vegueros',
]

# Chinese brand names (for stripping from text)
BRAND_CN = {
    'bolivar': '玻利瓦尔',
    'cohiba': '高希霸',
    'cuaba': '库阿巴',
    'diplomaticos': '外交官',
    'el-rey-del-mundo': '世界之王',
    'fonseca': '丰塞卡',
    'h-upmann': '乌普曼',
    'hoyo-de-monterrey': '好友蒙特雷',
    'jose-l-piedra': '比德罗',
    'juan-lopez': '胡安洛佩斯',
    'la-flor-de-cano': '拉弗洛尔德卡诺',
    'la-gloria-cubana': '古巴荣耀',
    'montecristo': '蒙特',
    'partagas': '帕特加斯',
    'por-larranaga': '波尔拉腊尼加',
    'punch': '潘趣',
    'quai-dorsay': '多赛尔',
    'quintero': '金特罗',
    'rafael-gonzalez': '拉斐尔冈萨雷斯',
    'ramon-allones': '拉蒙阿龙',
    'romeo-y-julieta': '罗密欧与朱丽叶',
    'saint-luis-rey': '圣路易斯雷',
    'san-cristobal': '圣克里斯托',
    'sancho-panza': '桑乔潘萨',
    'trinidad': '特立尼达',
    'vegas-robaina': '维加斯罗瓦伊纳',
    'vegueros': '维格罗',
}


def slug_to_english(slug):
    """Convert slug like 'siglo-vi' to 'Siglo VI'"""
    if not slug:
        return None
    # Capitalize each word
    parts = slug.split('-')
    result = []
    for p in parts:
        if p.upper() == 'BHK':
            result.append('BHK')
        elif p.lower() in ('i', 'ii', 'iii', 'iv', 'v', 'vi'):
            # Roman numerals
            result.append(p.upper())
        elif p.isdigit():
            result.append(p)
        else:
            result.append(p[0].upper() + p[1:] if p else '')
    return ' '.join(result)


def extract_chinese_name(raw_text, brand_slug):
    """Extract Chinese name from text like '高希霸 Cohiba 长矛 Lanceros'"""
    text = raw_text.strip()
    
    # Strip brand prefix: "{brand_cn} {brand_en} " or "{brand_cn} "
    brand_cn = BRAND_CN.get(brand_slug, '')
    brand_en = brand_slug.replace('-', ' ').title()
    
    # Remove brand prefix patterns:
    # 1. "高希霸 Cohiba " 
    # 2. "高希霸 "
    # 3. "Cohiba "
    if brand_cn:
        pattern = re.escape(brand_cn) + r'\s+' + re.escape(brand_en.replace(' ', r'\s+'))
        text = re.sub(r'^' + pattern + r'\s+', '', text)
        text = re.sub(r'^' + re.escape(brand_cn) + r'\s+', '', text)
    text = re.sub(r'^' + re.escape(brand_en.replace(' ', r'\s+')) + r'\s+', '', text)
    
    # Now text should be "长矛 Lanceros" or just "长矛"
    # Try to extract: find the last English word sequence and strip it
    # English word = starts with uppercase letter
    # Match: trailing sequence of English words
    
    # Check if text ends with English words like "BHK 52"
    # Split and check if last tokens are English
    tokens = text.split()
    
    # Find the boundary: the last token that starts with uppercase or is a digit
    # Everything before that is Chinese name
    chinese_tokens = []
    english_started = False
    for i, tok in enumerate(tokens):
        # Remove parentheses like "(10)" or "(25)"
        tok_clean = re.sub(r'\([^)]*\)', '', tok).strip()
        if not tok_clean:
            continue
        # If token starts with uppercase letter or is purely English/alphanumeric
        is_english = bool(re.match(r'^[A-Z][a-zéí]+$', tok_clean)) or \
                     bool(re.match(r'^[A-Z0-9][A-Za-z0-9éí.]+$', tok_clean)) or \
                     tok_clean.isdigit() or \
                     tok_clean.upper() in ('BHK', 'I', 'II', 'III', 'IV', 'V', 'VI', 'VII')
        if is_english:
            english_started = True
            break
        chinese_tokens.append(tok)
    
    cn_name = ' '.join(chinese_tokens).strip()
    
    # Handle multi-stick notation like "(10)"
    cn_name = re.sub(r'\s*\(\d+\)\s*$', '', cn_name).strip()
    
    return cn_name if cn_name else text


# ── Main Execution ──
if __name__ == '__main__':
    data_file = os.path.expanduser('~/cigardomtabaka/cigar_chinese_names_full.json')
    
    if os.path.exists(data_file):
        print(f'📄 Loading existing data from {data_file}')
        with open(data_file) as f:
            all_data = json.load(f)
        print(f'   {len(all_data)} entries loaded')
    else:
        all_data = []
    
    existing_keys = {(d['brand'], d['english_name']) for d in all_data}
    total_found = len(all_data)
    
    print(f'\n📊 Current DB state:')
    total = Cigar.objects.count()
    has_name = Cigar.objects.exclude(name='').count()
    print(f'   Total: {total}, Has Chinese: {has_name}, Empty: {total - has_name}')
    
    # Update DB from loaded data
    updated = 0
    for d in all_data:
        if d.get('chinese_name'):
            n = Cigar.objects.filter(
                brand=d['brand'], 
                english_name__iexact=d['english_name']
            ).update(name=d['chinese_name'])
            updated += n
    
    print(f'\n✅ Updated {updated} from loaded data')
    print(f'\nRemaining empty Chinese names: {Cigar.objects.filter(name="").count()}')
    
    print('\n⚠️  This script extracts from browser. Make sure a browser is open on the Chinese site.')
    print('   Call with: python extract_cn_names.py --browser')
    
    # Output summary
    missing = Cigar.objects.filter(name='').values('brand').annotate(
        # count manually
    ).values('brand').distinct()
    
    # Show remaining gaps
    from django.db.models import Count
    gaps = Cigar.objects.filter(name='').values('brand').annotate(
        cnt=Count('id')
    ).order_by('-cnt')
    print('\n📋 Remaining gaps:')
    for g in gaps:
        print(f'   {g["brand"]}: {g["cnt"]} empty')
