# Price Push API 实施计划

> **For agentic workers:** 本计划分 5 个阶段，顺序执行。步骤用 `- [ ]` checkbox 追踪。

**Goal:** 生产服务器开放 API 接收爬虫数据，Hermes 爬完自动推送，支持多节点

**Architecture:** 生产端 Django API `POST /api/prices/push-bulk/`（DEBUG=False 才启用），X-API-Key 认证。Hermes 端 `push_prices.py` 脚本序列化 ScrapedItem → POST。先全量推送历史数据，再设 cron 定时爬+推。

**Tech Stack:** Django REST framework, Python requests, SSH, cron

---

## Phase 1: 生产端 API 端点

### Task 1.1: 生产端新增 push API view 和路由

**Files:**
- Create: `price_tracker/push_api.py`（新文件，push-bulk 视图）
- Modify: `price_tracker/urls.py`（条件路由）
- Modify: `cigardomtabaka_backend/settings.py`（如需要加配置项，不需要）

**步骤：**

- [ ] **Step 1: 创建 `push_api.py`**

```python
"""价格数据推送 API — 仅 DEBUG=False 时可用"""
import json
import logging
from functools import wraps

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from price_tracker.models import PriceSource, PriceSnapshot, ExchangeRate
from price_tracker.scraper import BaseScraper, ScrapedItem
from price_tracker.delisting import detect_delistings
from cigars.models import Cigar

logger = logging.getLogger(__name__)


def require_api_key(view_func):
    """X-API-Key 认证装饰器"""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        api_key = getattr(settings, 'PRICE_PUSH_API_KEY', None)
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

    # 用 BaseScraper 走匹配引擎（不需要真实爬虫类）
    scraper = BaseScraper(source)
    scraper.logger = logger

    from django.utils import timezone
    today = timezone.localdate()

    matched = 0
    created = 0
    skipped = 0
    errors = 0

    scraped_combos = set()

    # URL 缓存
    url_cache = {}
    for snap in PriceSnapshot.objects.filter(source=source, url__gt='').values('url', 'raw_data', 'cigar_id'):
        url = snap['url']
        product = snap['raw_data'].get('product', '') if isinstance(snap['raw_data'], dict) else ''
        key = (url, product) if product else (url, str(snap['cigar_id']))
        url_cache[key] = snap['cigar_id']

    cache_hits = 0
    cache_misses = 0

    for item_data in items_data:
        try:
            # 构造 ScrapedItem
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

            # URL 缓存查找
            cigar = None
            if item.url:
                product_hint = item.raw_data.get('product', '')
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
            rate = ExchangeRate.get_rate(item.currency) or 7.0
            price_cny = round(item.price * rate, 2) if item.price is not None else None

            # 价格去重
            latest = PriceSnapshot.objects.filter(
                source=source,
                cigar=cigar,
                box_size=item.box_size or 0,
            ).order_by('-scraped_at').first()

            if latest and latest.price == item.price and latest.in_stock == item.in_stock:
                if latest.scraped_at.date() < today:
                    # 价格不变但今天没记录 → 更新 scraped_at 防止被误判下架
                    latest.scraped_at = timezone.now()
                    latest.save(update_fields=['scraped_at'])
                skipped += 1
                continue

            snapshot = PriceSnapshot.objects.create(
                source=source,
                cigar=cigar,
                price=item.price,
                original_price=item.original_price,
                currency=item.currency,
                price_cny=price_cny,
                box_size=item.box_size or 0,
                url=item.url,
                in_stock=item.in_stock,
                raw_data=item.raw_data,
                scraped_at=timezone.now(),
                scraped_date=today,
            )
            created += 1

        except Exception as e:
            logger.exception(f'Error processing item: {item_data.get("name", "?")}')
            errors += 1

    # 下架检测：只对比上次爬取结果
    delisted = 0
    if scraped_combos:
        from django.db.models import Max
        last_date = PriceSnapshot.objects.filter(
            source=source, in_stock=True
        ).exclude(scraped_date=today).aggregate(last=Max('scraped_date'))['last']

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
                            source=source, cigar=cigar,
                            price=None, currency=source.currency,
                            box_size=box_size or 0,
                            in_stock=False,
                            scraped_at=timezone.now(),
                            scraped_date=today,
                            raw_data={'delisted': True},
                        )
                        delisted += 1
                    except Cigar.DoesNotExist:
                        pass

    return JsonResponse({
        'ok': True,
        'source': source_slug,
        'received': len(items_data),
        'matched': matched,
        'created': created,
        'skipped': skipped,
        'delisted': delisted,
        'errors': errors,
    })
```

