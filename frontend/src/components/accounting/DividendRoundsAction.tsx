import { useState } from 'react';
import { parseAccountingApiError } from '../../api';
import type { DividendPreview, FundAccount, PaidDividendPayload } from '../../types';
import { formatDecimalAmount } from '../../utils/decimalDisplay';
import { DividendDialog } from './DividendPayoutDialog';
import { dividendButtonClass, dividendInputClass, dividendSecondaryClass } from './DividendRoundsAction.logic';
import { usePaidDividendForm } from './usePaidDividendForm';

export default function DividendRoundsAction({ accounts, businessDate, onChanged }: {
  accounts: FundAccount[]; businessDate: string; onChanged?: () => void;
}) {
  const form = usePaidDividendForm(accounts, businessDate, onChanged);
  const { input, setInput, attempt, busy, half } = form;
  return <section tabIndex={-1} data-guide="accounting-actions-dividend" className="text-fg">
    <div inert={Boolean(attempt?.warning)}>
      <h2 className="font-display text-xl font-semibold">记录已支付分红</h2>
      <p className="mt-1 text-xs leading-5 text-muted">两位合伙人各 50%。保存后扣减公司账户余额和未分配利润。</p>
      <form onSubmit={event => { event.preventDefault(); form.submit(); }} className="mt-4">
        <fieldset disabled={busy || Boolean(attempt)} className="grid gap-3 sm:grid-cols-2">
          <label className="text-xs font-semibold text-muted">分红总额（CNY）<input data-guide="accounting-dividend-total" inputMode="decimal" placeholder="0.00" value={input.total} onChange={event => setInput({ ...input, total: event.target.value })} className={dividendInputClass} /></label>
          <label className="text-xs font-semibold text-muted">实际支付日期<input data-guide="accounting-dividend-date" type="date" value={input.date} onChange={event => setInput({ ...input, date: event.target.value })} className={dividendInputClass} /></label>
          <label className="text-xs font-semibold text-muted sm:col-span-2">公司付款账户<select data-guide="accounting-dividend-account" value={input.account} onChange={event => setInput({ ...input, account: event.target.value })} className={dividendInputClass}><option value="">选择人民币账户</option>{form.cnyAccounts.map(account => <option key={account.id} value={account.id}>{account.name}</option>)}</select></label>
          {(['a', 'b'] as const).map((key, index) => <label key={key} className="text-xs font-semibold text-muted">合伙人 {index + 1}<select data-guide={`accounting-dividend-partner-${key}`} value={input[key]} onChange={event => setInput({ ...input, [key]: event.target.value })} className={dividendInputClass}><option value="">选择合伙人</option>{form.recipients.map(user => <option key={user.id} value={user.id} disabled={String(user.id) === input[key === 'a' ? 'b' : 'a']}>{user.name}</option>)}</select></label>)}
          <label className="text-xs font-semibold text-muted sm:col-span-2">备注（选填）<input value={input.note} onChange={event => setInput({ ...input, note: event.target.value })} placeholder="例如：十月利润分红" className={dividendInputClass} /></label>
        </fieldset>
        <div className="mt-4 flex flex-wrap gap-x-5 gap-y-2 rounded border border-gold/30 bg-[#FFFCF7] px-3 py-2.5 text-xs">
          {(['a', 'b'] as const).map((key, index) => <span key={key}><span className="text-muted">{form.recipients.find(user => String(user.id) === input[key])?.name || `合伙人 ${index + 1}`} · 50% </span><strong className="ml-1 font-mono">{half ? `¥${formatDecimalAmount(half, 'CNY')}` : '—'}</strong></span>)}
        </div>
        {input.total && !half && <p role="alert" className="mt-2 text-xs text-accent">总额须为正数，最多两位小数，并能按分精确平分。</p>}
        {form.query.isPending && <p role="status" className="mt-2 text-xs text-muted">正在加载合伙人…</p>}
        {form.query.error && <p role="alert" className="mt-2 text-sm text-red-700">{parseAccountingApiError(form.query.error).message}<button type="button" onClick={() => void form.query.refetch()} className={dividendSecondaryClass}>重新加载</button></p>}
        {!attempt?.warning && form.error && <p role="alert" className="mt-3 text-sm text-red-700">{form.error}</p>}
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
          <p className="text-xs text-muted">仅登记已发生的付款，不发起转账。</p>
          <button data-guide="accounting-dividend-save" type="submit" disabled={busy || !form.valid || Boolean(attempt)} className={dividendButtonClass}>{busy ? '保存中…' : '保存分红'}</button>
        </div>
      </form>
      {attempt?.uncertain && !attempt.warning && <div className="mt-3 space-y-2 rounded border border-gold/40 bg-[#FFFDF7] p-3 text-sm"><p>结果尚未确认，请重试本次记录，避免重复登记。</p><button type="button" disabled={busy} onClick={() => void form.save(attempt.payload)} className={dividendSecondaryClass}>重试本次记录</button></div>}
      {form.notice && <p role="status" className="mt-3 text-sm text-success">{form.notice}</p>}
    </div>
    {attempt?.warning && <DividendWarning key={attempt.warning.warning_fingerprint} payload={attempt.payload} preview={attempt.warning}
      accounts={accounts} recipients={form.recipients} busy={busy} uncertain={attempt.uncertain} error={form.error}
      onCancel={form.cancelWarning} onSave={form.save} />}
  </section>;
}

