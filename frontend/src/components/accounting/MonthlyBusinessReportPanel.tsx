import { Link } from 'react-router-dom';
import type { MonthlyBusinessComparisonMetric, MonthlyBusinessReport } from '../../types';
import { formatCny, formatSignedCny } from '../sales/salesState';
import { DonutBreakdown } from './MonthlyReportCharts';
import { formatCostCny } from './monthlyReportFormat';

interface Props {
  report?: MonthlyBusinessReport;
  error?: string;
  month: string;
  onRetry?: () => void;
}

const expenseLabels: Record<keyof MonthlyBusinessReport['profit']['operating_expense_breakdown'], string> = {
  salary_cny: '工资',
  rent_cny: '房租',
  transport_cny: '运输（含打车）',
  professional_services_cny: '专业服务',
  financial_cny: '财务费用',
  other_cny: '其他',
};

function comparisonText(metric: MonthlyBusinessComparisonMetric): string {
  if (metric.status === 'new') return '较上月新增';
  if (metric.status === 'not_available' || metric.change_rate == null) return '上月无可比基数';
  const percent = Number(metric.change_rate) * 100;
  const delta = Number(metric.delta_cny);
  if (delta === 0) return '与上月持平';
  if (percent === 0) return delta > 0 ? '较上月小幅增长' : '较上月小幅下降';
  return `较上月 ${percent > 0 ? '+' : ''}${percent.toFixed(1)}%`;
}

function comparisonTone(metric: MonthlyBusinessComparisonMetric): string {
  if (metric.status !== 'available') return 'text-muted';
  return Number(metric.delta_cny) >= 0 ? 'text-success' : 'text-accent';
}

