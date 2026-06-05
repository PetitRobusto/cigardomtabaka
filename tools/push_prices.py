#!/usr/bin/env python3
"""将本地价格数据推送到生产服务器 API

用法:
  python3 tools/push_prices.py --all          # 全量推送所有活跃 source
  python3 tools/push_prices.py -s coh_china   # 推送指定 source
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

from price_tracker.models import PriceSource, PriceSnapshot
from django.db.models import Max

API_URL = "https://cigardomtabaka.com/api/prices/push-bulk/"
API_KEY = os.environ.get('PRICE_PUSH_API_KEY', '')


def push_source(source_slug: str) -> dict:
    """把指定 source 的最新快照序列化并推送到生产"""
    source = PriceSource.objects.filter(slug=source_slug).first()
    if not source:
        return {'error': f'Source {source_slug} not found'}

    # 每个 (cigar, box_size) 的最新一条
    latest_ids = (
        PriceSnapshot.objects
        .filter(source=source)
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
        return {'error': f'No snapshots for {source_slug}'}

    print(f'[{source_slug}] Pushing {len(items)} items...')

    resp = requests.post(
        API_URL,
        json={'source_slug': source_slug, 'items': items},
        headers={'X-API-Key': API_KEY, 'Content-Type': 'application/json'},
        timeout=120,
        proxies={'http': None, 'https': None},  # 不走代理 — 直连生产服
    )
    resp.raise_for_status()
    result = resp.json()
    print(f'[{source_slug}] OK: received={result.get("received")} '
          f'matched={result.get("matched")} created={result.get("created")} '
          f'skipped={result.get("skipped")} delisted={result.get("delisted")}')
    return result


def push_all() -> dict:
    """推送所有活跃 source 的全量数据（跳过空壳）"""
    results = {}
    skip_slugs = {'egm', 'ihavanas'}
    for source in PriceSource.objects.filter(active=True).exclude(slug__in=skip_slugs):
        try:
            results[source.slug] = push_source(source.slug)
        except Exception as e:
            print(f'[{source.slug}] FAILED: {e}')
            results[source.slug] = {'error': str(e)}
    return results


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Push price data to production')
    parser.add_argument('--source', '-s', help='Source slug (omit for all)')
    parser.add_argument('--all', '-a', action='store_true', help='Push all active sources')
    args = parser.parse_args()

    if not API_KEY:
        print('ERROR: PRICE_PUSH_API_KEY environment variable not set')
        sys.exit(1)

    if args.source:
        result = push_source(args.source)
        if 'error' in result:
            print(f'ERROR: {result["error"]}')
            sys.exit(1)
    elif args.all or (not args.source and not args.all):
        results = push_all()
        errors = sum(1 for r in results.values() if 'error' in r)
        total_created = sum(r.get('created', 0) for r in results.values())
        print(f'\n=== DONE: {len(results)} sources, {total_created} new, {errors} errors ===')
