"""共享 helper — 品牌中文名解析、图片 URL 提取

在 views.py changes / list_aggregated 动作中重复出现，提取到此模块。
"""

from cigars.models import Brand


def resolve_brand_cn(english_name: str) -> str:
    """根据品牌英文名解析中文名（三层 fallback）

    Args:
        english_name: 品牌英文名（如 'Cohiba', 'Partagás'）

    Returns:
        中文品牌名，或退回英文名
    """
    brand_obj = Brand.objects.filter(english_name=english_name).first()
    if not brand_obj:
        brand_obj = Brand.objects.filter(english_name__startswith=english_name).first()
    if not brand_obj:
        brand_obj = Brand.objects.filter(english_name__icontains=english_name).first()
    return brand_obj.name if brand_obj else english_name


def get_cigar_image_url(cigar) -> str:
    """提取雪茄的首张图片 URL（安全访问 primary_image）

    Args:
        cigar: Cigar 模型实例（需要有 primary_image 属性）

    Returns:
        图片 URL 字符串或空字符串
    """
    img = cigar.primary_image
    if img and img.image:
        try:
            return img.image.url
        except Exception:
            pass
    return ''
