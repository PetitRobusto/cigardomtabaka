from django.shortcuts import render
from django.db.models import Count, Sum, Max, F, Q
from django.contrib.auth.decorators import login_required

from .models import Brand, Cigar, PurchaseBatch


PACKAGING_TRANSLATIONS = [
    # 盒型
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
    # 包装细节 — 数量型放前面（先匹配具体结构）
    (r'in aluminium tubes', '铝管装'),
    (r'of (\d+) aluminium tubed cigars', r'，\1 支铝管雪茄'),
    (r'aluminium tubed cigars', '铝管雪茄'),
    (r'aluminium tubes', '铝管'),
    (r'in cellophane', '套玻璃纸'),
    (r'in crystal tubes', '水晶管装'),
    (r'of (\d+) cigars', r'，\1 支'),
    (r'of (\d+) aluminium', r'，\1 铝'),
    (r'\s+in\s+(\d+)', r'，内含 \1'),
    # 限量/年份标记
    (r'\((\d[\d,]*)\s*produced\)', r'（限量 \1 件）'),
    (r'\(discontinued\s+(\d{4})\)', r'（\1 年停产）'),
    (r'\(discontinued\s+pre-(\d{4})\)', r'（\1 年前停产）'),
    (r'\(discontinued\s+c?(\d{4})\)', r'（约 \1 年停产）'),
    (r'\(released\s+(?:c\s*)?(\d{4})\)', r'（\1 年发布）'),
    (r'\(discontinued\)', '（已停产）'),
    (r'  +', ' '),
]


def translate_packaging(text: str) -> str:
    """翻译英文包装描述为中文，返回翻译后的字符串"""
    import re
    result = text.strip()
    for pattern, replacement in PACKAGING_TRANSLATIONS:
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
    # 清理多余的空格和标点
    result = result.replace(' .', '。').replace(' ,', '，')
    result = re.sub(r'\s+，', '，', result)
    result = re.sub(r'\s+。', '。', result)
    result = re.sub(r'\s+（', '（', result)
    result = result.strip(' ,.')
    return result





SECTION_ORDER = [
    ('global',        '🌍 全球品牌'),
    ('value',         '💎 价值品牌'),
    ('volume',        '📦 走量品牌'),
    ('other',         '📋 其他品牌'),
    ('ict',           '🏭 ICT 机制'),
    ('special',       '⭐ 特殊品牌'),
    ('discontinued',  '🪦 已停产品牌'),
]

