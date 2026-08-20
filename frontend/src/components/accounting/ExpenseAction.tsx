import { useMemo, useState, type FormEvent } from 'react';
import { parseAccountingApiError, recordExpense } from '../../api';
import type { AccountingApiError, ExpenseActionPayload, FundAccount } from '../../types';
import type { ActionState } from '../../features/accounting/actionState';
import { moscowBusinessDate } from '../../utils/businessDate';

export type ExpenseCategory = 'salary' | 'rent' | 'utilities' | 'professional' | 'interest' | 'other' | 'salary_expense';
export interface ExpenseActionValue {
  amount: string;
  fund_account_id?: number | '';
  business_date: string;
  note?: string;
}

interface ExpenseActionProps {
  accounts: FundAccount[];
  businessDate?: string;
  category?: ExpenseCategory;
  value?: Partial<ExpenseActionValue>;
  state?: ActionState;
  onChange?: (value: Partial<ExpenseActionValue> & { category?: ExpenseCategory }) => void;
  onSubmit?: (payload?: ExpenseActionPayload) => void | Promise<unknown>;
  /** 允许动作中心注入 mutation；默认走正式费用 API。 */
  submit?: (payload: ExpenseActionPayload) => Promise<unknown>;
}

// 费用默认日期按 Moscow 业务日，避免 UTC fallback 跨日错期。
const today = () => moscowBusinessDate();
const normaliseCategory = (category?: ExpenseCategory): Exclude<ExpenseCategory, 'salary_expense'> => category === 'salary_expense' ? 'salary' : (category || 'salary');

function isConflict(error: AccountingApiError) {
  return error.status === 409 || error.code === 'version_conflict' || error.code === 'conflict';
}

