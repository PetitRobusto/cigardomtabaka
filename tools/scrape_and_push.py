#!/usr/bin/env python3
"""爬取价格 → 本地入库 → 推送到生产 一站式脚本

用法:
  python3 tools/scrape_and_push.py              # 跑所有活跃源
  python3 tools/scrape_and_push.py -s coh_china  # 跑指定源
"""
import os
import sys
import json
import argparse
import requests

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cigardomtabaka_backend.settings')
import django
django.setup()

from price_tracker.scraper import run_scrape_sync
from price_tracker.models import PriceSource, PriceSnapshot
from django.db.models import Max

API_URL = "https://cigardomtabaka.com/api/prices/push-bulk/"
API_KEY=os.environ.get('PRICE_PUSH_API_KEY', '')

ACTIVE_SOURCES = ['coh_china', 'lcdh_nyon', 'lcdh_dl', 'lcdh_brussels', 'vipcigars']


def scrape_and_push(source_slug: str) -> dict:
    """爬取 → 本地入库 → 推送到生产"""
    print(f'\n=== [{source_slug}] Scraping... ===')
    try:
        result = run_scrape_sync(source_slug)
    except Exception as e:
        print(f'[{source_slug}] SCRAPE ERROR: {e}')
        return {'error': str(e)}

    if 'error' in result:
        print(f'[{source_slug}] SCRAPE FAILED: {result["error"]}')
        return result

    print(f'[{source_slug}] Scrape OK: {result.get("created", 0)} new, '
          f'{result.get("skipped", 0)} skipped, {result.get("matched", 0)} matched')

    # 推送全量最新快照到生产
    print(f'[{source_slug}] Pushing to production...')
    source = PriceSource.objects.get(slug=source_slug)
    latest_ids = (
        PriceSnapshot.objects.filter(source=source)
        .values('cigar_id', 'box_size')
        .annotate(max_id=Max('id'))
        .values_list('max_id', flat=True)
    )
    snapshots = PriceSnapshot.objects.filter(id__in=latest_ids).select_related('cigar')

    items = []
    for snap in snapshots.iterator():
        items.append({
            'name': snap.cigar.english_name or snap.cigar.name or '',
            'price': snap.price,
            'original_price': snap.original_price,
            'currency': snap.currency,
            'box_size': snap.box_size if snap.box_size != 0 else None,
            'url': snap.url or '',
            'in_stock': snap.in_stock,
            'raw_data': snap.raw_data or {},
        })

    if not items:
        print(f'[{source_slug}] WARNING: No items to push')
        return {'scrape': result, 'push': {'created': 0}}

    try:
        resp = requests.post(
            API_URL,
            json={'source_slug': source_slug, 'items': items},
            headers={'X-API-Key': API_KEY, 'Content-Type': 'application/json'},
            timeout=120,
        )
        resp.raise_for_status()
        push_result = resp.json()
    except requests.exceptions.RequestException as e:
        print(f'[{source_slug}] PUSH FAILED: {e}')
        return {'scrape': result, 'push': {'error': str(e)}}

    print(f'[{source_slug}] Push OK: received={push_result.get("received")} '
          f'created={push_result.get("created")} delisted={push_result.get("delisted")}')
    return {'scrape': result, 'push': push_result}


if __name__ == '__main__':
    if not API_KEY:
        print('ERROR: PRICE_PUSH_API_KEY environment variable not set')
        sys.exit(1)

    parser = argparse.ArgumentParser(description='Scrape prices and push to production')
    parser.add_argument('--source', '-s', help='Single source to run')
    args = parser.parse_args()

    sources = [args.source] if args.source else ACTIVE_SOURCES
    results = {}
    for slug in sources:
        try:
            results[slug] = scrape_and_push(slug)
        except Exception as e:
            print(f'[{slug}] FATAL: {e}')
            results[slug] = {'error': str(e)}

    total_created = sum(
        r.get('scrape', {}).get('created', 0) for r in results.values()
        if isinstance(r, dict) and 'scrape' in r
    )
    total_push_created = sum(
        r.get('push', {}).get('created', 0) for r in results.values()
        if isinstance(r, dict) and isinstance(r.get('push'), dict)
    )
    print(f'\n=== DONE ===')
    print(f'  Sources: {len(results)}')
    print(f'  New snapshots (local): {total_created}')
    print(f'  New snapshots (prod):  {total_push_created}')
