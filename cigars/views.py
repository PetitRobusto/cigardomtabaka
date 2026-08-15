from django.db.models import Count, Sum, Max, F
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse

from .models import Brand, Cigar, PurchaseBatch
from privnote.helpers import decimal_to_number


PACKAGING_TRANSLATIONS = [
    (r'Numbered black lacquered boîte nature box', '编号黑漆自然盒'),
    (r'Black lacquered boîte nature box', '黑漆自然盒'),
    (r'Black lacquered slide lid box', '黑漆滑盖木盒'),
    (r'Numbered varnished semi boîte nature box', '编号漆面半自然盒'),
    (r'Numbered varnished boîte nature box', '编号漆面自然盒'),
    (r'Numbered luxury boîte nature box', '编号豪华自然盒'),
    (r'Numbered semi boîte nature box', '编号半自然盒'),
    (r'Numbered slide lid box', '编号滑盖木盒'),
    (r'Numbered dress box', '编号木盒'),
    (r'Varnished slide lid box', '漆面滑盖木盒'),
    (r'Varnished boîte nature box', '漆面自然盒'),
    (r'Varnished semi boîte nature box', '漆面半自然盒'),
    (r'Luxury boîte nature box', '豪华自然盒'),
    (r'Semi boîte nature box', '半自然盒'),
    (r'Boîte nature box', '自然盒'),
    (r'Slide lid box', '滑盖木盒'),
    (r'Dress box', '木盒'),
    (r'(\d+) cardboard packs? of (\d+)', r'\1 个纸盒 × \2 支'),
    (r'Cardboard packs?', '纸盒'),
    (r'Display box', '展示盒'),
    (r'Jar', '陶瓷罐'),
    (r'Ceramic jar', '陶瓷罐'),
    (r'Cajón', '大木箱'),
    (r'Numbered humidor', '编号保湿盒'),
    (r'Humidor', '保湿盒'),
    (r'Travel humidor', '旅行保湿盒'),
    (r'Glass jar', '玻璃罐'),
    (r'Aluminium pack', '铝盒'),
    (r'Cardboard box', '纸盒'),
    (r'Numbered book', '编号书本盒'),
    (r'Numbered chest', '编号箱'),
    (r'Numbered box', '编号盒'),
    (r'in aluminium tubes', '铝管装'),
    (r'of (\d+) aluminium tubed cigars', r'，\1 支铝管雪茄'),
    (r'aluminium tubed cigars', '铝管雪茄'),
    (r'aluminium tubes', '铝管'),
    (r'in cellophane', '套玻璃纸'),
    (r'in crystal tubes', '水晶管装'),
    (r'of (\d+) cigars', r'，\1 支'),
    (r'of (\d+) aluminium', r'，\1 铝'),
    (r'\s+in\s+(\d+)', r'，内含 \1'),
    (r'\((\d[\d,]*)\s*produced\)', r'（限量 \1 件）'),
    (r'\(discontinued\s+(\d{4})\)', r'（\1 年停产）'),
    (r'\(discontinued\s+pre-(\d{4})\)', r'（\1 年前停产）'),
    (r'\(discontinued\s+c?(\d{4})\)', r'（约 \1 年停产）'),
    (r'\(released\s+(?:c\s*)?(\d{4})\)', r'（\1 年发布）'),
    (r'\(discontinued\)', '（已停产）'),
    (r'  +', ' '),
]


def translate_packaging(text: str) -> str:
    """翻译英文包装描述为中文"""
    import re
    result = text.strip()
    for pattern, replacement in PACKAGING_TRANSLATIONS:
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
    result = result.replace(' .', '。').replace(' ,', '，')
    result = re.sub(r'\s+，', '，', result)
    result = re.sub(r'\s+。', '。', result)
    result = re.sub(r'\s+（', '（', result)
    result = result.strip(' ,.')
    return result


