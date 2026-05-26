"""价格跟踪系统 — DRF Serializers"""
from rest_framework import serializers
from .models import PriceSource, PriceSnapshot, PriceAlert
from cigars.models import Brand


class PriceSourceSerializer(serializers.ModelSerializer):
    class Meta:
        model = PriceSource
        fields = [
            'id', 'name', 'slug', 'base_url', 'active',
            'currency', 'exchange_rate', 'last_scraped',
            'scrape_interval_hours',
        ]


class PriceSnapshotSerializer(serializers.ModelSerializer):
    source_name = serializers.CharField(source='source.name', read_only=True)
    source_slug = serializers.CharField(source='source.slug', read_only=True)
    source_currency = serializers.CharField(source='source.currency', read_only=True)
    cigar_name = serializers.CharField(source='cigar.name', read_only=True)
    cigar_english_name = serializers.CharField(source='cigar.english_name', read_only=True)
    cigar_brand = serializers.CharField(source='cigar.brand', read_only=True)
    cigar_brand_cn = serializers.SerializerMethodField()
    cigar_image_url = serializers.SerializerMethodField()

    class Meta:
        model = PriceSnapshot
        fields = [
            'id', 'source', 'source_name', 'source_slug', 'source_currency',
            'cigar', 'cigar_name', 'cigar_english_name', 'cigar_brand', 'cigar_brand_cn', 'cigar_image_url',
            'price', 'currency', 'price_cny',
            'box_size', 'box_price', 'url', 'in_stock',
            'scraped_at',
        ]
        read_only_fields = ['scraped_at']

    def get_cigar_brand_cn(self, obj):
        if obj.cigar and obj.cigar.brand:
            brand = Brand.objects.filter(english_name__iexact=obj.cigar.brand).first()
            if brand:
                return brand.name
        return None

    def get_cigar_image_url(self, obj):
        """获取雪茄第一张图片URL（优先本地，否则远程）"""
        if not obj.cigar:
            return None
        from cigars.models import CigarImage
        img = CigarImage.objects.filter(cigar=obj.cigar).order_by('order').first()
        if img:
            if img.image:
                return img.image.url
            if img.image_url:
                return img.image_url
        return None


class PriceAlertSerializer(serializers.ModelSerializer):
    source_name = serializers.CharField(source='source.name', read_only=True)
    cigar_name = serializers.CharField(source='cigar.name', read_only=True)
    condition_label = serializers.CharField(source='get_condition_display', read_only=True)

    class Meta:
        model = PriceAlert
        fields = [
            'id', 'cigar', 'cigar_name',
            'source', 'source_name',
            'condition', 'condition_label',
            'target_price', 'enabled',
            'last_triggered', 'created_at',
        ]
        read_only_fields = ['last_triggered', 'created_at']


# --- Dashboard / Aggregated Serializers ---

class CigarPriceSummarySerializer(serializers.Serializer):
    """仪表盘单款雪茄价格汇总"""
    cigar_id = serializers.IntegerField()
    cigar_name = serializers.CharField()
    cigar_brand = serializers.CharField()
    sources = serializers.ListField(child=serializers.DictField())


class LatestPriceSerializer(serializers.Serializer):
    """最新价格输出"""
    cigar_id = serializers.IntegerField()
    cigar_name = serializers.CharField()
    cigar_brand = serializers.CharField()
    cigar_brand_cn = serializers.CharField()
    cigar_image_url = serializers.CharField()
    source_id = serializers.IntegerField()
    source_name = serializers.CharField()
    source_slug = serializers.CharField()
    price = serializers.FloatField()
    currency = serializers.CharField()
    price_cny = serializers.FloatField(allow_null=True)
    box_price = serializers.FloatField(allow_null=True)
    in_stock = serializers.BooleanField()
    scraped_at = serializers.DateTimeField()
    # 涨跌 (需传前次价格算)
    change_pct = serializers.FloatField(allow_null=True, default=None)
    change_direction = serializers.CharField(allow_null=True, default=None)  # 'up'/'down'/'flat'
