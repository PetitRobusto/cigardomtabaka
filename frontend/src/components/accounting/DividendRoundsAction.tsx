import { useState } from 'react';
import { parseAccountingApiError } from '../../api';
import type { DividendPreview, FundAccount, PaidDividendPayload } from '../../types';
import { formatDecimalAmount } from '../../utils/decimalDisplay';
import { DividendDialog } from './DividendPayoutDialog';
import { dividendButtonClass, dividendCents, dividendInputClass, dividendMoney, dividendSecondaryClass } from './DividendRoundsAction.logic';
import { usePaidDividendForm } from './usePaidDividendForm';

export default function DividendRoundsAction({ accounts, businessDate, onChanged }: {
  accounts: FundAccount[]; businessDate: string; onChanged?: () => void;
}) {
  const form = usePaidDividendForm(accounts, businessDate, onChanged);
  const { input, setInput, attempt, busy, amounts } = form;
  return <section tabIndex={-1} data-guide="accounting-actions-dividend" className="text-fg">
    <div inert={Boolean(attempt?.warning)}>
      <h2 className="font-display text-xl font-semibold">记录已支付分红</h2>
      <p className="mt-1 text-xs leading-5 text-muted">填写本次个人实领金额，自动为另一位合伙人建立同额份额。公司账户只扣实际领取的款项。</p>
      <form onSubmit={event => { event.preventDefault(); form.submit(); }} className="mt-4">
        <fieldset disabled={busy || Boolean(attempt)} className="grid gap-3 sm:grid-cols-2">
          {(['a', 'b'] as const).map(key => <label key={key} className="text-xs font-semibold text-muted">{key === 'a' ? '本次领取人' : '另一位合伙人'}<select data-guide={`accounting-dividend-partner-${key}`} value={input[key]} onChange={event => setInput({ ...input, [key]: event.target.value })} className={dividendInputClass}><option value="">选择合伙人</option>{form.recipients.map(user => <option key={user.id} value={user.id} disabled={key === 'b' && String(user.id) === input.a}>{user.name}</option>)}</select></label>)}
          <label className="text-xs font-semibold text-muted">个人实领金额（CNY）<input data-guide="accounting-dividend-total" inputMode="decimal" placeholder="例如：5000" value={input.amount} onChange={event => setInput({ ...input, amount: event.target.value })} className={dividendInputClass} /></label>
          <label className="text-xs font-semibold text-muted">实际支付日期<input data-guide="accounting-dividend-date" type="date" value={input.date} onChange={event => setInput({ ...input, date: event.target.value })} className={dividendInputClass} /></label>
          <label className="text-xs font-semibold text-muted sm:col-span-2">公司付款账户<select data-guide="accounting-dividend-account" value={input.account} onChange={event => setInput({ ...input, account: event.target.value })} className={dividendInputClass}><option value="">选择人民币账户</option>{form.cnyAccounts.map(account => <option key={account.id} value={account.id}>{account.name}</option>)}</select></label>
          <label className="text-xs font-semibold text-muted sm:col-span-2">备注（选填）<input value={input.note} onChange={event => setInput({ ...input, note: event.target.value })} placeholder="例如：十月利润分红" className={dividendInputClass} /></label>
          <label className="flex items-start gap-2 text-xs text-muted sm:col-span-2"><input type="checkbox" checked={input.bothPaid} onChange={event => setInput({ ...input, bothPaid: event.target.checked })} className="mt-0.5 accent-accent" />另一位合伙人也已领取同额分红</label>
        </fieldset>
        <div className="mt-4 rounded border border-gold/30 bg-[#FFFCF7] px-3 py-2.5 text-xs">
          <dl className="grid gap-3 sm:grid-cols-3">
            {[
              ['总分配（两人各 50%）', amounts?.total],
              ['本次账户扣款', amounts?.paid],
              [`${form.recipients.find(user => String(user.id) === input.b)?.name || '另一位合伙人'} 待领`, amounts?.pending],
            ].map(([label, value]) => <div key={label}><dt className="text-muted">{label}</dt><dd className="mt-1 font-mono font-semibold">{value ? `¥${formatDecimalAmount(value, 'CNY')}` : '—'}</dd></div>)}
          </dl>
          <p className="mt-3 border-t border-border pt-2 leading-5 text-muted">未分配利润按总分配扣减。待领资金不冻结，领取前仍可正常用于采购和经营。</p>
        </div>
        {input.amount && !amounts && <p role="alert" className="mt-2 text-xs text-accent">个人实领金额须大于零、最多两位小数，且翻倍后的总额不能超出记账范围。</p>}
        {form.query.isPending && <p role="status" className="mt-2 text-xs text-muted">正在加载合伙人…</p>}
        {form.query.error && <p role="alert" className="mt-2 text-sm text-accent">{parseAccountingApiError(form.query.error).message}<button type="button" onClick={() => void form.query.refetch()} className={dividendSecondaryClass}>重新加载</button></p>}
        {!attempt?.warning && form.error && <p role="alert" className="mt-3 text-sm text-accent">{form.error}</p>}
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
          <p className="text-xs leading-5 text-muted">补领已有分红，请从明细中继续登记领取。<a href="#dividend-details" className="ml-1 underline underline-offset-2">查看分红明细</a><br />仅登记已发生的付款，不发起转账。</p>
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
  const total = dividendCents(payload.total_cny) ?? 0n;
  const paidA = dividendCents(payload.partner_a_paid_cny ?? dividendMoney(total / 2n)) ?? 0n;
  const paidB = dividendCents(payload.partner_b_paid_cny ?? dividendMoney(total / 2n)) ?? 0n;
  return <DividendDialog title={preview.warning ? '未分配利润不足' : '分红信息已更新'} busy={busy || uncertain} onClose={onCancel}>
    <dl className="space-y-2 rounded border border-gold/30 bg-[#FFFDF7] p-3 text-sm">{[
      ['总分配', `${payload.total_cny} CNY`], ['未分配利润', `${preview.retained_earnings_cny} CNY`],
      ['本次账户扣款', `${dividendMoney(paidA + paidB)} CNY`], ['待领合计', `${dividendMoney(total - paidA - paidB)} CNY`],
      ...[payload.partner_a_id, payload.partner_b_id].map((id, index) => [
        recipients.find(user => user.id === id)?.name ?? '—',
        `实领 ${dividendMoney(index === 0 ? paidA : paidB)} · 待领 ${dividendMoney(total / 2n - (index === 0 ? paidA : paidB))} CNY`,
      ]),
      ['公司付款账户', accounts.find(account => account.id === payload.fund_account_id)?.name || '—'],
      ['实际支付日期', payload.business_date], ['备注', payload.note || '—'],
    ].map(([label, value]) => <div key={label} className="flex justify-between gap-3"><dt className="shrink-0 text-muted">{label}</dt><dd className="whitespace-pre-wrap break-words text-right">{value}</dd></div>)}</dl>
    {preview.warning && <label className="flex items-start gap-2 rounded border border-[#ECD3B8] bg-[#F9EEE6] p-3 text-sm text-[#A75B27]"><input type="checkbox" className="mt-1 accent-accent" checked={ack} disabled={busy || uncertain} onChange={event => setAck(event.target.checked)} />我已知晓未分配利润将变为负数，并确认上述实领金额已实际支付。</label>}
    {error && <p role="alert" className="text-sm text-accent">{error}</p>}
    {uncertain && <p className="text-sm text-muted">结果尚未确认，请重试本次记录，避免重复登记。</p>}
    <footer className="flex flex-wrap justify-end gap-2"><button disabled={busy || uncertain} onClick={onCancel} className={dividendSecondaryClass}>返回修改</button><button disabled={busy || (!uncertain && Boolean(preview.warning) && !ack)} onClick={() => void onSave(uncertain ? payload : { ...payload, warning_ack: true, warning_fingerprint: preview.warning_fingerprint })} className={dividendButtonClass}>{busy ? '保存中…' : uncertain ? '重试本次记录' : '确认保存分红'}</button></footer>
  </DividendDialog>;
}
