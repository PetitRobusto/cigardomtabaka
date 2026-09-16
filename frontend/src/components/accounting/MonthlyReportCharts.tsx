import { Cell, Pie, PieChart, Tooltip } from 'recharts';
import { formatCostCny } from './monthlyReportFormat';

const REPORT_CHART_COLORS = [
  '#7A1F2E', '#B87A3A', '#466681', '#3D6B4F', '#A75B27', '#8A7E6E',
];

export interface DonutItem {
  name: string;
  value: number;
  color?: string;
}

export function DonutBreakdown({ items, totalLabel }: { items: DonutItem[]; totalLabel: string }) {
  const chartItems = items.map((item, index) => ({
    ...item,
    value: Math.max(0, item.value) || 0,
    color: item.color || REPORT_CHART_COLORS[index % REPORT_CHART_COLORS.length],
  }));
  const total = chartItems.reduce((sum, item) => sum + item.value, 0);

  return (
    <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
      <div className="relative mx-auto h-44 w-44 shrink-0" role="img" aria-label={`${totalLabel}环形图，合计${formatCostCny(total)}`}>
          <PieChart width={176} height={176}>
            <Pie
              data={total > 0 ? chartItems : [{ name: '暂无数据', value: 1, color: '#E8E0D6' }]}
              dataKey="value"
              nameKey="name"
              cx="50%"
              cy="50%"
              innerRadius={53}
              outerRadius={76}
              paddingAngle={total > 0 ? 2 : 0}
              stroke="none"
              isAnimationActive={false}
            >
              {(total > 0 ? chartItems : [{ color: '#E8E0D6' }]).map((item, index) => (
                <Cell key={`${item.color}-${index}`} fill={item.color} />
              ))}
            </Pie>
            {total > 0 && <Tooltip formatter={(value) => formatCostCny(Number(value))} />}
          </PieChart>
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center text-center">
          <span className="text-[10px] text-muted">{totalLabel}</span>
          <span className="mt-1 font-mono text-sm font-semibold">{formatCostCny(total)}</span>
        </div>
      </div>
      <div className="min-w-0 flex-1">
        {chartItems.map(item => {
          const percent = total > 0 ? item.value / total * 100 : 0;
          return (
            <div key={item.name} className="flex items-center gap-2 border-b border-dashed border-border py-1.5 last:border-b-0">
              <span className="h-2.5 w-2.5 shrink-0 rounded-sm" style={{ backgroundColor: item.color }} />
              <span className="min-w-0 flex-1 text-xs">{item.name}</span>
              <span className="font-mono text-[11px] text-muted">{percent.toFixed(1)}%</span>
              <span className="w-24 text-right font-mono text-xs">{formatCostCny(item.value)}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
