#!/usr/bin/env python3
"""Process raw cigar Chinese name data from MCP browser batches."""
import json, os, re, sys

sys.path.insert(0, os.path.expanduser('~/moscow_cigar'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'moscow_cigar_backend.settings')
import django; django.setup()
from cigars.models import Cigar

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

def extract_cn_and_en(text, brand_slug):
    """Extract Chinese+English names. Chinese = everything before the final English word sequence."""
    text = text.strip()
    cn, en_brand = BRAND_CN.get(brand_slug, ''), BRANDS.get(brand_slug, '')
    
    # Remove brand prefix
    for p in [f'{cn} {en_brand}', cn, en_brand]:
        if p: text = re.sub(r'^' + re.escape(p) + r'\s+', '', text).strip()
    
    tokens = text.split()
    
    # Find the LAST purely English word → everything from there to end is English name
    # "Core English" token: starts with uppercase letter, or is all-caps acronym (BHK), 
    # or is Roman numeral (I-VII), or is a specific single-letter name (A, B, etc.)
    core_eng = re.compile(r'^[A-Z][a-zéíñ]+$')
    all_caps = 'BHK I II III IV V VI VII A B C D E P T'.split()
    
    en_core_idx = -1
    for i in range(len(tokens) - 1, -1, -1):
        t = tokens[i]
        c = re.sub(r'\(\d+\)', '', t).strip()
        if not c: continue
        if core_eng.match(c) or c.upper() in all_caps:
            en_core_idx = i
            break  # found the core → everything from here is English
    
    if en_core_idx >= 0:
        # Chinese = everything before core English
        cn_tokens = tokens[:en_core_idx]
        # English = core English through end (strip parentheticals)
        en_tokens = []
        for t in tokens[en_core_idx:]:
            c = re.sub(r'\s*\(\d+\)\s*', '', t).strip()
            if c: en_tokens.append(c)
        en_name = ' '.join(en_tokens)
    else:
        cn_tokens = tokens
        en_name = ''
    
    cn_name = ' '.join(cn_tokens).strip()
    cn_name = re.sub(r'\s*\(\d+\)\s*$', '', cn_name).strip()
    
    return cn_name if cn_name else text, en_name


def try_match(brand, eng_name, cn_name):
    """Try multiple strategies to match and update a cigar"""
    # Strategy 1: exact match
    n = Cigar.objects.filter(brand=brand, english_name__iexact=eng_name).update(name=cn_name)
    if n > 0: return n
    
    # Strategy 2: accent-insensitive
    import unicodedata
    eng_ascii = unicodedata.normalize('NFKD', eng_name).encode('ascii', 'ignore').decode()
    if eng_ascii != eng_name:
        candidates = Cigar.objects.filter(brand=brand).values_list('english_name', flat=True)
        for cand in candidates:
            cand_ascii = unicodedata.normalize('NFKD', cand).encode('ascii', 'ignore').decode()
            if cand_ascii.lower() == eng_ascii.lower():
                return Cigar.objects.filter(brand=brand, english_name=cand).update(name=cn_name)
    
    # Strategy 3: case-insensitive exact
    n = Cigar.objects.filter(brand=brand, english_name__iexact=eng_name.lower()).update(name=cn_name)
    if n > 0: return n
    
    # Strategy 4: contains (be careful - could match multiple)
    matches = Cigar.objects.filter(brand=brand, english_name__icontains=eng_name)
    count = matches.count()
    if count == 1:
        return matches.update(name=cn_name)
    elif count > 1:
        # Try exact match among contains results
        exact = [m for m in matches if m.english_name.lower() == eng_name.lower()]
        if len(exact) == 1:
            return Cigar.objects.filter(id=exact[0].id).update(name=cn_name)
    
    return 0

def slug2eng(s):
    parts = s.split('-')
    res = []
    for p in parts:
        if p.upper() == 'BHK': res.append('BHK')
        elif p.upper() in ('I','II','III','IV','V','VI','VII'): res.append(p.upper())
        elif p.isdigit(): res.append(p)
        else: res.append(p[0].upper() + p[1:] if p else '')
    return ' '.join(res).replace('No ', 'No.')

total_up = total_match = 0
nf = []
files = sorted([f for f in os.listdir('.') if f.startswith('cigar_cn_batch') and f.endswith('.json')])
if not files:
    print("No batch files found! Need to save raw data first.")
    print("Looking for cigar_cn_full.json...")
    alt = 'cigar_cn_full.json' 
    if os.path.exists(alt): files = [alt]

for bf in files:
    print(f'\n📄 {bf}')
    with open(bf) as f: data = json.load(f)
    up = match = 0
    for bs, entries in data.items():
        enb = BRANDS.get(bs, bs)
        for e in entries:
            slug, txt = e[0], e[1]
            cn, en_from_text = extract_cn_and_en(txt, bs)
            if not cn: continue
            
            # Strategy A: use English name extracted from text
            if en_from_text:
                n = try_match(enb, en_from_text, cn)
                if n > 0:
                    up += n; match += 1
                    continue
            
            # Strategy B: try slug→english conversion
            eng = slug2eng(slug)
            n = try_match(enb, eng, cn)
            if n > 0:
                up += n; match += 1
                continue
            
            nf.append(f'{bs}: {txt[:40]}')
    print(f'  {match} matched, {up} rows')
    total_up += up; total_match += match

print(f'\n✅ Total: {total_match} entries, {total_up} rows')
if nf:
    print(f'⚠️ {len(nf)} not found (first 15):')
    for x in nf[:15]: print(f'  {x}')
e = Cigar.objects.filter(name='').count()
t = Cigar.objects.count()
print(f'\n📊 {t - e}/{t} ({(t-e)*100//t}%)')