- [ ] **Step 2: 修改 `price_tracker/urls.py` — 条件路由**

```bash
# 先看当前文件
cat ~/moscow_cigar/price_tracker/urls.py
```

```python
"""价格跟踪系统 — URL 路由"""
from django.conf import settings
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'sources', views.PriceSourceViewSet, basename='price-source')
router.register(r'snapshots', views.PriceSnapshotViewSet, basename='price-snapshot')
router.register(r'alerts', views.PriceAlertViewSet, basename='price-alert')

urlpatterns = [
    path('', include(router.urls)),
    path('import_coh/', views.import_coh_bulk, name='import_coh_bulk'),
]

# push-bulk 仅在 DEBUG=False 时注册
if not settings.DEBUG:
    from .push_api import push_bulk
    urlpatterns.append(path('push-bulk/', push_bulk, name='push_bulk'))
```

- [ ] **Step 3: 在生产服务器 .env 加 API key**

```bash
# 本地生成随机 key
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

然后在生产服务器 `/opt/cigardomtabaka/.env` 追加：
```
PRICE_PUSH_API_KEY=<生成的key>
```

```bash
# SSH 到生产执行
ssh -i ~/.ssh/id_ed25519 jason@103.110.65.50 "echo 'PRICE_PUSH_API_KEY=<key>' >> /opt/cigardomtabaka/.env"
```

- [ ] **Step 4: 提交代码 + 触发 CI/CD 部署**

```bash
cd ~/moscow_cigar
git add price_tracker/push_api.py price_tracker/urls.py
git commit -m "feat: add push-bulk API endpoint for scraper data (DEBUG=False only)"
git push origin main
```

等待 GitHub Actions 部署完成。

- [ ] **Step 5: 验证 API 可用**

```bash
# 从本机测试（应该 404，因为生产是 DEBUG=False）
curl -s -o /dev/null -w "%{http_code}" https://cigardomtabaka.com/api/prices/push-bulk/ -X POST

# 带 key 测试（空数据）
curl -s https://cigardomtabaka.com/api/prices/push-bulk/ \
  -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <key>" \
  -d '{"source_slug":"coh_china","items":[]}'
# 预期: {"ok":true,"source":"coh_china","received":0,...}
```

---

## Phase 2: Hermes 端推送脚本

### Task 2.1: 创建 `push_prices.py`

**Files:**
- Create: `tools/push_prices.py`

- [ ] **Step 1: 创建推送脚本**

```python
#!/usr/bin/env python3
"""将本地价格数据推送到生产服务器 API"""
import os, sys, json, argparse
import requests

# Django setup
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cigardomtabaka_backend.settings')
import django; django.setup()

from price_tracker.models import PriceSource, PriceSnapshot
from price_tracker.scraper import ScrapedItem

API_URL = "https://cigardomtabaka.com/api/prices/push-bulk/"
API_KEY = os.environ.get("PRICE_PUSH_API_KEY", "")


def push_source(source_slug: str) -> dict:
    """把指定 source 的最新快照序列化并推送到生产"""
    source = PriceSource.objects.filter(slug=source_slug, active=True).first()
    if not source:
        return {'error': f'Source {source_slug} not found or inactive'}

    # 取每个 (cigar, box_size) 的最新一条
    from django.db.models import Max
    latest_ids = (
        PriceSnapshot.objects
        .filter(source=source)
        .values('cigar_id', 'box_size')
        .annotate(max_id=Max('id'))
        .values_list('max_id', flat=True)
    )
    snapshots = PriceSnapshot.objects.filter(id__in=latest_ids).select_related('cigar')

    items = []
    for snap in snapshots:
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
        timeout=60,
    )
    resp.raise_for_status()
    result = resp.json()
    print(f'[{source_slug}] OK: received={result["received"]} matched={result["matched"]} '
          f'created={result["created"]} skipped={result["skipped"]} delisted={result["delisted"]}')
    return result


