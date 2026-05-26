"""价格跟踪系统 — DRF Serializers"""
from rest_framework import serializers
from .models import PriceSource, PriceSnapshot, PriceAlert


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
    # Variant-level aggregates (annotated by views, not model fields)
    min_price = serializers.FloatField(read_only=True, allow_null=True, default=None)
    max_price = serializers.FloatField(read_only=True, allow_null=True, default=None)
    record_count = serializers.IntegerField(read_only=True, default=0)

    def get_cigar_brand_cn(self, obj):
        """Look up Chinese brand name from Brand model (fuzzy match)"""
        from cigars.models import Brand
        brand_name = obj.cigar.brand
        # Exact match first
        brand = Brand.objects.filter(english_name=brand_name).first()
        if not brand:
            # Try prefix match (e.g. 'San Cristóbal' → 'San Cristóbal de la Habana')
            brand = Brand.objects.filter(english_name__startswith=brand_name).first()
        if not brand:
            # Try icontains
            brand = Brand.objects.filter(english_name__icontains=brand_name).first()
        return brand.name if brand else brand_name

    class Meta:
        model = PriceSnapshot
        fields = [
            'id', 'source', 'source_name', 'source_slug', 'source_currency',
            'cigar', 'cigar_name', 'cigar_english_name', 'cigar_brand', 'cigar_brand_cn',
            'price', 'currency', 'price_cny',
            'box_size', 'box_price', 'url', 'in_stock',
            'scraped_at',
            'min_price', 'max_price', 'record_count',
        ]
        read_only_fields = ['scraped_at']


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
