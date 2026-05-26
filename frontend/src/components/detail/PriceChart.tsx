import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
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

export function PriceChart({ variants }: PriceChartProps) {
  const chartData = buildChartData(variants);
  if (chartData.length === 0) return null;

  return (
    <div className="bg-white rounded-lg border border-[#E8E4DF] shadow-sm p-5 mb-8">
      <h3 className="text-sm font-bold text-[#1C1917] uppercase tracking-widest mb-4">
        价格走势
      </h3>
      <ResponsiveContainer width="100%" height={380}>
        <LineChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" stroke="#F0EDE8" />
          <XAxis
            dataKey="date"
            stroke="#A8A29E"
            tick={{ fontSize: 12, fill: '#A8A29E' }}
            tickLine={false}
            axisLine={{ stroke: '#E8E4DF' }}
          />
          <YAxis
            stroke="#A8A29E"
            tick={{ fontSize: 12, fill: '#A8A29E' }}
            tickLine={false}
            axisLine={false}
          />
          <Tooltip
            contentStyle={{
              background: '#fff',
              border: '1px solid #E8E4DF',
              borderRadius: 8,
              boxShadow: '0 4px 20px rgba(28,25,23,0.08)',
            }}
            labelStyle={{ color: '#1C1917', fontWeight: 700, fontSize: 13 }}
            itemStyle={{ fontSize: 13 }}
          />
          <Legend
            wrapperStyle={{ fontSize: 12, paddingTop: 12, color: '#78716C' }}
          />
          {variants.map((v, i) => (
            <Line
              key={`${v.source_slug}__${v.box_size}`}
              type="monotone"
              dataKey={variantLabel(v)}
              stroke={COLORS[i % COLORS.length]}
              strokeWidth={2.5}
              dot={{ r: 3, strokeWidth: 1.5, fill: '#fff' }}
              activeDot={{ r: 5, strokeWidth: 2.5 }}
              connectNulls
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