def push_all() -> dict:
    """推送所有活跃 source 的全量数据"""
    results = {}
    for source in PriceSource.objects.filter(active=True).exclude(slug__in=['egm', 'ihavanas']):
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
        print('ERROR: PRICE_PUSH_API_KEY env var not set')
        sys.exit(1)

    if args.source:
        push_source(args.source)
    elif args.all or not args.source:
        push_all()
```

- [ ] **Step 2: 配置本地 API key**

```bash
# 把生产的那把 key 加到本机 .env（或 hermes 环境变量）
echo 'PRICE_PUSH_API_KEY=<same-key-as-production>' >> ~/moscow_cigar/.env
```

---

## Phase 3: 一次性全量推送（先做！）

这是用户最优先的需求——先把现有数据全推到生产，让前端有数据。

- [ ] **Step 1: 先确保 Phase 1 代码已部署到生产**

```bash
# 确认部署完成
curl -s https://cigardomtabaka.com/api/prices/push-bulk/ -X POST \
  -H "X-API-Key: $PRICE_PUSH_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"source_slug":"coh_china","items":[]}'
# 预期: {"ok":true,...}
```

- [ ] **Step 2: 逐个 source 全量推送**

```bash
cd ~/moscow_cigar

# 每个 source 全量推送
PYTHONPATH="$HOME/moscow_cigar" python3 tools/push_prices.py -s coh_china
PYTHONPATH="$HOME/moscow_cigar" python3 tools/push_prices.py -s lcdh_nyon
PYTHONPATH="$HOME/moscow_cigar" python3 tools/push_prices.py -s lcdh_dl
PYTHONPATH="$HOME/moscow_cigar" python3 tools/push_prices.py -s vipcigars
PYTHONPATH="$HOME/moscow_cigar" python3 tools/push_prices.py -s lcdh_brussels
```

- [ ] **Step 3: 验证生产端数据**

SSH 到生产服务器确认数据已入库：
```bash
ssh -i ~/.ssh/id_ed25519 jason@103.110.65.50 \
  "cd /opt/cigardomtabaka && source venv/bin/activate && python -c \"
import os; os.environ['DJANGO_SETTINGS_MODULE']='cigardomtabaka_backend.settings'
import django; django.setup()
from price_tracker.models import PriceSource, PriceSnapshot
for s in PriceSource.objects.all():
    count = PriceSnapshot.objects.filter(source=s).count()
    latest = PriceSnapshot.objects.filter(source=s).order_by('-scraped_at').first()
    d = latest.scraped_at.strftime('%Y-%m-%d %H:%M') if latest else 'never'
    print(f'{s.slug:20s} | {count:4d} snaps | latest={d}')
\""
```

- [ ] **Step 4: 浏览器验证前端**

打开 https://cigardomtabaka.com/prices/ 确认价格卡片正常渲染。

---

## Phase 4: Hermes 定时爬虫 + 自动推送

### Task 4.1: 创建一站式脚本 `scrape_and_push.py`

**Files:**
- Create: `tools/scrape_and_push.py`

- [ ] **Step 1: 创建爬+推一体化脚本**

```python
#!/usr/bin/env python3
"""爬取价格 → 本地入库 → 推送到生产 一站式脚本"""
import os, sys, json, time
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cigardomtabaka_backend.settings')
import django; django.setup()

from price_tracker.scraper import run_scrape_sync
from price_tracker.models import PriceSource, PriceSnapshot
from django.db.models import Max

API_URL = "https://cigardomtabaka.com/api/prices/push-bulk/"
API_KEY = os.environ.get("PRICE_PUSH_API_KEY", "")

