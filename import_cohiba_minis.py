#!/usr/bin/env python3
import os,sys,django,json
os.environ['DJANGO_SETTINGS_MODULE']='moscow_cigar_backend.settings'
os.environ['DJANGO_DEBUG']='True'
sys.path.insert(0,'/home/jason/moscow_cigar')
django.setup()
from cigars.models import Cigar

data = [
    ('Mini White','白色 迷你',82,20,'','',''),
    ('Mini 2024 Edition','迷你 2024版',82,20,'','','2024 Edition'),
    ('Club 2025 Edition','俱乐部 2025版',96.5,22,'','','2025 Edition'),
    ('Club','俱乐部',96.5,22,'','',''),
    ('Club White','白色 俱乐部',96.5,22,'','',''),
    ('Short 50s','短号 50支装',82,27,'','',''),
    ('Short 100s','短号 100支装',82,27,'','',''),
    ('Short 2025 Limited Edition','短号 2025限量版',82,27,'Limited Edition Series','年限','2025 Limited Edition'),
    ('Wide Short 30s','宽号 30支装',100,32,'','',''),
    ('Wide Short 60s','宽号 60支装',100,32,'','',''),
    ('Short Year of the Snake 2025 LE','短号 2025蛇年限量版',82,27,'Limited Edition Series','年限','Year of the Snake 2025'),
    ('Short Year of the Horse 2026 LE','短号 2026马年限量版',82,27,'Limited Edition Series','年限','Year of the Horse 2026'),
    ('Wide Short Humidor 2024 LE','宽号 保湿盒 2024限量版',100,32,'Limited Edition Series','年限','2024 Limited Edition'),
    ('Wide Short Humidor 2025 LE','宽号 保湿盒 2025限量版',100,32,'Limited Edition Series','年限','2025 Limited Edition'),
]

for en,name,l,rg,rt,rt_cn,rn in data:
    c,is_new = Cigar.objects.get_or_create(
        brand='Cohiba', english_name=en, release_type=rt, release_name=rn,
        defaults=dict(name=name, length=l, ring_gauge=rg, vitola='Mini Cigar',
            origin='Cuban', status='Current', production_method='machine_rolled_short_filler',
            release_type_cn=rt_cn, url='',
            packagings=json.dumps([{'size':100,'type':'1套 100支'}], ensure_ascii=False))
    )
    tag = 'NEW' if is_new else 'UPD'
    if not is_new:
        c.production_method='machine_rolled_short_filler'
        c.save(update_fields=['production_method'])
    print(f'  {tag} Cohiba {en}')

total = Cigar.objects.filter(production_method='machine_rolled_short_filler').count()
print(f'\nTotal machine_rolled: {total}')
for b in Cigar.objects.filter(production_method='machine_rolled_short_filler').values('brand').distinct():
    cnt = Cigar.objects.filter(production_method='machine_rolled_short_filler', brand=b['brand']).count()
    print(f'  {b["brand"]}: {cnt}')
