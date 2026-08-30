import type { AccountingTransaction, FundAccount } from '../../types';
import { formatOriginalAmount } from '../sales/salesState';

interface ExchangeDetailsProps {
  month: string;
  transactions?: AccountingTransaction[];
  accounts?: FundAccount[];
  loading?: boolean;
  error?: string;
}

function accountLabel(accountId: number | null, accounts: FundAccount[]): string {
  if (accountId == null) return '未知账户';
  const account = accounts.find(item => item.id === accountId);
  return account ? `${account.name} · ${account.currency}` : `账户 #${accountId}`;
}

function amountText(value: string, currency: string): string {
  return `${formatOriginalAmount(Math.abs(Number(value)), currency)} ${currency}`;
}

export default function ExchangeDetails({ month, transactions = [], accounts = [], loading = false, error }: ExchangeDetailsProps) {
  const rows = [...transactions].sort((left, right) => right.business_date.localeCompare(left.business_date) || right.id - left.id);
  return <section className="mt-5 overflow-hidden rounded-md border border-border bg-white shadow-sm">
    <div className="flex flex-wrap items-end justify-between gap-3 border-b border-border px-5 py-4">
      <div><p className="text-[11px] font-bold uppercase tracking-[.12em] text-accent">Exchange ledger</p><h2 className="mt-1 font-display text-lg font-semibold">换汇明细</h2><p className="mt-1 text-xs text-muted">按业务日期展示本月已入账的 CNY / USDT → RUB 换汇。</p></div>
      <div className="text-right"><p className="text-[11px] text-muted">记录数</p><p className="mt-0.5 font-mono text-sm font-semibold">{loading ? '…' : rows.length} <span className="font-sans text-xs font-normal text-muted">笔</span></p></div>
    </div>
    {error && <p role="alert" className="m-5 rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}
    {loading ? <div role="status" className="px-5 py-8 text-center text-sm text-muted">换汇明细加载中…</div> : !error && rows.length === 0 ? <div className="px-5 py-8 text-center text-sm text-muted">{month} 暂无换汇记录</div> : !error && <div className="overflow-x-auto"><table className="w-full min-w-[760px] text-left text-sm"><thead className="border-b border-border bg-[#FFFDFA] text-[11px] text-muted"><tr><th className="whitespace-nowrap px-5 py-3 font-semibold">日期</th><th className="whitespace-nowrap px-3 py-3 font-semibold">转出账户</th><th className="whitespace-nowrap px-3 py-3 text-right font-semibold">转出金额</th><th className="whitespace-nowrap px-3 py-3 font-semibold">转入账户</th><th className="whitespace-nowrap px-3 py-3 text-right font-semibold">转入金额</th><th className="whitespace-nowrap px-5 py-3 text-right font-semibold">实际汇率</th></tr></thead><tbody>{rows.map(transaction => { const source = transaction.postings.find(posting => Number(posting.amount) < 0); const target = transaction.postings.find(posting => posting.currency === 'RUB' && Number(posting.amount) > 0); const rate = source && target && Number(source.amount) !== 0 ? Math.abs(Number(target.amount) / Number(source.amount)) : null; return <tr key={transaction.id} className="border-b border-border last:border-0 hover:bg-[#FFFCF9]"><td className="whitespace-nowrap px-5 py-3 font-mono text-xs text-muted">{transaction.business_date}</td><td className="px-3 py-3 text-xs">{accountLabel(source?.account_id ?? null, accounts)}</td><td className="whitespace-nowrap px-3 py-3 text-right font-mono text-xs">{source ? amountText(source.amount, source.currency) : '—'}</td><td className="px-3 py-3 text-xs">{accountLabel(target?.account_id ?? null, accounts)}</td><td className="whitespace-nowrap px-3 py-3 text-right font-mono text-xs">{target ? amountText(target.amount, target.currency) : '—'}</td><td className="whitespace-nowrap px-5 py-3 text-right font-mono text-xs">{rate == null ? '—' : `${rate.toLocaleString('zh-CN', { minimumFractionDigits: 4, maximumFractionDigits: 4 })} RUB / 原币`}</td></tr>; })}</tbody></table></div>}
  </section>;
}
