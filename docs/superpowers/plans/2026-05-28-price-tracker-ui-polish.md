# 价格监控UI打磨 实施计划

> **For agentic workers:** 直接按Task顺序执行，每步checkbox勾上。

**Goal:** 详情页展示全名/汇率、主页来源计数、特别release pill、在售pill换色、走势图双模式切换

**Architecture:** 后端加 `release_type_cn` 和全名拼装 → 前端5文件改展示逻辑

**Tech Stack:** Django DRF + React/TypeScript + Tailwind + Recharts

---

### Task 1: 后端 history 接口加 release_type_cn + 全名

**Files:**
- Modify: `price_tracker/views.py:199-206`

- [ ] **Step 1: 修改 history 响应，加 release_type_cn 和全名**

```python
# views.py history 方法，替换返回的 Response 部分
release_type_cn = cigar.release_type_cn if cigar else None
full_name = cigar.name or cigar.english_name or ''
if release_type_cn:
    full_name = f'{full_name} · {release_type_cn}'

return Response({
    'cigar_id': int(cigar_id),
    'cigar_brand': cigar.brand if cigar else None,
    'cigar_brand_cn': brand_cn,
    'cigar_name': full_name,
    'cigar_name_en': cigar.english_name if cigar else None,
    'release_type_cn': release_type_cn,
    'variants': list(variants.values()),
})
```

- [ ] **Step 2: 验证**

```bash
cd /home/jason/cigardomtabaka && python3 -c "
import os; os.environ.setdefault('DJANGO_SETTINGS_MODULE','cigardomtabaka_backend.settings')
import django; django.setup()
from price_tracker.models import PriceSnapshot
# 找个有 release_type 的 cigar
for s in PriceSnapshot.objects.select_related('cigar').filter(cigar__release_type_cn__gt='')[:3]:
    print(f'{s.cigar.english_name} → release: {s.cigar.release_type_cn}')
"
```

---

### Task 2: 后端 list_aggregated 加 release_type_cn

**Files:**
- Modify: `price_tracker/views.py:266-276`

- [ ] **Step 1: 在 cigars_map 构建中加入 release_type_cn**

在 `list_aggregated` 方法中，`cigars_map[cid]` 字典里加一行：

```python
'release_type_cn': snap.cigar.release_type_cn or '',
```

同时拼全名：

```python
rt = snap.cigar.release_type_cn or ''
'cigar_name': (snap.cigar.name or snap.cigar.english_name or '') + (f' · {rt}' if rt else ''),
```

---

### Task 3: 前端类型定义更新

**Files:**
- Modify: `frontend/src/types/index.ts`

- [ ] **Step 1: PriceHistoryResponse 加字段**

```typescript
export interface PriceHistoryResponse {
  cigar_id: number;
  cigar_name: string;
  cigar_name_en?: string;
  cigar_brand?: string;
  cigar_brand_cn?: string;
  release_type_cn?: string;  // 新增
  variants: Variant[];
}
```

- [ ] **Step 2: CigarListItem 加字段**

```typescript
export interface CigarListItem {
  cigar_id: number;
  cigar_name: string;
  cigar_name_en: string;
  cigar_brand: string;
  cigar_brand_cn: string;
  cigar_image_url: string;
  release_type_cn?: string;  // 新增
  sources: { ... }[];
  in_stock: boolean;
  avg_per_stick_cny: number | null;
}
```

---

### Task 4: PriceCard 改三处（来源计数 + 在售pill + release pill）

**Files:**
- Modify: `frontend/src/components/dashboard/PriceCard.tsx`

- [ ] **Step 1: 来源计数替换 SourceTag**

删除 107-112 行的 SourceTag 循环，替换为：

```tsx
{/* 来源计数 */}
<div className="flex items-center gap-1.5 text-[0.7rem] text-muted">
  <span className="font-semibold text-accent">{sourceSlugs.length}</span>
  <span>个网站有售</span>
</div>
```

同时顶部删掉 `import { SourceTag }`，不再需要。

- [ ] **Step 2: 在售pill换色**

将 59-64 行的 stone-900 改为 emerald：

```tsx
{cigar.in_stock && (
  <div className="absolute top-2.5 right-2.5 flex items-center gap-1.5
    bg-emerald-50 text-emerald-700 border border-emerald-200 text-[0.65rem] font-semibold
    px-2.5 py-1 rounded-full">
    <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
    在售
  </div>
)}
```

- [ ] **Step 3: 特别release pill（在在售pill下方）**

在在售pill后面（图片区域），加release pill：

```tsx
{/* 特别款标识 */}
{cigar.release_type_cn && (
  <div className="absolute top-2.5 left-2.5
    bg-amber-100 text-amber-800 border border-amber-300 text-[0.6rem] font-bold
    px-2 py-0.5 rounded-full uppercase tracking-wide">
    {cigar.release_type_cn}
  </div>
)}
```

注意：release pill在左边（`left-2.5`），在售pill在右边（`right-2.5`），不冲突。

---

### Task 5: DetailHeader 加 release pill

**Files:**
- Modify: `frontend/src/components/detail/DetailHeader.tsx`

- [ ] **Step 1: 在品牌pill旁边加 release pill**

