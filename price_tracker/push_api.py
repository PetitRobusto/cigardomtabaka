"""价格数据推送 API — 仅 DEBUG=False 时可用"""
import json
import logging
import os
from functools import wraps

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from price_tracker.ingestion import ingest_items
from price_tracker.models import PriceSource
from price_tracker.scraper import ScrapedItem

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

    items = [_parse_push_item(item_data, source) for item_data in items_data]
    result = ingest_items(source, items, mode='push')

    return JsonResponse({
        'ok': True,
        'source': source_slug,
        'received': len(items_data),
        'matched': result.matched,
        'created': result.created,
        'skipped': result.skipped,
        'delisted': result.delisted,
        'errors': result.errors,
        'error_summary': result.error_summary,
        'cache_hits': result.cache_hits,
        'cache_misses': result.cache_misses,
    })


def _parse_push_item(item_data, source: PriceSource) -> ScrapedItem:
    """Convert one push payload row to ScrapedItem."""
    data = item_data if isinstance(item_data, dict) else {}
    raw_data = data.get('raw_data', {})
    if not isinstance(raw_data, dict):
        raw_data = {}

    item = ScrapedItem(
        name=data.get('name', ''),
        price=data.get('price'),
        original_price=data.get('original_price'),
        box_size=data.get('box_size'),
        box_price=data.get('box_price'),
        url=data.get('url', ''),
        in_stock=data.get('in_stock', True),
        currency=data.get('currency', source.currency or 'USD'),
        raw_data=raw_data,
    )
    item.price_cny = data.get('price_cny')
    return item
