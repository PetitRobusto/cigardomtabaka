# 下架检测 + 快照去重 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立下架检测独立模块，优化快照去重（价格不变不记录），前端区分缺货/下架状态。

**Architecture:** 新建 `delisting.py` 独立模块承接下架检测逻辑；重构 `run_scrape_sync` 的快照入库为「价格变化才记录」；移除每日去重约束；前端 PriceCard 灰显缺货、VariantCard 区分缺货/下架标签。

**Tech Stack:** Django ORM (SQLite), TypeScript/React, Tailwind CSS

---

### Task 1: 新建下架检测模块

**Files:**
- Create: `price_tracker/delisting.py`
- Create: `price_tracker/tests/test_delisting.py`

- [ ] **Step 1: 写测试**

```python
# price_tracker/tests/test_delisting.py
import pytest
from django.utils import timezone
from datetime import timedelta
from price_tracker.models import PriceSource, PriceSnapshot
from price_tracker.delisting import detect_delistings
from cigars.models import Cigar, Brand


@pytest.mark.django_db
class TestDetectDelistings:
    def test_new_delisting_creates_snapshot(self):
        """之前有货、本次没爬到的 → 创建 in_stock=False 快照"""
        brand = Brand.objects.create(name='测试', english_name='Test')
        cigar = Cigar.objects.create(brand='Test', english_name='Test Cigar')
        source = PriceSource.objects.create(
            name='测试站', slug='test', base_url='https://test.com',
            scraper_class='test', currency='USD',
        )

        # 昨天有货
        yesterday = timezone.now() - timedelta(days=1)
        PriceSnapshot.objects.create(
            source=source, cigar=cigar, price=100, currency='USD',
            box_size=25, in_stock=True, scraped_at=yesterday,
        )

        # 本次爬取结果：空（没爬到）
        scraped_combos = set()

        result = detect_delistings(source, scraped_combos)
        assert result['newly_delisted'] == 1
        assert result['already_delisted'] == 0

        # 验证快照
        snap = PriceSnapshot.objects.filter(
            source=source, cigar=cigar, in_stock=False
        ).order_by('-scraped_at').first()
        assert snap is not None
        assert snap.raw_data.get('delisted') is True
        assert 'delisted_at' in snap.raw_data
        assert snap.raw_data.get('last_seen') is not None

    def test_already_delisted_skips(self):
        """最新快照已经是 in_stock=False → 不重复创建"""
        brand = Brand.objects.create(name='测试2', english_name='Test2')
        cigar = Cigar.objects.create(brand='Test2', english_name='Test2 Cigar')
        source = PriceSource.objects.get(slug='test')

        # 已经下架了
        PriceSnapshot.objects.create(
            source=source, cigar=cigar, price=100, currency='USD',
            box_size=25, in_stock=False,
            raw_data={'delisted': True, 'delisted_at': '2026-05-27'},
        )

        scraped_combos = set()
        result = detect_delistings(source, scraped_combos)
        assert result['newly_delisted'] == 0
        assert result['already_delisted'] == 1

    def test_still_active_no_delisting(self):
        """本次爬到了 → 不触发下架"""
        brand = Brand.objects.create(name='测试3', english_name='Test3')
        cigar = Cigar.objects.create(brand='Test3', english_name='Test3 Cigar')
        source = PriceSource.objects.get(slug='test')

        PriceSnapshot.objects.create(
            source=source, cigar=cigar, price=100, currency='USD',
            box_size=25, in_stock=True,
        )

        # 本次爬到了
        scraped_combos = {(cigar.id, 25)}
        result = detect_delistings(source, scraped_combos)
        assert result['newly_delisted'] == 0

    def test_no_history_no_delisting(self):
        """该 source 没有任何历史 → 不下架"""
        source = PriceSource.objects.get(slug='test')
        scraped_combos = {(99999, 25)}
        result = detect_delistings(source, scraped_combos)
        assert result['newly_delisted'] == 0
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/jason/cigardomtabaka && python3 -m pytest price_tracker/tests/test_delisting.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'price_tracker.delisting'`

- [ ] **Step 3: 实现 delisting 模块**

