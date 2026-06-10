"""Quote 业务逻辑 — 从 CigarPrice 构建报价单结构化数据"""
from django.db import models

from cigars.models import CigarPrice, PurchaseBatch
from privnote.helpers import get_thumb_url, get_brand_info_map


def build_quote_data(quote_mode='full', selected_ids=None, shipping_included=False,
                      customer_name=None, custom_prices=None, shipping_fee_per_stick=None):
    """从 CigarPrice 构建报价单结构化数据"""
    in_stock_cigar_ids = set(
        PurchaseBatch.objects.filter(remaining__gt=0)
        .values_list('cigar_id', flat=True)
        .distinct()
    )

    qs = CigarPrice.objects.filter(is_active=True).select_related('cigar')

    if quote_mode == 'custom' and selected_ids:
        qs = qs.filter(cigar_id__in=selected_ids)
    else:
        qs = qs.filter(
            models.Q(can_preorder=True) | models.Q(cigar_id__in=in_stock_cigar_ids)
        )

    brand_groups = {}
    total_items = 0
    custom_prices = custom_prices or {}
    shipping_fee_per_stick = shipping_fee_per_stick or (20 if shipping_included else 0)

    for cp in qs:
        cigar = cp.cigar
        brand = cigar.brand
        total_items += 1

        # 使用预计算的库存 ID 集合，避免 N+1 查询
        in_stock = cigar.id in in_stock_cigar_ids

        # 应用自定义价格覆盖
        wholesale_price = cp.wholesale_price
        per_stick_price = cp.per_stick_price
        price_key = f"{cigar.id}:{cp.box_size}"
        if price_key in custom_prices:
            try:
                custom_price = int(custom_prices[price_key])
                if custom_price > 0:
                    wholesale_price = custom_price
                    per_stick_price = round(custom_price / cp.box_size) if cp.box_size else cp.per_stick_price
            except (ValueError, TypeError):
                pass

        # 应用运费（含运费模式下，每支加运费，整盒再加整盒运费）
        if shipping_included and shipping_fee_per_stick > 0:
            box_size = cp.box_size or 1
            wholesale_price = round(wholesale_price + shipping_fee_per_stick * box_size)
            per_stick_price = round(per_stick_price + shipping_fee_per_stick)

        item = {
            'cigar_id': cigar.id,
            'brand': brand,
            'brand_cn': '',
            'name': cigar.name or cigar.english_name,
            'english_name': cigar.english_name,
            'vitola': cigar.vitola or '—',
            'box_size': cp.box_size,
            'wholesale_price': wholesale_price,
            'per_stick_price': per_stick_price,
            'thumb_url': get_thumb_url(cigar),
            'in_stock': in_stock,
            'can_preorder': cp.can_preorder,
        }

        if brand not in brand_groups:
            brand_groups[brand] = {
                'brand': brand,
                'brand_cn': '',
                'logo_url': None,
                'items': [],
            }
        brand_groups[brand]['items'].append(item)

    # 批量获取品牌中文名和 logo
    brand_en_names = list(brand_groups.keys())
    brand_info = get_brand_info_map(en_names=brand_en_names)
    for en_name, info in brand_info.items():
        if en_name in brand_groups:
            brand_groups[en_name]['brand_cn'] = info['name']
            brand_groups[en_name]['logo_url'] = info['logo_url']

    groups = []
    for brand in sorted(brand_groups.keys()):
        g = brand_groups[brand]
        groups.append({
            'brand': g['brand'],
            'brand_cn': g['brand_cn'] or g['brand'],
            'logo_url': g['logo_url'],
            'items': g['items'],
        })

    return {
        'mode': 'quote',
        'brand_groups': groups,
        'total_items': total_items,
        'shipping_included': shipping_included,
        'shipping_fee_per_stick': shipping_fee_per_stick,
        'customer_name': customer_name,
    }
