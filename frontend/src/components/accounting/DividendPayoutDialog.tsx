import { useEffect, useId, useRef, useState, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { X } from 'lucide-react';
import { parseAccountingApiError, recordDividendPayout } from '../../api';
import { isRetryableWriteError } from '../../api/idempotency';
import type { DividendPayoutPayload, DividendRound, FundAccount } from '../../types';
import { useDialogFocus } from '../../hooks/useDialogFocus';
import { dividendCents, dividendMoney, dividendInputClass, dividendButtonClass, dividendSecondaryClass } from './DividendRoundsAction.logic';

export function DividendDialog({ title, busy, onClose, children, entry = false, focusKey }: {
  title: string; busy: boolean; onClose: () => void; children: ReactNode; entry?: boolean; focusKey?: string;
}) {
  const ref = useDialogFocus(onClose, busy);
  const titleId = useId();
  // Replacing the entry form or warning removes its focused control.
  useEffect(() => { ref.current?.focus(); }, [ref, title, focusKey]);
  useEffect(() => {
    const previous = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => { document.body.style.overflow = previous; };
  }, []);
  return createPortal(<div role="presentation" className="fixed inset-0 z-50 grid place-items-center bg-fg/50 p-3 backdrop-blur-sm" onMouseDown={event => { if (event.target === event.currentTarget && !busy) onClose(); }}>
    <div ref={ref} tabIndex={-1} role="dialog" aria-modal="true" aria-labelledby={titleId} className={`flex max-h-[calc(100dvh-24px)] w-full flex-col overflow-hidden rounded-lg bg-white text-fg shadow-lg outline-none ${entry ? 'max-w-[640px]' : 'max-w-lg'}`}>
      <header className="flex shrink-0 items-center justify-between gap-3 border-b border-border px-5 py-3">
        <h2 id={titleId} className="font-display text-xl font-semibold">{title}</h2>
        <button type="button" aria-label="关闭分红弹窗" disabled={busy} onClick={onClose} className="inline-flex min-h-11 min-w-11 items-center justify-center rounded border border-border text-muted hover:border-gold hover:text-fg disabled:opacity-50"><X className="h-4 w-4" /></button>
      </header>
      <div className={entry ? 'flex min-h-0 flex-col' : 'space-y-4 overflow-y-auto p-5'}>{children}</div>
    </div>
  </div>, document.body);
}

export default function DividendPayoutDialog({ round, accounts, businessDate, onClose, onSaved }: {
  round: DividendRound; accounts: FundAccount[]; businessDate: string; onClose: () => void; onSaved: () => void;
}) {
  const [input, setInput] = useState({ recipient: '', account: '', amount: '', date: businessDate < round.business_date ? round.business_date : businessDate, note: '' });
  const [confirmation, setConfirmation] = useState<{ payload: DividendPayoutPayload; name: string; account: string } | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [uncertain, setUncertain] = useState(false);
  const inFlight = useRef(false);
  const cnyAccounts = accounts.filter(account => account.is_active && account.currency === 'CNY');
  const prepare = () => {
    const recipient = round.partners.find(user => String(user.id) === input.recipient);
    const account = cnyAccounts.find(account => String(account.id) === input.account);
    const amount = dividendCents(input.amount);
    if (!recipient || !account || amount === null || amount <= 0n) { setError('请选择领取人、人民币公司账户并填写正数金额'); return; }
    if (amount > (dividendCents(recipient.pending_cny) ?? 0n)) { setError('领取金额超过该人的剩余待领金额'); return; }
    if (!input.date || input.date < round.business_date) { setError('领取日期不能早于分配日期'); return; }
    setError('');
    setConfirmation({ name: recipient.name, account: account.name, payload: { recipient_id: recipient.id, fund_account_id: account.id, amount_cny: dividendMoney(amount), business_date: input.date, note: input.note } });
  };
  const save = async () => {
    if (!confirmation || inFlight.current) return;
    inFlight.current = true; setBusy(true); setError('');
    try { await recordDividendPayout(round.id, confirmation.payload); }
    catch (failure) { setError(parseAccountingApiError(failure).message); setUncertain(isRetryableWriteError(failure)); inFlight.current = false; setBusy(false); return; }
    inFlight.current = false; setBusy(false); onSaved();
  };
  return <DividendDialog title={confirmation ? '确认历史分红领取' : '继续登记领取'} busy={busy || uncertain} onClose={onClose}>
    {confirmation ? <>
      <dl className="space-y-2 rounded border border-gold/30 bg-[#FFFDF7] p-3 text-sm">{[
        ['领取人', confirmation.name], ['领取金额', `${confirmation.payload.amount_cny} CNY`],
        ['公司付款账户', confirmation.account], ['实际支付日期', confirmation.payload.business_date], ['备注', confirmation.payload.note || '—'],
      ].map(([label, value]) => <div key={label} className="flex justify-between gap-3"><dt className="text-muted">{label}</dt><dd className="whitespace-pre-wrap break-words text-right">{value}</dd></div>)}</dl>
      <p className="text-sm text-muted">登记已发生的付款，扣减公司账户余额与待领金额，不再扣减利润。</p>
      {error && <p role="alert" className="text-sm text-accent">{error}</p>}
      {uncertain && <p className="text-sm text-muted">结果尚未确认，请重试本次记录，避免重复登记。</p>}
      <footer className="flex justify-end gap-2"><button disabled={busy || uncertain} onClick={() => { setError(''); setConfirmation(null); }} className={dividendSecondaryClass}>返回修改</button><button disabled={busy} onClick={() => void save()} className={dividendButtonClass}>{busy ? '保存中…' : uncertain ? '重试本次领取' : '确认记录领取'}</button></footer>
    </> : <form onSubmit={event => { event.preventDefault(); prepare(); }} className="space-y-3">
      <p className="text-sm text-muted">分配日期 {round.business_date} · 仅补记历史待领分红。</p>
      <label className="block text-sm">领取人<select value={input.recipient} onChange={event => setInput({ ...input, recipient: event.target.value })} className={dividendInputClass}><option value="">选择领取人</option>{round.partners.map(partner => <option key={partner.id} value={partner.id} disabled={(dividendCents(partner.pending_cny) ?? 0n) <= 0n}>{partner.name} · 待领 {partner.pending_cny} CNY</option>)}</select></label>
      <label className="block text-sm">公司付款账户<select value={input.account} onChange={event => setInput({ ...input, account: event.target.value })} className={dividendInputClass}><option value="">选择人民币账户</option>{cnyAccounts.map(account => <option key={account.id} value={account.id}>{account.name}</option>)}</select></label>
      <label className="block text-sm">领取金额（CNY）<input inputMode="decimal" value={input.amount} onChange={event => setInput({ ...input, amount: event.target.value })} className={dividendInputClass} /></label>
      <label className="block text-sm">实际支付日期<input type="date" min={round.business_date} value={input.date} onChange={event => setInput({ ...input, date: event.target.value })} className={dividendInputClass} /></label>
      <label className="block text-sm">领取备注<textarea value={input.note} onChange={event => setInput({ ...input, note: event.target.value })} className={dividendInputClass} /></label>
      {error && <p role="alert" className="text-sm text-accent">{error}</p>}
      <footer className="flex justify-end gap-2"><button type="button" onClick={onClose} className={dividendSecondaryClass}>取消</button><button type="submit" className={dividendButtonClass}>核对领取</button></footer>
    </form>}
  </DividendDialog>;
}
