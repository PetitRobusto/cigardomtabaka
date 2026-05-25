"""Process all raw cigar Chinese name data from MCP browser batches and update DB."""
import json, os, re, sys

sys.path.insert(0, os.path.expanduser('~/moscow_cigar'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'moscow_cigar_backend.settings')
import django; django.setup()
from cigars.models import Cigar

# Brand slug → English name mapping
BRANDS = {
    'bolivar': 'Bolívar', 'cohiba': 'Cohiba', 'cuaba': 'Cuaba',
    'diplomaticos': 'Diplomáticos', 'el-rey-del-mundo': 'El Rey del Mundo',
    'fonseca': 'Fonseca', 'h-upmann': 'H. Upmann',
    'hoyo-de-monterrey': 'Hoyo de Monterrey', 'jose-l-piedra': 'José L. Piedra',
    'juan-lopez': 'Juan López', 'la-flor-de-cano': 'La Flor de Cano',
    'la-gloria-cubana': 'La Gloria Cubana', 'montecristo': 'Montecristo',
    'partagas': 'Partagás', 'por-larranaga': 'Por Larrañaga',
    'punch': 'Punch', 'quai-dorsay': "Quai d'Orsay",
    'quintero': 'Quintero', 'rafael-gonzalez': 'Rafael González',
    'ramon-allones': 'Ramón Allones', 'romeo-y-julieta': 'Romeo y Julieta',
    'saint-luis-rey': 'Saint Luis Rey', 'san-cristobal': 'San Cristóbal',
    'sancho-panza': 'Sancho Panza', 'trinidad': 'Trinidad',
    'vegas-robaina': 'Vegas Robaina', 'vegueros': 'Vegueros',
}

# Chinese brand name mapping for text stripping
BRAND_CN = {
    'bolivar': '玻利瓦', 'cohiba': '高希霸', 'cuaba': '库阿巴',
    'diplomaticos': '外交官', 'el-rey-del-mundo': '世界之王',
    'fonseca': '科塞卡', 'h-upmann': '乌普曼',
    'hoyo-de-monterrey': '好友', 'jose-l-piedra': '荷西比雅达',
    'juan-lopez': '胡安佩洛斯', 'la-flor-de-cano': '卡诺之花',
    'la-gloria-cubana': '古巴荣耀', 'montecristo': '蒙特',
    'partagas': '帕特加斯', 'por-larranaga': '波尔拉腊尼加',
    'punch': '潘趣', 'quai-dorsay': '希多尔赛',
    'quintero': '金特罗', 'rafael-gonzalez': '拉斐尔',
    'ramon-allones': '雷蒙阿隆尼', 'romeo-y-julieta': '罗密欧与朱丽叶',
    'saint-luis-rey': '圣路易斯雷伊', 'san-cristobal': '圣克里斯多',
    'sancho-panza': '桑丘潘萨', 'trinidad': '千里达',
    'vegas-robaina': '瓦格斯陆班纳', 'vegueros': '威古洛',
}


def extract_chinese_name(text, brand_slug):
    """Extract Chinese cigar name from text like '高希霸 Cohiba 长矛 Lanceros'"""
    text = text.strip()
    brand_cn = BRAND_CN.get(brand_slug, '')
    brand_en = BRANDS.get(brand_slug, '')
    
    # Remove brand prefix patterns
    prefixes = []
    if brand_cn:
        prefixes.append(brand_cn)
        prefixes.append(f'{brand_cn} {brand_en}')
    if brand_en:
        prefixes.append(brand_en)
    
    for prefix in prefixes:
        pattern = r'^' + re.escape(prefix) + r'\s+'
        text = re.sub(pattern, '', text).strip()
    
    if not text:
        return text
    
    # Split tokens and find where English starts
    tokens = text.split()
    cn_tokens = []
    for tok in tokens:
        clean = re.sub(r'\(\d+\)', '', tok).strip()
        if not clean:
            cn_tokens.append(tok)
            continue
        is_eng = (re.match(r'^[A-Z][a-zéíñ]+$', clean) or
                  re.match(r'^[A-Z0-9][A-Za-z0-9éíñ.]+$', clean) or
                  clean.isdigit() or
                  clean.upper() in ('BHK', 'I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'A', 'B', 'C', 'D', 'E', 'P'))
        if is_eng:
            break
        cn_tokens.append(tok)
    
    result = ' '.join(cn_tokens).strip()
    result = re.sub(r'\s*\(\d+\)\s*$', '', result).strip()
    return result if result else text


def slug_to_english(slug):
    """Convert slug to English name: 'siglo-vi' → 'Siglo VI'"""
    parts = slug.split('-')
    result = []
    for p in parts:
        if p.upper() == 'BHK':
            result.append('BHK')
        elif p.upper() in ('I', 'II', 'III', 'IV', 'V', 'VI', 'VII'):
            result.append(p.upper())
        elif p.isdigit():
            result.append(p)
        else:
            result.append(p[0].upper() + p[1:] if p else '')
    eng = ' '.join(result)
    # Fix common patterns
    eng = eng.replace('No ', 'No.')  # No2 → No.2
    return eng


def process_batch_file(filepath):
    """Process a raw batch JSON file: [slug, text] → update DB"""
    with open(filepath) as f:
        data = json.load(f)
    
    updated = 0
    matched = 0
    not_found = []
    
    for brand_slug, entries in data.items():
        en_brand = BRANDS.get(brand_slug, brand_slug)
        for entry in entries:
            slug, raw_text = entry[0], entry[1]
            cn_name = extract_chinese_name(raw_text, brand_slug)
            if not cn_name:
                continue
            
            eng_name = slug_to_english(slug)
            
            # Try exact match first
            n = Cigar.objects.filter(
                brand=en_brand,
                english_name__iexact=eng_name
            ).update(name=cn_name)
            
            if n == 0:
                # Try lowercase match
                n = Cigar.objects.filter(
                    brand=en_brand,
                    english_name__iexact=eng_name.lower()
                ).update(name=cn_name)
            
            if n == 0:
                # Try contains match
                n = Cigar.objects.filter(
                    brand=en_brand,
                    english_name__icontains=eng_name
                ).update(name=cn_name)
            
            if n == 0:
                not_found.append(f'{brand_slug}: {eng_name} ({slug})')
            else:
                matched += 1
            updated += n
    
    return updated, matched, not_found


if __name__ == '__main__':
    base_dir = os.path.expanduser('~/moscow_cigar')
    batch_files = [
        f for f in os.listdir(base_dir) 
        if f.startswith('cigar_cn_batch') and f.endswith('.json')
    ]
    
    total_updated = 0
    total_matched = 0
    all_not_found = []
    
    for bf in sorted(batch_files):
        fp = os.path.join(base_dir, bf)
        print(f'Processing {bf}...')
        up, ma, nf = process_batch_file(fp)
        total_updated += up
        total_matched += ma
        all_not_found.extend(nf)
        print(f'  {ma} matched, {up} rows updated')
    
    print(f'\n✅ Total: {total_matched} entries matched, {total_updated} rows updated')
    
    if all_not_found:
        print(f'\n⚠️ {len(all_not_found)} not found:')
        for nf in all_not_found[:20]:
            print(f'  {nf}')
        if len(all_not_found) > 20:
            print(f'  ... and {len(all_not_found) - 20} more')
    
    empty = Cigar.objects.filter(name='').count()
    total = Cigar.objects.count()
    print(f'\n📊 Has Chinese: {total - empty} / {total} ({(total-empty)*100//total}%)')
