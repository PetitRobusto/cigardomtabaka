import { useMemo, useState } from 'react';
import type {
  MonthlyBusinessComparisonMetric,
  MonthlyBusinessRankingRow,
  MonthlyBusinessReport,
} from '../../types';
import { formatCny, formatSignedCny } from '../sales/salesState';

interface Props {
  report?: MonthlyBusinessReport;
  error?: string;
  month: string;
}

type RankingGroup = 'brands' | 'products' | 'customers';
type RankingSort = 'sales_profit_cny' | 'net_sales_revenue_cny' | 'quantity';

const expenseLabels: Record<keyof MonthlyBusinessReport['profit']['operating_expense_breakdown'], string> = {
  salary_cny: '工资',
  rent_cny: '房租',
  utilities_cny: '水电',
  professional_services_cny: '专业服务',
  financial_cny: '财务费用',
  other_cny: '其他',
};

function monthTitle(month: string): string {
  const match = /^(\d{4})-(\d{2})$/.exec(month);
  return match ? `${match[1]}年${Number(match[2])}月经营月报` : '经营月报';
}

function comparisonText(metric: MonthlyBusinessComparisonMetric): string {
  if (metric.status === 'new') return '较上月新增';
  if (metric.status === 'not_available' || metric.change_rate == null) return '上月无可比基数';
  const percent = Number(metric.change_rate) * 100;
  return `较上月 ${percent >= 0 ? '+' : ''}${percent.toFixed(1)}%`;
}

function comparisonTone(metric: MonthlyBusinessComparisonMetric): string {
  if (metric.status !== 'available') return 'text-muted';
  return Number(metric.delta_cny) >= 0 ? 'text-success' : 'text-accent';
}