SECTION_ORDER = [
    ('global',        '全球品牌'),
    ('value',         '价值品牌'),
    ('volume',        '走量品牌'),
    ('other',         '其他品牌'),
    ('ict',           'ICT 机制'),
    ('special',       '特殊品牌'),
    ('discontinued',  '已停产品牌'),
]

RELEASE_TYPE_ORDER = [
    ('',                '常规款'),
    ('Limited Edition Series',          '限量版'),
    ('Regional Edition Series',         '地区限量版'),
    ('Commemorative Release',           '纪念版'),
    ('Habanos Collection Series',       '哈瓦那收藏系列'),
    ('Reserve Series',                  '珍藏系列'),
    ('Grand Reserve Series',            '特级珍藏系列'),
    ('Millennium Reserve Series',       '千禧珍藏系列'),
    ('Aged Habanos Series',             '陈年哈瓦那系列'),
    ('Duty Free and Travel Retail Series', '免税及旅行零售系列'),
    ('Chinese Year Series',             '中国年份系列'),
    ('Replica Antique Humidor Series',  '复刻古董保湿盒系列'),
    ('Vintage Series',                  '年份系列'),
    ('Special Events',                  '特别活动'),
    ('Other Special Release',           '其他特别版'),
    ('LCDH Exclusive Release',          'LCDH 独享'),
    ('Habanos Specialist and La Casa del Habano Exclusive', '专家店独享'),
]


# =================== API VIEWS ===================

def api_brand_list(request):
    """GET /api/brands/"""
    brands = list(Brand.objects.all().order_by('english_name'))
    cigar_counts = {}
    for row in Cigar.objects.filter(parent__isnull=True).values('brand').annotate(n=Count('id')):
        cigar_counts[row['brand']] = row['n']

    brand_by_cat = {}
    for b in brands:
        brand_by_cat.setdefault(b.category, []).append(b)

    sections = []
    for cat_key, cat_label in SECTION_ORDER:
        if cat_key in brand_by_cat:
            sections.append({
                'key': cat_key,
                'label': cat_label,
                'brands': [
                    {
                        'english_name': b.english_name,
                        'name': b.name or b.english_name,
                        'slug': b.slug,
                        'logo_url': b.logo.url if b.logo else None,
                        'origin': b.origin,
                        'category': b.category,
                        'cigar_count': cigar_counts.get(b.english_name, 0),
                    }
                    for b in brand_by_cat[cat_key]
                ],
            })

    return JsonResponse({'sections': sections, 'total_brands': len(brands)})


