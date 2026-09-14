import { useRef, useState, type ReactNode } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { confirmDividendRound, fetchDividendRounds, parseAccountingApiError, previewDividendRound, recordDividendPayout } from '../../api';
import type { DividendPayoutPayload, DividendPreview, DividendRound, DividendRoundPayload, FundAccount } from '../../types';
import { useDialogFocus } from '../../hooks/useDialogFocus';
import { dividendCents } from './DividendRoundsAction.logic';

const inputClass = 'mt-1 block w-full rounded border border-border bg-white p-2 text-sm';
const buttonClass = 'rounded bg-accent px-4 py-2 text-sm font-semibold text-white disabled:opacity-50';
const secondaryClass = 'rounded border border-border bg-white px-3 py-2 text-sm disabled:opacity-50';

function money(cents: bigint): string {
  return `${cents / 100n}.${(cents % 100n).toString().padStart(2, '0')}`;
}

type Allocation = { kind: 'allocation'; payload: DividendRoundPayload; names: string[]; half: string; preview: DividendPreview; stale: boolean };
type Payout = { kind: 'payout'; round: DividendRound; input: { recipient: string; account: string; amount: string; date: string; note: string }; confirmation?: { payload: DividendPayoutPayload; name: string; account: string } };
type Dialog = Allocation | Payout;

