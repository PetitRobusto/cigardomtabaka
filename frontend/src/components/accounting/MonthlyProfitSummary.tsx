import type { MonthlyProfitReport } from '../../types';
import { formatCny, formatSignedCny } from '../sales/salesState';

interface MonthlyProfitSummaryProps {
  profit?: MonthlyProfitReport;
  profitError?: string;
  month: string;
}

function monthTitle(month: string): string {
  const match = /^(\d{4})-(\d{2})$/.exec(month);
  return match ? `${match[1]}年${Number(match[2])}月经营总结` : '月度经营总结';
}

function absoluteAmount(value: string | number | null | undefined): number {
  return value == null || value === '' ? 0 : Math.abs(Number(value));
}

/** 月报只组合接口返回的已入账分类，不在浏览器推算账务事实。 */
export default function MonthlyProfitSummary({ profit, profitError, month }: MonthlyProfitSummaryProps) {
  const operatingExpenses = profit
    ? absoluteAmount(profit.salary_expense_cny)
      + absoluteAmount(profit.rent_expense_cny)
      + absoluteAmount(profit.utilities_expense_cny)
      + absoluteAmount(profit.professional_expense_cny)
      + absoluteAmount(profit.interest_expense_cny)
      + absoluteAmount(profit.other_expense_cny)
    : 0;
  const transportNet = profit
    ? absoluteAmount(profit.customer_transport_revenue_cny) - absoluteAmount(profit.transport_expense_cny)
    : 0;

  return (
    <section data-guide="accounting-profit" className="mb-7 overflow-hidden rounded-md border border-border bg-white shadow-sm">
      <div className="flex items-center justify-between gap-4 border-b border-border px-5 py-4">
        <div>
          <h2 className="font-display text-lg font-semibold">{monthTitle(month)}</h2>
          <p className="mt-0.5 text-xs text-muted">销售、成本和费用均来自已入账流水。</p>
        </div>
        <span className="font-mono text-xs text-muted">{profit?.transaction_count ?? '—'} {profit ? '笔流水' : ''}</span>
      </div>
      {profitError ? (
        <p className="px-5 py-8 text-center text-sm text-red-700">{profitError}</p>
      ) : !profit ? (
        <p className="px-5 py-8 text-center text-sm text-muted">加载中…</p>
      ) : (
        <div className="grid sm:grid-cols-2 xl:grid-cols-5">
          <Metric label="销售收入" value={formatCny(absoluteAmount(profit.sales_revenue_cny))} note="商品销售收入" />
          <Metric label="销售成本" value={formatCny(absoluteAmount(profit.cost_of_goods_sold_cny))} note="销售出库成本" />
          <Metric label="经营费用" value={formatCny(operatingExpenses)} note="工资、房租、专业服务、财务费用等" />
          <Metric label="人肉净额" value={formatSignedCny(transportNet)} note="客户支付减实际成本" />
          <Metric label="本月净利润" value={formatSignedCny(profit.net_profit_cny)} note="含库存及对账调整" net />
        </div>
      )}
      <div className="h-1 bg-gradient-to-r from-gold via-accent to-success" />
    </section>
  );
}

function Metric({ label, value, note, net = false }: { label: string; value: string; note: string; net?: boolean }) {
  return <div className={`border-b border-border p-4 last:border-b-0 sm:border-r xl:border-b-0 ${net ? 'bg-green-50 xl:border-r-0' : ''}`}><p className="text-[11px] text-muted">{label}</p><p className={`mt-1 font-mono font-semibold ${net ? 'text-xl text-success' : 'text-lg'}`}>{value}</p><p className="mt-1 text-[10px] text-muted">{note}</p></div>;
}
