import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import type { AccountingExpense, AccountingExpenseRefund, ExpensePeriodSummary, ExpenseRefundPayload, FundAccount } from '../../types';
import { apiErrorMessage } from '../../api';
import { useDialogFocus } from '../../hooks/useDialogFocus';
import { moscowBusinessDate } from '../../utils/businessDate';
import { formatDecimalAmount } from '../../utils/decimalDisplay';

interface ExpenseDetailsProps {
  month: string;
  expenses?: AccountingExpense[];
  refunds?: AccountingExpenseRefund[];
  summary?: ExpensePeriodSummary;
  accounts?: FundAccount[];
  loading?: boolean;
  error?: string;
  page?: number;
  nextPage?: number | null;
  onPageChange?: (page: number) => void;
  onLoadExpense?: (id: number) => Promise<AccountingExpense>;
  onRefund?: (expense: AccountingExpense, payload: ExpenseRefundPayload) => Promise<AccountingExpense>;
  onReverse?: (expense: AccountingExpense, reason: string) => Promise<void>;
}

type Mode = 'detail' | 'refund' | 'reverse';
const buttonClass = 'min-h-11 whitespace-nowrap rounded border border-border px-3 py-2 text-sm font-semibold disabled:cursor-not-allowed disabled:opacity-50';
const fieldClass = 'mt-1.5 min-h-11 w-full rounded border border-border bg-white px-3 py-2 text-base text-fg disabled:bg-cream';
const money = (value: string, currency = 'CNY') => `${currency === 'CNY' ? '¥' : ''}${formatDecimalAmount(value, currency)}${currency === 'CNY' ? '' : ` ${currency}`}`;

function cents(value: string): bigint | null {
  const match = /^(\d+)(?:\.(\d{1,8}))?$/.exec(value.trim());
  if (!match || value.length > 40 || /[1-9]/.test((match[2] || '').slice(2))) return null;
  return BigInt(match[1]) * 100n + BigInt((match[2] || '').slice(0, 2).padEnd(2, '0'));
}
function amountFromCents(value: bigint): string {
  const sign = value < 0 ? '-' : '';
  const absolute = value < 0 ? -value : value;
  return `${sign}${absolute / 100n}.${String(absolute % 100n).padStart(2, '0')}`;
}
function remaining(expense: AccountingExpense): string {
  return expense.remaining_refundable_amount ?? expense.original_amount;
}
function refundDisabledReason(expense: AccountingExpense): string {
  if (expense.reversed) return '原费用已撤回';
  if ((cents(remaining(expense)) ?? 0n) <= 0n) return '原费用已全部退回';
  return '';
}
function reversalDisabledReason(expense: AccountingExpense): string {
  if (expense.reversed) return '原费用已撤回';
  if ((cents(expense.refunded_amount || '0') ?? 0n) > 0n) return '已有退回，不能整笔撤回';
  return '';
}
function ExpenseStatus({ expense }: { expense: AccountingExpense }) {
  const label = expense.reversed ? '已撤回' : (cents(expense.refunded_amount || '0') ?? 0n) > 0n
    ? ((cents(remaining(expense)) ?? 0n) === 0n ? '全部退回' : '部分退回') : '';
  return label ? <span className="inline-block rounded-full bg-[#F1ECE5] px-2 py-1 text-[11px] text-muted">{label}</span> : null;
}

