import { useMemo, useState, type FormEvent } from 'react';
import { parseAccountingApiError, recordExpense } from '../../api';
import type { AccountingApiError, ExpenseActionPayload, ExpenseSubcategory, FundAccount } from '../../types';
import type { ActionState } from '../../features/accounting/actionState';
import { moscowBusinessDate } from '../../utils/businessDate';

export type ExpenseCategory = 'salary' | 'rent' | 'utilities' | 'professional' | 'interest' | 'other' | 'salary_expense';
export type ExpenseGroup = 'personnel' | 'rent' | 'utilities' | 'transport' | 'office' | 'facility' | 'marketing' | 'professional' | 'financial' | 'tax' | 'other';
export interface ExpenseActionValue {
  amount: string;
  fund_account_id?: number | '';
  business_date: string;
  subcategory?: ExpenseSubcategory;
  note?: string;
}

interface ExpenseOption { value: ExpenseSubcategory; label: string }
interface ExpenseGroupOption { value: ExpenseGroup; category: Exclude<ExpenseCategory, 'salary_expense'>; label: string; options: ExpenseOption[] }

const EXPENSE_GROUP_OPTIONS: ExpenseGroupOption[] = [
  { value: 'personnel', category: 'salary', label: '人员费用', options: [
    { value: 'personnel_salary', label: '工资' }, { value: 'personnel_bonus', label: '奖金 / 补贴' },
    { value: 'personnel_benefits', label: '员工福利' }, { value: 'personnel_recruiting', label: '招聘 / 培训' },
  ] },
  { value: 'rent', category: 'rent', label: '房租与物业', options: [
    { value: 'rent', label: '房租' }, { value: 'property', label: '物业管理费' }, { value: 'venue_service', label: '场地服务费' },
  ] },
  { value: 'utilities', category: 'utilities', label: '水电与能源', options: [
    { value: 'electricity', label: '电费' }, { value: 'water', label: '水费' }, { value: 'gas_heating', label: '燃气 / 供暖' }, { value: 'other_energy', label: '其他能源' },
  ] },
  { value: 'transport', category: 'other', label: '交通 / 物流', options: [
    { value: 'transport_taxi', label: '打车' }, { value: 'transport_public', label: '公共交通' }, { value: 'transport_travel', label: '火车 / 飞机' },
    { value: 'transport_delivery', label: '快递 / 配送' }, { value: 'transport_parking', label: '停车费 / 过路费' }, { value: 'transport_fuel', label: '燃油' },
  ] },
  { value: 'office', category: 'other', label: '办公 / 通讯', options: [
    { value: 'office_supplies', label: '办公用品' }, { value: 'office_printing', label: '打印 / 复印' }, { value: 'office_phone', label: '电话费' },
    { value: 'office_internet', label: '网络费' }, { value: 'office_software', label: '软件 / 订阅' }, { value: 'office_postage', label: '邮寄费' },
  ] },
  { value: 'facility', category: 'other', label: '场地 / 设备', options: [
    { value: 'facility_equipment', label: '设备购买' }, { value: 'facility_tools', label: '小型工具' }, { value: 'facility_repair', label: '维修 / 保养' }, { value: 'facility_cleaning', label: '清洁' },
  ] },
  { value: 'marketing', category: 'other', label: '销售与营销', options: [
    { value: 'marketing_advertising', label: '广告费' }, { value: 'marketing_platform', label: '平台服务费' }, { value: 'marketing_creative', label: '拍摄 / 设计' },
    { value: 'marketing_gift', label: '客户礼品' }, { value: 'marketing_promotion', label: '促销活动' },
  ] },
  { value: 'professional', category: 'professional', label: '专业服务', options: [
    { value: 'professional_accounting', label: '会计（专业服务）' }, { value: 'professional_legal', label: '法律服务' }, { value: 'professional_consulting', label: '咨询服务' },
    { value: 'professional_design', label: '设计服务' }, { value: 'professional_translation', label: '翻译服务' },
  ] },
  { value: 'financial', category: 'interest', label: '财务费用', options: [
    { value: 'financial_interest', label: '利息支出（财务费用）' }, { value: 'financial_bank_fee', label: '银行手续费' },
    { value: 'financial_payment_fee', label: '支付手续费' }, { value: 'financial_account_fee', label: '账户管理费' },
  ] },
  { value: 'tax', category: 'other', label: '税费与政府费用', options: [
    { value: 'tax', label: '税费' }, { value: 'registration', label: '注册费' }, { value: 'license', label: '许可证费' }, { value: 'notary', label: '公证 / 认证费' },
  ] },
  { value: 'other', category: 'other', label: '其他经营费用', options: [{ value: 'other', label: '其他' }] },
];