export default function MonthlyBusinessReportPanel({ report, error, month }: Props) {
  const [rankingGroup, setRankingGroup] = useState<RankingGroup>('brands');
  const [rankingSort, setRankingSort] = useState<RankingSort>('sales_profit_cny');
  const rows = useMemo(() => {
    if (!report) return [];
    return [...report.rankings[rankingGroup]].sort((left, right) => {
      const difference = Number(right[rankingSort]) - Number(left[rankingSort]);
      return difference || left.name.localeCompare(right.name, 'zh-CN');
    }).slice(0, 5);
  }, [rankingGroup, rankingSort, report]);

  return (
    <section data-guide="accounting-profit" className="mb-7 space-y-4">
      <div className="overflow-hidden rounded-md border border-border bg-white shadow-sm">
        <div className="flex flex-col justify-between gap-2 border-b border-border px-5 py-4 sm:flex-row sm:items-end">
          <div>
            <h2 className="font-display text-xl font-semibold">{monthTitle(month)}</h2>
            <p className="mt-1 text-xs text-muted">
              按业务日期实时计算；补录、退货和冲正会同步更新历史月份。
            </p>
          </div>
          {report && (
            <p className="font-mono text-xs text-muted">
              {report.period.period_start} — {report.period.period_end}
            </p>
          )}
        </div>
        {error ? (
          <p className="px-5 py-10 text-center text-sm text-red-700">{error}</p>
        ) : !report ? (
          <p className="px-5 py-10 text-center text-sm text-muted">月报加载中…</p>
        ) : (
          <>
            <div className="grid sm:grid-cols-2 xl:grid-cols-4">
              <HeadlineMetric
                label="净销售收入"
                value={formatCny(report.profit.sales_revenue_cny)}
                comparison={report.comparison.metrics.sales_revenue_cny}
                note={`${report.sales.fulfillment_order_count} 笔履约 · ${report.sales.return_order_count} 笔退货`}
              />
              <HeadlineMetric
                label="销售利润"
                value={formatSignedCny(report.profit.sales_profit_cny)}
                comparison={report.comparison.metrics.sales_profit_cny}
                note="销售收入 − 商品成本 − 人肉成本"
              />
              <HeadlineMetric
                label="核心经营利润"
                value={formatSignedCny(report.profit.core_operating_profit_cny)}
                comparison={report.comparison.metrics.core_operating_profit_cny}
                note="销售利润 − 经营费用"
              />
              <HeadlineMetric
                label="经营净利润"
                value={formatSignedCny(report.profit.net_operating_profit_cny)}
                comparison={report.comparison.metrics.net_operating_profit_cny}
                note="含库存及对账调整"
                emphasized
              />
            </div>
            <div className="h-1 bg-gradient-to-r from-gold via-accent to-success" />
          </>
        )}
      </div>

      {report && (
        <>
          <div className="grid gap-4 xl:grid-cols-2">
            <ReportCard title="成本结构" subtitle="不推断固定或变动属性">
              <div className="grid grid-cols-3 overflow-hidden rounded border border-border">
                <CompactMetric label="商品成本" value={formatCny(report.profit.product_cost_cny)} />
                <CompactMetric label="人肉成本" value={formatSignedCny(-Number(report.profit.human_cost_cny))} />
                <CompactMetric label="经营费用" value={formatCny(report.profit.operating_expenses_cny)} last />
              </div>
              <div className="mt-3 grid grid-cols-2 gap-x-5 gap-y-2 text-xs sm:grid-cols-3">
                {Object.entries(report.profit.operating_expense_breakdown).map(([key, value]) => (
                  <div key={key} className="flex justify-between gap-3 border-b border-border/70 pb-1.5">
                    <span className="text-muted">{expenseLabels[key as keyof typeof expenseLabels]}</span>
                    <span className="font-mono">{formatCny(value)}</span>
                  </div>
                ))}
              </div>
              <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 border-t border-border pt-3 text-xs text-muted">
                <span>库存调整 <b className="font-mono font-medium text-fg">{formatSignedCny(report.profit.inventory_adjustment_cny)}</b></span>
                <span>对账调整 <b className="font-mono font-medium text-fg">{formatSignedCny(report.profit.reconciliation_adjustment_cny)}</b></span>
              </div>
            </ReportCard>

            <ReportCard title="回款与占款" subtitle="独立于收入确认与利润">
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                <SmallStat label="客户收款" value={formatCny(report.cash.sales_receipts_cny)} />
                <SmallStat label="退款" value={formatSignedCny(-Number(report.cash.refunds_cny))} />
                <SmallStat label="客户收款净额" value={formatSignedCny(report.cash.net_receipts_cny)} />
                <SmallStat label="期末应收款" value={formatCny(report.cash.accounts_receivable_cny)} />
                <SmallStat label="客户预收款" value={formatCny(report.cash.customer_prepayments_cny)} />
              </div>
            </ReportCard>
          </div>

          <div className="grid gap-4 xl:grid-cols-[minmax(0,1.35fr)_minmax(300px,.65fr)]">
            <ReportCard title="库存经营分析" subtitle="历史月份使用当月末账务事实">
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-6">
                <SmallStat label="月初库存" value={formatCny(report.inventory.opening_cost_cny)} />
                <SmallStat label="本月入库" value={formatCny(report.inventory.received_cost_cny)} />
                <SmallStat label="商品消耗" value={formatCny(report.inventory.product_cost_consumed_cny)} />
                <SmallStat label="库存调整" value={formatSignedCny(report.inventory.adjustment_net_cny)} />
                <SmallStat label="月末库存" value={formatCny(report.inventory.closing_cost_cny)} />
                <SmallStat label="月度周转" value={report.inventory.monthly_turnover_rate == null ? '—' : `${Number(report.inventory.monthly_turnover_rate).toFixed(2)} 次`} />
              </div>
              <InventoryWarnings report={report} />
            </ReportCard>

            <ReportCard title="客户结构" subtitle="散客不按姓名推断身份">
              <div className="grid grid-cols-3 gap-3">
                <SmallStat label="履约客户" value={String(report.customers.fulfilled_customer_count)} />
                <SmallStat label="新客" value={String(report.customers.new_customer_count)} />
                <SmallStat label="复购客户" value={String(report.customers.repeat_customer_count)} />
              </div>
            </ReportCard>
          </div>

          <ReportCard title="经营贡献排行" subtitle={report.rankings.allocation_rule}>
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <ButtonGroup
                value={rankingGroup}
                onChange={value => setRankingGroup(value as RankingGroup)}
                options={[['brands', '品牌'], ['products', '商品'], ['customers', '客户']]}
                label="排行维度"
              />
              <ButtonGroup
                value={rankingSort}
                onChange={value => setRankingSort(value as RankingSort)}
                options={[['sales_profit_cny', '销售利润'], ['net_sales_revenue_cny', '销售收入'], ['quantity', '销量']]}
                label="排行方式"
              />
            </div>
            <RankingTable rows={rows} />
            {Number(report.rankings.unallocated_human_cost_cny) !== 0 && (
              <p className="mt-2 text-[11px] text-muted">本期入账与履约归属的人肉成本差额：{formatSignedCny(report.rankings.unallocated_human_cost_cny)}（正数表示本期入账较多，含跨期或未分摊费用；负数表示归属本期履约的成本较多）</p>
            )}
          </ReportCard>

          <ReportCard title="经营结论" subtitle="每条结论均引用本月报内可核验指标">
            <div className="grid gap-2 md:grid-cols-2">
              {report.conclusions.map(conclusion => (
                <div key={conclusion.code} className="rounded border border-border bg-[#FCFBF9] px-3 py-2.5">
                  <p className="text-sm">{conclusion.text}</p>
                  <p className="mt-1 font-mono text-[10px] text-muted">{conclusion.metric_keys.join(' · ') || '数据不足'}</p>
                </div>
              ))}
            </div>
          </ReportCard>
        </>
      )}
    </section>
  );
}