ACTIVE_SOURCES = ['coh_china', 'lcdh_nyon', 'lcdh_dl', 'lcdh_brussels', 'vipcigars']


def scrape_and_push(source_slug: str):
    """爬取 → 本地 → 推送"""
    print(f'\n=== [{source_slug}] Scraping... ===')
    result = run_scrape_sync(source_slug)
    if 'error' in result:
        print(f'[{source_slug}] SCRAPE FAILED: {result["error"]}')
        return result

    print(f'[{source_slug}] Scrape OK: {result.get("created", 0)} new, '
          f'{result.get("skipped", 0)} skipped')

    # 推送全量最新快照
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
    for snap in snapshots:
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

    resp = requests.post(
        API_URL,
        json={'source_slug': source_slug, 'items': items},
        headers={'X-API-Key': API_KEY, 'Content-Type': 'application/json'},
        timeout=120,
    )
    resp.raise_for_status()
    push_result = resp.json()
    print(f'[{source_slug}] Push OK: received={push_result["received"]} '
          f'created={push_result["created"]} delisted={push_result["delisted"]}')
    return {'scrape': result, 'push': push_result}


if __name__ == '__main__':
    if not API_KEY:
        print('ERROR: PRICE_PUSH_API_KEY not set')
        sys.exit(1)

    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', '-s', help='Single source to run')
    args = parser.parse_args()

    sources = [args.source] if args.source else ACTIVE_SOURCES
    results = {}
    for slug in sources:
        try:
            results[slug] = scrape_and_push(slug)
        except Exception as e:
            print(f'[{slug}] FAILED: {e}')
            results[slug] = {'error': str(e)}

    total_created = sum(
        r.get('scrape', {}).get('created', 0) for r in results.values()
    )
    print(f'\n=== DONE: {len(results)} sources, {total_created} new snapshots ===')
```

- [ ] **Step 2: 手动跑一次验证**

```bash
cd ~/moscow_cigar
PYTHONPATH="$HOME/moscow_cigar" python3 tools/scrape_and_push.py -s coh_china
# 预期: 爬取 → 本地入库 → 推送生产 → 返回统计
```

### Task 4.2: 设置 cron 定时任务（Hermes 内置 cron）

- [ ] **Step 1: 创建 cron job — 每小时跑所有源**

用 Hermes 内置 cronjob 工具设置。

Prompt: "Run `PYTHONPATH=/home/jason/moscow_cigar python3 /home/jason/moscow_cigar/tools/scrape_and_push.py` every hour. Output the result summary."

Schedule: `0 * * * *`（每小时整点）

- [ ] **Step 2: 验证 cron 运行**

等第一个整点后检查 cron 输出，确认爬取+推送成功。

---

## Phase 5: 最终验证

- [ ] **验证生产端数据实时更新**

```bash
# 查看生产数据库
ssh -i ~/.ssh/id_ed25519 jason@103.110.65.50 \
  "cd /opt/cigardomtabaka && source venv/bin/activate && python -c \"
import os; os.environ['DJANGO_SETTINGS_MODULE']='cigardomtabaka_backend.settings'
import django; django.setup()
from price_tracker.models import PriceSource, PriceSnapshot
for s in PriceSource.objects.all():
    count = PriceSnapshot.objects.filter(source=s).count()
    latest = PriceSnapshot.objects.filter(source=s).order_by('-scraped_at').first()
    d = latest.scraped_at.strftime('%Y-%m-%d %H:%M') if latest else 'never'
    print(f'{s.slug:20s} | {count:4d} snaps | latest={d}')
\""
```

- [ ] **浏览器验证** https://cigardomtabaka.com/prices/ 正常显示

- [ ] **API key 安全测试**

```bash
# 无 key → 403
curl -s -o /dev/null -w "%{http_code}" https://cigardomtabaka.com/api/prices/push-bulk/ -X POST -d '{}'
# 预期: 403

# 错 key → 403
curl -s https://cigardomtabaka.com/api/prices/push-bulk/ \
  -X POST -H "X-API-Key: wrongkey" -d '{}'
# 预期: {"error":"Invalid API key"}
```
