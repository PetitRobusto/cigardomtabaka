import { useState } from 'react';
import { Check, ClipboardCheck, Plus } from 'lucide-react';
import type { AccountingSummary, FundAccount, MonthlyProfitReport, Reconciliation } from '../../types';
import { apiErrorMessage, confirmReconciliation, createReconciliation } from '../../api';
import { formatCny, formatSignedCny, validateMoneyInput } from './salesState';
import { selectReconciliationAccountId } from './AccountingPanel.logic';

interface Props {
  accounts?: FundAccount[];
  summary?: AccountingSummary;
  profit?: MonthlyProfitReport;
  reconciliations?: Reconciliation[];
  accountsError?: string;
  summaryError?: string;
  profitError?: string;
  reconciliationError?: string;
  month: string;
  onChanged: () => void;
  showStats?: boolean;
}

const today = () => { const date = new Date(); return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 10); };
const incomeMoney = (value: string | number | null | undefined) => value == null ? '—' : formatCny(Math.abs(Number(value)));
const expenseMoney = (value: string | number | null | undefined) => value == null ? '—' : formatCny(Math.abs(Number(value)));

export default function AccountingPanel({ accounts, summary, profit, reconciliations, accountsError, summaryError, profitError, reconciliationError, month, onChanged, showStats = true }: Props) {
  const [showRecon, setShowRecon] = useState(false);
  const [accountId, setAccountId] = useState(accounts?.find(account => account.is_active)?.id ?? 0);
  const [actual, setActual] = useState('');
  const [date, setDate] = useState(today());
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const activeAccounts = (accounts || []).filter(account => account.is_active);
  // 账户异步加载后直接使用首个 active 账户，避免 effect 级联更新并保持提交行为。
  const selectedAccountId = selectReconciliationAccountId(activeAccounts, accountId);
  const reconciliationItems = reconciliations || [];
  const balances = summary?.fund_accounts ?? [];
  const availableCny = balances.filter(account => account.currency === 'CNY').reduce((sum, account) => sum + Number(account.cny_book_cost || 0), 0);

  const submitRecon = async (event: React.FormEvent) => {
    event.preventDefault(); setBusy(true); setError('');
    if (!selectedAccountId || !validateMoneyInput(actual)) { setError('请选择可用账户并输入非负、最多两位小数的实际余额'); setBusy(false); return; }
    try { await createReconciliation({ account_id: selectedAccountId, business_date: date, actual_amount: actual, note }); setShowRecon(false); setActual(''); setNote(''); onChanged(); }
    catch (requestError) { setError(apiErrorMessage(requestError)); }
    finally { setBusy(false); }
  };

  const confirm = async (id: number) => {
    setBusy(true); setError('');
    try { await confirmReconciliation(id); onChanged(); } catch (requestError) { setError(apiErrorMessage(requestError)); } finally { setBusy(false); }
  };

  return <div className="space-y-5">
{showStats && <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      <div className="rounded-md border border-border bg-white p-4 shadow-sm"><p className="text-[11px] uppercase tracking-wider text-muted">可用余额（CNY 账面）</p><p className="mt-2 font-mono text-2xl font-semibold">{formatCny(availableCny)}</p><p className="mt-1 text-[11px] text-muted">{balances.length} 个账户 · 截至 {summary?.as_of || '—'}</p></div>
      <div className="rounded-md border border-border bg-white p-4 shadow-sm"><p className="text-[11px] uppercase tracking-wider text-muted">本月净利润</p><p className="mt-2 font-mono text-2xl font-semibold text-success">{formatSignedCny(profit?.net_profit_cny)}</p><p className="mt-1 text-[11px] text-muted">收入 {incomeMoney(profit?.sales_revenue_cny)} · {month}</p></div>
      <div className="rounded-md border border-border bg-white p-4 shadow-sm"><p className="text-[11px] uppercase tracking-wider text-muted">库存剩余成本</p><p className="mt-2 font-mono text-2xl font-semibold">{formatCny(summary?.inventory_remaining_cost_cny)}</p><p className="mt-1 text-[11px] text-muted">在途 {formatCny(summary?.purchase_in_transit_cny)}</p></div>
      <div className="rounded-md border border-border bg-[#FFFAF3] p-4 shadow-sm"><p className="text-[11px] uppercase tracking-wider text-muted">待核对差额</p><p className="mt-2 font-mono text-2xl font-semibold text-accent">{reconciliationItems.filter(item => item.status === 'pending').length}</p><p className="mt-1 text-[11px] text-muted">应收 {formatCny(summary?.accounts_receivable_cny)} · 预收 {formatCny(summary?.customer_prepayments_cny)}</p></div>
    </section>}
    <section className="grid gap-5 lg:grid-cols-[1fr_1.15fr]">
      <div className="rounded-md border border-border bg-white shadow-sm"><div className="flex items-center justify-between border-b border-border px-5 py-4"><div><h2 className="font-display text-lg font-semibold">资金账户</h2><p className="text-xs text-muted">余额来自账务摘要接口</p></div><button data-guide="accounting-reconciliation-open" type="button" disabled={!activeAccounts.length || Boolean(accountsError || summaryError)} onClick={() => setShowRecon(true)} className="inline-flex items-center gap-1 rounded border border-border px-3 py-1.5 text-xs font-semibold hover:border-gold"><Plus className="h-3.5 w-3.5" />新建对账</button></div><div className="divide-y divide-border">{accountsError ? <RegionError message={accountsError} /> : summaryError ? <RegionError message={summaryError} /> : !summary ? <RegionLoading /> : !accounts ? <RegionLoading /> : balances.length === 0 ? <p className="px-5 py-8 text-center text-sm text-muted">暂无账户余额</p> : balances.map(account => <div key={account.account_id} className="flex items-center justify-between px-5 py-3"><div><p className="text-sm font-semibold">{account.name}</p><p className="text-[11px] text-muted">{account.currency}</p></div><p className="font-mono text-sm">{account.currency === 'CNY' ? formatCny(account.cny_book_cost) : `${account.original_balance} ${account.currency}`}</p></div>)}</div></div>
      <div data-guide="accounting-profit" className="rounded-md border border-border bg-white shadow-sm"><div className="flex items-center justify-between border-b border-border px-5 py-4"><div><h2 className="font-display text-lg font-semibold">月度利润</h2><p className="text-xs text-muted">FIFO 成本和人肉成本均来自已入账流水</p></div><span className="font-mono text-xs text-muted">{profit?.transaction_count ?? '—'} {profit ? '笔流水' : ''}</span></div>{profitError ? <RegionError message={profitError} /> : !profit ? <RegionLoading /> : <div className="grid grid-cols-2 gap-3 p-5"><Metric label="销售收入" value={incomeMoney(profit.sales_revenue_cny)} /><Metric label="客户人肉费收入" value={incomeMoney(profit.customer_transport_revenue_cny)} /><Metric label="销售成本" value={expenseMoney(profit.cost_of_goods_sold_cny)} /><Metric label="人肉费用" value={expenseMoney(profit.transport_expense_cny)} /><div className="col-span-2 rounded border border-green-100 bg-green-50 p-3"><p className="text-[11px] text-muted">净利润</p><p className="mt-1 font-mono text-xl font-semibold text-success">{formatSignedCny(profit.net_profit_cny)}</p></div></div>}</div>
    </section>
    <section data-guide="accounting-reconciliation" className="rounded-md border border-border bg-white shadow-sm"><div className="flex items-center justify-between border-b border-border px-5 py-4"><div><h2 className="font-display text-lg font-semibold">账户对账</h2><p className="text-xs text-muted">创建实盘快照后，确认才会完成对账闭环。</p></div><ClipboardCheck className="h-5 w-5 text-gold" /></div>{error && <p className="mx-5 mt-3 rounded bg-red-50 px-3 py-2 text-xs text-red-700">{error}</p>}{reconciliationError ? <RegionError message={reconciliationError} /> : !reconciliations ? <RegionLoading /> : <div className="divide-y divide-border">{reconciliations.length === 0 ? <p className="px-5 py-8 text-center text-sm text-muted">暂无对账记录</p> : reconciliations.map(item => { const account = accounts?.find(value => value.id === item.account_id); return <div key={item.id} className="flex flex-col gap-2 px-5 py-3 sm:flex-row sm:items-center sm:justify-between"><div><p className="text-sm font-semibold">{account?.name || `账户 #${item.account_id}`} <span className="ml-2 text-xs font-normal text-muted">{item.business_date}</span></p><p className="text-xs text-muted">系统 {item.system_amount} · 实盘 {item.actual_amount} · 差异 <span className={Number(item.difference) === 0 ? 'text-success' : 'text-accent'}>{item.difference}</span></p></div>{item.status === 'pending' ? <button data-guide="accounting-reconciliation-confirm" type="button" disabled={busy || Boolean(accountsError || summaryError)} onClick={() => confirm(item.id)} className="inline-flex w-fit items-center gap-1 rounded bg-accent px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-50"><Check className="h-3.5 w-3.5" />确认对账</button> : <span className="rounded-full bg-green-50 px-2 py-1 text-[10px] font-bold text-success">已确认</span>}</div>; })}</div>}</section>
    {showRecon && <div role="dialog" aria-modal="true" aria-labelledby="reconciliation-title" className="fixed inset-0 z-50 grid place-items-center bg-fg/30 p-4"><form onSubmit={submitRecon} className="w-full max-w-md rounded-md border border-border bg-white shadow-lg"><div className="flex items-center justify-between border-b border-border px-5 py-4"><h2 id="reconciliation-title" className="font-display text-lg font-semibold">新建账户对账</h2><button type="button" aria-label="关闭账户对账" onClick={() => setShowRecon(false)} className="text-muted">×</button></div><div className="space-y-3 p-5"><label className="block text-xs font-medium text-muted">资金账户<select data-guide="accounting-reconciliation-account" required value={selectedAccountId} onChange={event => setAccountId(Number(event.target.value))} className="mt-1.5 w-full rounded border border-border px-3 py-2 text-sm">{activeAccounts.map(account => <option key={account.id} value={account.id}>{account.name} · {account.currency}</option>)}</select></label><label className="block text-xs font-medium text-muted">业务日期<input data-guide="accounting-reconciliation-date" required type="date" value={date} onChange={event => setDate(event.target.value)} className="mt-1.5 w-full rounded border border-border px-3 py-2 text-sm" /></label><label className="block text-xs font-medium text-muted">实际余额<input data-guide="accounting-reconciliation-actual" required value={actual} onChange={event => setActual(event.target.value)} inputMode="decimal" className="mt-1.5 w-full rounded border border-border px-3 py-2 text-sm" /></label><label className="block text-xs font-medium text-muted">备注<textarea data-guide="accounting-reconciliation-note" value={note} onChange={event => setNote(event.target.value)} rows={2} className="mt-1.5 w-full rounded border border-border px-3 py-2 text-sm" /></label>{error && <p className="text-xs text-red-700">{error}</p>}<button data-guide="accounting-reconciliation-submit" disabled={busy || !selectedAccountId || !actual} className="w-full rounded bg-accent px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">{busy ? '创建中…' : '创建对账'}</button></div></form></div>}
  </div>;
}

function RegionError({ message }: { message: string }) { return <p className="px-5 py-8 text-center text-sm text-red-700">{message}</p>; }
function RegionLoading() { return <p className="px-5 py-8 text-center text-sm text-muted">加载中…</p>; }
function Metric({ label, value }: { label: string; value: string }) { return <div className="rounded border border-border bg-[#FFFDFA] p-3"><p className="text-[11px] text-muted">{label}</p><p className="mt-1 font-mono text-base font-semibold">{value}</p></div>; }