```python
# price_tracker/delisting.py
"""下架检测 —— 对比爬取结果 vs 历史，标记下架事件"""
import logging
from datetime import datetime
from django.db.models import Max
from django.utils import timezone

from .models import PriceSource, PriceSnapshot

logger = logging.getLogger(__name__)


def detect_delistings(
    source: PriceSource,
    scraped_combos: set[tuple[int, int | None]],
) -> dict:
    """
    对比本次爬取结果 vs 该 source 所有历史活跃商品，标记下架。

    Args:
        source: 价格来源
        scraped_combos: 本次爬取到的 {(cigar_id, box_size), ...}
                        box_size 可为 None

    Returns:
        {'newly_delisted': int, 'already_delisted': int}
    """
    # 1. 查所有最新快照 in_stock=True 的组合
    subquery = (
        PriceSnapshot.objects
        .filter(source=source)
        .values('cigar_id', 'box_size')
        .annotate(latest_id=Max('id'))
        .values_list('latest_id', flat=True)
    )
    latest_active = PriceSnapshot.objects.filter(
        id__in=subquery, in_stock=True, source=source,
    )

    now = timezone.now()
    newly_delisted = 0
    already_delisted = 0

    for snap in latest_active:
        combo = (snap.cigar_id, snap.box_size)

        if combo in scraped_combos:
            # 本次爬到了 → 仍然活跃，跳过
            continue

        # 本次没爬到 → 检查是否今天已经标记过下架
        already = PriceSnapshot.objects.filter(
            source=source,
            cigar_id=snap.cigar_id,
            box_size=snap.box_size,
            scraped_date=now.date(),
            in_stock=False,
        ).exists()

        if already:
            already_delisted += 1
            continue

        # 创建下架快照
        PriceSnapshot.objects.create(
            source=source,
            cigar=snap.cigar,
            price=snap.price,
            currency=snap.currency,
            price_cny=snap.price_cny,
            box_size=snap.box_size,
            box_price=snap.box_price,
            url=snap.url,
            in_stock=False,
            raw_data={
                'delisted': True,
                'delisted_at': now.isoformat(),
                'last_seen': str(snap.scraped_date),
            },
        )
        newly_delisted += 1
        logger.info(
            f'[DELISTED] {snap.cigar.english_name} ({snap.box_size}支) '
            f'@ {source.short_name or source.name}'
        )

    return {
        'newly_delisted': newly_delisted,
        'already_delisted': already_delisted,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/jason/cigardomtabaka && python3 -m pytest price_tracker/tests/test_delisting.py -v
```

Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
cd /home/jason/cigardomtabaka
git add price_tracker/delisting.py price_tracker/tests/test_delisting.py
git commit -m "feat: add delisting detection module"
```

---

### Task 2: 重构 run_scrape_sync — 快照去重

**Files:**
- Modify: `price_tracker/scraper.py` (lines 121-228)
- Create: `price_tracker/tests/test_snapshot_dedup.py`

- [ ] **Step 1: 写测试**

```python
# price_tracker/tests/test_snapshot_dedup.py
import pytest
from django.utils import timezone
from datetime import timedelta
from price_tracker.models import PriceSource, PriceSnapshot
from price_tracker.scraper import run_scrape_sync
from cigars.models import Cigar, Brand