def api_brand_detail(request, slug):
    """GET /api/brands/<slug>/"""
    brand = Brand.objects.get(slug=slug)
    all_cigars = Cigar.objects.filter(brand=brand.english_name)\
        .order_by('english_name')\
        .prefetch_related('images')

    current = []
    orphan_special = {}
    discontinued = []
    small_cigars = []

    for c in all_cigars:
        if c.parent_id:
            continue
        vitola_lower = (c.vitola or '').lower()
        if vitola_lower in ('mini', 'short', 'club'):
            small_cigars.append(c)
            continue
        status = c.status or ''
        rt = c.release_type or ''
        if status == 'Discontinued':
            discontinued.append(c)
        elif status == 'Special Releases':
            orphan_special.setdefault(rt, []).append(c)
        else:
            current.append(c)

    all_parents = current + discontinued + small_cigars
    for v in orphan_special.values():
        all_parents.extend(v)

    parent_children = {}
    for c in all_parents:
        children = list(Cigar.objects.filter(parent=c).order_by('release_type', 'english_name'))
        if children:
            parent_children[c.id] = children

    def _serialize_cigar(c):
        primary = c.primary_image
        return {
            'id': c.id,
            'name': c.name or c.english_name,
            'english_name': c.english_name,
            'vitola': c.vitola,
            'vitola_cn': c.vitola_cn,
            'length': c.length,
            'ring_gauge': c.ring_gauge,
            'release_type': c.release_type,
            'release_type_cn': c.release_type_cn,
            'status': c.status,
            'thumb_url': primary.thumbnail.url if primary and primary.thumbnail else None,
            'image_url': primary.image.url if primary and primary.image else None,
            'children': [
                {
                    'id': child.id,
                    'name': child.name or child.english_name,
                    'english_name': child.english_name,
                    'release_type': child.release_type,
                    'release_type_cn': child.release_type_cn,
                }
                for child in parent_children.get(c.id, [])
            ],
        }

    sections = []
    if current:
        sections.append({'label': f'常规款 ({len(current)})', 'cigars': [_serialize_cigar(c) for c in current]})

    special_sections = []
    for rt_key, rt_label in RELEASE_TYPE_ORDER:
        if rt_key in orphan_special:
            special_sections.append({'label': f'{rt_label} ({len(orphan_special[rt_key])})', 'cigars': [_serialize_cigar(c) for c in orphan_special[rt_key]]})
    if '' in orphan_special:
        special_sections.append({'label': f"其他特别版 ({len(orphan_special[''])})", 'cigars': [_serialize_cigar(c) for c in orphan_special['']]})

    special_total = sum(len(v) for v in orphan_special.values())
    if special_sections:
        sections.append({'label': f'独立特别发行 ({special_total})', 'is_header': True, 'cigars': []})
        sections.extend(special_sections)

    if discontinued:
        sections.append({'label': f'停产款 ({len(discontinued)})', 'cigars': [_serialize_cigar(c) for c in discontinued]})

    if small_cigars:
        sections.append({'label': f'小雪茄 ({len(small_cigars)})', 'cigars': [_serialize_cigar(c) for c in small_cigars]})

    return JsonResponse({
        'brand': {
            'english_name': brand.english_name,
            'name': brand.name or brand.english_name,
            'slug': brand.slug,
            'logo_url': brand.logo.url if brand.logo else None,
            'origin': brand.origin,
            'category': brand.category,
            'is_discontinued': brand.category == 'discontinued',
        },
        'sections': sections,
        'total': all_cigars.count(),
    })


def api_cigar_detail(request, cigar_id):
    """GET /api/cigars/<id>/"""
    import json
    from cigars.packaging import declared_box_sizes
    cigar = Cigar.objects.get(id=cigar_id)
    brand = Brand.objects.filter(english_name=cigar.brand).first()

    packagings = []
    if cigar.packagings:
        try:
            raw = json.loads(cigar.packagings)
            if isinstance(raw, dict):
                descs = [s.strip() for s in raw.get('raw', '').split('.') if s.strip()]
                for desc in descs:
                    packagings.append(translate_packaging(desc))
            elif isinstance(raw, list):
                for item in raw:
                    if isinstance(item, dict):
                        packagings.append(item)
        except json.JSONDecodeError:
            pass

    images = cigar.images.all().order_by('image_type', 'order')
    images_by_type = {}
    for img in images:
        type_label = img.get_image_type_display()
        images_by_type.setdefault(type_label, []).append({
            'url': img.image.url,
            'thumbnail_url': img.thumbnail.url if img.thumbnail else None,
            'image_type': img.image_type,
            'order': img.order,
            'is_primary': img.is_primary,
        })

    related = list(Cigar.objects.filter(brand=cigar.brand).exclude(id=cigar_id).order_by('?')[:8])
    children = list(Cigar.objects.filter(parent=cigar).order_by('release_type', 'english_name'))
    brand_cigar_count = Cigar.objects.filter(brand=cigar.brand, parent__isnull=True).count() if brand else 0

    return JsonResponse({
        'cigar': {
            'id': cigar.id,
            'brand': cigar.brand,
            'english_name': cigar.english_name,
            'name': cigar.name,
            'vitola': cigar.vitola,
            'vitola_cn': cigar.vitola_cn,
            'length': cigar.length,
            'ring_gauge': cigar.ring_gauge,
            'common_name': cigar.common_name,
            'common_name_cn': cigar.common_name_cn,
            'origin': cigar.origin,
            'status': cigar.status,
            'release_type': cigar.release_type,
            'release_type_cn': cigar.release_type_cn,
            'release_name': cigar.release_name,
            'production_method': cigar.production_method,
            'packagings': packagings,
            # Keep numeric accounting constraints separate from display text.
            'box_sizes': declared_box_sizes(cigar.packagings),
        },
        'brand': {
            'english_name': brand.english_name if brand else cigar.brand,
            'name': (brand.name if brand else None) or (brand.english_name if brand else cigar.brand),
            'slug': brand.slug if brand else None,
            'logo_url': brand.logo.url if brand and brand.logo else None,
            'cigar_count': brand_cigar_count,
        } if brand else None,
        'images_by_type': images_by_type,
        'total_images': images.count(),
        'related': [
            {
                'id': c.id,
                'name': c.name or c.english_name,
                'english_name': c.english_name,
                'vitola': c.vitola,
                'release_type_cn': c.release_type_cn,
                'thumb_url': c.primary_image.thumbnail.url if c.primary_image and c.primary_image.thumbnail else None,
            }
            for c in related
        ],
        'children': [
            {
                'id': c.id,
                'name': c.name or c.english_name,
                'english_name': c.english_name,
                'release_type': c.release_type,
                'release_type_cn': c.release_type_cn,
                'thumb_url': c.primary_image.thumbnail.url if c.primary_image and c.primary_image.thumbnail else None,
            }
            for c in children
        ],
    })