```tsx
{(data.cigar_brand_cn || data.cigar_brand) && (
  <div className="flex items-center gap-2 mb-3">
    <span className="inline-block text-[0.7rem] text-accent uppercase tracking-widest font-semibold
      px-3 py-1 bg-accent-light border border-accent rounded-full">
      {data.cigar_brand_cn || data.cigar_brand}
    </span>
    {data.release_type_cn && (
      <span className="inline-block text-[0.65rem] font-bold text-amber-800 bg-amber-100 
        border border-amber-300 px-2.5 py-0.5 rounded-full uppercase tracking-wide">
        {data.release_type_cn}
      </span>
    )}
  </div>
)}
```

---

### Task 6: VariantCard 删原币种fallback

**Files:**
- Modify: `frontend/src/components/detail/VariantCard.tsx:98-107`

- [ ] **Step 1: 删除 never-reached fallback 分支**

当前第98-107行：
```tsx
{!priceCny && !pricePerStick && (
  <div>...</div>
)}
```

这个分支因为DB里price_cny全有，永远走不到。直接删掉。

---

### Task 7: PriceChart 加双模式切换

**Files:**
- Modify: `frontend/src/components/detail/PriceChart.tsx`
- Modify: `frontend/src/utils/priceData.ts`

- [ ] **Step 1: priceData.ts — buildChartData 支持双模式**

```typescript
/** 
 * 为价格走势图构建数据
 * @param mode 'original' = 原币种 | 'cny_per_stick' = 单支人民币
 */
export function buildChartData(variants: Variant[], mode: 'original' | 'cny_per_stick' = 'cny_per_stick') {
  const dateMap: Record<string, Record<string, number | string>> = {};
  variants.forEach((v) => {
    const currency = v.currency || 'USD';
    const label = mode === 'original' 
      ? `${v.source_short_name || v.source_name} ${v.box_label} · ${currency}`
      : `${v.source_short_name || v.source_name} ${v.box_label} · ¥`;
    (v.points || []).forEach((p) => {
      const date = p.date?.split('T')[0] || p.date;
      if (!dateMap[date]) dateMap[date] = { date };
      if (mode === 'original') {
        dateMap[date][label] = p.price;
      } else {
        // 单支人民币 = price_cny / box_size
        const bs = v.box_size || 1;
        dateMap[date][label] = p.price_cny != null ? +(p.price_cny / bs).toFixed(2) : null;
      }
    });
  });
  return Object.values(dateMap).sort((a, b) =>
    (a.date as string).localeCompare(b.date as string)
  );
}
```

- [ ] **Step 2: PriceChart.tsx — 加 toggle + state**

```tsx
import { useState } from 'react';
// ...

export function PriceChart({ variants }: PriceChartProps) {
  const [mode, setMode] = useState<'original' | 'cny_per_stick'>('original');
  const chartData = buildChartData(variants, mode);
  if (chartData.length === 0) return null;

  const isCny = mode === 'cny_per_stick';

  return (
    <motion.div ...>
      {/* Header + Toggle */}
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-bold text-fg uppercase tracking-widest">
          价格走势{isCny ? '（单支人民币）' : '（原币种）'}
        </h3>
        <button
          onClick={() => setMode(m => m === 'original' ? 'cny_per_stick' : 'original')}
          className="text-xs font-semibold px-3 py-1.5 rounded-full border transition-colors
            bg-accent-light text-accent border-accent hover:bg-accent hover:text-white"
        >
          {isCny ? '查看原币种' : '换算单支¥'}
        </button>
      </div>
      
      {/* YAxis formatter */}
      <YAxis
        ...
        tickFormatter={(v: number) => isCny ? `¥${v.toLocaleString()}` : v.toLocaleString()}
      />
      {/* Tooltip formatter */}
      <Tooltip
        ...
        formatter={(value: number) => [isCny ? `¥${value.toLocaleString()}` : value.toLocaleString()]}
      />
    </motion.div>
  );
}
```

---

### Task 8: 构建 + 部署 + 验证

- [ ] **Step 1: 构建前端**

```bash
cd /home/jason/cigardomtabaka/frontend && npm run build
```

- [ ] **Step 2: 重启 Django**

```bash
kill $(pgrep -f "manage.py runserver") 2>/dev/null
cd /home/jason/cigardomtabaka && python3 manage.py runserver 0.0.0.0:8000 --noreload &
sleep 2
```

- [ ] **Step 3: 验证API**

```bash
# 验证 history 接口有 release_type_cn
curl -s -u admin:admin 'http://localhost:8000/api/prices/snapshots/history/?cigar_id=1&days=30' | python3 -m json.tool | head -15

# 验证 list_aggregated 有 release_type_cn
curl -s -u admin:admin 'http://localhost:8000/api/prices/snapshots/list/' | python3 -m json.tool | head -20
```

- [ ] **Step 4: 浏览器验证**

打开 `/prices/`，检查：
- PriceCard上显示「N个网站有售」
- 在售pill绿色
- 有release_type的雪茄左上角有amber pill
- 点进详情，DetailHeader显示全名+release pill
- 价格走势图有toggle按钮，默认原币种，可以切单支¥
