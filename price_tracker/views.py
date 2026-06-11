"""价格跟踪系统 — DRF Views"""
from django.db.models import OuterRef, Subquery, Max
from django.utils import timezone
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
from .pricing import per_stick, avg_per_stick, convert_to_cny
from .helpers import resolve_brand_cn, get_cigar_image_url

from django.db.models import Max, OuterRef, Subquery


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
        # 默认过滤异常价格（可通过 ?show_anomalous=1 查看全部）
        if self.request.query_params.get('show_anomalous') != '1':
            qs = qs.filter(is_anomalous=False)
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
                    'scraped_name': (snap.raw_data or {}).get('title_original') or (snap.raw_data or {}).get('product', '') or '',
                    'delisted': (snap.raw_data or {}).get('delisted', False),
                    'points': [],
                }
            variants[key]['points'].append({
                'date': snap.scraped_at.isoformat(),
                'price': snap.price,
                'original_price': snap.original_price,
                'price_cny': snap.price_cny,
                'in_stock': snap.in_stock,
                'delisted': (snap.raw_data or {}).get('delisted', False),
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
                v['delisted'] = latest_point.get('delisted', False)
                v['scraped_at'] = latest_point.get('date')
                # 每支单价 = 整盒人民币价 / 支数（使用共享定价模块）
                v['price_per_stick'] = per_stick(v['current_price_cny'], v['box_size'])

        release_type_cn = cigar.release_type_cn if cigar else None

        return Response({
            'cigar_id': int(cigar_id),
            'cigar_brand': cigar.brand if cigar else None,
            'cigar_brand_cn': brand_cn,
            'cigar_name': (cigar.name or cigar.english_name) if cigar else None,
            'cigar_name_en': cigar.english_name if cigar else None,
            'release_type_cn': release_type_cn,
            'variants': list(variants.values()),
        })

    @action(detail=False, methods=['get'])
    def changes(self, request):
        """返回最近48小时内的价格变动和补货事件"""
        from datetime import timedelta

        cutoff = timezone.now() - timedelta(hours=48)

        snapshots = (
            PriceSnapshot.objects
            .select_related('cigar', 'source')
            .prefetch_related('cigar__images')
            .filter(scraped_at__gte=cutoff, is_anomalous=False)
            .order_by('cigar_id', 'source_id', 'box_size', '-scraped_at')
        )

        # Group into scrape cycles: snapshots within 5s of each other are same-cycle
        # (COH/EGM scrapers produce multiple entries per scrape — box vs stick pricing)
        groups = {}
        for snap in snapshots:
            key = (snap.cigar_id, snap.source_id, snap.box_size)
            if key not in groups:
                groups[key] = []
            # Skip if this snapshot belongs to a scrape cycle already represented
            is_same_cycle = False
            for existing in groups[key]:
                if abs((snap.scraped_at - existing.scraped_at).total_seconds()) < 5:
                    is_same_cycle = True
                    break
            if not is_same_cycle:
                groups[key].append(snap)
            # Keep latest 2 cycles only (ordered by -scraped_at)
            if len(groups[key]) > 2:
                groups[key] = groups[key][:2]

        price_changes = []
        restocks = []

        for key, snaps in groups.items():
            if len(snaps) < 2:
                continue
            latest, prev = snaps[0], snaps[1]

            # Safety: both prices must be positive, and old price must be meaningful
            price_ok = (latest.price is not None and prev.price is not None
                        and latest.price > 0 and prev.price > 0
                        and latest.price != prev.price
                        and prev.price >= 0.1)  # avoid division-by-near-zero inflation
            if price_ok:
                change_pct = round((latest.price - prev.price) / prev.price * 100, 1)
                # Clamp extreme values: beyond ±99.9% is almost certainly a data error
                if abs(change_pct) > 99.9:
                    change_pct = max(-99.9, min(change_pct, 999.9))
                direction = 'up' if latest.price > prev.price else 'down'

                brand_cn = resolve_brand_cn(latest.cigar.brand)
                img_url = get_cigar_image_url(latest.cigar)

                price_changes.append({
                    'cigar_id': latest.cigar_id,
                    'cigar_name': latest.cigar.name or latest.cigar.english_name or '',
                    'cigar_brand': latest.cigar.brand,
                    'cigar_brand_cn': brand_cn,
                    'cigar_image_url': img_url,
                    'source_name': latest.source.name,
                    'source_short_name': latest.source.short_name or latest.source.name,
                    'source_slug': latest.source.slug,
                    'box_size': latest.box_size,
                    'old_price': prev.price,
                    'new_price': latest.price,
                    'old_price_cny': prev.price_cny,
                    'new_price_cny': latest.price_cny,
                    'currency': latest.currency or latest.source.currency,
                    'change_pct': change_pct,
                    'change_direction': direction,
                    'changed_at': latest.scraped_at.isoformat(),
                })

            if not prev.in_stock and latest.in_stock:
                brand_cn = resolve_brand_cn(latest.cigar.brand)
                img_url = get_cigar_image_url(latest.cigar)

                restocks.append({
                    'cigar_id': latest.cigar_id,
                    'cigar_name': latest.cigar.name or latest.cigar.english_name or '',
                    'cigar_brand': latest.cigar.brand,
                    'cigar_brand_cn': brand_cn,
                    'cigar_image_url': img_url,
                    'source_name': latest.source.name,
                    'source_short_name': latest.source.short_name or latest.source.name,
                    'source_slug': latest.source.slug,
                    'box_size': latest.box_size,
                    'price': latest.price,
                    'price_cny': latest.price_cny,
                    'currency': latest.currency or latest.source.currency,
                    'restocked_at': latest.scraped_at.isoformat(),
                })

        price_changes.sort(key=lambda x: x['changed_at'], reverse=True)
        restocks.sort(key=lambda x: x['restocked_at'], reverse=True)

        return Response({
            'price_changes': price_changes[:20],
            'restocks': restocks[:20],
        })

    @action(detail=False, methods=['get'], url_path='list')
    def list_aggregated(self, request):
        """Dashboard列表页聚合数据 — 每款雪茄一条，带均价/主图/来源"""
        from django.db.models import Max as DMax

        # 1. 取每个(cigar, source, box_size)的最新快照（排除异常+售罄）
        latest_ids = (
            PriceSnapshot.objects
            .filter(is_anomalous=False, in_stock=True)
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

        # 2. 按雪茄聚合
        cigars_map = {}
        for snap in snapshots:
            cid = snap.cigar_id
            if cid not in cigars_map:
                brand_name = snap.cigar.brand
                brand_cn = resolve_brand_cn(brand_name)
                img_url = get_cigar_image_url(snap.cigar)

                rt = snap.cigar.release_type_cn or ''
                cigars_map[cid] = {
                    'cigar_id': cid,
                    'cigar_name': snap.cigar.name or snap.cigar.english_name or '',
                    'cigar_name_en': snap.cigar.english_name or '',
                    'cigar_brand': brand_name,
                    'cigar_brand_cn': brand_cn,
                    'cigar_image_url': img_url,
                    'release_type_cn': rt,
                    'production_method': snap.cigar.production_method or '',
                    'sources': [],
                    'in_stock': False,
                    'avg_per_stick_cny': None,
                }

            entry = cigars_map[cid]
            currency = (snap.currency or snap.source.currency or 'USD').strip()

            # CNY 换算：已存的 price_cny > 共享汇率换算
            if snap.price_cny is not None:
                price_cny = snap.price_cny
            elif snap.price:
                price_cny = convert_to_cny(snap.price, currency)
            else:
                price_cny = None

            entry['sources'].append({
                'source_id': snap.source_id,
                'source_name': snap.source.name,
                'source_short_name': snap.source.short_name or snap.source.name,
                'source_slug': snap.source.slug,
                'price': snap.price,
                'original_price': snap.original_price,
                'price_cny': price_cny,
                'currency': currency,
                'box_size': snap.box_size,
                'in_stock': snap.in_stock,
                'url': snap.url or snap.source.base_url,
            })

            if snap.in_stock:
                entry['in_stock'] = True

        # 3. 计算平均单支价（与详情页算法一致：
        #   取 round(price_cny/box_size, 2) 的算术平均，保留两位小数）
        # 排序规则：品牌 → 常规款 > 非常规款（机制小雪茄/特别款）
        BRANDS_ORDER = [
            '高希霸', '蒙特', '罗密欧与朱丽叶', '帕特加斯',
            '好友', '乌普曼',
        ]
        result = list(cigars_map.values())
        for entry in result:
            entry['avg_per_stick_cny'] = avg_per_stick(entry['sources'])
        def _sort_key(entry):
            brand_order = BRANDS_ORDER.index(entry['cigar_brand_cn']) if entry['cigar_brand_cn'] in BRANDS_ORDER else 999
            # 非常规款判断：机制雪茄 或 有特别款类型
            prod_method = (entry.get('production_method') or '').lower()
            is_machine_made = 'machine' in prod_method
            has_special = bool(entry.get('release_type_cn'))
            is_non_regular = is_machine_made or has_special
            category = 1 if is_non_regular else 0
            return (brand_order, entry['cigar_brand_cn'] or '', category, entry['cigar_name'] or '')

        result.sort(key=_sort_key)

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
                    PriceSnapshot.objects.create(
                        cigar=cigar, source=source, price=price,
                        currency='USD', price_cny=convert_to_cny(price, 'USD'),
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