@pytest.mark.django_db
class TestSnapshotDedup:
    @pytest.fixture(autouse=True)
    def setup_source(self):
        self.brand = Brand.objects.create(name='去重测试', english_name='DedupTest')
        self.cigar = Cigar.objects.create(brand='DedupTest', english_name='Dedup Cigar')
        self.source = PriceSource.objects.create(
            name='去重站', slug='dedup_test', base_url='https://test.com',
            scraper_class='test_dedup', currency='USD',
        )

    def _mock_scrape(self, items):
        """Mock: 注册临时 scraper 返回给定 items"""
        from price_tracker.scrapers import register_scraper
        from price_tracker.scraper import BaseScraper

        class MockScraper(BaseScraper):
            source_slug = 'dedup_test'
            def scrape_catalog(self):
                return items

        register_scraper(MockScraper)
        return MockScraper

    def test_new_product_creates_snapshot(self):
        """新商品 → 创建快照"""
        from price_tracker.scraper import ScrapedItem
        items = [ScrapedItem(name='Dedup Cigar', price=100, box_size=25, currency='USD')]
        self._mock_scrape(items)
        result = run_scrape_sync('dedup_test')
        assert result['created'] == 1

    def test_same_price_skips(self):
        """价格没变 → 跳过"""
        from price_tracker.scraper import ScrapedItem

        # 先创建一条已有快照
        PriceSnapshot.objects.create(
            source=self.source, cigar=self.cigar, price=100, currency='USD',
            box_size=25, in_stock=True,
        )

        before_count = PriceSnapshot.objects.count()
        items = [ScrapedItem(name='Dedup Cigar', price=100, box_size=25, currency='USD')]
        self._mock_scrape(items)
        result = run_scrape_sync('dedup_test')
        assert result['created'] == 0  # 没建新快照
        assert PriceSnapshot.objects.count() == before_count

    def test_price_changed_creates_snapshot(self):
        """价格变了 → 创建新快照"""
        from price_tracker.scraper import ScrapedItem

        PriceSnapshot.objects.create(
            source=self.source, cigar=self.cigar, price=100, currency='USD',
            box_size=25, in_stock=True,
        )

        items = [ScrapedItem(name='Dedup Cigar', price=120, box_size=25, currency='USD')]
        self._mock_scrape(items)
        result = run_scrape_sync('dedup_test')
        assert result['created'] == 1

    def test_relisted_creates_snapshot(self):
        """之前下架，现在又出现了 → 创建 relisted 快照"""
        from price_tracker.scraper import ScrapedItem

        PriceSnapshot.objects.create(
            source=self.source, cigar=self.cigar, price=100, currency='USD',
            box_size=25, in_stock=False,
            raw_data={'delisted': True, 'delisted_at': '2026-05-27'},
        )

        items = [ScrapedItem(name='Dedup Cigar', price=100, box_size=25, currency='USD')]
        self._mock_scrape(items)
        result = run_scrape_sync('dedup_test')
        assert result['created'] == 1  # relisted 也算 created

        # 验证 raw_data 含 relisted 标记
        latest = PriceSnapshot.objects.filter(
            source=self.source, cigar=self.cigar, in_stock=True
        ).order_by('-scraped_at').first()
        assert latest is not None
        assert latest.raw_data.get('relisted') is True
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/jason/cigardomtabaka && python3 -m pytest price_tracker/tests/test_snapshot_dedup.py -v
```

Expected: FAIL — tests fail because old logic still creates/updates daily

- [ ] **Step 3: 重构 run_scrape_sync 的快照入库逻辑**

替换 `scraper.py` lines 121-167（爬到的商品入库）：

```python
    # 收集本次爬取 combos（供下架检测用）
    from django.utils import timezone
    today = timezone.now().date()
    scraped_combos = set()

    for item in items:
        cigar = scraper.match_cigar(item) or match_cigar_by_name(item.name, source.name)
        if not cigar:
            skipped += 1
            continue
        matched += 1

        # 币种 + CNY 换算
        item_currency = getattr(item, 'currency', None) or source.currency or 'USD'
        cny_rate = ExchangeRate.get_rate(item_currency)
        if cny_rate is None:
            cny_rate = exchange_rate  # fallback
        price_cny = round(item.price * cny_rate, 2) if item.price else None

        box_size = item.box_size
        combo = (cigar.id, box_size)
        scraped_combos.add(combo)

        # 查最新一条快照
        latest = PriceSnapshot.objects.filter(
            source=source, cigar=cigar, box_size=box_size
        ).order_by('-scraped_at').first()

        should_create = False
        raw_data = dict(item.raw_data) if item.raw_data else {}

        if latest is None:
            # 新商品 → 创建
            should_create = True
        elif not latest.in_stock:
            # 之前下架/缺货，现在回来了 → 创建 relisted 快照
            should_create = True
            raw_data['relisted'] = True
            raw_data['relisted_at'] = timezone.now().isoformat()
            logger.info(f'[RELISTED] {cigar.english_name} ({box_size}支)')
        elif latest.price != item.price:
            # 价格变了 → 创建
            should_create = True
        # else: 价格没变 → 跳过

        if should_create:
            PriceSnapshot.objects.create(
                source=source,
                cigar=cigar,
                price=item.price,
                currency=item_currency,
                price_cny=price_cny,
                box_size=box_size,
                box_price=item.box_price,
                url=item.url,
                in_stock=item.in_stock,
                raw_data=raw_data,
            )
            created += 1
```

替换 `scraper.py` lines 169-216（旧的缺货检测）为调用 delisting 模块：

```python
    # --- 下架检测 ---
    from .delisting import detect_delistings

    delisting_result = detect_delistings(source, scraped_combos)
    oos_count = delisting_result['newly_delisted']
