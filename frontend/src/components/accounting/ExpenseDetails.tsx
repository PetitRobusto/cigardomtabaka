import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { ArrowLeft, ArrowRight, Check, CornerDownLeft, MoreHorizontal, ReceiptText, Undo2, Wallet, X } from 'lucide-react';
import type { AccountingExpense, AccountingExpenseRefund, ExpensePeriodSummary, ExpenseRefundPayload, FundAccount } from '../../types';
import { apiErrorMessage } from '../../api';
import { useDialogFocus } from '../../hooks/useDialogFocus';
import { moscowBusinessDate } from '../../utils/businessDate';
import { formatDecimalAmount } from '../../utils/decimalDisplay';
import ExpenseCategoryBadge from './ExpenseCategoryBadge';

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
const buttonClass = 'expense-button';
const fieldClass = 'expense-field';
const money = (value: string, currency = 'CNY') => `${currency === 'CNY' ? '¥' : ''}${formatDecimalAmount(value, currency)}${currency === 'CNY' ? '' : ` ${currency}`}`;

function expenseLabels(expense: AccountingExpense) {
  const label = expense.subcategory_label || expense.category_label;
  const separator = label.indexOf(' · ');
  return separator >= 0
    ? { category: label.slice(0, separator), detail: label.slice(separator + 3) }
    : { category: expense.category_label || '其他', detail: label };
}

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
  const tone = expense.reversed ? 'reversed' : label === '全部退回' ? 'full' : 'partial';
  return label ? <span className={`expense-status expense-status--${tone}`}>{label}</span> : null;
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
    <summary aria-label={`费用 ${expense.id} 更多操作`} title="费用操作" className="expense-icon-button list-none"><MoreHorizontal aria-hidden="true" size={16} strokeWidth={1.8} /></summary>
    <div className="expense-menu">
      <p className="expense-menu-label">{expenseLabels(expense).detail} · {expense.business_date}</p>
      <button type="button" onClick={() => select('detail')} className="expense-menu-action"><ReceiptText aria-hidden="true" size={15} strokeWidth={1.8} />查看明细</button>
      {canRefund && <><button type="button" disabled={!!refundReason} onClick={() => select('refund')} className="expense-menu-action"><CornerDownLeft aria-hidden="true" size={15} strokeWidth={1.8} />登记退回</button>{refundReason && <p className="expense-menu-reason">{refundReason}</p>}</>}
      {canReverse && <div className="border-t border-border"><button type="button" disabled={!!reverseReason} onClick={() => select('reverse')} className="expense-menu-action expense-menu-danger"><Undo2 aria-hidden="true" size={15} strokeWidth={1.8} />撤回记录</button>{reverseReason && <p className="expense-menu-reason">{reverseReason}</p>}</div>}
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
    { label: '费用支出', value: summary.spent_cny, tone: 'spent', note: '本月发生额 · CNY 口径' },
    { label: '费用退回', value: summary.refunded_cny, tone: 'refund', note: '本月实际到账退回' },
    ...(cents(summary.reversed_cny) ? [{ label: '撤回冲减', value: summary.reversed_cny, tone: 'reversed', note: '原记录与冲正流水均保留' }] : []),
    { label: '净费用', value: summary.net_cny, tone: 'net', note: '支出 − 退回 − 撤回冲减' },
  ] : [{ label: '费用支出', value: fallbackTotal, tone: 'spent', note: '当前页账面合计 · CNY' }];
  return <section aria-labelledby="accounting-expense-details-title" className="expense-ledger">
    <dl aria-label="费用概览" className="expense-panel expense-overview">{stats.map(({ label, value, tone, note }) => <div key={label} className={`expense-stat expense-stat--${tone}`}><dt>{label}</dt><dd>{loading ? '…' : money(value)}</dd><small>{note}</small></div>)}</dl>
    <div className="expense-panel">
      <header className="expense-panel-head">
        <div><h2 id="accounting-expense-details-title" className="expense-panel-title">费用明细</h2><p className="expense-caption">支出与退回按业务日期倒序 · 原币保留原始金额 · CNY 为人民币账面成本</p></div>
        <span className="text-xs text-muted">{month} · 第 {page} 页</span>
      </header>
      {notice && <p role="status" className="expense-hint expense-hint--success m-4">{notice}</p>}
      {error && <p role="alert" className="expense-hint expense-hint--danger m-4">{error}</p>}
      {loading && <div role="status" className="p-5"><span className="sr-only">费用明细加载中…</span><div aria-hidden="true" className="space-y-5">{[0, 1, 2].map(index => <div key={index} className="flex animate-pulse items-center gap-5"><span className="h-3 w-16 rounded bg-[#F1ECE5]" /><span className="h-5 w-24 rounded bg-[#F1ECE5]" /><span className="h-3 flex-1 rounded bg-[#F1ECE5]" /></div>)}</div></div>}
      {!loading && !error && <>
        <div className="expense-table-head" aria-hidden="true"><span>日期</span><span>一级分类</span><span>费用明细</span><span className="text-right">原币金额</span><span className="text-right">CNY 账面</span><span>资金账户</span><span className="sr-only">操作</span></div>
        <ul>{rows.map(({ id, date, expense, refund }) => {
          const record = (expense || refund)!;
          const labels = expense ? expenseLabels(expense) : null;
          return <li key={id} className="expense-row">
            <time dateTime={date} className="expense-row-date">{date.slice(5).replace('-', '/')}</time>
            <div className="expense-row-category">{expense && labels ? <><ExpenseCategoryBadge label={labels.category} subcategory={expense.subcategory} /><ExpenseStatus expense={expense} /></> : <span className="expense-refund-badge"><CornerDownLeft aria-hidden="true" size={12} strokeWidth={1.8} />费用退回</span>}</div>
            <div className="expense-row-description" title={expense?.subcategory_label}>
              <p>{labels?.detail || `${refund?.expense_label || '费用'} · 退回`}</p>
              {record.note && <p className="expense-caption whitespace-pre-wrap">{record.note}</p>}
              {refund && <p className="expense-caption">原费用日期 {refund.expense_business_date}</p>}
              {expense && (cents(expense.refunded_amount || '0') ?? 0n) > 0n && <p className="expense-caption">累计退回 {money(expense.refunded_amount!, expense.currency)}</p>}
            </div>
            <div className="expense-row-amounts"><p className={`expense-row-original${refund ? ' expense-money-refund' : ''}`}><span className="sr-only">原币金额 </span>{refund ? '−' : ''}{money(record.original_amount, record.currency)}</p>
            <p className={`expense-row-cny${refund ? ' expense-money-refund' : expense?.reversed ? ' expense-money-reversed' : ''}`}><span className="sr-only">CNY 账面 </span>{refund ? '−' : ''}{money(record.amount_cny)}</p></div>
            <p className="expense-row-account"><span className="sr-only">{refund ? '收款：' : '付款：'}</span>{record.fund_account_name}</p>
            <div className="expense-row-actions">{expense ? <ExpenseMore expense={expense} canRefund={!!onRefund} canReverse={!!onReverse} onSelect={mode => { setNotice(''); setSelected({ id: expense.id, initial: expense, mode }); }} /> : <button type="button" className="expense-icon-button" aria-label="查看原费用" title="查看原费用" onClick={() => setSelected({ id: refund!.expense_id, mode: 'detail' })}><ReceiptText aria-hidden="true" size={16} strokeWidth={1.8} /></button>}</div>
          </li>;
        })}</ul>
        {!rows.length && <div className="expense-empty"><span className="expense-empty-icon"><ReceiptText aria-hidden="true" size={20} strokeWidth={1.5} /></span><h3 className="font-display font-semibold">本月还没有已入账费用或退回记录</h3><p className="expense-caption">切换明细月份可查看历史费用。</p></div>}
        {onPageChange && (page > 1 || nextPage != null) && <div className="expense-pagination"><button type="button" className={buttonClass} disabled={page <= 1} onClick={() => onPageChange(page - 1)}><ArrowLeft aria-hidden="true" size={14} />上一页</button><span className="text-xs text-muted">第 {page} 页</span><button type="button" className={buttonClass} disabled={nextPage == null} onClick={() => nextPage && onPageChange(nextPage)}>下一页<ArrowRight aria-hidden="true" size={14} /></button></div>}
      </>}
    </div>
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
  const TitleIcon = mode === 'detail' ? ReceiptText : mode === 'refund' ? CornerDownLeft : Undo2;
  const labels = expense ? expenseLabels(expense) : null;
  return createPortal(<div className="expense-modal-backdrop" onClick={event => { if (event.target === event.currentTarget && !busy) onClose(); }}>
    <div ref={dialogRef} tabIndex={-1} role="dialog" aria-modal="true" aria-labelledby="expense-dialog-title" className="expense-modal">
      <header className="expense-modal-head"><h2 id="expense-dialog-title" className="expense-modal-title"><TitleIcon aria-hidden="true" size={19} strokeWidth={1.6} />{title}</h2><button type="button" disabled={busy} onClick={onClose} className="expense-icon-button" aria-label="关闭"><X aria-hidden="true" size={18} strokeWidth={1.8} /></button></header>
      <div className="expense-modal-body">
        {loading && <p role="status" className="mb-3 text-sm text-muted">正在核对原费用…</p>}
        {loadError && <div role="alert" className="expense-hint expense-hint--danger mb-3">{loadError}<button type="button" className={`${buttonClass} ml-2`} onClick={() => { setLoadError(''); setLoading(true); setReload(value => value + 1); }}>重试</button></div>}
        {!expense && !loading && !loadError && <p role="alert" className="expense-hint expense-hint--danger">无法读取原费用，请关闭后重试。</p>}
        {expense && labels && <>
          <div className="expense-detail-summary">
            <div className="flex flex-wrap items-center gap-2"><ExpenseCategoryBadge label={labels.category} subcategory={expense.subcategory} /><ExpenseStatus expense={expense} /></div>
            <h3 className="mt-2 text-sm font-semibold">{labels.detail}</h3>
            <p className="expense-caption"><time dateTime={expense.business_date}>{expense.business_date}</time> · {expense.fund_account_name}</p>
            <p className="expense-caption whitespace-pre-wrap">{expense.note || '无备注'}</p>
          </div>
          <dl className="expense-detail-kv mt-1">{[
            ['原费用', money(expense.original_amount, expense.currency)],
            ['累计退回', money(expense.refunded_amount || '0', expense.currency)],
            ['剩余可退', money(expense.reversed ? '0' : remaining(expense), expense.currency)],
            ['净支出（CNY）', money(expense.reversed ? '0' : expense.net_amount_cny ?? expense.amount_cny)],
          ].map(([label, value]) => <div key={label}><dt>{label}</dt><dd className="font-mono">{value}</dd></div>)}</dl>
          {mode === 'detail' ? <>
            <h3 className="mb-1 mt-5 flex items-center gap-1.5 text-xs font-semibold text-muted"><CornerDownLeft aria-hidden="true" size={14} />退回记录</h3>
            {expense.refunds?.length ? <ul className="expense-detail-history">{expense.refunds.map(refund => <li key={refund.id}>
              <div className="flex flex-wrap justify-between gap-2"><time className="font-mono text-xs text-muted" dateTime={refund.business_date}>{refund.business_date}</time><strong className="font-mono font-semibold text-success">{money(refund.original_amount, refund.currency)}</strong></div>
              <p className="expense-caption"><Wallet aria-hidden="true" size={12} className="mr-1 inline-block" />收款：{refund.fund_account_name}</p><p className="expense-caption whitespace-pre-wrap">{refund.note}</p>
            </li>)}</ul> : <p className="expense-caption py-3">暂无退回记录</p>}
            {expense.reversed && <p className="expense-hint mt-3">已整笔撤回冲回，不再计入净费用。整笔撤回日期：{expense.reversal_business_date}</p>}
            {onRefund && refundDisabledReason(expense) && <p className="expense-caption mt-3">{refundDisabledReason(expense)}</p>}
          </> : <form id="expense-action-form" onSubmit={submit} className="mt-4 space-y-4">
            {blocked && <p role="alert" className="expense-hint">{blocked}</p>}
            <fieldset disabled={busy || loading || !!loadError || !!blocked} className="space-y-4">
              {mode === 'refund' && <>
                <label className="expense-field-label">本次退回金额（{expense.currency}）<input autoComplete="off" inputMode="decimal" required value={amount} onChange={event => setAmount(event.target.value)} className={`${fieldClass} font-mono`} placeholder="请输入实际收到的金额" /></label>
                {overLimit && <p role="alert" className="expense-hint expense-hint--danger">不能超过剩余可退金额 {money(remaining(expense), expense.currency)}</p>}
                <label className="expense-field-label">实际到账日期<input type="date" required min={expense.business_date} value={businessDate} onChange={event => setBusinessDate(event.target.value)} className={fieldClass} /></label>
                <label className="expense-field-label">收款账户<select required value={accountId} onChange={event => setAccountId(event.target.value)} className={fieldClass}><option value="">请选择实际收款账户</option>{eligible.map(item => <option key={item.id} value={item.id}>{item.name} · {item.currency}</option>)}</select></label>
                {!eligible.length && <p role="alert" className="expense-hint expense-hint--danger">没有启用的同币种公司账户，暂时无法登记退回。</p>}
              </>}
              <label className="expense-field-label">{mode === 'refund' ? '退回原因' : '撤回原因'}<textarea required rows={3} value={note} onChange={event => setNote(event.target.value)} className={fieldClass} /></label>
            </fieldset>
            {mode === 'refund' ? <p className="expense-hint">{account && amountCents != null && amountCents > 0n ? `${account.name} 增加 ${money(amount, expense.currency)}。` : '请核对实际到账金额、日期和账户。'}{expense.currency === 'CNY' && amountCents != null && amountCents > 0n ? `本次冲减费用 ${money(amount)}。` : '按原费用的人民币账面成本冲减费用。'}原费用和退回记录均保留。</p> : <p className="expense-hint expense-hint--danger">将整笔冲回 {money(expense.original_amount, expense.currency)} 至原付款账户，业务日期为 {moscowBusinessDate()}。仅用于原登记有误；实际收到部分退款请使用“登记退回”。</p>}
            {error && <p role="alert" className="expense-hint expense-hint--danger">{error}</p>}
          </form>}
        </>}
      </div>
      <footer className="expense-modal-foot">
        {mode === 'detail' ? <>
          <button type="button" onClick={onClose} className={buttonClass}>关闭</button>
          {expense && onRefund && <button type="button" disabled={loading || !!loadError || !!refundDisabledReason(expense)} onClick={() => setMode('refund')} className={`${buttonClass} expense-button--danger`}><CornerDownLeft aria-hidden="true" size={14} />登记退回</button>}
        </> : <>
          <button type="button" disabled={busy} onClick={onClose} className={buttonClass}>取消</button>
          <button type="submit" form="expense-action-form" disabled={busy || !valid} className={`${buttonClass} expense-button--danger`}><Check aria-hidden="true" size={14} />{busy ? '入账中…' : mode === 'refund' ? '确认退回并入账' : '确认整笔撤回'}</button>
        </>}
      </footer>
    </div>
  </div>, document.body);
}