@login_required
def api_inventory(request):
    """GET /api/inventory/"""
    if not request.user.is_staff:
        return JsonResponse({'error': 'Forbidden'}, status=403)

    stock_data = {}
    batches = PurchaseBatch.objects.filter(remaining__gt=0).values(
        'cigar_id'
    ).annotate(
        total_stock=Sum('remaining'),
        total_cost=Sum(F('remaining') * F('unit_cost_cny')),
        latest_date=Max('purchased_at'),
    )

    for row in batches:
        stock_data[row['cigar_id']] = {
            'total_stock': row['total_stock'],
            'total_cost': row['total_cost'],
            'avg_cost': (row['total_cost'] / row['total_stock']) if row['total_stock'] else 0,
            'latest_date': row['latest_date'].isoformat() if row['latest_date'] else None,
        }

    cigars = Cigar.objects.filter(id__in=stock_data.keys()).order_by('brand', 'english_name')

    result = []
    for c in cigars:
        sd = stock_data[c.id]
        result.append({
            'id': c.id,
            'brand': c.brand,
            'name': c.name or c.english_name,
            'english_name': c.english_name,
            'release_type_cn': c.release_type_cn,
            'release_type': c.release_type,
            'total_stock': sd['total_stock'],
            'total_cost': decimal_to_number(sd['total_cost']),
            'avg_cost': decimal_to_number(sd['avg_cost']),
            'latest_date': sd['latest_date'],
        })

    brands_with_stock = sorted(set(c['brand'] for c in result))
    total_qty = sum(c['total_stock'] for c in result)
    total_cost_sum = sum(c['total_cost'] for c in result)

    brand_filter = request.GET.get('brand', '')
    search_query = request.GET.get('q', '').strip()

    if brand_filter:
        result = [c for c in result if c['brand'] == brand_filter]
    if search_query:
        result = [
            c for c in result
            if search_query.lower() in c['name'].lower() or search_query.lower() in c['english_name'].lower()
        ]

    return JsonResponse({
        'cigars': result,
        'brands': brands_with_stock,
        'stats': {
            'brand_count': len(brands_with_stock),
            'cigar_count': len(result),
            'total_qty': total_qty,
            'total_cost': total_cost_sum,
        },
    })