function HeadlineMetric({ label, value, comparison, note, emphasized = false }: {
  label: string;
  value: string;
  comparison: MonthlyBusinessComparisonMetric;
  note: string;
  emphasized?: boolean;
}) {
  return (
    <div className={`border-b border-border p-4 sm:border-r xl:border-b-0 ${emphasized ? 'bg-green-50 xl:border-r-0' : ''}`}>
      <p className="text-[11px] text-muted">{label}</p>
      <p className={`mt-1 font-mono text-xl font-semibold ${emphasized ? 'text-success' : ''}`}>{value}</p>
      <p className={`mt-1 text-[11px] ${comparisonTone(comparison)}`}>{comparisonText(comparison)}</p>
      <p className="mt-1 text-[10px] text-muted">{note}</p>
    </div>
  );
}

function ReportCard({ title, subtitle, children }: { title: string; subtitle: string; children: React.ReactNode }) {
  return (
    <section className="rounded-md border border-border bg-white p-4 shadow-sm">
      <div className="mb-3">
        <h3 className="font-display text-base font-semibold">{title}</h3>
        <p className="mt-0.5 text-[11px] text-muted">{subtitle}</p>
      </div>
      {children}
    </section>
  );
}

function CompactMetric({ label, value, last = false }: { label: string; value: string; last?: boolean }) {
  return <div className={`p-3 ${last ? '' : 'border-r border-border'}`}><p className="text-[10px] text-muted">{label}</p><p className="mt-1 font-mono text-sm font-semibold">{value}</p></div>;
}

function SmallStat({ label, value }: { label: string; value: string }) {
  return <div className="rounded border border-border bg-[#FCFBF9] p-3"><p className="text-[10px] text-muted">{label}</p><p className="mt-1 font-mono text-sm font-semibold">{value}</p></div>;
}

function ButtonGroup({ value, onChange, options, label }: { value: string; onChange: (value: string) => void; options: [string, string][]; label: string }) {
  return <div className="inline-flex rounded border border-border bg-white p-0.5" role="group" aria-label={label}>{options.map(([option, text]) => <button key={option} type="button" aria-pressed={value === option} onClick={() => onChange(option)} className={`rounded px-2.5 py-1 text-xs ${value === option ? 'bg-[#F5EFE8] text-accent' : 'text-muted hover:text-fg'}`}>{text}</button>)}</div>;
}

function RankingTable({ rows }: { rows: MonthlyBusinessRankingRow[] }) {
  if (!rows.length) return <p className="py-6 text-center text-sm text-muted">本期暂无排行数据</p>;
  return (
    <div className="overflow-x-auto rounded border border-border">
      <table className="w-full min-w-[720px] text-xs">
        <thead className="bg-[#FCFBF9] text-muted"><tr><th className="px-3 py-2 text-left font-medium">名称</th><th className="px-3 py-2 text-right font-medium">净销售收入</th><th className="px-3 py-2 text-right font-medium">销量</th><th className="px-3 py-2 text-right font-medium">商品成本</th><th className="px-3 py-2 text-right font-medium">人肉成本</th><th className="px-3 py-2 text-right font-medium">销售利润</th><th className="px-3 py-2 text-right font-medium">利润率</th></tr></thead>
        <tbody>{rows.map(row => <tr key={String(row.key)} className="border-t border-border"><td className="px-3 py-2.5 font-medium">{row.name}</td><td className="px-3 py-2.5 text-right font-mono">{formatSignedCny(row.net_sales_revenue_cny)}</td><td className="px-3 py-2.5 text-right font-mono">{row.quantity}</td><td className="px-3 py-2.5 text-right font-mono">{formatSignedCny(row.product_cost_cny)}</td><td className="px-3 py-2.5 text-right font-mono">{formatSignedCny(-Number(row.human_cost_cny))}</td><td className="px-3 py-2.5 text-right font-mono font-semibold">{formatSignedCny(row.sales_profit_cny)}</td><td className="px-3 py-2.5 text-right font-mono">{row.sales_profit_rate == null ? '—' : `${(Number(row.sales_profit_rate) * 100).toFixed(1)}%`}</td></tr>)}</tbody>
      </table>
    </div>
  );
}

function InventoryWarnings({ report }: { report: MonthlyBusinessReport }) {
  const warnings = report.inventory.warnings;
  if (warnings.status === 'unavailable') return <p className="mt-3 text-[11px] text-muted">库存预警：{warnings.reason}</p>;
  if (!warnings.items.length) return <p className="mt-3 text-[11px] text-success">近 90 天未发现高成本无动销或库存偏高商品。</p>;
  return <div className="mt-3 space-y-1.5">{warnings.items.map(item => <div key={item.cigar_id} className="flex flex-wrap justify-between gap-2 rounded bg-orange-50 px-3 py-2 text-xs text-orange-800"><span>{item.name} · {item.warning_type === 'no_movement_90d' ? '90 天无动销' : '预计库存超过 180 天'}</span><span className="font-mono">占用 {formatCny(item.inventory_cost_cny)}</span></div>)}</div>;
}