function DividendWarning({ payload, preview, accounts, recipients, busy, uncertain, error, onCancel, onSave }: {
  payload: PaidDividendPayload; preview: DividendPreview; accounts: FundAccount[]; recipients: { id: number; name: string }[];
  busy: boolean; uncertain: boolean; error: string; onCancel: () => void; onSave: (payload: PaidDividendPayload) => Promise<void>;
}) {
  const [ack, setAck] = useState(false);
  return <DividendDialog title={preview.warning ? '未分配利润不足' : '分红信息已更新'} busy={busy || uncertain} onClose={onCancel}>
    <dl className="space-y-2 rounded border border-gold/30 bg-[#FFFDF7] p-3 text-sm">{[
      ['分红总额', `${payload.total_cny} CNY`], ['未分配利润', `${preview.retained_earnings_cny} CNY`],
      ['合伙人', [payload.partner_a_id, payload.partner_b_id].map(id => recipients.find(user => user.id === id)?.name ?? '—').join('、') + ' · 各 50%'],
      ['公司付款账户', accounts.find(account => account.id === payload.fund_account_id)?.name || '—'],
      ['实际支付日期', payload.business_date], ['备注', payload.note || '—'],
    ].map(([label, value]) => <div key={label} className="flex justify-between gap-3"><dt className="shrink-0 text-muted">{label}</dt><dd className="whitespace-pre-wrap break-words text-right">{value}</dd></div>)}</dl>
    {preview.warning && <label className="flex items-start gap-2 rounded border border-[#ECD3B8] bg-[#F9EEE6] p-3 text-sm text-[#A75B27]"><input type="checkbox" className="mt-1" checked={ack} disabled={busy || uncertain} onChange={event => setAck(event.target.checked)} />我已知晓未分配利润将变为负数，并确认这笔分红已实际支付。</label>}
    {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
    {uncertain && <p className="text-sm text-muted">结果尚未确认，请重试本次记录，避免重复登记。</p>}
    <footer className="flex flex-wrap justify-end gap-2"><button disabled={busy || uncertain} onClick={onCancel} className={dividendSecondaryClass}>返回修改</button><button disabled={busy || (!uncertain && Boolean(preview.warning) && !ack)} onClick={() => void onSave(uncertain ? payload : { ...payload, warning_ack: true, warning_fingerprint: preview.warning_fingerprint })} className={dividendButtonClass}>{busy ? '保存中…' : uncertain ? '重试本次记录' : '确认保存分红'}</button></footer>
  </DividendDialog>;
}
