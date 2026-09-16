import { useMemo, useState } from 'react';
import type { MonthlyBusinessRankingRow, MonthlyBusinessReport } from '../../types';
import { formatSignedCny } from '../sales/salesState';
import { DonutBreakdown } from './MonthlyReportCharts';
import { formatCostCny } from './monthlyReportFormat';

type RankingGroup = 'brands' | 'products' | 'customers';
type RankingSort = 'sales_profit_cny' | 'net_sales_revenue_cny' | 'quantity';

const groupLabels: Record<RankingGroup, string> = { brands: '品牌', products: '商品', customers: '客户' };
const sortLabels: Record<RankingSort, string> = { sales_profit_cny: '销售利润', net_sales_revenue_cny: '净销售收入', quantity: '销量' };

export default function ContributionRankingPanel({ report }: { report: MonthlyBusinessReport }) {
  const [group, setGroup] = useState<RankingGroup>('brands');
  const [sort, setSort] = useState<RankingSort>('sales_profit_cny');
  const [showAll, setShowAll] = useState(false);
  const rows = useMemo(() => [...report.rankings[group]].sort((left, right) => {
    const difference = Number(right[sort]) - Number(left[sort]);
    return difference || left.name.localeCompare(right.name, 'zh-CN');
  }), [group, report, sort]);
  const visibleRows = showAll ? rows : rows.slice(0, 6);
  const maxValue = Math.max(0, ...rows.map(row => Math.abs(Number(row[sort]))));
  const totals = rows.reduce((result, row) => ({
    revenue: result.revenue + Number(row.net_sales_revenue_cny),
    quantity: result.quantity + Number(row.quantity),
    productCost: result.productCost + Math.abs(Number(row.product_cost_cny)),
    humanCost: result.humanCost + Math.abs(Number(row.human_cost_cny)),
    profit: result.profit + Number(row.sales_profit_cny),
  }), { revenue: 0, quantity: 0, productCost: 0, humanCost: 0, profit: 0 });

  return (
    <div className="space-y-6">
      <section className="rounded-md border border-border bg-white p-4 shadow-sm">
        <h2 className="font-display text-lg font-semibold">品牌销售利润贡献占比</h2>
        <div className="mt-4 max-w-2xl">
          <DonutBreakdown
            totalLabel="利润合计"
            items={report.rankings.brands.map(row => ({ name: row.name, value: Math.max(0, Number(row.sales_profit_cny)) }))}
          />
        </div>
      </section>

      <section className="rounded-md border border-border bg-white p-4 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <ButtonGroup
            value={group}
            onChange={value => { setGroup(value as RankingGroup); setShowAll(false); }}
            options={[['brands', '品牌'], ['products', '商品'], ['customers', '客户']]}
            label="排行维度"
          />
          <label className="flex items-center gap-2 text-xs text-muted">
            排序
            <select value={sort} onChange={event => { setSort(event.target.value as RankingSort); setShowAll(false); }} className="rounded border border-border bg-white px-3 py-2 text-sm text-fg">
              <option value="sales_profit_cny">销售利润</option>
              <option value="net_sales_revenue_cny">净销售收入</option>
              <option value="quantity">销量</option>
            </select>
          </label>
        </div>
      </section>

      <section className="rounded-md border border-border bg-white p-4 shadow-sm">
        <h2 className="font-display text-lg font-semibold">{groupLabels[group]}排行速览</h2>
        <p className="mt-1 text-[11px] text-muted">按{sortLabels[sort]}，精确数值见下方明细</p>
        {rows.length ? <div className="mt-4 space-y-2.5">{rows.slice(0, 6).map(row => {
          const value = Number(row[sort]);
          const width = maxValue > 0 ? Math.max(2, Math.abs(value) / maxValue * 100) : 0;
          return <div key={String(row.key)} className="grid grid-cols-[minmax(90px,140px)_minmax(90px,1fr)_100px] items-center gap-3 text-xs"><span className="truncate">{row.name}</span><span className="h-3.5 overflow-hidden rounded-sm bg-[#F1ECE5]"><span className="block h-full rounded-sm bg-accent/80" style={{ width: `${width}%` }} /></span><span className="text-right font-mono">{sort === 'quantity' ? `${row.quantity} 支` : formatSignedCny(value)}</span></div>;
        })}</div> : <EmptyRanking group={groupLabels[group]} />}
      </section>

      {Math.abs(Number(report.rankings.unallocated_human_cost_cny)) > 0 && (
        <p className="rounded-md border border-[#F5E8D8] bg-[#FFFCF6] px-3 py-2 text-xs">
          另有 <span className="font-mono font-semibold">{formatCostCny(report.rankings.unallocated_human_cost_cny)}</span> 人肉成本尚未分摊到具体{groupLabels[group]}。
        </p>
      )}

      <section className="overflow-hidden rounded-md border border-border bg-white shadow-sm">
        <div className="border-b border-border px-4 py-3">
          <h2 className="font-display text-lg font-semibold">{groupLabels[group]}贡献明细</h2>
          <p className="mt-1 text-[11px] text-muted">共 {rows.length} 条 · 按{sortLabels[sort]}排序</p>
        </div>
        {rows.length ? <>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] text-xs">
              <thead className="bg-[#FCFBF9] text-muted"><tr><Th>名称</Th><Th numeric>净销售收入</Th><Th numeric>销量</Th><Th numeric>商品成本</Th><Th numeric>人肉成本</Th><Th numeric>销售利润</Th><Th numeric>利润率</Th></tr></thead>
              <tbody>{visibleRows.map(row => <RankingRow key={String(row.key)} row={row} />)}</tbody>
              <tfoot className="border-t border-border bg-[#FCFBF9] font-semibold"><tr><Td>合计</Td><Td numeric>{formatSignedCny(totals.revenue)}</Td><Td numeric>{totals.quantity} 支</Td><Td numeric>{formatCostCny(totals.productCost)}</Td><Td numeric>{formatCostCny(totals.humanCost)}</Td><Td numeric>{formatSignedCny(totals.profit)}</Td><Td numeric>{totals.revenue > 0 ? `${(totals.profit / totals.revenue * 100).toFixed(1)}%` : '—'}</Td></tr></tfoot>
            </table>
          </div>
          {!showAll && rows.length > 6 && <div className="border-t border-border p-3 text-center"><button type="button" onClick={() => setShowAll(true)} className="rounded border border-border bg-white px-4 py-2 text-xs font-semibold hover:border-gold">查看更多（剩余 {rows.length - 6} 条）</button></div>}
        </> : <EmptyRanking group={groupLabels[group]} />}
      </section>

      <details className="rounded-md border border-border bg-white">
        <summary className="cursor-pointer px-4 py-3 text-sm font-semibold">口径说明</summary>
        <p className="border-t border-border px-4 py-3 text-xs leading-6 text-muted">{report.rankings.allocation_rule}。所有金额均为人民币；成本类金额在成本语境中以正数呈现。</p>
      </details>
    </div>
  );
}