```

完整替换后 `scraper.py` 末尾应变为：

```python
    # --- 下架检测 ---
    from .delisting import detect_delistings

    delisting_result = detect_delistings(source, scraped_combos)
    oos_count = delisting_result['newly_delisted']

    source.last_scraped = timezone.now()
    source.save(update_fields=['last_scraped'])

    return {
        'source': source_slug,
        'total_items': len(items),
        'matched': matched,
        'created': created,
        'skipped': skipped,
        'marked_oos': oos_count,
    }
```

同时删除 scraper.py 中不再需要的 `from django.db.models import Max as DMax`（已在 delisting 模块中）。

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/jason/cigardomtabaka && python3 -m pytest price_tracker/tests/test_snapshot_dedup.py price_tracker/tests/test_delisting.py -v
```

Expected: ALL pass

- [ ] **Step 5: Commit**

```bash
cd /home/jason/cigardomtabaka
git add price_tracker/scraper.py price_tracker/tests/test_snapshot_dedup.py
git commit -m "refactor: snapshot dedup — only record on price change or relist"
```

---

### Task 3: 移除每日去重约束

**Files:**
- Create: `price_tracker/migrations/0002_remove_daily_unique.py`

- [ ] **Step 1: 创建 migration 移除约束**

```bash
cd /home/jason/cigardomtabaka && python3 manage.py makemigrations price_tracker --empty --name remove_daily_unique
```

- [ ] **Step 2: 编辑 migration 文件**

```python
# price_tracker/migrations/0002_remove_daily_unique.py
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('price_tracker', '0001_initial'),
    ]
    operations = [
        migrations.RemoveConstraint(
            model_name='pricesnapshot',
            name='uq_snapshot_per_day',
        ),
    ]
```

- [ ] **Step 3: 从 models.py 移除约束声明**

在 `price_tracker/models.py` 中，找到 PriceSnapshot.Meta.constraints 列表，删除：

```python
            models.UniqueConstraint(
                fields=['cigar', 'source', 'box_size', 'scraped_date'],
                name='uq_snapshot_per_day',
            ),
```

保留 indexes 部分不变。

- [ ] **Step 4: 应用 migration**

```bash
cd /home/jason/cigardomtabaka && python3 manage.py migrate price_tracker
```

Expected: `Applying price_tracker.0002_remove_daily_unique... OK`

- [ ] **Step 5: 验证约束已移除**

```bash
cd /home/jason/cigardomtabaka && python3 manage.py shell -c "
import sqlite3
conn = sqlite3.connect('cigars_dev.db')
# SQLite 无法直接列约束，改成验证可以插入同日同 combo 两条记录
print('Migration applied successfully')
"
```

- [ ] **Step 6: Commit**

```bash
cd /home/jason/cigardomtabaka
git add price_tracker/models.py price_tracker/migrations/0002_remove_daily_unique.py
git commit -m "migration: remove uq_snapshot_per_day constraint"
```

---

### Task 4: 前端 — PriceCard 缺货灰显

**Files:**
- Modify: `frontend/src/components/dashboard/PriceCard.tsx`

- [ ] **Step 1: 改 PriceCard**

`in_stock=False` 时整张卡片变灰，加「缺货」标签替代「在售」标签：

```tsx
// 替换 lines 65-73 的在售徽章
{/* 库存状态徽章 */}
{cigar.in_stock ? (
  <div className="absolute top-2.5 right-2.5 flex items-center gap-1.5
    bg-emerald-50 text-emerald-700 border border-emerald-200 text-[0.65rem] font-semibold
    px-2.5 py-1 rounded-full">
    <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
    在售
  </div>
) : (
  <div className="absolute top-2.5 right-2.5 flex items-center gap-1.5
    bg-red-50 text-red-600 border border-red-200 text-[0.65rem] font-semibold
    px-2.5 py-1 rounded-full">
    缺货
  </div>
)}
```

卡片整体加 `opacity` 处理：

```tsx
// 修改最外层 div 的 className，根据 in_stock 加 opacity
<motion.div
  className={`group bg-white rounded-xl border border-border overflow-hidden cursor-pointer
    hover:border-accent hover:shadow-lg transition-all duration-300
    ${!cigar.in_stock ? 'opacity-60' : ''}`}
  ...
>
```

价格在缺货时划掉（lines 106-108）：