function ExpenseMore({ expense, onSelect, canRefund, canReverse }: {
  expense: AccountingExpense; onSelect: (mode: Mode) => void; canRefund: boolean; canReverse: boolean;
}) {
  const ref = useRef<HTMLDetailsElement>(null);
  useEffect(() => {
    const close = (event: PointerEvent) => { if (ref.current && !ref.current.contains(event.target as Node)) ref.current.open = false; };
    document.addEventListener('pointerdown', close);
    return () => document.removeEventListener('pointerdown', close);
  }, []);
  const select = (mode: Mode) => {
    if (ref.current) { ref.current.open = false; ref.current.querySelector('summary')?.focus(); }
    onSelect(mode);
  };
  const refundReason = refundDisabledReason(expense);
  const reverseReason = reversalDisabledReason(expense);
  return <details ref={ref} className="relative" onKeyDown={event => {
    if (event.key === 'Escape' && ref.current) { ref.current.open = false; ref.current.querySelector('summary')?.focus(); }
  }}>
    <summary aria-label={`费用 ${expense.id} 更多操作`} className={`${buttonClass} flex cursor-pointer list-none items-center justify-center gap-1 bg-white [&::-webkit-details-marker]:hidden`}>⋯ <span>更多</span></summary>
    <div className="fixed bottom-[calc(4.5rem+env(safe-area-inset-bottom))] left-4 right-4 z-[60] rounded-md border border-border bg-white p-1 shadow-lg md:absolute md:bottom-full md:left-auto md:right-0 md:mb-1 md:w-56">
      <button type="button" onClick={() => select('detail')} className="min-h-11 w-full rounded px-3 py-2 text-left text-sm hover:bg-cream">查看明细</button>
      {canRefund && <><button type="button" disabled={!!refundReason} onClick={() => select('refund')} className="min-h-11 w-full rounded px-3 py-2 text-left text-sm hover:bg-cream disabled:opacity-50">登记退回</button>{refundReason && <p className="px-3 pb-2 text-xs text-muted">{refundReason}</p>}</>}
      {canReverse && <div className="border-t border-border"><button type="button" disabled={!!reverseReason} onClick={() => select('reverse')} className="min-h-11 w-full rounded px-3 py-2 text-left text-sm text-red-700 hover:bg-red-50 disabled:opacity-50">撤回记录</button>{reverseReason && <p className="px-3 pb-2 text-xs text-muted">{reverseReason}</p>}</div>}
    </div>
  </details>;
}