# 品牌详情页 release type 展示顺序
RELEASE_TYPE_ORDER = [
    ('',                '📦 常规款'),
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


def brand_list(request):
    """品牌列表页 — 按分类分组，带 LOGO + 产地 + 停产标记"""
    brands = list(Brand.objects.all().order_by('english_name'))

    # 手动统计每品牌款数（排除子雪茄）
    cigar_counts = {}
    for row in Cigar.objects.filter(parent__isnull=True).values('brand').annotate(n=Count('id')):
        cigar_counts[row['brand']] = row['n']
    for b in brands:
        b.cigar_count = cigar_counts.get(b.english_name, 0)

    # 按分类分组
    brand_by_cat = {}
    for b in brands:
        brand_by_cat.setdefault(b.category, []).append(b)

    sections = []
    for cat_key, cat_label in SECTION_ORDER:
        if cat_key in brand_by_cat:
            sections.append({
                'key': cat_key,
                'label': f'{cat_label} ({len(brand_by_cat[cat_key])})',
                'brands': brand_by_cat[cat_key],
            })

    return render(request, 'cigars/brand_list.html', {
        'sections': sections,
        'total_brands': len(brands),
    })


def brand_detail(request, slug):
    """品牌详情页 — 三区：常规款 | 特别发行 | 停产款 + 机制茄"""
    brand = Brand.objects.get(slug=slug)
    all_cigars = Cigar.objects.filter(brand=brand.english_name)\
        .order_by('english_name')\
        .prefetch_related('images')

    current = []         # 所有 Current（不含机制茄/小雪茄）
    orphan_special = {}  # 无 parent 的 Special Releases（不含机制茄/小雪茄）
    discontinued = []    # Discontinued（不含子款，不含机制茄/小雪茄）
    small_cigars = []    # 小雪茄 (vitola: Mini/Short/Club)

    for c in all_cigars:
        if c.parent_id:
            continue  # 子雪茄 → 不独立展示
        
        # 小雪茄单独分组（放最后）
        if c.vitola in ('Mini', 'Short', 'Club'):
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

    # 为所有父款统计子款数量
    all_parents = current + discontinued + small_cigars
    for v in orphan_special.values():
        all_parents.extend(v)
    for c in all_parents:
        c.children = list(
            Cigar.objects.filter(parent=c).order_by('release_type', 'english_name')
        )

    sections = []

    # 📦 常规款
    if current:
        child_count = sum(1 for c in current if c.children)
        label = f'📦 常规款 ({len(current)})'
        if child_count:
            label += f' · {child_count} 款含子款'
        sections.append({'label': label, 'cigars': current})

    # ⭐ 独立特别发行（无 parent）
    special_sections = []
    for rt_key, rt_label in RELEASE_TYPE_ORDER:
        if rt_key in orphan_special:
            label = f'{rt_label} ({len(orphan_special[rt_key])})'
            special_sections.append({'label': label, 'cigars': orphan_special[rt_key]})

    if '' in orphan_special:
        special_sections.append({
            'label': f'其他特别版 ({len(orphan_special[""])})',
            'cigars': orphan_special[''],
        })

    special_total = sum(len(v) for v in orphan_special.values())
    if special_sections:
        sections.append({
            'label': f'⭐ 独立特别发行 ({special_total})',
            'cigars': [], 'is_header': True,
        })
        sections.extend(special_sections)

    # 🪦 停产款（含子款）
    if discontinued:
        child_count = sum(1 for c in discontinued if c.children)
        label = f'🪦 停产款 ({len(discontinued)})'
        if child_count:
            label += f' · {child_count} 款含子款'
        sections.append({'label': label, 'cigars': discontinued})

    # ⚙️ 小雪茄 (Mini/Short/Club)
    if small_cigars:
        child_count = sum(1 for c in small_cigars if c.children)
        label = f'🪶 小雪茄 ({len(small_cigars)})'
        if child_count:
            label += f' · {child_count} 款含子款'
        sections.append({'label': label, 'cigars': small_cigars})

    return render(request, 'cigars/brand_detail.html', {
        'brand': brand,
        'sections': sections,
        'total': all_cigars.count(),
    })


def cigar_detail(request, cigar_id):
    """雪茄详情页 — 全部信息 + 所有图片"""
    import json

    cigar = Cigar.objects.get(id=cigar_id)
    brand = Brand.objects.filter(english_name=cigar.brand).first()

    # 解析包装信息
    packagings = []
    if cigar.packagings:
        try:
            raw = json.loads(cigar.packagings)
            # packagings 是 dict: {raw, box_sizes, sub_quantity}
            if isinstance(raw, dict):
                descs = [s.strip() for s in raw.get('raw', '').split('.') if s.strip()]
                for desc in descs:
                    packagings.append(translate_packaging(desc))
            elif isinstance(raw, list):
                # 兼容旧格式
                for item in raw:
                    if isinstance(item, dict):
                        packagings.append(item)
        except json.JSONDecodeError:
            pass

    # 图片分组
    images = cigar.images.all().order_by('image_type', 'order')
    images_by_type = {}
    for img in images:
        images_by_type.setdefault(img.get_image_type_display(), []).append(img)

    # 同品牌其他雪茄（推荐）
    related = list(Cigar.objects.filter(
        brand=cigar.brand
    ).exclude(id=cigar_id).order_by('?')[:8])

    # 子款列表（如果是父款）
    children = list(Cigar.objects.filter(
        parent=cigar
    ).order_by('release_type', 'english_name'))

    return render(request, 'cigars/cigar_detail.html', {
        'cigar': cigar,
        'brand': brand,
        'packagings': packagings,
        'images_by_type': images_by_type,
        'total_images': images.count(),
        'related': related,
        'children': children,
    })


@login_required
def inventory(request):
    """库存总览页 — 仅 staff 可访问"""
    if not request.user.is_staff:
        return render(request, '403.html', status=403)

    # 从 PurchaseBatch 聚合库存数据
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
            'avg_cost': round(row['total_cost'] / row['total_stock'], 2),
            'latest_date': row['latest_date'],
        }

    # 获取对应雪茄对象
    cigars = Cigar.objects.filter(id__in=stock_data.keys()).order_by('brand', 'english_name')

    # 组装结果列表
    result = []
    for c in cigars:
        sd = stock_data[c.id]
        c.total_stock = sd['total_stock']
        c.total_cost = sd['total_cost']
        c.avg_cost = sd['avg_cost']
        c.latest_date = sd['latest_date']
        result.append(c)

    # 统计数据
    brands_with_stock = sorted(set(c.brand for c in result))
    total_qty = sum(c.total_stock for c in result)
    total_cost_sum = sum(c.total_cost for c in result)

    # 品牌筛选
    brand_filter = request.GET.get('brand', '')
    search_query = request.GET.get('q', '').strip()

    if brand_filter:
        result = [c for c in result if c.brand == brand_filter]
    if search_query:
        result = [
            c for c in result
            if search_query.lower() in (c.name or c.english_name).lower()
        ]

    return render(request, 'cigars/inventory.html', {
        'cigars': result,
        'brands': brands_with_stock,
        'brand_filter': brand_filter,
        'search_query': search_query,
        'stats': {
            'brand_count': len(brands_with_stock),
            'cigar_count': len(result),
            'total_qty': total_qty,
            'total_cost': total_cost_sum,
        },
    })