export default function ExpenseAction({ accounts, businessDate = today(), category, value, state, onChange, onSubmit, submit }: ExpenseActionProps) {
  const [localCategory, setLocalCategory] = useState<ExpenseCategory>(category || 'salary');
  const [localValue, setLocalValue] = useState<ExpenseActionValue>({ amount: '', business_date: businessDate, ...value });
  const [localState, setLocalState] = useState<ActionState>({ status: 'idle', input: {} });
  const [fallbackError, setFallbackError] = useState('');
  const currentCategory = category ?? localCategory;
  const current = value ? { ...localValue, ...value } : localValue;
  const actionState = state || localState;
  const [localCurrency, setLocalCurrency] = useState<'CNY' | 'RUB'>('CNY');
  const currency = value?.fund_account_id
    ? accounts.find(account => account.id === value.fund_account_id)?.currency || localCurrency
    : localCurrency;
  const filteredAccounts = useMemo(() => accounts.filter(account => account.is_active && account.currency === currency), [accounts, currency]);
  const accountId = filteredAccounts.some(account => account.id === current.fund_account_id)
    ? current.fund_account_id || ''
    : filteredAccounts[0]?.id || '';
  const categoryLabel: Record<Exclude<ExpenseCategory, 'salary_expense'>, string> = {
    salary: '工资',
    rent: '房租',
    utilities: '水电',
    professional: '会计（专业服务）',
    interest: '利息支出（财务费用）',
    other: '其他经营费用',
  };

  const update = (patch: Partial<ExpenseActionValue>) => {
    const next = { ...current, ...patch };
    if (!value) setLocalValue(next);
    onChange?.(patch);
  };
  const updateCategory = (next: ExpenseCategory) => {
    if (!category) setLocalCategory(next);
    onChange?.({ category: next, fund_account_id: '' });
    if (!value) setLocalValue(currentValue => ({ ...currentValue, fund_account_id: '' }));
  };
  const updateCurrency = (next: 'CNY' | 'RUB') => {
    setLocalCurrency(next);
    onChange?.({ fund_account_id: '' });
    if (!value) setLocalValue(currentValue => ({ ...currentValue, fund_account_id: '' }));
  };

  const setActionState = (next: ActionState) => { if (!state) setLocalState(next); };

  const submitForm = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setFallbackError('');
    const payload: ExpenseActionPayload = { category: normaliseCategory(currentCategory), amount: current.amount, fund_account_id: Number(accountId), business_date: current.business_date, note: current.note || '' };
    if (!payload.fund_account_id || !payload.amount || !payload.business_date) {
      setFallbackError('请选择账户并填写金额和业务日期');
      return;
    }
    setActionState({ status: 'loading', input: { ...current, category: currentCategory }, error: undefined });
    try {
      const result = submit ? await submit(payload) : onSubmit ? await onSubmit(payload) : await recordExpense(payload);
      setActionState({ status: 'success', input: { ...current, category: currentCategory }, result, error: undefined });
    } catch (requestError) {
      const parsed = parseAccountingApiError(requestError);
      const nextStatus = isConflict(parsed) ? 'conflict' : 'error';
      // 失败保留金额、日期和备注，避免重试时重新录入费用事实。
      setActionState({ status: nextStatus, input: { ...current, category: currentCategory }, error: { code: parsed.code, message: parsed.message, details: parsed.details } });
    }
  };

  const errorMessage = fallbackError || actionState.error?.message;
  const busy = actionState.status === 'loading';
  return (
    <section tabIndex={-1} data-guide="accounting-actions-expense" className="rounded-md border border-border bg-white shadow-sm">
      <div className="flex items-center justify-between border-b border-border px-5 py-4"><div><h2 className="font-display text-lg font-semibold">记录经营费用</h2><p className="mt-0.5 text-xs text-muted">每种费用都可以选择人民币或卢布账户。</p></div><span className="text-[11px] uppercase tracking-wider text-accent">Expense</span></div>
      <form onSubmit={submitForm} className="space-y-3 p-5">
        {errorMessage && <p role="alert" className={`rounded border px-3 py-2 text-sm ${actionState.status === 'conflict' ? 'border-amber-200 bg-amber-50 text-amber-800' : 'border-red-200 bg-red-50 text-red-700'}`}>{errorMessage}</p>}
        {actionState.status === 'success' && <p className="rounded border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-800">费用已记录</p>}
        <label className="block text-xs font-medium text-muted">费用类别<select data-guide="accounting-expense-category" value={normaliseCategory(currentCategory)} onChange={event => updateCategory(event.target.value as ExpenseCategory)} className="mt-1.5 w-full rounded border border-border bg-white px-3 py-2 text-sm text-fg">{Object.entries(categoryLabel).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
        <div className="grid gap-3 sm:grid-cols-2"><label className="block text-xs font-medium text-muted">支付币种<select data-guide="accounting-expense-currency" required disabled={busy} value={currency} onChange={event => updateCurrency(event.target.value as 'CNY' | 'RUB')} className="mt-1.5 w-full rounded border border-border bg-white px-3 py-2 text-sm text-fg"><option value="CNY">人民币（CNY）</option><option value="RUB">卢布（RUB）</option></select></label><label className="block text-xs font-medium text-muted">资金账户（{currency}）<select data-guide="accounting-expense-account" required disabled={busy || !filteredAccounts.length} value={accountId} onChange={event => update({ fund_account_id: Number(event.target.value) })} className="mt-1.5 w-full rounded border border-border bg-white px-3 py-2 text-sm text-fg disabled:cursor-not-allowed disabled:bg-[#F5F1EC]"><option value="" disabled>{filteredAccounts.length ? `选择 ${currency} 账户` : `暂无可用 ${currency} 账户`}</option>{filteredAccounts.map(account => <option key={account.id} value={account.id}>{account.name} · {account.currency}</option>)}</select></label></div>
        <div className="grid gap-3 sm:grid-cols-2"><label className="block text-xs font-medium text-muted">金额（{currency}）<input data-guide="accounting-expense-amount" required value={current.amount} onChange={event => update({ amount: event.target.value })} inputMode="decimal" placeholder="例如 5000.00" className="mt-1.5 w-full rounded border border-border px-3 py-2 text-sm" /></label><label className="block text-xs font-medium text-muted">业务日期<input data-guide="accounting-expense-date" required type="date" value={current.business_date} onChange={event => update({ business_date: event.target.value })} className="mt-1.5 w-full rounded border border-border px-3 py-2 text-sm" /></label></div>
        <label className="block text-xs font-medium text-muted">备注<textarea data-guide="accounting-expense-note" value={current.note || ''} onChange={event => update({ note: event.target.value })} rows={2} placeholder={`${categoryLabel[normaliseCategory(currentCategory)]}说明（可选）`} className="mt-1.5 w-full resize-none rounded border border-border px-3 py-2 text-sm" /></label>
        <div data-guide="accounting-expense-submit" className="flex items-center justify-between border-t border-border pt-3"><span className="text-xs text-muted">当前分类：{categoryLabel[normaliseCategory(currentCategory)]} · {currency}</span><button type="submit" disabled={busy || !filteredAccounts.length} className="rounded bg-accent px-4 py-2.5 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50">{busy ? '记录中…' : '记录费用'}</button></div>
      </form>
    </section>
  );
}
