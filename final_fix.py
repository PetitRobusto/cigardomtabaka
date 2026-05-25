"""Final fix: fill remaining empty Chinese names with best-effort matching"""
import json, os, re, sys, unicodedata

sys.path.insert(0, os.path.expanduser('~/moscow_cigar'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'moscow_cigar_backend.settings')
import django; django.setup()
from cigars.models import Cigar

base = os.path.expanduser('~/moscow_cigar')

# Load all raw data from batch files
raw = {}
for fn in sorted(os.listdir(base)):
    if fn.startswith('cigar_cn_batch') and fn.endswith('.json'):
        with open(os.path.join(base, fn)) as f:
            raw.update(json.load(f))

# Also load bolivar
cf = os.path.join(base, 'cigar_cn_full.json')
if os.path.exists(cf):
    with open(cf) as f:
        d = json.load(f)
        for k, v in d.items():
            raw[k] = v

BRANDS_MAP = {
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

def norm(s):
    """Normalize string for comparison"""
    return unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode().lower()

def slug2eng(s):
    p = s.split('-')
    r = []
    for x in p:
        if x.upper() == 'BHK': r.append('BHK')
        elif x.upper() in ('I','II','III','IV','V','VI','VII'): r.append(x.upper())
        elif x.isdigit(): r.append(x)
        else: r.append(x[0].upper() + x[1:] if x else '')
    return ' '.join(r).replace('No ', 'No.')

def extract_en(text):
    """Extract English name from text (last English word sequence)"""
    tokens = text.strip().split()
    # Find the last sequence of English words
    en_tokens = []
    for t in reversed(tokens):
        c = re.sub(r'\(\d+\)', '', t).strip()
        if not c: continue
        is_eng = (re.match(r'^[A-Z][a-zéíñ]+$', c) or
                  re.match(r'^[A-Z0-9][A-Za-z0-9éíñ.]+$', c) or
                  c.isdigit() or
                  c.upper() in 'BHK I II III IV V VI VII A B C D E P T'.split())
        if not is_eng:
            break
        en_tokens.insert(0, re.sub(r'\s*\(\d+\)\s*', '', c).strip())
    return ' '.join(en_tokens) if en_tokens else ''

# Build a lookup: {brand: {norm(english_name): [cigar_ids]}}
db_lookup = {}
for c in Cigar.objects.all():
    b = c.brand
    if b not in db_lookup:
        db_lookup[b] = {}
    n = norm(c.english_name)
    db_lookup[b].setdefault(n, []).append(c.id)

total_updated = 0
total_matched = 0

for brand_slug, entries in raw.items():
    en_brand = BRANDS_MAP.get(brand_slug, brand_slug)
    for entry in entries:
        if isinstance(entry[0], str):
            slug, raw_text = entry[0], entry[1]
        else:
            # Bolívar format: [slug, cn_name]
            slug, cn_name = entry[0], entry[1]
            # Convert directly
            eng = slug2eng(slug)
            norm_eng = norm(eng)
            if en_brand in db_lookup and norm_eng in db_lookup[en_brand]:
                ids = db_lookup[en_brand][norm_eng]
                Cigar.objects.filter(id__in=ids, name='').update(name=cn_name)
                total_matched += 1
                total_updated += len(ids)
            continue
        
        # Extract Chinese name from text — scan backwards from end
        text = raw_text.strip()
        tokens = text.split()
        # Find where English name starts (from end)
        en_start = len(tokens)
        for i in range(len(tokens) - 1, -1, -1):
            t = tokens[i]
            c = re.sub(r'\(\d+\)', '', t).strip()
            if not c: continue
            is_eng = (re.match(r'^[A-Z]', c) or
                      c.upper() in 'BHK I II III IV V VI VII A B C D E P T'.split())
            if is_eng:
                en_start = i
            else:
                break
        cn_name = ' '.join(tokens[:en_start]).strip()
        cn_name = re.sub(r'\s*\(\d+\)\s*$', '', cn_name).strip()
        
        if not cn_name:
            continue
        
        # Try to match in order:
        # 1. Extract English name from text
        en_from_text = extract_en(raw_text)
        
        # 2. Try slug → english
        en_from_slug = slug2eng(slug)
        
        # Try all English name candidates
        candidates = [en_from_text, en_from_slug]
        matched = False
        for eng_cand in candidates:
            if not eng_cand: continue
            norm_eng = norm(eng_cand)
            if en_brand in db_lookup and norm_eng in db_lookup[en_brand]:
                ids = db_lookup[en_brand][norm_eng]
                n = Cigar.objects.filter(id__in=ids, name='').update(name=cn_name)
                if n > 0:
                    total_matched += 1
                    total_updated += n
                    matched = True
                    break
        
        if not matched:
            # Last resort: fuzzy substring match (single result only)
            if en_from_text:
                sub_matches = Cigar.objects.filter(
                    brand=en_brand, name='',
                    english_name__icontains=en_from_text
                )
                if sub_matches.count() == 1:
                    sub_matches.update(name=cn_name)
                    total_matched += 1
                    total_updated += 1

empty = Cigar.objects.filter(name='').count()
total = Cigar.objects.count()
print(f'Final update: {total_matched} entries, {total_updated} rows')
print(f'Has Chinese: {total - empty}/{total} ({(total-empty)*100//total}%)')
