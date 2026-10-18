import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { apiErrorMessage, fetchFundReceipts, recordFundReceipt } from '../../api';
import type { FundAccount, FundReceiptPayload, FundReceiptsResponse } from '../../types';
import { useDialogFocus } from '../../hooks/useDialogFocus';
import { moscowBusinessDate } from '../../utils/businessDate';
import { formatCny } from '../sales/salesState';

const buttonClass = 'min-h-11 rounded border border-border px-3 py-2 text-sm font-semibold disabled:opacity-50';
const inputClass = 'mt-1 block min-h-11 w-full rounded border border-border bg-white px-3 py-2 text-base';

export default function FundReceiptAction({ accounts, disabled = false, onChanged }: {
  accounts: FundAccount[]; disabled?: boolean; onChanged: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [history, setHistory] = useState(false);
  const [page, setPage] = useState(1);
  const [revision, setRevision] = useState(0);
  const [result, setResult] = useState<{ key: string; data?: FundReceiptsResponse; error: string }>();
  const requestKey = `${open}:${history}:${page}:${revision}`;
  const loading = (open || history) && result?.key !== requestKey;
  const error = result?.key === requestKey ? result.error : '';
  const data = result?.data;
  const [notice, setNotice] = useState('');
  useEffect(() => {
    if (!open && !history) return;
    let cancelled = false;
    fetchFundReceipts(page).then(data => { if (!cancelled) setResult({ key: requestKey, data, error: '' }); })
      .catch(failure => { if (!cancelled) setResult({ key: requestKey, error: apiErrorMessage(failure, '入账记录加载失败') }); });
    return () => { cancelled = true; };
  }, [open, history, page, requestKey]);

  const completed = () => {
    setOpen(false); setHistory(true); setPage(1); setRevision(value => value + 1);
    setNotice('人民币已入账，可继续换汇和采购付款。');
    try { onChanged(); } catch { setNotice('人民币已入账，请刷新页面查看余额。'); }
  };
  const ready = !loading && !error && Boolean(data);
  return <div className="border-t border-border p-4">
    <div inert={open}>
      <div className="flex flex-wrap gap-2">
        <button type="button" className={buttonClass} disabled={disabled} onClick={() => { setNotice(''); setOpen(true); }}>人民币入账</button>
        <button type="button" className={`${buttonClass} text-muted`} aria-expanded={history} onClick={() => setHistory(value => !value)}>{history ? '收起入账记录' : '查看入账记录'}</button>
      </div>
      {notice && <p role="status" className="mt-3 text-sm text-success">{notice}</p>}
      {history && <div className="mt-3 space-y-3">
        {loading && <p className="text-sm text-muted">加载中…</p>}
        {error && <p role="alert" className="text-sm text-red-700">{error} <button className={buttonClass} onClick={() => setRevision(value => value + 1)}>重试</button></p>}
        {ready && <>
          {data!.receipts.length === 0 && <p className="text-sm text-muted">暂无人民币入账记录</p>}
          {data!.receipts.map(receipt => <article key={receipt.id} className="rounded border border-border bg-cream p-3 text-sm">
            <div className="flex flex-wrap justify-between gap-2"><strong className="break-all">{receipt.contributor_name}</strong><span className="font-mono text-success">+{formatCny(receipt.amount_cny)}</span></div>
            <p className="mt-1 break-all text-xs text-muted">{receipt.business_date} · {receipt.fund_account_name} · 流水 #{receipt.ledger_transaction_id}</p>
            {receipt.note && <p className="mt-2 whitespace-pre-wrap break-words">{receipt.note}</p>}
          </article>)}
          <div className="flex items-center justify-between gap-2"><button className={buttonClass} disabled={page === 1} onClick={() => setPage(value => value - 1)}>上一页</button><span className="text-xs text-muted">第 {page} 页</span><button className={buttonClass} disabled={!data!.next_page} onClick={() => setPage(data!.next_page!)}>下一页</button></div>
        </>}
      </div>}
    </div>
    {open && <ReceiptDialog accounts={accounts} contributors={ready ? data!.contributors : []} loading={loading} loadError={error}
      retry={() => setRevision(value => value + 1)} onClose={() => setOpen(false)} onDone={completed} />}
  </div>;
}

function ReceiptDialog({ accounts, contributors, loading, loadError, retry, onClose, onDone }: {
  accounts: FundAccount[]; contributors: { id: number; name: string }[]; loading: boolean;
  loadError: string; retry: () => void; onClose: () => void; onDone: () => void;
}) {
  const [form, setForm] = useState({ contributor: '', account: '', amount: '', date: moscowBusinessDate(), note: '' });
  const [confirmation, setConfirmation] = useState<{ payload: FundReceiptPayload; name: string; account: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false);
  const [error, setError] = useState('');
  const close = () => { if (!inFlight.current) onClose(); };
  const dialogRef = useDialogFocus(close, busy);
  useEffect(() => {
    const previous = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => { document.body.style.overflow = previous; };
  }, []);
  const cnyAccounts = accounts.filter(account => account.is_active && account.currency === 'CNY');
  const validAmount = /^\d{1,12}(\.\d{1,2})?$/.test(form.amount) && /[1-9]/.test(form.amount);
  const valid = validAmount && form.date >= '2026-08-10' && form.date <= moscowBusinessDate()
    && contributors.some(user => String(user.id) === form.contributor)
    && cnyAccounts.some(account => String(account.id) === form.account) && !loading && !loadError;
  const preview = () => {
    if (!valid) return;
    const [whole, fraction = ''] = form.amount.split('.');
    setError('');
    setConfirmation({
      payload: { contributor_id: Number(form.contributor), fund_account_id: Number(form.account),
        amount_cny: `${BigInt(whole)}.${fraction.padEnd(2, '0')}`, business_date: form.date, note: form.note },
      name: contributors.find(user => String(user.id) === form.contributor)!.name,
      account: cnyAccounts.find(account => String(account.id) === form.account)!.name,
    });
  };
  const confirm = async () => {
    if (!confirmation || inFlight.current) return;
    inFlight.current = true; setBusy(true); setError('');
    try { await recordFundReceipt(confirmation.payload); }
    catch (failure) { setError(apiErrorMessage(failure, '入账失败，请重试')); inFlight.current = false; setBusy(false); return; }
    inFlight.current = false; setBusy(false); onDone();
  };

  return createPortal(<div className="fixed inset-0 z-[70] flex items-end justify-center bg-fg/40 sm:items-center sm:p-4">
    <div ref={dialogRef} tabIndex={-1} role="dialog" aria-modal="true" aria-labelledby="fund-receipt-title"
      className="flex max-h-[100dvh] w-full max-w-lg flex-col rounded-t-lg border border-border bg-white shadow-xl outline-none sm:max-h-[90dvh] sm:rounded-lg">
      <header className="flex shrink-0 items-center justify-between gap-2 border-b border-border px-4 py-3"><h2 id="fund-receipt-title" className="font-display text-lg font-semibold">{confirmation ? '确认人民币入账' : '人民币入账'}</h2><button type="button" className={buttonClass} disabled={busy} onClick={close} aria-label="关闭人民币入账">关闭</button></header>
      <div className="min-h-0 space-y-4 overflow-y-auto p-4">
        <p className="text-sm text-muted">记录投入公司的资金，不计收入和利润。到账后可继续换汇买货。</p>
        {confirmation ? <dl className="space-y-3 rounded border border-border bg-cream p-4 text-sm">
          <div><dt className="text-muted">投入人</dt><dd className="break-all font-semibold">{confirmation.name}</dd></div>
          <div><dt className="text-muted">到账账户</dt><dd className="break-all font-semibold">{confirmation.account}</dd></div>
          <div><dt className="text-muted">到账金额</dt><dd className="font-mono text-lg font-semibold">{formatCny(confirmation.payload.amount_cny)}</dd></div>
          <div><dt className="text-muted">实际到账日期</dt><dd>{confirmation.payload.business_date}</dd></div>
          {confirmation.payload.note && <div><dt className="text-muted">备注</dt><dd className="whitespace-pre-wrap break-words">{confirmation.payload.note}</dd></div>}
        </dl> : <form id="fund-receipt-form" onSubmit={event => { event.preventDefault(); preview(); }} className="space-y-4">
          {loading && <p className="text-sm text-muted">加载投入人…</p>}
          {loadError && <p role="alert" className="text-sm text-red-700">{loadError} <button type="button" className={buttonClass} onClick={retry}>重试</button></p>}
          <label className="block text-sm">投入人<select className={inputClass} value={form.contributor} required onChange={event => setForm({ ...form, contributor: event.target.value })}><option value="">选择投入人</option>{contributors.map(user => <option key={user.id} value={user.id}>{user.name}</option>)}</select></label>
          <label className="block text-sm">到账账户<select className={inputClass} value={form.account} required onChange={event => setForm({ ...form, account: event.target.value })}><option value="">选择人民币账户</option>{cnyAccounts.map(account => <option key={account.id} value={account.id}>{account.name}</option>)}</select></label>
          {!cnyAccounts.length && <p className="text-sm text-muted">请先在资金账户中创建或启用人民币账户。</p>}
          <label className="block text-sm">到账金额（CNY）<input className={inputClass} inputMode="decimal" required maxLength={15} placeholder="例如 30000.00" value={form.amount} onChange={event => setForm({ ...form, amount: event.target.value })} /></label>
          {form.amount && !validAmount && <p role="alert" className="text-sm text-red-700">请输入大于零、小于一万亿元的金额，最多两位小数。</p>}
          <label className="block text-sm">实际到账日期<input className={`${inputClass} min-w-0 max-w-full`} type="date" required min="2026-08-10" max={moscowBusinessDate()} value={form.date} onChange={event => setForm({ ...form, date: event.target.value })} /></label>
          <label className="block text-sm">备注（选填）<textarea className={inputClass} rows={2} maxLength={2000} value={form.note} onChange={event => setForm({ ...form, note: event.target.value })} /></label>
        </form>}
        {confirmation && <p className="text-xs text-muted">请确认资金已实际到账。确认后保留正式流水，当前不提供撤回操作。</p>}
        {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
      </div>
      <footer className="flex shrink-0 gap-3 border-t border-border px-4 pb-[max(1rem,env(safe-area-inset-bottom))] pt-3">
        <button type="button" className={`${buttonClass} flex-1`} disabled={busy} onClick={() => { if (confirmation) { setConfirmation(null); setError(''); } else close(); }}>{confirmation ? '返回修改' : '取消'}</button>
        {confirmation ? <button type="button" disabled={busy} className={`${buttonClass} flex-[2] border-accent bg-accent text-white`} onClick={() => void confirm()}>{busy ? '入账中…' : '确认入账'}</button>
          : <button type="submit" form="fund-receipt-form" disabled={!valid} className={`${buttonClass} flex-[2] border-accent bg-accent text-white`}>核对入账信息</button>}
      </footer>
    </div>
  </div>, document.body);
}
