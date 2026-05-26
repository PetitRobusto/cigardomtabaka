"""价格跟踪系统 — DRF Views"""
from django.db.models import OuterRef, Subquery, Max
from django.utils import timezone
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from datetime import timedelta
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import PriceSource, PriceSnapshot, PriceAlert
from .serializers import (
    PriceSourceSerializer,
    PriceSnapshotSerializer,
    PriceAlertSerializer,
    LatestPriceSerializer,
    AggregatedCigarSerializer,
)

from django.db.models import Max, OuterRef, Subquery


# --- Template View ---

@login_required
def price_dashboard(request, path=None):
    """价格仪表盘页面（React SPA 挂载）"""
    return render(request, 'price_tracker/dashboard.html')


# --- DRF ViewSets ---


class PriceSourceViewSet(viewsets.ReadOnlyModelViewSet):
    """价格来源 — 只读"""
    queryset = PriceSource.objects.filter(active=True)
    serializer_class = PriceSourceSerializer
    permission_classes = [permissions.IsAuthenticated]


class PriceSnapshotViewSet(viewsets.ReadOnlyModelViewSet):
    """价格快照 — 只读 + 自定义查询"""
    serializer_class = PriceSnapshotSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = PriceSnapshot.objects.select_related('cigar', 'source')
        # 按雪茄过滤
        cigar_id = self.request.query_params.get('cigar_id')
        if cigar_id:
            qs = qs.filter(cigar_id=cigar_id)
        # 按来源过滤
        source_id = self.request.query_params.get('source_id')
        if source_id:
            qs = qs.filter(source_id=source_id)
        # 时间范围（默认30天）
        days = int(self.request.query_params.get('days', 30))
        cutoff = timezone.now() - timedelta(days=days)
        qs = qs.filter(scraped_at__gte=cutoff)
        return qs

    @action(detail=False, methods=['get'])
    def latest(self, request):
        """所有最新价格快照 — 每款雪茄每个来源取最新一条"""
        from django.db.models import Max
        # 每个(cigar, source, box_size)的最新scraped_at
        latest_ids = (
            PriceSnapshot.objects
            .values('cigar_id', 'source_id', 'box_size')
            .annotate(max_id=Max('id'))
            .values_list('max_id', flat=True)
        )
        snapshots = (
            PriceSnapshot.objects
            .select_related('cigar', 'source')
            .filter(id__in=latest_ids)
            .order_by('cigar__brand', 'cigar__english_name', 'source__name', 'box_size')
        )

        # 品牌过滤
        brand = request.query_params.get('brand')
        if brand:
            snapshots = snapshots.filter(cigar__brand=brand)

        # 来源过滤
        source_slug = request.query_params.get('source')
        if source_slug:
            snapshots = snapshots.filter(source__slug=source_slug)

        # Pre-compute variant-level aggregates (min_price, max_price, record_count)
        # for every (cigar_id, source_id, box_size) combination found in today's data
        from django.db.models import Min as DMin, Max as DMax, Count as DCount
        agg_map = {}
        today_variants = snapshots.values('cigar_id', 'source_id', 'box_size').distinct()
        for v in today_variants:
            agg = PriceSnapshot.objects.filter(
                cigar_id=v['cigar_id'],
                source_id=v['source_id'],
                box_size=v['box_size'],
            ).aggregate(
                min_p=DMin('price'),
                max_p=DMax('price'),
                cnt=DCount('id'),
            )
            agg_map[(v['cigar_id'], v['source_id'], v['box_size'])] = agg

        serializer = PriceSnapshotSerializer(snapshots, many=True, context={'request': request})
        data = serializer.data

        # Attach variant-level aggregates to each snapshot
        for item in data:
            key = (item['cigar'], item['source'], item.get('box_size'))
            agg = agg_map.get(key, {})
            item['min_price'] = agg.get('min_p')
            item['max_price'] = agg.get('max_p')
            item['record_count'] = agg.get('cnt', 0)

        return Response(data)

    @action(detail=False, methods=['get'])
    def history(self, request):
        """单款雪茄价格历史 —— 按 (来源, 包装) 分组，未来可接多源"""
        cigar_id = request.query_params.get('cigar_id')
        if not cigar_id:
            return Response(
                {'error': 'cigar_id required'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        days = int(request.query_params.get('days', 30))
        cutoff = timezone.now() - timedelta(days=days)

        snapshots = (
            PriceSnapshot.objects
            .select_related('source', 'cigar')
            .filter(cigar_id=cigar_id, scraped_at__gte=cutoff)
            .order_by('source__name', 'box_size', 'scraped_at')
        )

        cigar = snapshots[0].cigar if snapshots.exists() else None

        # Resolve Chinese brand name
        brand_cn = None
        if cigar:
            from cigars.models import Brand
            brand_obj = Brand.objects.filter(english_name=cigar.brand).first()
            if not brand_obj:
                brand_obj = Brand.objects.filter(english_name__startswith=cigar.brand).first()
            if not brand_obj:
                brand_obj = Brand.objects.filter(english_name__icontains=cigar.brand).first()
            brand_cn = brand_obj.name if brand_obj else cigar.brand

        # 按 (来源, 包装) 分组 —— 每个 variant 独立追踪
        variants = {}
        for snap in snapshots:
            bs = snap.box_size
            key = f'{snap.source.slug}__{bs}'
            if key not in variants:
                short_nm = snap.source.short_name or snap.source.name
                box_label = f'{bs}支' if bs else '25支'
                variants[key] = {
                    'source_id': snap.source_id,
                    'source_name': snap.source.name,
                    'source_short_name': short_nm,
                    'source_slug': snap.source.slug,
                    'source_url': snap.source.base_url,
                    'currency': snap.currency,
                    'box_size': bs,
                    'box_label': box_label,
                    'url': snap.url or snap.source.base_url,
                    'scraped_name': (snap.raw_data or {}).get('title_original', '') or '',
                    'points': [],
                }
            variants[key]['points'].append({
                'date': snap.scraped_at.isoformat(),
                'price': snap.price,
                'price_cny': snap.price_cny,
                'in_stock': snap.in_stock,
            })

        # Compute aggregates per variant
        for v in variants.values():
            prices = [p['price'] for p in v['points'] if p['price'] is not None]
            v['current_price'] = prices[-1] if prices else None
            v['min_price'] = min(prices) if prices else None
            v['max_price'] = max(prices) if prices else None
            v['record_count'] = len(v['points'])
            # 最新一条的衍生字段
            latest_point = v['points'][-1] if v['points'] else None
            if latest_point:
                v['current_price_cny'] = latest_point.get('price_cny')
                v['in_stock'] = latest_point.get('in_stock', True)
                v['scraped_at'] = latest_point.get('date')
                # 每支单价 = 整盒人民币价 / 支数
                if v['current_price_cny'] and v['box_size']:
                    v['price_per_stick'] = round(v['current_price_cny'] / v['box_size'], 2)
                else:
                    v['price_per_stick'] = None

        return Response({
            'cigar_id': int(cigar_id),
            'cigar_brand': cigar.brand if cigar else None,
            'cigar_brand_cn': brand_cn,
            'cigar_name': (cigar.name or cigar.english_name) if cigar else None,
            'cigar_name_en': cigar.english_name if cigar else None,
            'variants': list(variants.values()),
        })

    @action(detail=False, methods=['get'], url_path='list')
    def list_aggregated(self, request):
        """Dashboard列表页聚合数据 — 每款雪茄一条，带均价/主图/来源"""
        from django.db.models import Max as DMax
        from cigars.models import Brand
        from .models import ExchangeRate

        # 1. 取每个(cigar, source, box_size)的最新快照
        latest_ids = (
            PriceSnapshot.objects
            .values('cigar_id', 'source_id', 'box_size')
            .annotate(max_id=DMax('id'))
            .values_list('max_id', flat=True)
        )
        snapshots = (
            PriceSnapshot.objects
            .select_related('cigar', 'source')
            .prefetch_related('cigar__images')
            .filter(id__in=latest_ids)
            .order_by('cigar__brand', 'cigar__english_name', 'source__name')
        )

        # 品牌过滤
        brand = request.query_params.get('brand')
        if brand:
            snapshots = snapshots.filter(cigar__brand=brand)

        def _cny_convert(price: float, currency: str) -> float | None:
            """优先用DB汇率，fallback到保守估值"""
            result = ExchangeRate.cny_convert(price, currency)
            if result is not None:
                return result
            # 最后兜底：保守估算
            fallback = {'USD': 7.0, 'CHF': 8.0, 'EUR': 7.8}
            rate = fallback.get(currency.upper(), 7.0)
            return round(price * rate, 2)

        # 2. 按雪茄聚合
        cigars_map = {}
        for snap in snapshots:
            cid = snap.cigar_id
            if cid not in cigars_map:
                brand_name = snap.cigar.brand
                brand_obj = Brand.objects.filter(english_name=brand_name).first()
                if not brand_obj:
                    brand_obj = Brand.objects.filter(english_name__startswith=brand_name).first()
                if not brand_obj:
                    brand_obj = Brand.objects.filter(english_name__icontains=brand_name).first()
                brand_cn = brand_obj.name if brand_obj else brand_name

                img_url = ''
                img = snap.cigar.primary_image
                if img and img.image:
                    try:
                        img_url = img.image.url
                    except Exception:
                        pass

                cigars_map[cid] = {
                    'cigar_id': cid,
                    'cigar_name': snap.cigar.name or snap.cigar.english_name or '',
                    'cigar_name_en': snap.cigar.english_name or '',
                    'cigar_brand': brand_name,
                    'cigar_brand_cn': brand_cn,
                    'cigar_image_url': img_url,
                    'sources': [],
                    'in_stock': False,
                    'avg_per_stick_cny': None,
                }

            entry = cigars_map[cid]
            currency = (snap.currency or snap.source.currency or 'USD').strip()

            # CNY 换算：已存的 price_cny > DB 汇率 > 保守估算
            if snap.price_cny is not None:
                price_cny = snap.price_cny
            elif snap.price:
                price_cny = _cny_convert(snap.price, currency)
            else:
                price_cny = None

            entry['sources'].append({
                'source_id': snap.source_id,
                'source_name': snap.source.name,
                'source_short_name': snap.source.short_name or snap.source.name,
                'source_slug': snap.source.slug,
                'price': snap.price,
                'price_cny': price_cny,
                'currency': currency,
                'box_size': snap.box_size,
                'in_stock': snap.in_stock,
                'url': snap.url or snap.source.base_url,
            })

            if snap.in_stock:
                entry['in_stock'] = True

        # 3. 计算平均单支价 + 排序
        result = list(cigars_map.values())
        for entry in result:
            per_stick = []
            for s in entry['sources']:
                if s['price_cny'] and s['box_size'] and s['box_size'] > 0:
                    per_stick.append(s['price_cny'] / s['box_size'])
            if per_stick:
                entry['avg_per_stick_cny'] = round(sum(per_stick) / len(per_stick), 0)

        BRANDS_ORDER = [
            '高希霸', '蒙特', '罗密欧与朱丽叶', '帕特加斯',
            '好友', '乌普曼',
        ]
        result.sort(key=lambda x: (
            BRANDS_ORDER.index(x['cigar_brand_cn']) if x['cigar_brand_cn'] in BRANDS_ORDER else 999,
            x['cigar_brand_cn'] or '',
            x['cigar_name'] or '',
        ))

        return Response(result)


class PriceAlertViewSet(viewsets.ModelViewSet):
    """价格预警 — 完整 CRUD"""
    serializer_class = PriceAlertSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return PriceAlert.objects.select_related('cigar', 'source').order_by('cigar__brand')


# --- COH Bulk Import ---

import json, re
from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import api_view, permission_classes
from cigars.models import Cigar
from price_tracker.scraper import match_cigar_by_name

COH_SLUG_BRAND_MAP = {
    'belinda': 'Belinda', 'bolivar': 'Bolívar', 'cohiba': 'Cohiba',
    'combinaciones': 'Combinaciones', 'cuaba': 'Cuaba',
    'diplomaticos': 'Diplomáticos', 'el-rey-del-mundo': 'El Rey del Mundo',
    'fonseca': 'Fonseca', 'guantanamera': 'Guantanamera',
    'h.upmann': 'H. Upmann', 'hoyo-de-monterrey': 'Hoyo de Monterrey',
    'jose-l.-piedra': 'José L. Piedra', 'juan-lopez': 'Juan López',
    'la-flor-de-cano': 'La Flor de Cano', 'la-gloria-cubana': 'La Gloria Cubana',
    'montecristo': 'Montecristo', 'partagas': 'Partagás',
    'por-larranaga': 'Por Larrañaga', 'punch': 'Punch',
    'quai-dorsay': "Quai d'Orsay", 'quintero-y-hermano': 'Quintero',
    'rafael-gonzalez': 'Rafael González', 'ramon-allones': 'Ramón Allones',
    'romeo-y-julieta': 'Romeo y Julieta', 'saint-luis-rey': 'Saint Luis Rey',
    'san-cristobal-de-la-habana': 'San Cristóbal', 'sancho-panza': 'Sancho Panza',
    'trinidad': 'Trinidad', 'troya': 'Troya',
    'vegas-robaina': 'Vegas Robaina', 'vegueros': 'Vegueros', 'vintage': 'Vintage',
}


def _clean_name(name):
    name = name.strip()
    name = re.sub(r'\s*[-–]\s*\d{4}\s*$', '', name)
    name = re.sub(r'^\d+\s*Packs?-\s*', '', name)
    return name.strip()


@csrf_exempt
@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])  # Restored
def import_coh_bulk(request):
    """接收浏览器直接 POST 的 COH 全站数据"""
    data = request.data
    source = PriceSource.objects.get(slug='coh')
    now = timezone.now()

    stats = {'total': 0, 'matched': 0, 'created': 0, 'skipped': 0, 'unmatched': []}

    for slug, products in data.items():
        brand = COH_SLUG_BRAND_MAP.get(slug, slug)
        for prod in products:
            stats['total'] += 1
            name = _clean_name(prod.get('name', ''))
            price = prod.get('price')
            if not price:
                stats['skipped'] += 1
                continue

            cigar = match_cigar_by_name(name, brand_hint=brand)
            if not cigar:
                name2 = re.sub(r'\s*(Travel Humidor|Gift Box|Humidor|Limited Edition|Year of the \w+|Anejados)\s*', '', name, flags=re.I).strip()
                if name2 != name:
                    cigar = match_cigar_by_name(name2, brand_hint=brand)

            if cigar:
                stats['matched'] += 1
                # Parse box info: "25 Box" → box_size=25, "3x2 Box" → box_size=6
                box_info = prod.get('box_info', '')
                box_size = None
                if box_info:
                    m = re.match(r'(\d+)(?:x(\d+))?\s*(?:Box|Pack|Bundle|Single)', box_info)
                    if m:
                        a, b = int(m.group(1)), m.group(2)
                        box_size = a * int(b) if b else a

                # Dedup by cigar + source + box_size + date (allow multiple packagings)
                existing = PriceSnapshot.objects.filter(
                    cigar=cigar, source=source, box_size=box_size,
                    scraped_date=now.date()
                ).first()
                if not existing:
                    from price_tracker.models import ExchangeRate
                    usd_rate = ExchangeRate.get_rate('USD') or 7.0
                    PriceSnapshot.objects.create(
                        cigar=cigar, source=source, price=price,
                        currency='USD', price_cny=round(price * usd_rate, 2),
                        box_size=box_size, box_price=price,
                        in_stock=True, scraped_at=now,
                        raw_data={'coh_name': prod.get('name',''), 'box_info': box_info},
                    )
                    stats['created'] += 1
            else:
                stats['unmatched'].append(f'{brand}: {name}')

    return Response({
        'ok': True,
        'total': stats['total'],
        'matched': stats['matched'],
        'created': stats['created'],
        'skipped': stats['skipped'],
        'unmatched_count': len(stats['unmatched']),
        'unmatched': stats['unmatched'][:20],
    })
