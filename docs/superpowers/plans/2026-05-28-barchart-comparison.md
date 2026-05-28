# PriceChart 改为柱状对比 + 线图走势

> **For agentic workers:** 直接改 PriceChart.tsx，步骤用 checkbox (`- [ ]`) 跟踪。

**Goal:** 上面的"单支价格对比"从线图改为柱状图（BarChart），每个 variant 一根柱子，直观对比当前单支¥；下面"原币种走势"保持线图不变。

**Architecture:** 两个 recharts chart：BarChart（单支对比） + LineChart（原币种走势）。数据从 Variant 数组提取，柱状图用最新单支 CNY 价格，线图用历史走势数据。

**Tech Stack:** React + TypeScript + recharts + Tailwind CSS

---

### Task 1: 重写 PriceChart.tsx — 上柱下线的双图布局

**Files:**
- Modify: `frontend/src/components/detail/PriceChart.tsx`

- [ ] **Step 1: 改标题和图表类型**

把上面的"单支价格走势"线图完全替换为 recharts BarChart：

```tsx
import { BarChart, Bar, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
```

顶部卡片：
- 标题改为 `单支价格对比 · ¥`
- 去掉价格摘要 pills（柱状图本身就已经是最直观的对比）
- 用 BarChart，每条 variant 一根柱子
- Y轴 ¥/支，X轴 variant 名称

底部卡片保持不变（原币种走势线图）。

- [ ] **Step 2: 构建柱状图数据**

```tsx
// 从 variants 提取当前单支 CNY 价格作为柱状图数据
function buildBarData(variants: Variant[]) {
  return variants.map((v, i) => {
    const points = v.points || [];
    const latest = points[points.length - 1];
    const bs = v.box_size || 1;
    const perStick = latest && latest.price_cny != null 
      ? +(latest.price_cny / bs).toFixed(2) 
      : (v.price_per_stick ?? 0);
    return {
      name: `${v.source_short_name || v.source_name} ${v.box_label}`,
      price: perStick,
      color: COLORS[i % COLORS.length],
    };
  });
}
```

- [ ] **Step 3: 渲染柱状图**

```tsx
{cnyData.length > 0 && (
  <motion.div ...>
    <h3>单支价格对比 · ¥</h3>
    <ResponsiveContainer width="100%" height={380}>
      <BarChart data={barData} margin={{ top: 10, right: 20, bottom: 60, left: 20 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#F0EDE8" vertical={false} />
        <XAxis
          dataKey="name"
          stroke="#A8A29E"
          tick={{ fontSize: 11, fill: '#78716C' }}
          tickLine={false}
          axisLine={{ stroke: '#E8E4DF' }}
          angle={-20}
          textAnchor="end"
          interval={0}
        />
        <YAxis
          stroke="#A8A29E"
          tick={{ fontSize: 12, fill: '#A8A29E' }}
          tickLine={false}
          axisLine={false}
          tickFormatter={(v: number) => `¥${v}`}
          width={55}
        />
        <Tooltip
          contentStyle={{ background: '#fff', border: '1px solid #E8E4DF', borderRadius: 12 }}
          formatter={(value: number) => [`¥${value.toLocaleString()}`, '单支价格']}
        />
        <Bar
          dataKey="price"
          radius={[6, 6, 0, 0]}
          maxBarSize={64}
        >
          {/* Each bar gets its own color */}
          {barData.map((entry, idx) => (
            <Cell key={idx} fill={entry.color} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  </motion.div>
)}
```

注意：recharts Bar 需要 `Cell` 来分别上色。

- [ ] **Step 4: 底部原币种走势保持不变**

直接用现有的 LineChart 代码，数据用 `buildChartData(variants, 'original')`，标签、网格、tooltip 都不动。

- [ ] **Step 5: 构建验证**

```bash
cd /home/jason/moscow_cigar/frontend && npm run build
```

确认无 TS 错误，构建成功。

- [ ] **Step 6: 浏览器验证**

1. 重启 Django（kill + runserver）
2. 打开 `/prices/cigar/95/` 详情页
3. 确认：上图是柱状图，每根柱颜色不同，Y轴 ¥/支；下图是原币种线图
4. 确认：柱状图 X 轴标签不重叠

- [ ] **Step 7: 提交**

```bash
git add -A && git commit -m "feat: replace per-stick line chart with bar chart for price comparison"
```
