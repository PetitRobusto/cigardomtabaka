import { useState, useEffect } from 'react';
import { BarChart, Bar, Cell, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { motion } from 'framer-motion';
import type { Variant } from '../../types';
import { buildChartData, variantLabel } from '../../utils/priceData';

function useIsMobile() {
  const [isMobile, setIsMobile] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia('(max-width: 640px)');
    const handler = (e: MediaQueryListEvent | MediaQueryList) => setIsMobile(e.matches);
    handler(mq);
    mq.addEventListener('change', handler);
    return () => mq.removeEventListener('change', handler);
  }, []);
  return isMobile;
}

const COLORS = [
  '#A16207', '#c0392b', '#2c3e50', '#27ae60', '#8e44ad',
  '#e67e22', '#2980b9', '#16a085', '#d35400', '#7f8c8d',
  '#1abc9c', '#9b59b6', '#f39c12', '#e74c3c', '#34495e',
];

interface PriceChartProps {
  variants: Variant[];
}

interface BarDatum {
  name: string;
  price: number;
  color: string;
  tag: string | null;
}

/** 从 variants 提取当前单支 CNY 价格用于柱状图对比 */
function buildBarData(variants: Variant[]): BarDatum[] {
  const raw = variants.map((v, i) => {
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
      tag: null as string | null,
    };
  });

  if (raw.length === 0) return raw;

  const prices = raw.map((d) => d.price);
  const max = Math.max(...prices);
  const min = Math.min(...prices);
  const avg = prices.reduce((a, b) => a + b, 0) / prices.length;

  // 找到最接近平均价的值
  let closestDelta = Math.abs(prices[0] - avg);
  for (const p of prices) {
    const d = Math.abs(p - avg);
    if (d < closestDelta) {
      closestDelta = d;
    }
  }

  // 只在多于 1 根柱子时标注（否则全一样）
  const unique = new Set(prices);
  if (unique.size <= 1) return raw;

  // 标注策略：先标最高/最低，再标最接近平均（避免重复）
  const usedTags = new Set<string>();
  for (const d of raw) {
    if (d.price === max && !usedTags.has('最高')) {
      d.tag = '最高';
      usedTags.add('最高');
    } else if (d.price === min && !usedTags.has('最低')) {
      d.tag = '最低';
      usedTags.add('最低');
    }
  }
  // 最接近平均 —— 排除已标记的，找最接近的
  if (unique.size >= 3 && !usedTags.has('均价')) {
    let bestIdx = -1;
    let bestDelta = Infinity;
    for (let i = 0; i < raw.length; i++) {
      if (raw[i].tag) continue; // 已被标为最高/最低
      const d = Math.abs(raw[i].price - avg);
      if (d < bestDelta) { bestDelta = d; bestIdx = i; }
    }
    if (bestIdx >= 0) {
      raw[bestIdx].tag = '均价';
    }
  }

  return raw;
}

