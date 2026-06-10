"""Inventory 业务逻辑 — 从 PurchaseBatch 构建盒装库存结构化数据"""
from collections import OrderedDict

from cigars.models import PurchaseBatch
from privnote.helpers import get_thumb_url, get_brand_info_map


def build_inventory_data():
    """从 PurchaseBatch 构建盒装库存结构化数据"""
    batches = list(
        PurchaseBatch.objects
        .filter(remaining__gt=0)
        .select_related('cigar', 'purchase_order_item')
        .order_by('cigar__brand', 'cigar__english_name')
    )

    if not batches:
        return {
            'mode': 'inventory',
            'brand_groups': [],
            'total_items': 0,
            'total_boxes': 0,
            'total_loose': 0,
            'empty': True,
        }

    keyed = OrderedDict()
    for b in batches:
        box_size = b.purchase_order_item.box_size or 25
        key = (b.cigar.brand, b.cigar.english_name, box_size)
        if key not in keyed:
            keyed[key] = {'cigar': b.cigar, 'box_size': box_size, 'remaining': 0, 'cost': 0}
        keyed[key]['remaining'] += b.remaining
        keyed[key]['cost'] = round(
            (keyed[key]['cost'] * (keyed[key]['remaining'] - b.remaining) + b.unit_cost_cny * b.remaining)
            / keyed[key]['remaining'], 2
        ) if keyed[key]['remaining'] > 0 else b.unit_cost_cny

    brand_groups = OrderedDict()
    for (brand, ename, bs), entry in keyed.items():
        if brand not in brand_groups:
            brand_groups[brand] = []
        r = entry['remaining']
        full_boxes = r // bs
        loose = r % bs
        cigar = entry['cigar']
        brand_groups[brand].append({
            'name': cigar.name or cigar.english_name,
            'english_name': cigar.english_name,
            'vitola': cigar.vitola or '—',
            'box_size': bs,
            'full_boxes': full_boxes,
            'loose': loose,
            'total_sticks': r,
            # 价格留空，由前端或调用方决定
            'box_price': None,
            'stick_price': None,
            'thumb_url': get_thumb_url(cigar),
        })

    # 批量获取品牌信息
    brand_info = get_brand_info_map()

    groups = []
    for brand, items in brand_groups.items():
        info = brand_info.get(brand, {'name': brand, 'logo_url': None})
        groups.append({
            'brand': brand,
            'name': info['name'],
            'logo_url': info['logo_url'],
            'items': items,
        })

    total_boxes = sum(item['full_boxes'] for g in groups for item in g['items'])
    total_loose = sum(item['loose'] for g in groups for item in g['items'])
    total_items = sum(len(g['items']) for g in groups)

    return {
        'mode': 'inventory',
        'brand_groups': groups,
        'total_items': total_items,
        'total_boxes': total_boxes,
        'total_loose': total_loose,
        'empty': False,
    }