export default function DividendRoundsAction({ accounts, businessDate, onChanged }: {
  accounts: FundAccount[]; businessDate: string; onChanged?: () => void;
}) {
  const client = useQueryClient();
  const [page, setPage] = useState(1);
  const query = useQuery({ queryKey: ['dividend-rounds', page], queryFn: () => fetchDividendRounds(page) });
  const recipients = query.data?.recipients ?? [];
  const cnyAccounts = accounts.filter(account => account.is_active && account.currency === 'CNY');
  const [input, setInput] = useState({ total: '', a: '', b: '', date: businessDate, note: '' });
  const [dialog, setDialog] = useState<Dialog | null>(null);
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [ack, setAck] = useState(false);
  const cents = dividendCents(input.total);
  const half = cents !== null && cents > 0n && cents % 2n === 0n ? money(cents / 2n) : null;
  const validAllocation = Boolean(half && input.date && input.a !== input.b
    && recipients.some(user => String(user.id) === input.a) && recipients.some(user => String(user.id) === input.b));

  const refresh = () => {
    void client.invalidateQueries({ queryKey: ['dividend-rounds'] });
    try { onChanged?.(); } catch { setNotice('记账成功；页面刷新失败，请点击重新加载。'); }
  };
  const begin = () => {
    if (inFlight.current) return false;
    inFlight.current = true; setBusy(true); setError(''); setNotice(''); return true;
  };
  const finish = () => { inFlight.current = false; setBusy(false); };
  const close = () => { if (!inFlight.current) { setDialog(null); setError(''); } };

  const preview = async () => {
    if (!validAllocation || !half || !begin()) return;
    const payload: DividendRoundPayload = { total_cny: money(cents!), partner_a_id: Number(input.a), partner_b_id: Number(input.b), business_date: input.date, note: input.note };
    const names = [input.a, input.b].map(id => recipients.find(user => String(user.id) === id)!.name);
    try {
      const result = await previewDividendRound(payload);
      setAck(false);
      setDialog({ kind: 'allocation', payload, names, half, preview: result, stale: false });
    } catch (failure) { setError(parseAccountingApiError(failure).message); } finally { finish(); }
  };

  const freshPreview = async () => {
    if (dialog?.kind !== 'allocation' || !begin()) return;
    const frozen = dialog;
    try {
      const result = await previewDividendRound(frozen.payload);
      setAck(false); setDialog({ ...frozen, preview: result, stale: false });
    } catch (failure) { setError(parseAccountingApiError(failure).message); } finally { finish(); }
  };

  const confirm = async () => {
    if (!dialog || (dialog.kind === 'allocation' && (dialog.stale || (dialog.preview.warning && !ack)))
      || (dialog.kind === 'payout' && !dialog.confirmation) || !begin()) return;
    const frozen = dialog;
    try {
      if (frozen.kind === 'allocation') {
        await confirmDividendRound({ ...frozen.payload, warning_fingerprint: frozen.preview.warning_fingerprint, warning_ack: ack });
      } else {
        await recordDividendPayout(frozen.round.id, frozen.confirmation!.payload);
      }
    } catch (failure) {
      const parsed = parseAccountingApiError(failure);
      setError(parsed.message);
      if (parsed.code === 'warning_stale' && frozen.kind === 'allocation') { setDialog({ ...frozen, stale: true }); setAck(false); }
      finish(); return;
    }
    setDialog(null); setNotice(frozen.kind === 'allocation' ? '分配已确认，现金尚未支付。' : '领取已入账。');
    finish(); refresh();
  };

  const confirmPayoutInput = () => {
    if (dialog?.kind !== 'payout' || inFlight.current) return;
    const { input: value, round } = dialog;
    const recipient = round.partners.find(user => String(user.id) === value.recipient);
    const account = cnyAccounts.find(account => String(account.id) === value.account);
    const amount = dividendCents(value.amount);
    if (!recipient || !account || amount === null || amount <= 0n) { setError('请选择领取人、人民币公司账户并填写正数金额'); return; }
    if (amount > (dividendCents(recipient.pending_cny) ?? 0n)) { setError('领取金额超过该人的剩余待领金额'); return; }
    if (!value.date || value.date < round.business_date) { setError('领取日期不能早于分配日期'); return; }
    setError('');
    setDialog({ ...dialog, confirmation: { name: recipient.name, account: account.name,
      payload: { recipient_id: recipient.id, fund_account_id: account.id, amount_cny: money(amount), business_date: value.date, note: value.note } } });
  };

  return <section tabIndex={-1} data-guide="accounting-actions-dividend" className="text-fg">
    <div inert={Boolean(dialog)}>
      <h2 className="font-display text-xl font-semibold">分红分配与领取</h2>
      <p className="mt-1 text-sm text-muted">每轮两人各 50%。确认分配不付现金；实际领取单独记账，可分期、使用同一公司账户。</p>
      <form onSubmit={event => { event.preventDefault(); void preview(); }} className="my-5 rounded border border-border bg-[#FAF8F5] p-4">
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="text-sm">分红总额（CNY）<input data-guide="accounting-dividend-total" inputMode="decimal" value={input.total} onChange={event => setInput({ ...input, total: event.target.value })} className={inputClass} /></label>
          <label className="text-sm">分配日期<input data-guide="accounting-dividend-date" type="date" value={input.date} onChange={event => setInput({ ...input, date: event.target.value })} className={inputClass} /></label>
          {(['a', 'b'] as const).map((key, index) => <label key={key} className="text-sm">领取人 {index + 1}<select data-guide={`accounting-dividend-partner-${key}`} value={input[key]} onChange={event => setInput({ ...input, [key]: event.target.value })} className={inputClass}><option value="">选择系统用户</option>{recipients.map(user => <option key={user.id} value={user.id} disabled={String(user.id) === input[key === 'a' ? 'b' : 'a']}>{user.name}</option>)}</select></label>)}
          <label className="text-sm sm:col-span-2">分配备注<textarea value={input.note} onChange={event => setInput({ ...input, note: event.target.value })} className={inputClass} /></label>
        </div>
        <p className="my-3 text-sm text-muted">{half ? `每人 ${half} CNY` : '总额须为正且能按分精确平分，例如 100.02 元；100.01 元不可平分。'}</p>
        <button data-guide="accounting-dividend-preview" type="submit" disabled={busy || !validAllocation} className={buttonClass}>{busy ? '预览中…' : '预览分配'}</button>
      </form>
      {!dialog && error && <p role="alert" className="my-3 text-sm text-red-700">{error}</p>}
      {notice && <p role="status" className="my-3 text-sm text-accent">{notice}</p>}
      {query.isPending && <p role="status">正在加载分红轮次…</p>}
      {query.error && <p role="alert" className="my-3 text-sm text-red-700">{parseAccountingApiError(query.error).message}<button onClick={() => void query.refetch()} className={secondaryClass}>重新加载</button></p>}
      <div className="space-y-4">{query.data?.rounds.map(round => <article key={round.id} className="rounded border border-border bg-white p-4">
        <div className="flex flex-wrap items-center justify-between gap-2"><h3 className="font-semibold">第 {round.id} 轮 · {round.total_cny} CNY</h3><span className="text-xs text-muted">{round.business_date} · 分配流水 #{round.ledger_transaction_id}</span></div>
        <div className="my-3 grid gap-3 sm:grid-cols-2">{round.partners.map(partner => <div key={partner.id} className="rounded border border-border bg-[#FAF8F5] p-3"><h4 className="font-semibold">{partner.name} · 50%</h4><dl className="mt-2 grid grid-cols-3 gap-2 text-xs">{[['应分', partner.allocated_cny], ['已领', partner.paid_cny], ['待领', partner.pending_cny]].map(([label, amount]) => <div key={label}><dt className="text-muted">{label}</dt><dd className="mt-1 break-all font-mono text-sm">{amount}</dd></div>)}</dl></div>)}</div>
        {round.note && <p className="mb-3 whitespace-pre-wrap break-words text-sm text-muted">{round.note}</p>}
        {(dividendCents(round.pending_cny) ?? 0n) > 0n && <button type="button" disabled={busy} onClick={() => { setError(''); setDialog({ kind: 'payout', round, input: { recipient: '', account: '', amount: '', date: businessDate < round.business_date ? round.business_date : businessDate, note: '' } }); }} className={secondaryClass}>记录领取 · 第 {round.id} 轮</button>}
        {round.payouts.length > 0 && <details className="mt-3 text-sm"><summary className="cursor-pointer text-muted">领取记录（{round.payouts.length}）</summary><ul className="mt-2 space-y-2">{round.payouts.map(payout => <li key={payout.id} className="rounded border border-border p-2"><p>{payout.recipient_name} · <span className="font-mono">{payout.amount_cny} CNY</span></p><p className="text-xs text-muted">{payout.business_date} · {payout.fund_account_name} · 流水 #{payout.ledger_transaction_id}</p>{payout.note && <p className="whitespace-pre-wrap break-words">{payout.note}</p>}</li>)}</ul></details>}
      </article>)}</div>
      {query.data && <div className="my-4 flex items-center gap-3 text-sm"><button disabled={busy || page === 1} onClick={() => setPage(page - 1)} className={secondaryClass}>上一页</button><span>第 {page} 页 · 共 {query.data.count} 轮</span><button disabled={busy || !query.data.next_page} onClick={() => setPage(query.data!.next_page!)} className={secondaryClass}>下一页</button></div>}
      {Boolean(query.data?.legacy_dividends.length) && <details className="rounded border border-border bg-[#FAF8F5] p-3 text-sm text-muted"><summary>历史 A/B 分红（只读，最近 50 条）</summary><p className="my-2">保留原记录和草稿，不转换为新轮次或待领取金额。</p>{query.data?.legacy_dividends.map(old => <p key={old.id}>#{old.id} · {old.business_date || '—'} · {old.total_cny} CNY · {old.status === 'draft' ? '历史草稿' : '已确认'}</p>)}</details>}
    </div>
    {dialog && <DividendDialog title={dialog.kind === 'allocation' ? '确认分红分配' : dialog.confirmation ? '确认分红领取' : '记录分红领取'} busy={busy} onClose={close}>
      {dialog.kind === 'allocation' ? <>
        <div data-guide="accounting-dividend-preview-result"><Facts rows={[
          ['分配总额', `${dialog.payload.total_cny} CNY`], ...dialog.names.map(name => [name, `${dialog.half} CNY · 50%`]),
          ['分配日期', dialog.payload.business_date], ['备注', dialog.payload.note || '—'], ['未分配利润', `${dialog.preview.retained_earnings_cny} CNY`],
        ]} /></div>
        <p className="text-sm text-accent">确认后锁定两人及金额，形成待付分红，不扣现金；正式记录不能直接改删。</p>
        {dialog.preview.warning && <label className="flex items-start gap-2 text-sm text-accent"><input data-guide="accounting-dividend-warning" type="checkbox" checked={ack} disabled={busy || dialog.stale} onChange={event => setAck(event.target.checked)} />本轮超过可用未分配利润；我已核实并明确同意继续分配。</label>}
        {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
        <footer className="flex flex-wrap justify-end gap-2"><button disabled={busy} onClick={close} className={secondaryClass}>返回修改</button>{dialog.stale ? <button disabled={busy} onClick={() => void freshPreview()} className={buttonClass}>重新预览</button> : <button data-guide="accounting-dividend-confirm" disabled={busy || Boolean(dialog.preview.warning && !ack)} onClick={() => void confirm()} className={buttonClass}>{busy ? '入账中…' : '确认分配（不付款）'}</button>}</footer>
      </> : dialog.confirmation ? <>
        <Facts rows={[
          ['分红轮次', `第 ${dialog.round.id} 轮`], ['领取人', dialog.confirmation.name], ['领取金额', `${dialog.confirmation.payload.amount_cny} CNY`],
          ['公司付款账户', dialog.confirmation.account], ['领取日期', dialog.confirmation.payload.business_date], ['备注', dialog.confirmation.payload.note || '—'],
        ]} />
        <p className="text-sm text-accent">实际扣减公司人民币账户和该人的待领分红，不再次扣利润。</p>
        {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
        <footer className="flex justify-end gap-2"><button disabled={busy} onClick={() => { setError(''); setDialog({ ...dialog, confirmation: undefined }); }} className={secondaryClass}>返回修改</button><button disabled={busy} onClick={() => void confirm()} className={buttonClass}>{busy ? '入账中…' : '确认领取并付款'}</button></footer>
      </> : <form onSubmit={event => { event.preventDefault(); confirmPayoutInput(); }} className="space-y-3">
        <p className="text-sm text-muted">第 {dialog.round.id} 轮 · 两人可使用同一公司账户。</p>
        <label className="block text-sm">领取人<select value={dialog.input.recipient} onChange={event => setDialog({ ...dialog, input: { ...dialog.input, recipient: event.target.value } })} className={inputClass}><option value="">选择该轮领取人</option>{dialog.round.partners.map(partner => <option key={partner.id} value={partner.id} disabled={(dividendCents(partner.pending_cny) ?? 0n) <= 0n}>{partner.name} · 待领 {partner.pending_cny} CNY</option>)}</select></label>
        <label className="block text-sm">公司付款账户<select value={dialog.input.account} onChange={event => setDialog({ ...dialog, input: { ...dialog.input, account: event.target.value } })} className={inputClass}><option value="">选择人民币账户</option>{cnyAccounts.map(account => <option key={account.id} value={account.id}>{account.name}</option>)}</select></label>
        <label className="block text-sm">领取金额（CNY）<input inputMode="decimal" value={dialog.input.amount} onChange={event => setDialog({ ...dialog, input: { ...dialog.input, amount: event.target.value } })} className={inputClass} /></label>
        <label className="block text-sm">领取日期<input type="date" min={dialog.round.business_date} value={dialog.input.date} onChange={event => setDialog({ ...dialog, input: { ...dialog.input, date: event.target.value } })} className={inputClass} /></label>
        <label className="block text-sm">领取备注<textarea value={dialog.input.note} onChange={event => setDialog({ ...dialog, input: { ...dialog.input, note: event.target.value } })} className={inputClass} /></label>
        {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
        <footer className="flex justify-end gap-2"><button type="button" onClick={close} className={secondaryClass}>取消</button><button type="submit" className={buttonClass}>核对领取</button></footer>
      </form>}
    </DividendDialog>}
  </section>;
}

function Facts({ rows }: { rows: string[][] }) {
  return <dl className="space-y-2 rounded border border-gold/30 bg-[#FFFDF7] p-3 text-sm">{rows.map(([label, value], index) => <div key={index} className="flex justify-between gap-3"><dt className="shrink-0 text-muted">{label}</dt><dd className="whitespace-pre-wrap break-words text-right font-semibold">{value}</dd></div>)}</dl>;
}

function DividendDialog({ title, busy, onClose, children }: { title: string; busy: boolean; onClose: () => void; children: ReactNode }) {
  const ref = useDialogFocus(onClose, busy);
  return <div role="presentation" className="fixed inset-0 z-50 grid place-items-center bg-fg/50 p-3 backdrop-blur-sm" onMouseDown={event => { if (event.target === event.currentTarget && !busy) onClose(); }}><div ref={ref} tabIndex={-1} role="dialog" aria-modal="true" aria-labelledby="dividend-dialog-title" className="max-h-[90dvh] w-full max-w-lg overflow-y-auto rounded-lg bg-white p-5 shadow-2xl outline-none"><h2 id="dividend-dialog-title" className="mb-4 font-display text-xl font-semibold">{title}</h2><div className="space-y-4">{children}</div></div></div>;
}