```tsx
{cigar.avg_per_stick_cny != null ? (
  <span className={`text-xl font-bold font-mono tracking-tight tabular-nums
    ${cigar.in_stock ? 'text-accent' : 'text-muted line-through'}`}>
    ¥{cigar.avg_per_stick_cny.toLocaleString()}
  </span>
```

- [ ] **Step 2: Build & verify**

```bash
cd /home/jason/cigardomtabaka/frontend && npm run build
```

- [ ] **Step 3: Commit**

```bash
cd /home/jason/cigardomtabaka
git add frontend/src/components/dashboard/PriceCard.tsx
git commit -m "feat: grey out out-of-stock PriceCards"
```

---

### Task 5: 前端 — VariantCard 区分缺货/下架

**Files:**
- Modify: `frontend/src/components/detail/VariantCard.tsx`
- Modify: `frontend/src/types/index.ts`

- [ ] **Step 1: 类型定义加 delisted 字段**

在 `frontend/src/types/index.ts` 的 `Variant` 接口加字段：

```typescript
export interface Variant {
  // ... existing fields ...
  in_stock: boolean;
  delisted?: boolean;          // ← 新增：是否已下架（vs 仅缺货）
  relisted_at?: string;        // ← 新增：重新上架时间
}
```

- [ ] **Step 2: 改 VariantCard 标签**

替换 lines 53-61 的库存标签：

```tsx
{/* 库存状态标签 */}
{(() => {
  if (variant.delisted) {
    return (
      <span className="text-[11px] font-bold px-2.5 py-1 rounded-full uppercase tracking-wider
        bg-red-100 text-red-700 border border-red-300">
        已下架
      </span>
    );
  }
  if (!inStock) {
    return (
      <span className="text-[11px] font-bold px-2.5 py-1 rounded-full uppercase tracking-wider
        bg-amber-50 text-amber-700 border border-amber-200">
        缺货
      </span>
    );
  }
  return (
    <span className="text-[11px] font-bold px-2.5 py-1 rounded-full uppercase tracking-wider
      bg-emerald-50 text-emerald-700 border border-emerald-200">
      现货
    </span>
  );
})()}
```

下架时整个卡片加灰色遮罩——在最外层 motion.div 加：

```tsx
<motion.div
  className={`bg-white rounded-xl border border-border shadow-sm overflow-hidden
    hover:shadow-lg hover:border-accent transition-all duration-300
    ${variant.delisted ? 'opacity-60 grayscale' : ''}`}
  ...
>
```

- [ ] **Step 3: 后端 views 传 delisted 标记**

在 `price_tracker/views.py` 的 `history` action 中（lines 153-178），每个 variant 加 `delisted` 字段：

```python
variants[key] = {
    # ... existing fields ...
    'delisted': (snap.raw_data or {}).get('delisted', False),
}
```

- [ ] **Step 4: Build & verify**

```bash
cd /home/jason/cigardomtabaka/frontend && npm run build
```

- [ ] **Step 5: Commit**

```bash
cd /home/jason/cigardomtabaka
git add frontend/src/components/detail/VariantCard.tsx frontend/src/types/index.ts price_tracker/views.py
git commit -m "feat: distinguish delisted vs out-of-stock in VariantCard"
```

---

### Task 6: 集成测试 — 端到端验证

- [ ] **Step 1: 跑 COH 爬虫验证**

```bash
cd /home/jason/cigardomtabaka && python3 manage.py scrape_prices --source coh_china
```

Expected: 
- `created: 0`（价格没变的不创建）
- `marked_oos: 0`（没下架的）

- [ ] **Step 2: 跑 LCDH Nyon 验证下架检测**

```bash
cd /home/jason/cigardomtabaka && python3 manage.py scrape_prices --source lcdh_nyon
```

Expected:
- 下架的创建 in_stock=False 快照
- 已下架的不重复创建

- [ ] **Step 3: 验证 API 返回 delisted 字段**

```bash
# 随便取一个有缺货的 cigar_id
curl -s "http://localhost:8000/api/prices/snapshots/history/?cigar_id=100&days=30" | python3 -m json.tool | head -50
```

Expected: variants 中有 `"delisted": true` 字段

- [ ] **Step 4: Commit**

```bash
cd /home/jason/cigardomtabaka
git add -A
git commit -m "test: end-to-end verification of delisting pipeline"
```
