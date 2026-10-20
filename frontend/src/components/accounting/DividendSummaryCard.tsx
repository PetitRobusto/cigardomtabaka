import { useQuery } from '@tanstack/react-query';
import { fetchDividendRounds, parseAccountingApiError } from '../../api';
import { formatDecimalAmount } from '../../utils/decimalDisplay';
import { dividendSecondaryClass } from './DividendRoundsAction.logic';

const money = (value: string) => `¥${formatDecimalAmount(value, 'CNY')}`;

export default function DividendSummaryCard() {
  const query = useQuery({ queryKey: ['dividend-rounds', 'summary'], queryFn: () => fetchDividendRounds() });
  const summary = query.data?.summary;
  return <section aria-labelledby="dividend-summary-title" className="min-w-0 overflow-hidden rounded-md border border-border bg-white shadow-sm">
    <header className="border-b border-border px-5 py-4">
      <h2 id="dividend-summary-title" className="font-display text-lg font-semibold">分红总览</h2>
      <p className="mt-1 text-xs text-muted">全部已确认分红轮次 · 不随明细月份切换</p>
    </header>
    {query.isPending ? <p role="status" className="px-5 py-6 text-sm text-muted">分红总览加载中…</p> : query.error || !summary ?
      <div role="alert" className="space-y-3 px-5 py-4 text-sm text-accent"><p>{query.error ? parseAccountingApiError(query.error).message : '分红总览暂不可用，请重新加载。'}</p><button type="button" onClick={() => void query.refetch()} className={dividendSecondaryClass}>重新加载</button></div> : <>
        <dl className="flex flex-wrap items-center justify-between gap-2 border-b border-dashed border-border bg-[#FFFDFA] px-5 py-4"><dt className="text-xs text-muted">待领合计</dt><dd className="break-all font-mono text-xl font-semibold text-[#A75B27]">{money(summary.pending_cny)}</dd></dl>
        {summary.partners.length === 0 ? <p className="px-5 py-6 text-center text-sm text-muted">暂无已确认分红轮次</p> :
          <div className="divide-y divide-dashed divide-border">{summary.partners.map(partner => <div key={partner.id} className="px-5 py-3">
            <h3 className="mb-2 break-words text-sm font-semibold">{partner.name}</h3>
            <dl className="grid grid-cols-3 gap-3">{[
              ['累计应分', partner.allocated_cny], ['累计已领', partner.paid_cny], ['待领', partner.pending_cny],
            ].map(([label, value]) => <div key={label} className="min-w-0"><dt className="text-[11px] text-muted">{label}</dt><dd className={`mt-1 break-all font-mono text-xs font-semibold ${label === '待领' ? 'text-[#A75B27]' : 'text-fg'}`}>{money(value)}</dd></div>)}</dl>
          </div>)}</div>}
        <p className="border-t border-border px-5 py-3 text-[11px] leading-5 text-muted">待领资金不冻结，领取前仍可正常用于采购和经营。补领请从对应分红明细登记。</p>
      </>}
  </section>;
}
