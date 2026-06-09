#!/usr/bin/env python3
"""将本地价格数据推送到生产服务器 API

用法:
  python3 tools/push_prices.py                 # 全量推送所有活跃 source
  python3 tools/push_prices.py -s coh_china    # 推送指定 source
  python3 tools/push_prices.py -a              # 同上（全量）
  python3 tools/push_prices.py -a --after-scrape  # 只推爬取成功的源
"""
import os
import sys
import json
import argparse
import requests

BASE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, BASE_DIR)

# 加载 .env（cron 环境没有预设环境变量）
from dotenv import load_dotenv
load_dotenv(os.path.join(BASE_DIR, '.env'))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cigardomtabaka_backend.settings')
import django
django.setup()

from price_tracker.models import PriceSource, PriceSnapshot
from django.db.models import Max

API_URL = "https://cigardomtabaka.com/api/prices/push-bulk/"
API_KEY = os.environ.get('PRICE_PUSH_API_KEY', '')
STATUS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.scrape_status.json')


def push_source(source_slug: str) -> dict:
    """把指定 source 的最新快照序列化并推送到生产"""
    source = PriceSource.objects.filter(slug=source_slug).first()
    if not source:
        return {'error': f'Source {source_slug} not found'}

    # 每个 (cigar, box_size) 的最新在售记录（不下架标记）
    latest_ids = (
        PriceSnapshot.objects
        .filter(source=source, in_stock=True)
        .values('cigar_id', 'box_size')
        .annotate(max_id=Max('id'))
        .values_list('max_id', flat=True)
    )
    snapshots = PriceSnapshot.objects.filter(id__in=latest_ids).select_related('cigar')

    items = []
    for snap in snapshots.iterator():
        name_for_push = (
            snap.raw_data.get('title_original')
            or snap.raw_data.get('product_name')
            or snap.raw_data.get('title')
            or snap.cigar.english_name
            or snap.cigar.name
            or ''
        )
        items.append({
            'name': name_for_push,
            'price': snap.price,
            'original_price': snap.original_price,
            'price_cny': snap.price_cny,
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
        proxies={'http': None, 'https': None},
    )
    resp.raise_for_status()
    result = resp.json()
    print(f'[{source_slug}] OK: received={result.get("received")} '
          f'matched={result.get("matched")} created={result.get("created")} '
          f'skipped={result.get("skipped")} delisted={result.get("delisted")}')
    return result


def push_all(skip_slugs: set = None) -> dict:
    """推送所有活跃 source，跳过 skip_slugs 中的源"""
    results = {}
    base_skip = {'egm', 'ihavanas'}
    if skip_slugs:
        base_skip |= skip_slugs

    for source in PriceSource.objects.filter(active=True).exclude(slug__in=base_skip):
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
    parser.add_argument('--after-scrape', action='store_true',
                        help='Only push sources that just scraped successfully (reads .scrape_status.json)')
    args = parser.parse_args()

    if not API_KEY:
        print('ERROR: PRICE_PUSH_API_KEY environment variable not set')
        sys.exit(1)

    # 读取 scrape 状态，过滤失败源
    skip_slugs = set()
    if args.after_scrape:
        try:
            with open(STATUS_FILE) as f:
                status = json.load(f)
            skip_slugs = {slug for slug, s in status.items() if not s.get('success')}
            if skip_slugs:
                print(f'Skip failed sources: {", ".join(sorted(skip_slugs))}')
            ok_slugs = {slug for slug, s in status.items() if s.get('success')}
            print(f'OK sources: {len(ok_slugs)}')
        except FileNotFoundError:
            print('WARNING: .scrape_status.json not found, pushing all')
        except Exception as e:
            print(f'WARNING: failed to read status file: {e}, pushing all')

    if args.source:
        if args.source in skip_slugs:
            print(f'ERROR: {args.source} scrape failed, skipping push')
            sys.exit(1)
        result = push_source(args.source)
        if 'error' in result:
            print(f'ERROR: {result["error"]}')
            sys.exit(1)
    elif args.all or (not args.source and not args.all):
        results = push_all(skip_slugs=skip_slugs)
        errors = sum(1 for r in results.values() if 'error' in r)
        total_created = sum(r.get('created', 0) for r in results.values())
        print(f'\n=== DONE: {len(results)} sources, {total_created} new, {errors} errors ===')