export default function MonthlyBusinessReportPanel({ report, error, month, onRetry }: Props) {
  if (error) {
    return (
      <section className="rounded-md border border-red-200 bg-white px-5 py-12 text-center shadow-sm" role="alert">
        <p className="text-sm text-red-700">{error}</p>
        {onRetry && <button type="button" onClick={onRetry} className="mt-4 rounded bg-accent px-4 py-2 text-sm font-semibold text-white">重新加载</button>}
      </section>
    );
  }
  if (!report) return <MonthlyReportSkeleton />;

  const expenseItems = Object.entries(report.profit.operating_expense_breakdown).map(([key, value]) => ({
    name: expenseLabels[key as keyof typeof expenseLabels],
    value: Number(value),
  }));
  const costItems = [
    { name: '商品成本', value: Number(report.profit.product_cost_cny) },
    { name: '人肉成本', value: Number(report.profit.human_cost_cny) },
    { name: '经营费用', value: Number(report.profit.operating_expenses_cny) },
  ];
  const hasCostReversals = [...costItems, ...expenseItems].some(item => item.value < 0);
  const hasAdjustments = Number(report.profit.inventory_adjustment_cny) !== 0
    || Number(report.profit.reconciliation_adjustment_cny) !== 0;
  const topBrands = [...report.rankings.brands]
    .sort((left, right) => Number(right.sales_profit_cny) - Number(left.sales_profit_cny))
    .slice(0, 3);

  return (
    <section data-guide="accounting-profit" className="space-y-7">
      <div className="grid gap-3 lg:grid-cols-3">
        <HeadlineMetric
          label="净销售收入"
          value={formatCny(report.profit.sales_revenue_cny)}
          comparison={report.comparison.metrics.sales_revenue_cny}
          note={`履约 ${report.sales.fulfillment_order_count} 单 · 退货 ${report.sales.return_order_count} 单`}
        />
        <HeadlineMetric
          label="销售利润"
          value={formatSignedCny(report.profit.sales_profit_cny)}
          comparison={report.comparison.metrics.sales_profit_cny}
          note={`销售利润率 ${report.profit.sales_profit_rate == null ? '—' : `${(Number(report.profit.sales_profit_rate) * 100).toFixed(1)}%`}`}
        />
        <HeadlineMetric
          label="经营净利润"
          value={formatSignedCny(report.profit.net_operating_profit_cny)}
          comparison={report.comparison.metrics.net_operating_profit_cny}
          note="销售利润扣除经营费用后的最终经营结果"
          emphasized
        >
          {hasAdjustments && (
            <div className="mt-3 space-y-1 border-t border-dashed border-border pt-2 text-[11px] text-muted">
              <MetricLine label="调整前经营利润" value={formatSignedCny(report.profit.core_operating_profit_cny)} />
              <MetricLine label="库存调整" value={formatSignedCny(report.profit.inventory_adjustment_cny)} />
              <MetricLine label="对账调整" value={formatSignedCny(report.profit.reconciliation_adjustment_cny)} />
            </div>
          )}
        </HeadlineMetric>
      </div>

      <ReportSection title="成本结构" meta="库存调整与对账调整不计入常规成本">
        <div className="grid gap-4 xl:grid-cols-2">
          <ReportCard title="成本构成"><DonutBreakdown items={costItems} totalLabel="成本合计" /></ReportCard>
          <ReportCard title="经营费用构成">
            <DonutBreakdown items={expenseItems} totalLabel="费用合计" />
            <p className="mt-3 text-[11px] text-muted">运输包含打车、公共交通、差旅、配送、停车和燃油。</p>
          </ReportCard>
        </div>
        {hasCostReversals && <p className="mt-2 text-[11px] text-muted">本月包含成本冲正；环形图仅展示冲正后仍为正的成本项。</p>}
      </ReportSection>

      <ReportSection title="回款与占款">
        <MetricStrip columns="five">
          <StripMetric label="客户收款" value={formatCny(report.cash.sales_receipts_cny)} />
          <StripMetric label="退款" value={formatCostCny(report.cash.refunds_cny)} />
          <StripMetric label="收款净额" value={formatSignedCny(report.cash.net_receipts_cny)} />
          <StripMetric label="期末应收款" value={formatCny(report.cash.accounts_receivable_cny)} />
          <StripMetric label="客户预收款" value={formatCny(report.cash.customer_prepayments_cny)} />
        </MetricStrip>
      </ReportSection>

      <ReportSection title="库存经营分析" meta="按人民币库存成本计价">
        <ReportCard>
          <MetricStrip columns="six" flat>
            <StripMetric label="月初库存" value={formatCny(report.inventory.opening_cost_cny)} />
            <StripMetric label="本月入库" value={formatCny(report.inventory.received_cost_cny)} />
            <StripMetric label="商品消耗" value={formatCostCny(report.inventory.product_cost_consumed_cny)} />
            <StripMetric label="库存调整" value={formatSignedCny(report.inventory.adjustment_net_cny)} />
            <StripMetric label="月末库存" value={formatCny(report.inventory.closing_cost_cny)} />
            <StripMetric label="月度周转" value={report.inventory.monthly_turnover_rate == null ? '—' : `${Number(report.inventory.monthly_turnover_rate).toFixed(2)} 次`} />
          </MetricStrip>
          <InventoryWarnings report={report} />
        </ReportCard>
      </ReportSection>

      <ReportSection title="客户结构" meta="新客与复购客户可能重叠，不作加总">
        <div className="grid gap-3 sm:grid-cols-3">
          <CustomerMetric label="履约客户" value={`${report.customers.fulfilled_customer_count} 位`} note="本月有履约订单" />
          <CustomerMetric label="新客" value={`${report.customers.new_customer_count} 位`} note="本月首次履约" />
          <CustomerMetric label="复购客户" value={`${report.customers.repeat_customer_count} 位`} note="本月前已有履约" />
        </div>
      </ReportSection>

      <ReportSection title="经营结论">
        <ReportCard>
          <ol className="divide-y divide-dashed divide-border">
            {report.conclusions.map((conclusion, index) => (
              <li key={conclusion.code} className="flex gap-3 py-3 first:pt-0 last:pb-0">
                <span className="shrink-0 font-mono text-xs text-gold">{String(index + 1).padStart(2, '0')}</span>
                <p className="text-sm leading-6">{conclusion.text}</p>
              </li>
            ))}
          </ol>
        </ReportCard>
      </ReportSection>

      <ReportSection title="经营贡献排行" meta="按销售利润 · 前三名">
        <ReportCard>
          {topBrands.length ? (
            <div className="divide-y divide-dashed divide-border">
              {topBrands.map((row, index) => (
                <div key={String(row.key)} className="grid grid-cols-[28px_minmax(0,1fr)_auto] items-center gap-3 py-3 first:pt-0 last:pb-0">
                  <span className="font-mono text-xs text-gold">{String(index + 1).padStart(2, '0')}</span>
                  <span className="truncate text-sm font-medium">{row.name}</span>
                  <span className="font-mono text-sm font-semibold">{formatSignedCny(row.sales_profit_cny)}</span>
                </div>
              ))}
            </div>
          ) : <p className="py-6 text-center text-sm text-muted">本月无销售，暂无经营贡献数据。</p>}
          <div className="mt-4 text-right"><Link className="text-sm font-semibold text-accent hover:underline" to={`/reports/contributions?month=${month}`}>查看完整经营贡献排行 →</Link></div>
        </ReportCard>
      </ReportSection>
    </section>
  );
}

