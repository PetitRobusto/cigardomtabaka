"""价格数据推送 API — 仅 DEBUG=False 时可用"""
import json
import logging
import os
from functools import wraps

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.utils import timezone

from price_tracker.models import PriceSource, PriceSnapshot
from price_tracker.scraper import BaseScraper, ScrapedItem
from cigars.models import Cigar

logger = logging.getLogger(__name__)


def require_api_key(view_func):
    """X-API-Key 认证装饰器"""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        api_key = os.environ.get('PRICE_PUSH_API_KEY', '')
        if not api_key:
            return JsonResponse({'error': 'Forbidden'}, status=403)
        request_key = request.headers.get('X-API-Key', '')
        if request_key != api_key:
            return JsonResponse({'error': 'Invalid API key'}, status=403)
        return view_func(request, *args, **kwargs)
    return wrapper


@csrf_exempt
@require_POST
@require_api_key
def push_bulk(request):
    """批量接收爬虫价格数据

    POST /api/prices/push-bulk/
    Header: X-API-Key: <secret>
    Body: {"source_slug": "coh_china", "items": [...]}
    """
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    source_slug = body.get('source_slug', '').strip()
    items_data = body.get('items', [])

    if not source_slug:
        return JsonResponse({'error': 'source_slug is required'}, status=400)
    if not isinstance(items_data, list):
        return JsonResponse({'error': 'items must be a list'}, status=400)
    if len(items_data) > 500:
        return JsonResponse({'error': 'Too many items (max 500)'}, status=400)

    source = PriceSource.objects.filter(slug=source_slug).first()
    if not source:
        return JsonResponse({'error': f'Unknown source: {source_slug}'}, status=400)

    scraper = BaseScraper(source)
    scraper.logger = logger

    today = timezone.localdate()
    matched = 0
    created = 0
    skipped = 0
    errors = 0
    error_samples = []  # 临时调试：收集错误详情
    scraped_combos = set()
    anomaly_groups = set()  # 本次创建的 (cigar_id, box_size)，用于异常重算

    # URL 缓存 — key=(url, product_name)
    url_cache = {}
    for snap in PriceSnapshot.objects.filter(source=source, url__gt='').values(
        'url', 'raw_data', 'cigar_id'
    ):
        url = snap['url']
        raw = snap['raw_data'] or {}
        product = raw.get('product', '') if isinstance(raw, dict) else ''
        key = (url, product) if product else (url, str(snap['cigar_id']))
        url_cache[key] = snap['cigar_id']

    cache_hits = 0
    cache_misses = 0

    for item_data in items_data:
        try:
            raw_data = item_data.get('raw_data', {})
            if not isinstance(raw_data, dict):
                raw_data = {}

            item = ScrapedItem(
                name=item_data.get('name', ''),
                price=item_data.get('price'),
                original_price=item_data.get('original_price'),
                currency=item_data.get('currency', source.currency or 'USD'),
                box_size=item_data.get('box_size'),
                url=item_data.get('url', ''),
                in_stock=item_data.get('in_stock', True),
                raw_data=raw_data,
            )

            if not item.name:
                errors += 1
                continue

            # URL 缓存找
            cigar = None
            if item.url:
                product_hint = item.raw_data.get('product', '') if isinstance(item.raw_data, dict) else ''
                cache_key = (item.url, product_hint) if product_hint else (item.url, '')
                if cache_key in url_cache:
                    try:
                        cigar = Cigar.objects.get(id=url_cache[cache_key])
                        cache_hits += 1
                    except Cigar.DoesNotExist:
                        del url_cache[cache_key]

            # 走匹配引擎
            if not cigar:
                cigar = scraper.match_cigar(item)
                if cigar:
                    cache_misses += 1

            if not cigar:
                errors += 1
                continue

            matched += 1
            scraped_combos.add((cigar.id, item.box_size))

            # 人民币价格：优先用推送方算好的（避免生产端汇率缺失）
            price_cny = item_data.get('price_cny')
            if price_cny is None and item.price is not None:
                from .pricing import convert_to_cny
                price_cny = convert_to_cny(item.price, item.currency)

            # 价格去重（浮点容差 0.01）
            box_key = item.box_size  # 保持 None 语义
            from django.db.models import Q
            box_filter = Q(box_size=box_key) if box_key is not None else Q(box_size__isnull=True)
            latest = PriceSnapshot.objects.filter(
                source=source,
                cigar=cigar,
            ).filter(box_filter).order_by('-scraped_at').first()

            # 浮点数用容差比较（避免 IEEE 754 精度问题）
            price_same = (
                latest is not None
                and latest.price is not None
                and item.price is not None
                and abs(float(latest.price) - float(item.price)) < 0.01
            )
            # 原币价 + CNY 都相同才跳过（汇率变动时 CNY 会变）
            cny_same = (
                price_cny is not None
                and latest.price_cny is not None
                and abs(float(latest.price_cny) - float(price_cny)) < 0.01
            )
            if price_same and cny_same and latest.in_stock == item.in_stock:
                if latest.scraped_at.date() < today:
                    latest.scraped_at = timezone.now()
                    latest.save(update_fields=['scraped_at'])
                skipped += 1
                continue

            PriceSnapshot.objects.create(
                source=source,
                cigar=cigar,
                price=item.price,
                original_price=item.original_price,
                currency=item.currency,
                price_cny=price_cny,
                box_size=box_key,
                url=item.url,
                in_stock=item.in_stock,
                raw_data=item.raw_data,
                scraped_at=timezone.now(),
                scraped_date=today,
            )
            created += 1
            anomaly_groups.add((cigar.id, box_key))

        except Exception as e:
            err_msg = f'{type(e).__name__}: {e}'
            logger.exception('Error processing item: %s — %s', item_data.get('name', '?'), err_msg)
            if len(error_samples) < 5:
                error_samples.append({'item': item_data.get('name', '?'), 'error': err_msg})
            errors += 1

    # 下架检测 — 只对比上次爬取
    delisted = 0
    if scraped_combos:
        from django.db.models import Max
        last_date = (
            PriceSnapshot.objects
            .filter(source=source, in_stock=True)
            .exclude(scraped_date=today)
            .aggregate(last=Max('scraped_date'))['last']
        )

        if last_date:
            prev_combos = set(
                PriceSnapshot.objects.filter(
                    source=source, scraped_date=last_date, in_stock=True
                ).values_list('cigar_id', 'box_size')
            )
            for cigar_id, box_size in prev_combos:
                if (cigar_id, box_size) not in scraped_combos:
                    try:
                        cigar = Cigar.objects.get(id=cigar_id)
                        PriceSnapshot.objects.create(
                            source=source,
                            cigar=cigar,
                            price=None,
                            currency=source.currency,
                            box_size=box_size or 0,
                            in_stock=False,
                            scraped_at=timezone.now(),
                            scraped_date=today,
                            raw_data={'delisted': True},
                        )
                        delisted += 1
                    except Cigar.DoesNotExist:
                        pass

    # 更新 source 最后爬取时间
    source.last_scraped = timezone.now()
    source.save(update_fields=['last_scraped'])

    # --- 异常检测 ---
    if anomaly_groups:
        from .anomaly import detect_and_mark_group
        for cid, bs in anomaly_groups:
            detect_and_mark_group(cid, bs)

    return JsonResponse({
        'ok': True,
        'source': source_slug,
        'received': len(items_data),
        'matched': matched,
        'created': created,
        'skipped': skipped,
        'delisted': delisted,
        'errors': errors,
        'error_samples': error_samples,  # 临时调试
        'cache_hits': cache_hits,
        'cache_misses': cache_misses,
    })
