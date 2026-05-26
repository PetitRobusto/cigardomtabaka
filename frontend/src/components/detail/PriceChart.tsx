import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import type { Variant } from '../../types';
import { buildChartData, variantLabel } from '../../utils/priceData';

const COLORS = [
  '#8B6914', '#c0392b', '#2c3e50', '#27ae60', '#8e44ad',
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
    <div className="bg-white rounded-md border border-stone-100 shadow-sm p-4 mb-8">
      <ResponsiveContainer width="100%" height={400}>
        <LineChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" stroke="#E7E5E4" />
          <XAxis
            dataKey="date"
            stroke="#78716C"
            tick={{ fontSize: 14, fill: '#78716C' }}
            tickLine={false}
          />
          <YAxis
            stroke="#78716C"
            tick={{ fontSize: 14, fill: '#78716C' }}
            tickLine={false}
            axisLine={false}
          />
          <Tooltip
            contentStyle={{
              background: '#fff',
              border: '1px solid #D6D3D1',
              borderRadius: 8,
              boxShadow: '0 4px 16px rgba(12,10,9,0.08)',
            }}
            labelStyle={{ color: '#1C1917', fontWeight: 600 }}
            itemStyle={{ fontSize: 13 }}
          />
          <Legend
            wrapperStyle={{ fontSize: 13, paddingTop: 8 }}
          />
          {variants.map((v, i) => (
            <Line
              key={`${v.source_slug}__${v.box_size}`}
              type="monotone"
              dataKey={variantLabel(v)}
              stroke={COLORS[i % COLORS.length]}
              strokeWidth={2}
              dot={{ r: 3, strokeWidth: 1, fill: '#fff' }}
              activeDot={{ r: 5, strokeWidth: 2 }}
              connectNulls
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