export default function ExpenseDetails({ month, expenses = [], refunds = [], summary, accounts = [], loading = false, error,
  page = 1, nextPage, onPageChange, onLoadExpense, onRefund, onReverse }: ExpenseDetailsProps) {
  const [selected, setSelected] = useState<{ id: number; initial?: AccountingExpense; mode: Mode } | null>(null);
  const [notice, setNotice] = useState('');
  const fallbackTotal = amountFromCents(expenses.reduce((sum, item) => sum + (cents(item.amount_cny) ?? 0n), 0n));
  const rows = [
    ...expenses.map(expense => ({ date: expense.business_date, id: `expense-${expense.id}`, expense, refund: undefined })),
    ...refunds.map(refund => ({ date: refund.business_date, id: `refund-${refund.id}`, expense: undefined, refund })),
  ].sort((a, b) => b.date.localeCompare(a.date) || b.id.localeCompare(a.id));
  const stats = summary ? [
    ['费用支出', summary.spent_cny], ['费用退回', summary.refunded_cny],
    ...(cents(summary.reversed_cny) ? [['撤回冲减', summary.reversed_cny]] : []), ['净费用', summary.net_cny],
  ] : [['费用支出', fallbackTotal]];
  return <section aria-labelledby="accounting-expense-details-title" className="mb-7 rounded-md border border-border bg-white shadow-sm">
    <div className="border-b border-border px-4 py-4 sm:px-5">
      <div className="flex flex-wrap items-baseline justify-between gap-2"><h2 id="accounting-expense-details-title" className="font-display text-xl font-semibold">费用明细</h2><span className="text-xs text-muted">{month} · 按实际业务日期</span></div>
      <p className="mt-1 text-xs text-muted">本月发生额与累计退回分开展示；历史费用可切换明细月份查找。</p>
      <dl className="mt-4 grid grid-cols-2 gap-3 sm:flex sm:flex-wrap sm:gap-x-8">{stats.map(([label, value]) => <div key={label} className="min-w-0"><dt className="text-xs text-muted">{label}</dt><dd className="mt-1 break-all font-mono text-base font-semibold">{loading ? '…' : money(value)}</dd></div>)}</dl>
    </div>
    {notice && <p role="status" className="m-4 rounded border border-green-200 bg-green-50 p-3 text-sm text-green-800">{notice}</p>}
    {error && <p role="alert" className="m-4 rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</p>}
    {loading && <p role="status" className="p-8 text-center text-sm text-muted">费用明细加载中…</p>}
    {!loading && !error && <>
      <div className="hidden grid-cols-[100px_minmax(0,1fr)_150px_minmax(100px,0.7fr)_104px] gap-4 border-b border-border bg-[#FFFDFA] px-5 py-3 text-xs text-muted md:grid" aria-hidden="true"><span>日期</span><span>费用明细</span><span className="text-right">金额</span><span>资金账户</span><span className="text-right">操作</span></div>
      <ul className="divide-y divide-border">{rows.map(({ id, date, expense, refund }) => <li key={id} className="relative px-4 py-4 sm:px-5 md:grid md:grid-cols-[100px_minmax(0,1fr)_150px_minmax(100px,0.7fr)_104px] md:items-center md:gap-4">
        <div className="mb-2 flex items-center justify-between gap-2 md:mb-0"><span className="font-mono text-xs text-muted">{date}</span><span className="md:hidden">{expense && <ExpenseStatus expense={expense} />}{refund && <span className="rounded-full bg-green-50 px-2 py-1 text-xs text-green-800">费用退回</span>}</span></div>
        <div className="min-w-0 pr-24 md:pr-0"><p className="break-words text-sm font-semibold">{expense ? expense.subcategory_label || expense.category_label : `${refund?.expense_label || '费用'} · 退回`}</p><p className="mt-1 break-words text-xs text-muted">{expense?.note || refund?.note || '—'}</p>{expense && <div className="mt-1 hidden md:block"><ExpenseStatus expense={expense} /></div>}{refund && <p className="mt-1 text-xs text-muted">原费用日期 {refund.expense_business_date}</p>}</div>
        <div className="mt-3 min-w-0 pr-24 md:mt-0 md:pr-0 md:text-right"><p className="break-all font-mono text-base font-semibold">{money((expense || refund)!.original_amount, (expense || refund)!.currency)}</p>{refund && <p className="text-xs text-green-800">资金增加 · 费用减少</p>}{expense && (cents(expense.refunded_amount || '0') ?? 0n) > 0n && <p className="mt-1 text-xs text-muted">累计退回 {money(expense.refunded_amount!, expense.currency)}</p>}{(expense || refund)!.currency !== 'CNY' && <p className="text-xs text-muted">账面 {money((expense || refund)!.amount_cny)}</p>}</div>
        <p className="mt-2 min-w-0 break-words pr-24 text-xs text-muted md:mt-0 md:pr-0">{refund ? '收款：' : '付款：'}{(expense || refund)!.fund_account_name}</p>
        <div className="absolute bottom-4 right-4 md:static md:justify-self-end">{expense ? <ExpenseMore expense={expense} canRefund={!!onRefund} canReverse={!!onReverse} onSelect={mode => { setNotice(''); setSelected({ id: expense.id, initial: expense, mode }); }} /> : <button type="button" className={buttonClass} onClick={() => setSelected({ id: refund!.expense_id, mode: 'detail' })}>查看原费用</button>}</div>
      </li>)}</ul>
      {!rows.length && <div className="px-5 py-10 text-center"><p className="font-semibold">本月还没有已入账费用或退回记录</p><p className="mt-1 text-xs text-muted">切换明细月份可查看历史费用。</p></div>}
      {onPageChange && (page > 1 || nextPage != null) && <div className="flex items-center justify-between gap-3 border-t border-border p-4"><button type="button" className={buttonClass} disabled={page <= 1} onClick={() => onPageChange(page - 1)}>上一页</button><span className="text-xs text-muted">第 {page} 页</span><button type="button" className={buttonClass} disabled={nextPage == null} onClick={() => nextPage && onPageChange(nextPage)}>下一页</button></div>}
    </>}
    {selected && <ExpenseDialog key={`${selected.id}-${selected.mode}`} id={selected.id} initial={selected.initial} mode={selected.mode} accounts={accounts} onLoad={onLoadExpense} onRefund={onRefund} onReverse={onReverse} onClose={() => setSelected(null)} onDone={message => { setSelected(null); setNotice(message); }} />}
  </section>;
}

function ExpenseDialog({ id, initial, mode: initialMode, accounts, onLoad, onRefund, onReverse, onClose, onDone }: {
  id: number; initial?: AccountingExpense; mode: Mode; accounts: FundAccount[];
  onLoad?: ExpenseDetailsProps['onLoadExpense']; onRefund?: ExpenseDetailsProps['onRefund']; onReverse?: ExpenseDetailsProps['onReverse'];
  onClose: () => void; onDone: (message: string) => void;
}) {
  const [expense, setExpense] = useState(initial);
  const [mode, setMode] = useState(initialMode);
  const [loading, setLoading] = useState(!!onLoad);
  const [loadError, setLoadError] = useState('');
  const [reload, setReload] = useState(0);
  const [error, setError] = useState('');
  const [amount, setAmount] = useState('');
  const [accountId, setAccountId] = useState('');
  const [businessDate, setBusinessDate] = useState(moscowBusinessDate());
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false);
  const dialogRef = useDialogFocus(onClose, busy);
  useEffect(() => {
    const oldOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => { document.body.style.overflow = oldOverflow; };
  }, []);
  useEffect(() => {
    if (!onLoad) return;
    let active = true;
    onLoad(id).then(value => { if (active) setExpense(value); }).catch(e => { if (active) setLoadError(apiErrorMessage(e, '原费用加载失败')); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [id, onLoad, reload]);
  const eligible = accounts.filter(account => account.is_active && account.currency === expense?.currency);
  const account = eligible.find(item => String(item.id) === accountId);
  const amountCents = cents(amount);
  const overLimit = expense && amountCents != null && amountCents > (cents(remaining(expense)) ?? 0n);
  const blocked = expense ? (mode === 'refund' ? refundDisabledReason(expense) : reversalDisabledReason(expense)) : '';
  const valid = !!expense && !loading && !loadError && !blocked && !!note.trim()
    && (mode !== 'refund' || (amountCents != null && amountCents > 0n && !overLimit && !!account && !!businessDate && businessDate >= expense.business_date));
  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!valid || !expense || inFlight.current) return;
    inFlight.current = true;
    setBusy(true); setError('');
    try {
      if (mode === 'refund' && onRefund && account) {
        await onRefund(expense, { amount: amount.trim(), fund_account_id: account.id, business_date: businessDate, note: note.trim() });
        onDone('费用退回已入账，账户余额和费用汇总已更新。');
      } else if (mode === 'reverse' && onReverse) {
        await onReverse(expense, note.trim());
        onDone('费用已撤回，原记录和冲正流水已保留。');
      }
    } catch (e) { setError(apiErrorMessage(e, '操作失败，请核对后重试')); }
    finally { inFlight.current = false; setBusy(false); }
  };
  const title = mode === 'detail' ? '费用详情' : mode === 'refund' ? '登记费用退回' : '撤回费用记录';
  return createPortal(<div className="fixed inset-0 z-[100] flex items-end justify-center bg-black/40 p-2 sm:items-center sm:p-4" onClick={event => { if (event.target === event.currentTarget && !busy) onClose(); }}>
    <div ref={dialogRef} tabIndex={-1} role="dialog" aria-modal="true" aria-labelledby="expense-dialog-title" className="flex max-h-[calc(100dvh-1rem)] w-full min-w-0 max-w-lg flex-col overflow-hidden rounded-lg bg-white shadow-xl outline-none">
      <header className="flex shrink-0 items-center justify-between gap-3 border-b border-border px-4 py-3"><h2 id="expense-dialog-title" className="font-display text-xl font-semibold">{title}</h2><button type="button" disabled={busy} onClick={onClose} className={buttonClass}>关闭</button></header>
      <div className="min-h-0 overflow-y-auto overscroll-contain p-4 [overflow-wrap:anywhere]">
        {loading && <p role="status" className="mb-3 text-sm text-muted">正在核对原费用…</p>}
        {loadError && <div role="alert" className="mb-3 text-sm text-red-700">{loadError}<button type="button" className={`${buttonClass} ml-2`} onClick={() => { setLoadError(''); setLoading(true); setReload(value => value + 1); }}>重试</button></div>}
        {!expense && !loading && !loadError && <p role="alert">无法读取原费用，请关闭后重试。</p>}
        {expense && <>
          <div className="rounded border border-border bg-[#FFFDFA] p-3 text-sm"><p className="font-semibold">{expense.subcategory_label || expense.category_label}</p><p className="mt-1 text-xs text-muted">{expense.business_date} · {expense.fund_account_name}</p><p className="mt-1 text-xs text-muted">{expense.note || '无备注'}</p><dl className="mt-3 grid grid-cols-2 gap-3">{[
            ['原费用', money(expense.original_amount, expense.currency)], ['累计退回', money(expense.refunded_amount || '0', expense.currency)],
            ['剩余可退', money(remaining(expense), expense.currency)], ['净支出（CNY）', money(expense.net_amount_cny ?? expense.amount_cny)],
          ].map(([label, value]) => <div key={label}><dt className="text-xs text-muted">{label}</dt><dd className="mt-1 break-all font-mono">{value}</dd></div>)}</dl><div className="mt-2"><ExpenseStatus expense={expense} /></div></div>
          {mode === 'detail' ? <>
            <h3 className="mb-2 mt-5 font-semibold">退回记录</h3>
            {expense.refunds?.length ? <ul className="divide-y divide-border">{expense.refunds.map(refund => <li key={refund.id} className="py-3 text-sm"><div className="flex flex-wrap justify-between gap-2"><span>{refund.business_date}</span><strong className="font-mono">{money(refund.original_amount, refund.currency)}</strong></div><p className="mt-1 text-xs text-muted">收款：{refund.fund_account_name}</p><p className="mt-1 text-xs text-muted">{refund.note}</p></li>)}</ul> : <p className="text-sm text-muted">暂无退回记录</p>}
            {expense.reversed && <p className="mt-3 text-sm text-muted">整笔撤回日期：{expense.reversal_business_date}</p>}
            {onRefund && <div className="mt-4"><button type="button" disabled={loading || !!loadError || !!refundDisabledReason(expense)} onClick={() => setMode('refund')} className={`${buttonClass} w-full`}>登记退回</button>{refundDisabledReason(expense) && <p className="mt-2 text-xs text-muted">{refundDisabledReason(expense)}</p>}</div>}
          </> : <form id="expense-action-form" onSubmit={submit} className="mt-4 space-y-4">
            {blocked && <p role="alert" className="rounded bg-cream p-3 text-sm">{blocked}</p>}
            <fieldset disabled={busy || loading || !!loadError || !!blocked} className="space-y-4">
              {mode === 'refund' && <>
                <label className="block text-sm">本次退回金额（{expense.currency}）<input autoComplete="off" inputMode="decimal" required value={amount} onChange={event => setAmount(event.target.value)} className={fieldClass} placeholder="请输入实际收到的金额" /></label>
                {overLimit && <p role="alert" className="text-sm text-red-700">不能超过剩余可退金额 {money(remaining(expense), expense.currency)}</p>}
                <label className="block text-sm">实际到账日期<input type="date" required min={expense.business_date} value={businessDate} onChange={event => setBusinessDate(event.target.value)} className={fieldClass} /></label>
                <label className="block text-sm">收款账户<select required value={accountId} onChange={event => setAccountId(event.target.value)} className={fieldClass}><option value="">请选择实际收款账户</option>{eligible.map(item => <option key={item.id} value={item.id}>{item.name} · {item.currency}</option>)}</select></label>
                {!eligible.length && <p role="alert" className="text-sm text-red-700">没有启用的同币种公司账户，暂时无法登记退回。</p>}
              </>}
              <label className="block text-sm">{mode === 'refund' ? '退回原因' : '撤回原因'}<textarea required rows={3} value={note} onChange={event => setNote(event.target.value)} className={fieldClass} /></label>
            </fieldset>
            {mode === 'refund' ? <p className="rounded border border-border bg-[#FFFAF3] p-3 text-sm leading-6">{account && amountCents != null && amountCents > 0n ? `${account.name} 增加 ${money(amount, expense.currency)}。` : '请核对实际到账金额、日期和账户。'}{expense.currency === 'CNY' && amountCents != null && amountCents > 0n ? `本次冲减费用 ${money(amount)}。` : '按原费用的人民币账面成本冲减费用。'}原费用和退回记录均保留。</p> : <p className="rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700">将整笔冲回 {money(expense.original_amount, expense.currency)} 至原付款账户，业务日期为 {moscowBusinessDate()}。仅用于原登记有误；实际收到部分退款请使用“登记退回”。</p>}
            {error && <p role="alert" className="rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</p>}
          </form>}
        </>}
      </div>
      {mode !== 'detail' && <footer className="flex shrink-0 gap-3 border-t border-border bg-[#FFFDF9] px-4 pb-[max(1rem,env(safe-area-inset-bottom))] pt-3"><button type="button" disabled={busy} onClick={onClose} className={`${buttonClass} flex-1`}>取消</button><button type="submit" form="expense-action-form" disabled={busy || !valid} className={`${buttonClass} flex-[2] border-accent bg-accent text-white`}>{busy ? '入账中…' : mode === 'refund' ? '确认退回并入账' : '确认整笔撤回'}</button></footer>}
    </div>
  </div>, document.body);
}
