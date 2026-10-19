import { Fragment, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { fetchDividendRounds, parseAccountingApiError } from '../../api';
import type { DividendRound, FundAccount } from '../../types';
import { formatDecimalAmount } from '../../utils/decimalDisplay';
import DividendPayoutDialog from './DividendPayoutDialog';
import { dividendCents, dividendSecondaryClass } from './DividendRoundsAction.logic';

const money = (value: string) => `¥${formatDecimalAmount(value, 'CNY')}`;

export default function DividendDetails({ month, accounts, businessDate, onChanged }: {
  month: string; accounts: FundAccount[]; businessDate: string; onChanged?: () => void;
}) {
  const client = useQueryClient();
  const [page, setPage] = useState(1);
  const [expanded, setExpanded] = useState<number | null>(null);
  const [payout, setPayout] = useState<DividendRound | null>(null);
  const [notice, setNotice] = useState('');
  const query = useQuery({ queryKey: ['dividend-rounds', 'details', month, page], queryFn: () => fetchDividendRounds(page, month) });
  const saved = () => {
    setPayout(null); setNotice('领取已记录。');
    void client.invalidateQueries({ queryKey: ['dividend-rounds'] });
    try { onChanged?.(); } catch { setNotice('记账成功；页面刷新失败，请点击重新加载。'); }
  };
  return <section id="dividend-details" className="mt-5 min-w-0 overflow-hidden rounded-md border border-border bg-white shadow-sm">
    <div inert={Boolean(payout)}>
      <div className="flex flex-wrap items-end justify-between gap-3 border-b border-border px-5 py-4">
        <div><h2 className="font-display text-lg font-semibold">分红明细</h2><p className="mt-1 text-xs text-muted">{month} · 按分配或实际领取日期筛选，展开查看付款详情。</p></div>
        <div className="text-right text-xs text-muted">记录数 <strong className="ml-1 font-mono text-sm text-fg">{query.isPending ? '…' : query.data?.count ?? '—'}</strong> 笔</div>
      </div>
      {notice && <p role="status" className="px-5 pt-3 text-sm text-success">{notice}</p>}
      {query.error && <p role="alert" className="m-5 text-sm text-red-700">{parseAccountingApiError(query.error).message}<button type="button" onClick={() => void query.refetch()} className={dividendSecondaryClass}>重新加载</button></p>}
      {query.isPending ? <p role="status" className="px-5 py-8 text-center text-sm text-muted">分红明细加载中…</p> : !query.error && query.data?.rounds.length === 0 ? <p className="px-5 py-8 text-center text-sm text-muted">{month} 暂无分红记录</p> : !query.error && <>
        <p className="px-5 pt-2 text-xs text-muted sm:hidden">可横向滑动查看完整表格</p>
        <div className="overflow-x-auto"><table aria-label="分红明细" className="w-full min-w-[900px] text-left text-sm">
          <thead className="border-b border-border bg-[#FFFDFA] text-[11px] text-muted"><tr>{['分配日期', '分红总额', '合伙人 1', '合伙人 2', '付款账户', '备注', '支付状态', '详情'].map((label, index) => <th key={label} className={`whitespace-nowrap px-4 py-2.5 font-semibold ${index === 1 ? 'text-right' : ''}`}>{label}</th>)}</tr></thead>
          <tbody>{query.data?.rounds.map(round => {
            const pending = dividendCents(round.pending_cny) ?? 0n;
            const partial = pending > 0n && pending < (dividendCents(round.total_cny) ?? 0n);
            const status = pending === 0n ? '已付清' : partial ? '部分领取' : '待领取';
            const accountNames = [...new Set(round.payouts.map(item => item.fund_account_name))];
            return <Fragment key={round.id}>
              <tr className="border-b border-border hover:bg-[#FFFCF9]">
                <td className="whitespace-nowrap px-4 py-2.5 font-mono text-xs">{round.business_date}</td>
                <td className="whitespace-nowrap px-4 py-2.5 text-right font-mono text-xs font-semibold">{money(round.total_cny)}</td>
                {round.partners.map(partner => <td key={partner.id} className="whitespace-nowrap px-4 py-2.5 text-xs"><span className="text-muted">{partner.name}</span> <span className="font-mono">{money(partner.allocated_cny)}</span></td>)}
                <td className="px-4 py-2.5 text-xs">{accountNames.join('、') || '尚未付款'}</td>
                <td className="max-w-40 truncate px-4 py-2.5 text-xs text-muted" title={round.note}>{round.note || '—'}</td>
                <td className="px-4 py-2.5"><span className={`whitespace-nowrap rounded-full px-2 py-1 text-[11px] ${pending === 0n ? 'bg-[#E9F1EB] text-[#3D6B4F]' : partial ? 'bg-[#EAF0F4] text-[#466681]' : 'bg-[#F9EEE6] text-[#A75B27]'}`}>{status}</span></td>
                <td className="px-4 py-2.5"><button type="button" aria-expanded={expanded === round.id} onClick={() => setExpanded(expanded === round.id ? null : round.id)} className="whitespace-nowrap text-xs font-semibold text-accent hover:underline">{expanded === round.id ? '收起详情' : '查看详情'}</button></td>
              </tr>
              {expanded === round.id && <tr className="border-b border-border bg-[#FFFDFA]"><td colSpan={8} className="px-4 py-3">
                <div className="rounded border border-dashed border-border p-3 text-xs">
                  <h3 className="mb-2 font-semibold text-muted">付款详情</h3>
                  {round.note && <p className="mb-3 whitespace-pre-wrap break-words text-muted">{round.note}</p>}
                  {round.payouts.length === 0 ? <p className="text-muted">尚无实际付款记录</p> : <ul className="space-y-2">{round.payouts.map(item => <li key={item.id} className="flex flex-wrap justify-between gap-2 border-b border-dashed border-border pb-2 last:border-0"><span>{item.recipient_name} · <span className="font-mono">{item.business_date}</span> · {item.fund_account_name}{item.note && <span className="ml-2 whitespace-pre-wrap break-words text-muted">{item.note}</span>}</span><strong className="font-mono">{money(item.amount_cny)}</strong></li>)}</ul>}
                  {pending > 0n && <div className="mt-3 flex flex-wrap items-center justify-between gap-3"><p className="text-muted">{round.partners.map(partner => `${partner.name} 待领 ${money(partner.pending_cny)}`).join(' · ')}</p><button type="button" onClick={() => setPayout(round)} className={dividendSecondaryClass}>继续登记领取</button></div>}
                </div>
              </td></tr>}
            </Fragment>;
          })}</tbody>
        </table></div>
      </>}
      {query.data && <div className="flex items-center justify-end gap-3 px-5 py-3 text-xs text-muted"><button disabled={page === 1 || query.isFetching} onClick={() => { setPage(page - 1); setExpanded(null); }} className={dividendSecondaryClass}>上一页</button><span>第 {page} 页</span><button disabled={!query.data.next_page || query.isFetching} onClick={() => { setPage(query.data!.next_page!); setExpanded(null); }} className={dividendSecondaryClass}>下一页</button></div>}
      {Boolean(query.data?.legacy_dividends.length) && <details className="mx-5 mb-4 rounded border border-border p-3 text-xs text-muted"><summary className="cursor-pointer">历史 A/B 分红（只读，最近 50 条）</summary><div className="mt-2 space-y-2">{query.data?.legacy_dividends.map(item => <p key={item.id}>{item.business_date || '—'} · {money(item.total_cny || '0')} · {item.status === 'draft' ? '历史草稿' : '已确认'}</p>)}</div></details>}
    </div>
    {payout && <DividendPayoutDialog round={payout} accounts={accounts} businessDate={businessDate} onClose={() => setPayout(null)} onSaved={saved} />}
  </section>;
}
