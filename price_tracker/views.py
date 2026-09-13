"""价格跟踪系统 — DRF Views"""
from django.db.models import OuterRef, Subquery, Max, Q, Case, When, F
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
from .presentation import product_name, anomaly_info
from math import isfinite


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
        """单款雪茄历史：按来源、盒规、商品链接分组；当前报价独立于时间窗口"""
        cigar_id = request.query_params.get('cigar_id')
        if not cigar_id:
            return Response(
                {'error': 'cigar_id required'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            cigar_id = int(cigar_id)
            raw_days = request.query_params.get('days', '30')
            days = None if raw_days == 'all' else int(raw_days)
            if cigar_id <= 0 or (days is not None and not 1 <= days <= 36500):
                raise ValueError
        except (ValueError, TypeError):
            return Response({'error': 'cigar_id must be positive; days must be 1–36500 or all'}, status=400)
        cutoff = timezone.now() - timedelta(days=days) if days is not None else None

        # Current quotes are independent of the history window. URL identifies an offer.
        snapshots = list(PriceSnapshot.objects.select_related('source', 'cigar')
                         .filter(cigar_id=cigar_id)
                         .order_by('source__name', 'box_size', 'scraped_at', 'id'))
        from cigars.models import Cigar
        cigar = snapshots[0].cigar if snapshots else Cigar.objects.filter(pk=cigar_id).first()
        brand_cn = resolve_brand_cn(cigar.brand) if cigar else None
        variants = {}
        for snap in snapshots:
            bs = snap.box_size
            key = (snap.source_id, bs, snap.url)
            if key not in variants:
                variants[key] = {
                    'source_id': snap.source_id,
                    'source_name': snap.source.name,
                    'source_short_name': snap.source.short_name or snap.source.name,
                    'source_slug': snap.source.slug,
                    'source_url': snap.source.base_url,
                    'source_currency': snap.source.currency,
                    'source_exchange_rate': snap.source.exchange_rate,
                    'box_size': bs,
                    'box_label': f'{bs}支' if bs and bs > 0 else '未知盒规',
                    'record_count': 0,
                    'points': [],
                }
            v = variants[key]
            raw = snap.raw_data if isinstance(snap.raw_data, dict) else {}
            point = {
                'snapshot_id': snap.id,
                'date': snap.scraped_at.isoformat(),
                'price': snap.price,
                'original_price': snap.original_price,
                'price_cny': snap.price_cny,
                'currency': snap.currency,
                'in_stock': snap.in_stock,
                'delisted': raw.get('delisted') is True,
                'anomaly': anomaly_info(snap),
            }
            if cutoff is None or snap.scraped_at >= cutoff:
                v['points'].append(point)
            v['record_count'] += 1
            # Every current field comes from the same latest snapshot, including null prices.
            v.update({
                'snapshot_id': snap.id,
                'product_name': product_name(snap),
                'scraped_name': product_name(snap),
                'currency': snap.currency,
                'url': snap.url or snap.source.base_url,
                'current_price': snap.price,
                'current_price_cny': snap.price_cny,
                'in_stock': snap.in_stock,
                'delisted': point['delisted'],
                'anomaly': point['anomaly'],
                'scraped_at': point['date'],
                'price_per_stick': per_stick(snap.price_cny, bs),
            })

        for v in variants.values():
            prices = [p['price'] for p in v['points']
                      if p['currency'] == v['currency'] and p['price'] is not None
                      and isfinite(p['price']) and p['price'] > 0
                      and p['in_stock'] and not p['delisted'] and not p['anomaly']]
            v['min_price'] = min(prices) if prices else None
            v['max_price'] = max(prices) if prices else None
            v['history_record_count'] = len(v['points'])

        release_type_cn = cigar.release_type_cn if cigar else None

        return Response({
            'cigar_id': int(cigar_id),
            'cigar_brand': cigar.brand if cigar else None,
            'cigar_brand_cn': brand_cn,
            'cigar_name': (cigar.name or cigar.english_name) if cigar else None,
            'cigar_name_en': cigar.english_name if cigar else None,
            'release_type_cn': release_type_cn,
            'history_days': days,
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

        latest = (PriceSnapshot.objects
                  .filter(cigar_id=OuterRef('cigar_id'), source_id=OuterRef('source_id'),
                          url=OuterRef('url')).order_by('-scraped_at', '-id'))
        # NULL is its own identity, distinct even from an explicitly invalid zero box.
        latest_ids = (PriceSnapshot.objects.annotate(latest_id=Case(
            When(box_size__isnull=True, then=Subquery(latest.filter(box_size__isnull=True).values('id')[:1])),
            default=Subquery(latest.filter(box_size=OuterRef('box_size')).values('id')[:1]),
        )).filter(id=F('latest_id')).values('id'))
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

            # Use stored snapshot conversion, matching history; never invent a fallback here.
            price_cny = snap.price_cny

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
                'delisted': bool((snap.raw_data or {}).get('delisted', False)),
                'anomaly': anomaly_info(snap),
                'url': snap.url or snap.source.base_url,
            })

            if snap.in_stock and not (snap.raw_data or {}).get('delisted'):
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
            # 均价只反映当前可售、未下架且有有效盒规的报价。
            entry['avg_per_stick_cny'] = avg_per_stick([
                source for source in entry['sources']
                if source['in_stock'] and not source['delisted'] and not source['anomaly']
                and source['price_cny'] is not None and isfinite(source['price_cny'])
                and source['price_cny'] > 0 and source['box_size'] and source['box_size'] > 0
            ])
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

from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import api_view, permission_classes
from price_tracker.coh_import import iter_coh_items
from price_tracker.ingestion import ingest_items


@csrf_exempt
@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])  # Restored
def import_coh_bulk(request):
    """接收浏览器直接 POST 的 COH 全站数据"""
    data = request.data
    source = PriceSource.objects.get(slug='coh')

    items, stats = iter_coh_items(data)
    result = ingest_items(source, items, mode='import', run_delisting=False)

    return Response({
        'ok': True,
        'total': stats['total'],
        'matched': result.matched,
        'created': result.created,
        'skipped': stats['skipped_no_price'] + result.skipped,
        'unmatched_count': len(result.unmatched),
        'unmatched': result.unmatched[:20],
    })
