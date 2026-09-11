import { useRef, useState } from 'react';
import type { AccountingTransaction, FundAccount } from '../../types';
import { apiErrorMessage } from '../../api';
import { moscowBusinessDate } from '../../utils/businessDate';
import { formatDecimalAmount, formatDecimalRatio } from '../../utils/decimalDisplay';
import { useDialogFocus } from '../../hooks/useDialogFocus';

interface ExchangeDetailsProps {
  month: string;
  transactions?: AccountingTransaction[];
  accounts?: FundAccount[];
  loading?: boolean;
  error?: string;
  onReverse?: (transaction: AccountingTransaction, businessDate: string, reason: string) => Promise<void>;
}

function accountLabel(accountId: number | null, accounts: FundAccount[]): string {
  if (accountId == null) return '未知账户';
  const account = accounts.find(item => item.id === accountId);
  return account ? `${account.name} · ${account.currency}` : `账户 #${accountId}`;
}

function amountText(value: string, currency: string): string {
  return `${formatDecimalAmount(value, currency, true)} ${currency}`;
}

export default function ExchangeDetails({ month, transactions = [], accounts = [], loading = false, error, onReverse }: ExchangeDetailsProps) {
  const [reversal, setReversal] = useState<{ transaction: AccountingTransaction; businessDate: string; reason: string } | null>(null);
  const [reversing, setReversing] = useState(false);
  const [reverseError, setReverseError] = useState('');
  const requestInFlight = useRef(false);
  const rows = transactions.filter(item => item.source_type !== 'ledger_reversal').sort((left, right) => right.business_date.localeCompare(left.business_date) || right.id - left.id);
  const confirmReverse = async () => {
    if (!reversal || !onReverse || !reversal.reason.trim() || reversing || requestInFlight.current) return;
    const pending = reversal;
    requestInFlight.current = true;
    setReversing(true);
    setReverseError('');
    try {
      await onReverse(pending.transaction, pending.businessDate, pending.reason.trim());
      setReversal(current => current?.transaction.id === pending.transaction.id ? null : current);
    } catch (requestError) {
      setReverseError(apiErrorMessage(requestError, '换汇回撤失败'));
    } finally {
      requestInFlight.current = false;
      setReversing(false);
    }
  };
  return <section className="mt-5 overflow-hidden rounded-md border border-border bg-white shadow-sm">
    <div className="flex flex-wrap items-end justify-between gap-3 border-b border-border px-5 py-4">
      <div><p className="text-[11px] font-bold uppercase tracking-[.12em] text-accent">Exchange ledger</p><h2 className="mt-1 font-display text-lg font-semibold">换汇明细</h2><p className="mt-1 text-xs text-muted">按业务日期展示本月已入账的 CNY / USDT → RUB 换汇。</p></div>
      <div className="text-right"><p className="text-[11px] text-muted">记录数</p><p className="mt-0.5 font-mono text-sm font-semibold">{loading ? '…' : rows.length} <span className="font-sans text-xs font-normal text-muted">笔</span></p></div>
    </div>
    {error && <p role="alert" className="m-5 rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}
    {loading ? <div role="status" className="px-5 py-8 text-center text-sm text-muted">换汇明细加载中…</div> : !error && rows.length === 0 ? <div className="px-5 py-8 text-center text-sm text-muted">{month} 暂无换汇记录</div> : !error && <div className="overflow-x-auto"><table className="w-full min-w-[860px] text-left text-sm"><thead className="border-b border-border bg-[#FFFDFA] text-[11px] text-muted"><tr><th className="whitespace-nowrap px-5 py-3 font-semibold">日期</th><th className="whitespace-nowrap px-3 py-3 font-semibold">转出账户</th><th className="whitespace-nowrap px-3 py-3 text-right font-semibold">转出金额</th><th className="whitespace-nowrap px-3 py-3 font-semibold">转入账户</th><th className="whitespace-nowrap px-3 py-3 text-right font-semibold">转入金额</th><th className="whitespace-nowrap px-3 py-3 text-right font-semibold">实际汇率</th><th className="whitespace-nowrap px-5 py-3 text-right font-semibold">操作</th></tr></thead><tbody>{rows.map(transaction => { const source = transaction.postings.find(posting => posting.amount.trim().startsWith('-')); const target = transaction.postings.find(posting => posting.currency === 'RUB' && !posting.amount.trim().startsWith('-') && posting.amount !== '0'); const rate = source && target ? formatDecimalRatio(target.amount, source.amount.replace(/^\s*-/, '')) : null; return <tr key={transaction.id} className="border-b border-border last:border-0 hover:bg-[#FFFCF9]"><td className="whitespace-nowrap px-5 py-3 font-mono text-xs text-muted">{transaction.business_date}</td><td className="px-3 py-3 text-xs">{accountLabel(source?.account_id ?? null, accounts)}</td><td className="whitespace-nowrap px-3 py-3 text-right font-mono text-xs">{source ? amountText(source.amount, source.currency) : '—'}</td><td className="px-3 py-3 text-xs">{accountLabel(target?.account_id ?? null, accounts)}</td><td className="whitespace-nowrap px-3 py-3 text-right font-mono text-xs">{target ? amountText(target.amount, target.currency) : '—'}</td><td className="whitespace-nowrap px-3 py-3 text-right font-mono text-xs">{rate == null ? '—' : `${rate} RUB / 原币`}</td><td className="whitespace-nowrap px-5 py-3 text-right text-xs">{transaction.reversed_by_id ? <span className="rounded-full bg-[#F1ECE5] px-2 py-1 text-muted" title={transaction.reversal_business_date ? `冲正日期 ${transaction.reversal_business_date}` : undefined}>已撤回</span> : onReverse ? <button type="button" onClick={() => { setReverseError(''); setReversal({ transaction, businessDate: moscowBusinessDate(), reason: '' }); }} className="rounded border border-accent px-2 py-1 font-semibold text-accent hover:bg-accent-light">撤回</button> : '—'}</td></tr>; })}</tbody></table></div>}
    {reversal && <ExchangeReversalModal value={reversal} accounts={accounts} busy={reversing} error={reverseError} onChange={setReversal} onCancel={() => { if (!reversing) setReversal(null); }} onConfirm={confirmReverse} />}
  </section>;
}

export function ExchangeReversalModal({ value, accounts, busy, error, onChange, onCancel, onConfirm }: {
  value: { transaction: AccountingTransaction; businessDate: string; reason: string };
  accounts: FundAccount[];
  busy: boolean;
  error?: string;
  onChange: (value: { transaction: AccountingTransaction; businessDate: string; reason: string }) => void;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const dialogRef = useDialogFocus(onCancel, busy);
  const source = value.transaction.postings.find(posting => posting.amount.trim().startsWith('-'));
  const target = value.transaction.postings.find(posting => posting.currency === 'RUB' && !posting.amount.trim().startsWith('-') && posting.amount !== '0');
  return <div role="presentation" className="fixed inset-0 z-50 grid place-items-center bg-fg/50 p-3 backdrop-blur-sm" onMouseDown={event => { if (event.target === event.currentTarget && !busy) onCancel(); }}><div ref={dialogRef} tabIndex={-1} role="dialog" aria-modal="true" aria-labelledby="exchange-reversal-title" aria-describedby="exchange-reversal-risk" className="w-full max-w-lg overflow-hidden rounded-lg bg-white shadow-2xl outline-none"><div className="border-b border-border px-5 py-4"><p className="text-[11px] font-bold uppercase tracking-[.12em] text-accent">Controlled reversal</p><h2 id="exchange-reversal-title" className="mt-1 font-display text-xl font-semibold">确认回撤换汇</h2><p className="mt-1 text-xs text-muted">保留原记录，并新增金额完全相反的正式流水。</p></div><div className="space-y-4 px-5 py-5"><p id="exchange-reversal-risk" className="rounded border border-[#E3C3C6] bg-[#FAF1F0] px-3 py-3 text-sm leading-6 text-accent">将回撤 {source ? `${accountLabel(source.account_id, accounts)} 的 ${amountText(source.amount, source.currency)}` : '原币转出'} → {target ? `${accountLabel(target.account_id, accounts)} 的 ${amountText(target.amount, target.currency)}` : '卢布转入'}。若任一账户已有后续流水，后端会拒绝本次操作。</p><label className="block text-xs font-semibold text-muted">回撤日期 *<input type="date" value={value.businessDate} disabled={busy} onChange={event => onChange({ ...value, businessDate: event.target.value })} className="mt-1.5 w-full rounded border border-border px-3 py-2 text-sm disabled:bg-cream" /></label><label className="block text-xs font-semibold text-muted">回撤原因 *<textarea rows={2} value={value.reason} disabled={busy} onChange={event => onChange({ ...value, reason: event.target.value })} placeholder="例如：实际到账金额录入错误" className="mt-1.5 w-full resize-y rounded border border-border px-3 py-2 text-sm disabled:bg-cream" /></label>{error && <p role="alert" className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}</div><footer className="flex justify-end gap-2 border-t border-border bg-[#FFFDF9] px-5 py-4"><button type="button" disabled={busy} onClick={onCancel} className="rounded border border-border bg-white px-3 py-2 text-sm font-semibold hover:border-gold disabled:opacity-50">取消</button><button type="button" disabled={busy || !value.businessDate || !value.reason.trim()} onClick={onConfirm} className="rounded border border-accent bg-white px-4 py-2 text-sm font-semibold text-accent hover:bg-accent-light disabled:opacity-50">{busy ? '回撤中…' : '确认回撤并写入反向流水'}</button></footer></div></div>;
}