interface ExpenseActionProps {
  accounts: FundAccount[];
  businessDate?: string;
  category?: ExpenseCategory;
  value?: Partial<ExpenseActionValue>;
  state?: ActionState;
  onChange?: (value: Partial<ExpenseActionValue> & { category?: ExpenseCategory }) => void;
  onSubmit?: (payload?: ExpenseActionPayload) => void | Promise<unknown>;
  submit?: (payload: ExpenseActionPayload) => Promise<unknown>;
}

const today = () => moscowBusinessDate();
const normaliseCategory = (category?: ExpenseCategory): Exclude<ExpenseCategory, 'salary_expense'> => category === 'salary_expense' ? 'salary' : (category || 'salary');
const groupFor = (category: Exclude<ExpenseCategory, 'salary_expense'>, subcategory?: ExpenseSubcategory): ExpenseGroupOption =>
  EXPENSE_GROUP_OPTIONS.find(group => group.category === category && (!subcategory || group.options.some(option => option.value === subcategory)))
  || EXPENSE_GROUP_OPTIONS.find(group => group.category === category)
  || EXPENSE_GROUP_OPTIONS[0];

function isConflict(error: AccountingApiError) { return error.status === 409 || error.code === 'version_conflict' || error.code === 'conflict'; }

export default function ExpenseAction({ accounts, businessDate = today(), category, value, state, onChange, onSubmit, submit }: ExpenseActionProps) {
  const initialCategory = normaliseCategory(category);
  const initialGroup = groupFor(initialCategory, value?.subcategory);
  const [localCategory, setLocalCategory] = useState<ExpenseCategory>(category || 'salary');
  const [localGroup, setLocalGroup] = useState<ExpenseGroup>(initialGroup.value);
  const [localSubcategory, setLocalSubcategory] = useState<ExpenseSubcategory>(value?.subcategory || initialGroup.options[0].value);
  const [localValue, setLocalValue] = useState<ExpenseActionValue>({ amount: '', business_date: businessDate, ...value });
  const [localState, setLocalState] = useState<ActionState>({ status: 'idle', input: {} });
  const [fallbackError, setFallbackError] = useState('');
  const currentCategory = normaliseCategory(category ?? localCategory);
  const currentGroup = EXPENSE_GROUP_OPTIONS.find(group => group.value === (category ? groupFor(currentCategory, value?.subcategory).value : localGroup)) || initialGroup;
  const currentSubcategory = value?.subcategory || localSubcategory;
  const current = value ? { ...localValue, ...value } : localValue;
  const actionState = state || localState;
  const [localCurrency, setLocalCurrency] = useState<'CNY' | 'RUB'>('CNY');
  const currency = value?.fund_account_id ? accounts.find(account => account.id === value.fund_account_id)?.currency || localCurrency : localCurrency;
  const filteredAccounts = useMemo(() => accounts.filter(account => account.is_active && account.currency === currency), [accounts, currency]);
  const accountId = filteredAccounts.some(account => account.id === current.fund_account_id) ? current.fund_account_id || '' : filteredAccounts[0]?.id || '';

  const update = (patch: Partial<ExpenseActionValue>) => { const next = { ...current, ...patch }; if (!value) setLocalValue(next); onChange?.(patch); };
  const updateGroup = (nextGroup: ExpenseGroup) => {
    const option = EXPENSE_GROUP_OPTIONS.find(group => group.value === nextGroup) || EXPENSE_GROUP_OPTIONS[0];
    const nextSubcategory = option.options[0].value;
    setLocalGroup(nextGroup); setLocalCategory(option.category); setLocalSubcategory(nextSubcategory);
    onChange?.({ category: option.category, subcategory: nextSubcategory, fund_account_id: '' });
    if (!value) setLocalValue(currentValue => ({ ...currentValue, subcategory: nextSubcategory, fund_account_id: '' }));
  };
  const updateSubcategory = (next: ExpenseSubcategory) => { setLocalSubcategory(next); onChange?.({ subcategory: next }); if (!value) setLocalValue(currentValue => ({ ...currentValue, subcategory: next })); };
  const updateCurrency = (next: 'CNY' | 'RUB') => { setLocalCurrency(next); onChange?.({ fund_account_id: '' }); if (!value) setLocalValue(currentValue => ({ ...currentValue, fund_account_id: '' })); };
  const setActionState = (next: ActionState) => { if (!state) setLocalState(next); };

  const submitForm = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); setFallbackError('');
    const payload: ExpenseActionPayload = { category: currentCategory, subcategory: currentSubcategory, amount: current.amount, fund_account_id: Number(accountId), business_date: current.business_date, note: current.note || '' };
    if (!payload.fund_account_id || !payload.amount || !payload.business_date || !payload.subcategory) { setFallbackError('请选择费用分类、费用明细和账户，并填写金额、业务日期'); return; }
    setActionState({ status: 'loading', input: { ...current, category: currentCategory, subcategory: currentSubcategory }, error: undefined });
    try {
      const result = submit ? await submit(payload) : onSubmit ? await onSubmit(payload) : await recordExpense(payload);
      setActionState({ status: 'success', input: { ...current, category: currentCategory, subcategory: currentSubcategory }, result, error: undefined });
    } catch (requestError) {
      const parsed = parseAccountingApiError(requestError); const nextStatus = isConflict(parsed) ? 'conflict' : 'error';
      setActionState({ status: nextStatus, input: { ...current, category: currentCategory, subcategory: currentSubcategory }, error: { code: parsed.code, message: parsed.message, details: parsed.details } });
    }
  };

  const errorMessage = fallbackError || actionState.error?.message;
  const busy = actionState.status === 'loading';
  return (
    <section tabIndex={-1} data-guide="accounting-actions-expense" className="rounded-md border border-border bg-white shadow-sm">
      <div className="flex items-center justify-between border-b border-border px-5 py-4"><div><h2 className="font-display text-lg font-semibold">记录经营费用</h2><p className="mt-0.5 text-xs text-muted">先选费用分类，再选具体明细；每种费用都可以选择人民币或卢布账户。</p></div><span className="text-[11px] uppercase tracking-wider text-accent">Expense</span></div>
      <form onSubmit={submitForm} className="space-y-3 p-5">
        {errorMessage && <p role="alert" className={`rounded border px-3 py-2 text-sm ${actionState.status === 'conflict' ? 'border-amber-200 bg-amber-50 text-amber-800' : 'border-red-200 bg-red-50 text-red-700'}`}>{errorMessage}</p>}
        {actionState.status === 'success' && <p className="rounded border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-800">费用已记录</p>}
        <div className="grid gap-3 sm:grid-cols-2"><label className="block text-xs font-medium text-muted">费用分类<select data-guide="accounting-expense-category" value={currentGroup.value} onChange={event => updateGroup(event.target.value as ExpenseGroup)} className="mt-1.5 w-full rounded border border-border bg-white px-3 py-2 text-sm text-fg">{EXPENSE_GROUP_OPTIONS.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label><label className="block text-xs font-medium text-muted">费用明细<select data-guide="accounting-expense-subcategory" required disabled={busy} value={currentSubcategory} onChange={event => updateSubcategory(event.target.value as ExpenseSubcategory)} className="mt-1.5 w-full rounded border border-border bg-white px-3 py-2 text-sm text-fg">{currentGroup.options.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label></div>
        <div className="grid gap-3 sm:grid-cols-2"><label className="block text-xs font-medium text-muted">支付币种<select data-guide="accounting-expense-currency" required disabled={busy} value={currency} onChange={event => updateCurrency(event.target.value as 'CNY' | 'RUB')} className="mt-1.5 w-full rounded border border-border bg-white px-3 py-2 text-sm text-fg"><option value="CNY">人民币（CNY）</option><option value="RUB">卢布（RUB）</option></select></label><label className="block text-xs font-medium text-muted">资金账户（{currency}）<select data-guide="accounting-expense-account" required disabled={busy || !filteredAccounts.length} value={accountId} onChange={event => update({ fund_account_id: Number(event.target.value) })} className="mt-1.5 w-full rounded border border-border bg-white px-3 py-2 text-sm text-fg disabled:cursor-not-allowed disabled:bg-[#F5F1EC]"><option value="" disabled>{filteredAccounts.length ? `选择 ${currency} 账户` : `暂无可用 ${currency} 账户`}</option>{filteredAccounts.map(account => <option key={account.id} value={account.id}>{account.name} · {account.currency}</option>)}</select></label></div>
        <div className="grid gap-3 sm:grid-cols-2"><label className="block text-xs font-medium text-muted">金额（{currency}）<input data-guide="accounting-expense-amount" required value={current.amount} onChange={event => update({ amount: event.target.value })} inputMode="decimal" placeholder="例如 5000.00" className="mt-1.5 w-full rounded border border-border px-3 py-2 text-sm" /></label><label className="block text-xs font-medium text-muted">业务日期<input data-guide="accounting-expense-date" required type="date" value={current.business_date} onChange={event => update({ business_date: event.target.value })} className="mt-1.5 w-full rounded border border-border px-3 py-2 text-sm" /></label></div>
        <label className="block text-xs font-medium text-muted">备注<textarea data-guide="accounting-expense-note" value={current.note || ''} onChange={event => update({ note: event.target.value })} rows={2} placeholder={`${currentGroup.label} · ${currentGroup.options.find(option => option.value === currentSubcategory)?.label || ''}说明（可选）`} className="mt-1.5 w-full resize-none rounded border border-border px-3 py-2 text-sm" /></label>
        <div data-guide="accounting-expense-submit" className="flex items-center justify-between border-t border-border pt-3"><span className="text-xs text-muted">当前分类：{currentGroup.label} · {currentGroup.options.find(option => option.value === currentSubcategory)?.label} · {currency}</span><button type="submit" disabled={busy || !filteredAccounts.length} className="rounded bg-accent px-4 py-2.5 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50">{busy ? '记录中…' : '记录费用'}</button></div>
      </form>
    </section>
  );
}
