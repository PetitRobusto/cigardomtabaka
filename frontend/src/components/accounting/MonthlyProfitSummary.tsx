import type { MonthlyProfitReport } from '../../types';
import { formatSignedCny } from '../sales/salesState';

interface MonthlyProfitSummaryProps {
  profit?: MonthlyProfitReport;
  profitError?: string;
  month: string;
}

function monthTitle(month: string): string {
  const match = /^(\d{4})-(\d{2})$/.exec(month);
  return match ? `${match[1]}年${Number(match[2])}月经营总结` : '月度经营总结';
}

/** 月报只组合接口返回的已入账分类，不在浏览器推算账务事实。 */
export default function MonthlyProfitSummary({ profit, profitError, month }: MonthlyProfitSummaryProps) {
  const operatingExpenses = profit
    ? Number(profit.salary_expense_cny)
      + Number(profit.rent_expense_cny)
      + Number(profit.utilities_expense_cny)
      + Number(profit.professional_expense_cny)
      + Number(profit.interest_expense_cny)
      + Number(profit.other_expense_cny)
    : 0;
  const salesRevenue = profit
    ? -Number(profit.sales_revenue_cny) - Number(profit.customer_transport_revenue_cny)
    : 0;
  const transportCost = profit
    ? Number(profit.transport_expense_cny)
      + Number(profit.transport_settlement_expense_cny ?? 0)
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
          <Metric label="销售收入" value={formatSignedCny(salesRevenue)} note="商品金额与客户承担的人肉费" />
          <Metric label="商品成本" value={formatSignedCny(profit.cost_of_goods_sold_cny)} note="已履约商品的库存成本" />
          <Metric label="经营费用" value={formatSignedCny(operatingExpenses)} note="工资、房租、专业服务、财务费用等" />
          <Metric label="人肉成本" value={formatSignedCny(-transportCost)} note="实际人肉成本与运输结算" />
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
