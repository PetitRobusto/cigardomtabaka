#!/usr/bin/env python3
"""爬取所有活跃源的价格数据 → 存入本地 cigars.db。不推送！

用法:
  python3 tools/scrape.py              # 并行爬全部活跃源
  python3 tools/scrape.py -s cigarone  # 爬指定源（调试用）

退出码：
  0 = 全部成功
  1 = 部分或全部失败
  2 = 无活跃源

爬取完成后写 tools/.scrape_status.json，push_prices.py 用 --after-scrape 读取。
"""

import os
import sys
import time
import json
import argparse
import concurrent.futures

BASE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, BASE_DIR)

from dotenv import load_dotenv
load_dotenv(os.path.join(BASE_DIR, '.env'))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cigardomtabaka_backend.settings')
import django
django.setup()

from price_tracker.scraper import run_scrape_sync
from price_tracker.models import PriceSource

SKIP_SLUGS = {'egm', 'ihavanas'}
SKIP_SCRAPERS = {'test'}  # 去掉测试源，防止拖慢全量爬取
RETRY_COUNT = 1
STATUS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.scrape_status.json')


def scrape_source(slug: str) -> dict:
    """爬取单个源，带重试"""
    for attempt in range(RETRY_COUNT + 1):
        try:
            result = run_scrape_sync(slug)
        except Exception as e:
            result = {'error': str(e)}

        if 'error' not in result:
            return result

        if attempt < RETRY_COUNT:
            print(f'[{slug}] 重试 {attempt+1}/{RETRY_COUNT}: {result["error"]}')
            time.sleep(5)
        else:
            print(f'[{slug}] 失败: {result["error"]}')
            return result

    return {'error': 'unknown'}


MIN_FREE_GB = 2


def _check_disk():
    """返回根分区空闲 GB，失败返回 None"""
    try:
        stat = os.statvfs('/')
        return (stat.f_bavail * stat.f_frsize) / (1024 ** 3)
    except Exception:
        return None


def scrape_all() -> dict:
    """Nyon 单独复用 CDP，其它活跃源继续并行爬取。"""
    # ⛔ 磁盘防线：< 2G 直接退出，避免 Chromium EPIPE
    free_gb = _check_disk()
    if free_gb is not None and free_gb < MIN_FREE_GB:
        print(f'⛔ 磁盘仅剩 {free_gb:.1f}G，低于 {MIN_FREE_GB}G 阈值，跳过爬取')
        sources = list(
            PriceSource.objects.filter(active=True)
            .exclude(slug__in=SKIP_SLUGS)
            .exclude(scraper_class__in=SKIP_SCRAPERS)
        )
        status = {}
        for s in sources:
            status[s.slug] = {
                'success': False,
                'time': time.strftime('%Y-%m-%dT%H:%M:%S'),
                'new': 0, 'matched': 0, 'skipped': 0,
                'error': f'disk low ({free_gb:.1f}G < {MIN_FREE_GB}G)',
            }
        try:
            with open(STATUS_FILE, 'w') as f:
                json.dump(status, f, indent=2)
        except Exception:
            pass
        return {}, len(sources)  # 返回全部失败

    sources = [
        s.slug for s in PriceSource.objects.filter(active=True)
        .exclude(slug__in=SKIP_SLUGS)
        .exclude(scraper_class__in=SKIP_SCRAPERS)
    ]
    if not sources:
        print('无活跃爬虫源')
        return {}, 0

    start = time.time()
    results = {}

    # Nyon 依赖 Hermes CDP Chrome 的 Cloudflare 会话，先独占 9222 跑完，
    # 避免和其它 CDP 爬虫并发打开页面互相抢 context/tab。
    nyon_slug = 'lcdh_nyon'
    if nyon_slug in sources:
        sources.remove(nyon_slug)
        print('=== 单独爬取 lcdh_nyon（CDP 复用） ===')
        r = scrape_source(nyon_slug)
        results[nyon_slug] = r
        elapsed = time.time() - start
        if 'error' in r:
            print(f'  [{nyon_slug}] ❌ {r["error"]} ({elapsed:.0f}s)')
        else:
            print(f'  [{nyon_slug}] ✅ new={r.get("created",0)} '
                  f'skip={r.get("skipped",0)} match={r.get("matched",0)} '
                  f'({elapsed:.0f}s)')

    print(f'=== 并行爬取 {len(sources)} 个源（max 2 workers） ===')
    max_workers = min(2, len(sources)) if sources else 1
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(scrape_source, slug): slug for slug in sources}
        for future in concurrent.futures.as_completed(futures):
            slug = futures[future]
            try:
                r = future.result()
            except Exception as e:
                r = {'error': str(e)}
            results[slug] = r

            elapsed = time.time() - start
            if 'error' in r:
                print(f'  [{slug}] ❌ {r["error"]} ({elapsed:.0f}s)')
            else:
                print(f'  [{slug}] ✅ new={r.get("created",0)} '
                      f'skip={r.get("skipped",0)} match={r.get("matched",0)} '
                      f'({elapsed:.0f}s)')

    elapsed = time.time() - start
    total_created = sum(
        r.get('created', 0) for r in results.values()
        if isinstance(r, dict)
    )
    errors = sum(
        1 for r in results.values()
        if isinstance(r, dict) and 'error' in r
    )

    # 写状态文件
    status = {}
    for slug, r in results.items():
        if isinstance(r, dict):
            status[slug] = {
                'success': 'error' not in r,
                'time': time.strftime('%Y-%m-%dT%H:%M:%S'),
                'new': r.get('created', 0),
                'matched': r.get('matched', 0),
                'skipped': r.get('skipped', 0),
            }
    try:
        with open(STATUS_FILE, 'w') as f:
            json.dump(status, f, indent=2)
    except Exception as e:
        print(f'⚠️  写状态文件失败: {e}')

    print(f'\n=== 爬取完成 ({elapsed:.0f}s) ===')
    print(f'  源: {len(results)}  新增: {total_created}  失败: {errors}')
    if errors:
        failed_list = [s for s, r in results.items() if isinstance(r, dict) and 'error' in r]
        print(f'  失败源: {", ".join(failed_list)}')
    return results, errors


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='爬取价格数据到本地DB')
    parser.add_argument('--source', '-s', help='只爬指定源')
    args = parser.parse_args()

    if args.source:
        r = scrape_source(args.source)
        ok = 'error' not in r
        print(f'{"OK" if ok else "FAIL"}: {r}')
        sys.exit(0 if ok else 1)
    else:
        _, errors = scrape_all()
        sys.exit(0 if errors == 0 else 1)