export function PriceChart({ variants }: PriceChartProps) {
  const isMobile = useIsMobile();
  const barHeight = isMobile ? 240 : 380;
  const lineHeight = isMobile ? 200 : 280;
  const chartMargin = isMobile
    ? { top: 32, right: 4, bottom: 40, left: 4 }
    : { top: 40, right: 20, bottom: 60, left: 20 };
  const tickFontSize = isMobile ? 9 : 11;
  const maxBarSize = isMobile ? 40 : 64;

  const barData = buildBarData(variants);
  const originalData = buildChartData(variants, 'original');

  if (originalData.length === 0 && barData.length === 0) return null;

  return (
    <>
      {/* ===== 单支价格对比 · ¥ — 柱状图 ===== */}
      {barData.length > 0 && (
        <motion.div
          className="bg-white rounded-xl border border-accent/20 shadow-md p-5 mb-6"
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, delay: 0.05 }}
        >
          <h3 className="text-sm font-bold text-accent uppercase tracking-widest mb-4">
            单支价格对比 · ¥
          </h3>
          <ResponsiveContainer width="100%" height={barHeight}>
            <BarChart data={barData} margin={chartMargin}>
              <CartesianGrid strokeDasharray="3 3" stroke="#F0EDE8" vertical={false} />
              <XAxis
                dataKey="name"
                stroke="#A8A29E"
                tick={{ fontSize: tickFontSize, fill: '#78716C' }}
                tickLine={false}
                axisLine={{ stroke: '#E8E4DF' }}
                angle={isMobile ? -45 : -20}
                textAnchor="end"
                interval={isMobile ? 'preserveStartEnd' : 0}
                height={isMobile ? 50 : 60}
              />
              <YAxis
                stroke="#A8A29E"
                tick={{ fontSize: isMobile ? 9 : 12, fill: '#A8A29E' }}
                tickLine={false}
                axisLine={false}
                tickFormatter={(v: number) => (isMobile ? `¥${Math.round(v)}` : `¥${v}`)}
                width={isMobile ? 35 : 55}
              />
              <Tooltip
                contentStyle={{
                  background: '#fff',
                  border: '1px solid #E8E4DF',
                  borderRadius: 12,
                  boxShadow: '0 4px 20px rgba(28,25,23,0.08)',
                }}
                labelStyle={{ color: '#1C1917', fontWeight: 700, fontSize: 13 }}
                itemStyle={{ fontSize: 13 }}
                formatter={(value) => {
                  // Recharts 可能传入非数值占位，先收窄再格式化。
                  if (typeof value !== 'number') return ['—', '单支价格'];
                  return [`¥${value.toLocaleString()}`, '单支价格'];
                }}
              />
              <Bar dataKey="price" radius={[isMobile ? 3 : 6, isMobile ? 3 : 6, 0, 0]} maxBarSize={maxBarSize}
                label={({ x, y, width, value, index }) => {
                  if (
                    typeof index !== 'number'
                    || typeof x !== 'number'
                    || typeof y !== 'number'
                    || typeof width !== 'number'
                    || typeof value !== 'number'
                  ) return null;
                  const tag = barData[index]?.tag;
                  if (!tag) return null;
                  const colors: Record<string, string> = {
                    '最高': '#dc2626',
                    '最低': '#16a34a',
                    '均价': '#78716C',
                  };
                  return (
                    <text
                      x={x + width / 2}
                      y={y - 8}
                      textAnchor="middle"
                      fill={colors[tag] || '#78716C'}
                      fontSize={11}
                      fontWeight={700}
                    >
                      {tag} ¥{value.toLocaleString()}
                    </text>
                  );
                }}
              >
                {barData.map((entry, idx) => (
                  <Cell key={idx} fill={entry.color} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </motion.div>
      )}

      {/* ===== 原币种走势 — 线图 ===== */}
      {originalData.length > 0 && (
        <motion.div
          className="bg-white rounded-xl border border-border shadow-sm p-5 mb-8"
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, delay: 0.15 }}
        >
          <h3 className="text-sm font-bold text-fg uppercase tracking-widest mb-4">
            原币种走势
          </h3>
          <ResponsiveContainer width="100%" height={lineHeight}>
            <LineChart data={originalData} margin={chartMargin}>
              <CartesianGrid strokeDasharray="3 3" stroke="#F0EDE8" />
              <XAxis
                dataKey="date"
                stroke="#A8A29E"
                tick={{ fontSize: isMobile ? 9 : 12, fill: '#A8A29E' }}
                tickLine={false}
                axisLine={{ stroke: '#E8E4DF' }}
              />
              <YAxis
                stroke="#A8A29E"
                tick={{ fontSize: isMobile ? 9 : 12, fill: '#A8A29E' }}
                tickLine={false}
                axisLine={false}
                tickFormatter={(v: number) => v.toLocaleString()}
                width={isMobile ? 35 : 55}
              />
              <Tooltip
                contentStyle={{
                  background: '#fff',
                  border: '1px solid #E8E4DF',
                  borderRadius: 12,
                  boxShadow: '0 4px 20px rgba(28,25,23,0.08)',
                }}
                labelStyle={{ color: '#1C1917', fontWeight: 700, fontSize: 13 }}
                itemStyle={{ fontSize: 13 }}
              />
              <Legend wrapperStyle={{ fontSize: 12, paddingTop: 12, color: '#78716C' }} />
              {variants.map((v, i) => (
                <Line
                  key={`${v.source_slug}__${v.box_size}`}
                  type="monotone"
                  dataKey={variantLabel(v, 'original')}
                  stroke={COLORS[i % COLORS.length]}
                  strokeWidth={isMobile ? 1.5 : 2.5}
                  dot={isMobile ? false : { r: 3, strokeWidth: 1.5, fill: '#fff' }}
                  activeDot={isMobile ? { r: 4 } : { r: 5, strokeWidth: 2.5 }}
                  connectNulls
                  name={variantLabel(v, 'original')}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </motion.div>
      )}
    </>
  );
}