function RankingRow({ row }: { row: MonthlyBusinessRankingRow }) {
  return <tr className="border-t border-border"><Td>{row.name}</Td><Td numeric>{formatSignedCny(row.net_sales_revenue_cny)}</Td><Td numeric>{row.quantity} 支</Td><Td numeric>{formatCostCny(row.product_cost_cny)}</Td><Td numeric>{formatCostCny(row.human_cost_cny)}</Td><Td numeric strong>{formatSignedCny(row.sales_profit_cny)}</Td><Td numeric>{row.sales_profit_rate == null ? '—' : `${(Number(row.sales_profit_rate) * 100).toFixed(1)}%`}</Td></tr>;
}

function Th({ numeric = false, children }: { numeric?: boolean; children: React.ReactNode }) {
  return <th className={`px-3 py-2.5 font-medium ${numeric ? 'text-right' : 'text-left'}`}>{children}</th>;
}

function Td({ numeric = false, strong = false, children }: { numeric?: boolean; strong?: boolean; children: React.ReactNode }) {
  return <td className={`px-3 py-2.5 ${numeric ? 'text-right font-mono' : ''} ${strong ? 'font-semibold' : ''}`}>{children}</td>;
}

function ButtonGroup({ value, onChange, options, label }: { value: string; onChange: (value: string) => void; options: [string, string][]; label: string }) {
  return <div className="inline-flex rounded border border-border bg-[#FBF8F4] p-0.5" role="group" aria-label={label}>{options.map(([option, text]) => <button key={option} type="button" aria-pressed={value === option} onClick={() => onChange(option)} className={`rounded px-3 py-1.5 text-xs ${value === option ? 'bg-white font-semibold text-accent shadow-sm' : 'text-muted hover:text-fg'}`}>{text}</button>)}</div>;
}

function EmptyRanking({ group }: { group: string }) {
  return <div className="px-5 py-10 text-center text-sm text-muted"><strong className="mb-1 block text-fg">排行为空</strong>本月没有销售记录，暂无{group}贡献数据。</div>;
}