function HeadlineMetric({ label, value, comparison, note, emphasized = false, children }: {
  label: string;
  value: string;
  comparison: MonthlyBusinessComparisonMetric;
  note: string;
  emphasized?: boolean;
  children?: React.ReactNode;
}) {
  return (
    <div className={`rounded-md border border-border bg-white p-4 shadow-sm ${emphasized ? 'border-t-[3px] border-t-accent' : ''}`}>
      <p className="text-xs text-muted">{label}</p>
      <p className="mt-2 font-mono text-2xl font-semibold tracking-tight">{value}</p>
      <p className={`mt-1 text-xs ${comparisonTone(comparison)}`}>{comparisonText(comparison)}</p>
      <p className="mt-2 text-[11px] text-muted">{note}</p>
      {children}
    </div>
  );
}

function ReportSection({ title, meta, children }: { title: string; meta?: string; children: React.ReactNode }) {
  return <section><div className="mb-3 flex flex-wrap items-baseline justify-between gap-2"><h2 className="font-display text-xl font-semibold">{title}</h2>{meta && <p className="text-[11px] text-muted">{meta}</p>}</div>{children}</section>;
}

function ReportCard({ title, children }: { title?: string; children: React.ReactNode }) {
  return <div className="rounded-md border border-border bg-white p-4 shadow-sm">{title && <h3 className="mb-4 font-display text-base font-semibold">{title}</h3>}{children}</div>;
}

function MetricLine({ label, value }: { label: string; value: string }) {
  return <div className="flex justify-between gap-4"><span>{label}</span><span className="font-mono text-fg">{value}</span></div>;
}

function MetricStrip({ columns, flat = false, children }: { columns: 'five' | 'six'; flat?: boolean; children: React.ReactNode }) {
  return <div className={`grid overflow-hidden ${flat ? '' : 'rounded-md border border-border bg-white shadow-sm'} grid-cols-2 ${columns === 'five' ? 'lg:grid-cols-5' : 'lg:grid-cols-6'}`}>{children}</div>;
}

function StripMetric({ label, value }: { label: string; value: string }) {
  return <div className="border-b border-r border-border p-4 last:border-r-0 lg:border-b-0"><p className="text-[11px] text-muted">{label}</p><p className="mt-1.5 font-mono text-base font-semibold">{value}</p></div>;
}

function CustomerMetric({ label, value, note }: { label: string; value: string; note: string }) {
  return <div className="rounded-md border border-border bg-white p-4 shadow-sm"><p className="text-xs text-muted">{label}</p><p className="mt-2 font-mono text-2xl font-semibold">{value}</p><p className="mt-1 text-[11px] text-muted">{note}</p></div>;
}

function InventoryWarnings({ report }: { report: MonthlyBusinessReport }) {
  const warnings = report.inventory.warnings;
  if (warnings.status === 'unavailable') return <p className="mt-4 border-t border-dashed border-border pt-3 text-[11px] text-muted">库存预警：{warnings.reason}</p>;
  if (!warnings.items.length) return <p className="mt-4 border-t border-dashed border-border pt-3 text-[11px] text-success">近 90 天未发现高成本无动销或库存偏高商品。</p>;
  return <div className="mt-4 border-t border-dashed border-border pt-3"><h3 className="mb-2 text-xs font-semibold text-muted">库存预警</h3><div className="space-y-1.5">{warnings.items.map(item => <div key={item.cigar_id} className="flex flex-wrap justify-between gap-2 rounded bg-orange-50 px-3 py-2 text-xs text-orange-800"><span>{item.name} · {item.warning_type === 'no_movement_90d' ? '90 天无动销' : '预计库存超过 180 天'}</span><span className="font-mono">占用 {formatCostCny(item.inventory_cost_cny)}</span></div>)}</div></div>;
}

function MonthlyReportSkeleton() {
  return <div aria-label="月报加载中" className="space-y-4"><div className="grid gap-3 lg:grid-cols-3">{[0, 1, 2].map(item => <div key={item} className="h-32 animate-pulse rounded-md bg-[#EDE6DC]" />)}</div><div className="grid gap-4 xl:grid-cols-2"><div className="h-64 animate-pulse rounded-md bg-[#EDE6DC]" /><div className="h-64 animate-pulse rounded-md bg-[#EDE6DC]" /></div></div>;
}
