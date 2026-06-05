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

from price_tracker.models import PriceSource, PriceSnapshot, ExchangeRate
from price_tracker.scraper import BaseScraper, ScrapedItem
from cigars.models import Cigar

logger = logging.getLogger(__name__)


def require_api_key(view_func):
    """X-API-Key 认证装饰器"""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        api_key = os.environ.get('PRICE_PUSH_API_KEY', '')
        if not api_key:
            return JsonResponse({'error': 'API key not configured'}, status=500)
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
    scraped_combos = set()

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

            # 汇率换算 CNY
            rate = ExchangeRate.get_rate(item.currency) if item.currency else None
            if rate is None:
                rate = 7.0
            price_cny = round(item.price * rate, 2) if item.price is not None else None

            # 价格去重
            box_key = item.box_size or 0
            latest = PriceSnapshot.objects.filter(
                source=source,
                cigar=cigar,
                box_size=box_key,
            ).order_by('-scraped_at').first()

            if latest and latest.price == item.price and latest.in_stock == item.in_stock:
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

        except Exception:
            logger.exception('Error processing item: %s', item_data.get('name', '?'))
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

    return JsonResponse({
        'ok': True,
        'source': source_slug,
        'received': len(items_data),
        'matched': matched,
        'created': created,
        'skipped': skipped,
        'delisted': delisted,
        'errors': errors,
        'cache_hits': cache_hits,
        'cache_misses': cache_misses,
    })
