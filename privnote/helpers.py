"""privnote 通用工具函数 — 零业务逻辑，纯数据转换"""
import json
import re
from decimal import Decimal

from cigars.models import Brand, Cigar, PurchaseBatch


# ── 缩略图 URL ──

def get_thumb_url(cigar):
    """获取雪茄缩略图 URL"""
    primary = cigar.primary_image
    if primary and primary.thumbnail:
        return primary.thumbnail.url
    return ''


# ── 有库存雪茄 ID 集合 ──

def get_in_stock_cigar_ids():
    """返回所有有库存（remaining > 0）的雪茄 ID 集合"""
    return set(
        PurchaseBatch.objects.filter(remaining__gt=0)
        .values_list('cigar_id', flat=True)
        .distinct()
    )


# ── 品牌信息批量映射 ──

def get_brand_info_map(en_names=None):
    """
    批量获取品牌信息映射。
    :param en_names: 若提供，只查询这些品牌英文名；否则查询全部
    :return: dict[en_name, {'name': str, 'logo_url': str|None}]
    """
    qs = Brand.objects.all()
    if en_names is not None:
        qs = qs.filter(english_name__in=en_names)

    return {
        b.english_name: {
            'name': b.name or b.english_name,
            'logo_url': b.logo.url if b.logo else None,
        }
        for b in qs
    }


# ── 安全 JSON 解析 ──

def safe_json_loads(raw, default=None):
    """安全解析 JSON 字符串，失败时返回 default"""
    if not raw:
        return default
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return default


def decimal_to_number(value):
    """将 Decimal 转为前端友好的 int/float。"""
    if value is None:
        return None
    if not isinstance(value, Decimal):
        return value
    if value == value.to_integral_value():
        return int(value)
    return float(value)


# ── 搜索词拆分 ──

def split_search_terms(q):
    """按 CJK/非 CJK 边界拆分查询词，支持 '帕特D4' → ['帕特', 'D4']"""
    terms = re.findall(r'[\u4e00-\u9fff]+|[^\u4e00-\u9fff\s]+', q)
    return [t.lower() for t in terms if len(t) >= 1]


# ── PaymentMethod 序列化 ──

def serialize_payment_method(pm, *, include_fund_account=False):
    """将 PaymentMethod 序列化；资金账户 ID 仅供 staff 配置接口使用。"""
    data = {
        'id': pm.id,
        'method_type': pm.method_type,
        'label': pm.label,
        'bank_name': pm.bank_name,
        'card_number': pm.card_number,
        'card_holder': pm.card_holder,
        'qr_url': pm.qr_image.url if pm.qr_image else None,
        'remark': pm.remark,
    }
    if include_fund_account:
        data['fund_account_id'] = pm.fund_account_id
    return data


# ── 雪茄最小序列化 ──

def serialize_cigar_minimal(cigar, include_batches=False, stock_only=False):
    """
    将雪茄序列化为最小化字典，用于搜索结果和报价列表。
    :param include_batches: 是否包含批次详情（仅搜索用）
    :param stock_only: 若为 True 且 include_batches=True，则过滤有库存批次
    """
    from django.db import models

    result = {
        'id': cigar.id,
        'name': cigar.name or cigar.english_name,
        'english_name': cigar.english_name,
        'brand': cigar.brand,
        'vitola': cigar.vitola or '',
        'length': cigar.length,
        'ring_gauge': cigar.ring_gauge,
        'thumb_url': get_thumb_url(cigar),
    }

    if include_batches:
        batches = []
        total_stock = 0
        qs = cigar.purchasebatch_set.filter(remaining__gt=0)
        if stock_only:
            for b in qs.select_related('purchase_order_item'):
                box_size = b.box_size or (
                    b.purchase_order_item.box_size if b.purchase_order_item_id else None
                ) or 25
                batches.append({
                    'batch_id': b.id,
                    'box_size': box_size,
                    'remaining': b.remaining,
                    'unit_cost_cny': decimal_to_number(b.unit_cost_cny),
                })
                total_stock += b.remaining
        else:
            total_stock = qs.aggregate(total=models.Sum('remaining'))['total'] or 0

        result['batches'] = batches
        result['stock_qty'] = total_stock

    return result
