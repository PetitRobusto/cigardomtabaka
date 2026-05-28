import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { motion } from 'framer-motion';
import type { Variant } from '../../types';
import { buildChartData, variantLabel } from '../../utils/priceData';

const COLORS = [
  '#A16207', '#c0392b', '#2c3e50', '#27ae60', '#8e44ad',
  '#e67e22', '#2980b9', '#16a085', '#d35400', '#7f8c8d',
  '#1abc9c', '#9b59b6', '#f39c12', '#e74c3c', '#34495e',
];

interface PriceChartProps {
  variants: Variant[];
}

/** 从 chartData 中提取每个 variant 的最新有效价格 */
function extractLatestPrices(
  variants: Variant[],
  chartData: Record<string, unknown>[],
  mode: 'original' | 'cny_per_stick',
): { key: string; label: string; price: number; color: string; currency?: string }[] {
  const result: { key: string; label: string; price: number; color: string; currency?: string }[] = [];
  variants.forEach((v, i) => {
    const dk = variantLabel(v, mode);
    for (let j = chartData.length - 1; j >= 0; j--) {
      const val = chartData[j][dk];
      if (val != null && typeof val === 'number') {
        result.push({
          key: dk,
          label: `${v.source_short_name || v.source_name} ${v.box_label}`,
          price: val,
          color: COLORS[i % COLORS.length],
          currency: mode === 'cny_per_stick' ? '¥' : v.currency,
        });
        break;
      }
    }
  });
  return result;
}

export function PriceChart({ variants }: PriceChartProps) {
  const cnyData = buildChartData(variants, 'cny_per_stick');
  const originalData = buildChartData(variants, 'original');

  if (originalData.length === 0 && cnyData.length === 0) return null;

  const latestStick = extractLatestPrices(variants, cnyData, 'cny_per_stick');
  const latestOriginal = extractLatestPrices(variants, originalData, 'original');

  const sharedGrid = <CartesianGrid strokeDasharray="3 3" stroke="#F0EDE8" />;
  const sharedX = (
    <XAxis
      dataKey="date"
      stroke="#A8A29E"
      tick={{ fontSize: 12, fill: '#A8A29E' }}
      tickLine={false}
      axisLine={{ stroke: '#E8E4DF' }}
    />
  );
  const sharedTooltip = (prefix?: string) => (
    <Tooltip
      contentStyle={{
        background: '#fff',
        border: '1px solid #E8E4DF',
        borderRadius: 12,
        boxShadow: '0 4px 20px rgba(28,25,23,0.08)',
      }}
      labelStyle={{ color: '#1C1917', fontWeight: 700, fontSize: 13 }}
      itemStyle={{ fontSize: 13 }}
      formatter={(value: number) => [
        prefix ? `${prefix}${value.toLocaleString()}` : value.toLocaleString(),
      ]}
    />
  );
  const sharedLegend = (
    <Legend wrapperStyle={{ fontSize: 12, paddingTop: 12, color: '#78716C' }} />
  );

  return (
    <>
      {/* ===== 单支价格走势 · ¥ ===== */}
      {cnyData.length > 0 && (
        <motion.div
          className="bg-white rounded-xl border border-accent/20 shadow-md p-5 mb-6"
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, delay: 0.05 }}
        >
          <h3 className="text-sm font-bold text-accent uppercase tracking-widest mb-3">
            单支价格走势 · ¥
          </h3>

          {/* Current price summary */}
          {latestStick.length > 0 && (
            <div className="flex flex-wrap gap-2 mb-4">
              {latestStick.map((item) => (
                <span
                  key={item.key}
                  className="inline-flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-full border"
                  style={{ borderColor: item.color, color: item.color, backgroundColor: `${item.color}10` }}
                >
                  <span className="w-2 h-2 rounded-full" style={{ backgroundColor: item.color }} />
                  {item.label}
                  <span className="tabular-nums font-bold">¥{item.price.toLocaleString()}</span>
                </span>
              ))}
            </div>
          )}

          <ResponsiveContainer width="100%" height={380}>
            <LineChart data={cnyData} margin={{ right: 20 }}>
              {sharedGrid}
              {sharedX}
              <YAxis
                stroke="#A8A29E"
                tick={{ fontSize: 12, fill: '#A8A29E' }}
                tickLine={false}
                axisLine={false}
                tickFormatter={(v: number) => `¥${v}`}
                width={55}
              />
              {sharedTooltip('¥')}
              {sharedLegend}
              {variants.map((v, i) => (
                <Line
                  key={`${v.source_slug}__${v.box_size}`}
                  type="monotone"
                  dataKey={variantLabel(v, 'cny_per_stick')}
                  stroke={COLORS[i % COLORS.length]}
                  strokeWidth={2.5}
                  dot={{ r: 3, strokeWidth: 1.5, fill: '#fff' }}
                  activeDot={{ r: 5, strokeWidth: 2.5 }}
                  connectNulls
                  name={variantLabel(v, 'cny_per_stick')}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </motion.div>
      )}

      {/* ===== 原币种走势 ===== */}
      {originalData.length > 0 && (
        <motion.div
          className="bg-white rounded-xl border border-border shadow-sm p-5 mb-8"
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, delay: 0.15 }}
        >
          <h3 className="text-sm font-bold text-fg uppercase tracking-widest mb-3">
            原币种走势
          </h3>

          {/* Current price summary */}
          {latestOriginal.length > 0 && (
            <div className="flex flex-wrap gap-2 mb-4">
              {latestOriginal.map((item) => (
                <span
                  key={item.key}
                  className="inline-flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-full border border-border bg-white text-muted"
                >
                  <span className="w-2 h-2 rounded-full" style={{ backgroundColor: item.color }} />
                  {item.label.replace(/ · (USD|CHF|EUR|GBP)$/, '')}
                  <span className="tabular-nums font-bold text-fg">
                    {item.currency} {item.price.toLocaleString()}
                  </span>
                </span>
              ))}
            </div>
          )}

          <ResponsiveContainer width="100%" height={280}>
            <LineChart data={originalData}>
              {sharedGrid}
              {sharedX}
              <YAxis
                stroke="#A8A29E"
                tick={{ fontSize: 12, fill: '#A8A29E' }}
                tickLine={false}
                axisLine={false}
                tickFormatter={(v: number) => v.toLocaleString()}
                width={55}
              />
              {sharedTooltip()}
              {sharedLegend}
              {variants.map((v, i) => (
                <Line
                  key={`${v.source_slug}__${v.box_size}`}
                  type="monotone"
                  dataKey={variantLabel(v, 'original')}
                  stroke={COLORS[i % COLORS.length]}
                  strokeWidth={2.5}
                  dot={{ r: 3, strokeWidth: 1.5, fill: '#fff' }}
                  activeDot={{ r: 5, strokeWidth: 2.5 }}
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
