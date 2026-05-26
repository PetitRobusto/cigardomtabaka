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
                box_label = f'{bs}支' if bs else '25支'
                variants[key] = {
                    'source_id': snap.source_id,
                    'source_name': snap.source.name,
                    'source_slug': snap.source.slug,
                    'source_url': snap.source.base_url,
                    'currency': snap.currency,
                    'box_size': bs,
                    'box_label': box_label,
                    'url': snap.url or snap.source.base_url,
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

        return Response({
            'cigar_id': int(cigar_id),
            'cigar_brand': cigar.brand if cigar else None,
            'cigar_brand_cn': brand_cn,
            'cigar_name': (cigar.name or cigar.english_name) if cigar else None,
            'cigar_name_en': cigar.english_name if cigar else None,
            'variants': list(variants.values()),
        })

    @action(detail=False, methods=['get'])
    def aggregated(self, request):
        """聚合视图：每款雪茄的跨源价格+库存汇总，前端仪表盘单次加载"""
        from django.db.models import Max as DMax, Min as DMin
        from cigars.models import Brand, Cigar

        # 获取每个 (cigar, source, box_size) 的最新快照（含缺货记录）
        latest_ids = (
            PriceSnapshot.objects
            .values('cigar_id', 'source_id', 'box_size')
            .annotate(max_id=DMax('id'))
            .values_list('max_id', flat=True)
        )
        snapshots = (
            PriceSnapshot.objects
            .select_related('cigar', 'source')
            .filter(id__in=latest_ids)
            .order_by('cigar__brand', 'cigar__english_name', 'source__name')
        )

        # 品牌过滤
        brand = request.query_params.get('brand')
        if brand:
            snapshots = snapshots.filter(cigar__brand=brand)

        # 按雪茄组织
        cigars_map = {}
        for snap in snapshots:
            cid = snap.cigar_id
            if cid not in cigars_map:
                # 获取中文品牌名
                brand_name = snap.cigar.brand
                brand_obj = Brand.objects.filter(english_name=brand_name).first()
                if not brand_obj:
                    brand_obj = Brand.objects.filter(english_name__startswith=brand_name).first()
                if not brand_obj:
                    brand_obj = Brand.objects.filter(english_name__icontains=brand_name).first()

                cigars_map[cid] = {
                    'cigar_id': cid,
                    'cigar_name': snap.cigar.name or '',
                    'cigar_english_name': snap.cigar.english_name or '',
                    'cigar_brand': brand_name,
                    'cigar_brand_cn': brand_obj.name if brand_obj else brand_name,
                    'sources': [],
                    'any_in_stock': False,
                    'best_price': None,
                    'best_price_source': None,
                }

            entry = cigars_map[cid]
            entry['sources'].append({
                'source_id': snap.source_id,
                'source_name': snap.source.name,
                'source_slug': snap.source.slug,
                'price': snap.price,
                'currency': snap.currency or 'USD',
                'price_cny': snap.price_cny,
                'box_size': snap.box_size,
                'box_price': snap.box_price,
                'in_stock': snap.in_stock,
                'scraped_at': snap.scraped_at.isoformat() if snap.scraped_at else None,
                'url': snap.url or None,
            })

            if snap.in_stock:
                entry['any_in_stock'] = True
                if entry['best_price'] is None or snap.price < entry['best_price']:
                    entry['best_price'] = snap.price
                    entry['best_price_source'] = snap.source.name

        result = list(cigars_map.values())

        # 计算涨跌（对比上一次同源同包装的价格）
        for entry in result:
            for src in entry['sources']:
                cid = entry['cigar_id']
                sid = src['source_id']
                bs = src['box_size']
                # 找上一条不同日期的快照
                prev = PriceSnapshot.objects.filter(
                    cigar_id=cid, source_id=sid, box_size=bs,
                    in_stock=True,
                ).exclude(
                    scraped_at=src.get('scraped_at'),
                ).order_by('-scraped_at').first()
                if prev and prev.price:
                    change = src['price'] - prev.price if src['price'] else 0
                    pct = round((change / prev.price) * 100, 1) if prev.price else None
                    direction = 'up' if change > 0 else ('down' if change < 0 else 'flat')
                    src['change_pct'] = pct
                    src['change_direction'] = direction

        # 支持只回 in_stock 的雪茄
        in_stock_only = request.query_params.get('in_stock_only')
        if in_stock_only:
            result = [e for e in result if e['any_in_stock']]

        search = request.query_params.get('search')
        if search:
            q = search.lower()
            result = [
                e for e in result
                if q in e['cigar_name'].lower()
                or q in (e['cigar_english_name'] or '').lower()
                or q in e['cigar_brand'].lower()
                or q in (e['cigar_brand_cn'] or '').lower()
            ]

        serializer = AggregatedCigarSerializer(result, many=True)
        return Response(serializer.data)


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
                    PriceSnapshot.objects.create(
                        cigar=cigar, source=source, price=price,
                        currency='USD', price_cny=round(price * 7.25, 2),
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
