import { useMemo, useState, type FormEvent } from 'react';
import type { AccountingApiError, ExchangeActionPayload, FundAccount } from '../../types';
import { exchangeToRub, parseAccountingApiError } from '../../api';
import type { ActionState } from '../../features/accounting/actionState';
import { moscowBusinessDate } from '../../utils/businessDate';
import { selectActiveAccountId } from './ExchangeAction.logic';

export interface ExchangeActionValue {
  source_account_id?: number | '';
  rub_account_id?: number | '';
  source_amount: string;
  rub_amount: string;
  business_date: string;
}

interface ExchangeActionProps {
  accounts: FundAccount[];
  businessDate?: string;
  value?: Partial<ExchangeActionValue>;
  state?: ActionState;
  onChange?: (value: Partial<ExchangeActionValue>) => void;
  onSubmit?: (payload?: ExchangeActionPayload) => void | Promise<unknown>;
  /** 允许工作台注入 mutation；未注入时直接调用正式 API。 */
  submit?: (payload: ExchangeActionPayload) => Promise<unknown>;
}

// 换汇默认日期按 Moscow 业务日，避免浏览器/UTC 日界造成错期。
const today = () => moscowBusinessDate();
const emptyValue = (businessDate: string): ExchangeActionValue => ({ source_amount: '', rub_amount: '', business_date: businessDate });

function isConflict(error: AccountingApiError) {
  return error.status === 409 || error.code === 'version_conflict' || error.code === 'conflict';
}

export default function ExchangeAction({ accounts, businessDate, value, state, onChange, onSubmit, submit }: ExchangeActionProps) {
  const defaults = useMemo(() => emptyValue(businessDate || today()), [businessDate]);
  const [localValue, setLocalValue] = useState<ExchangeActionValue>({ ...defaults, ...value });
  const [localState, setLocalState] = useState<ActionState>({ status: 'idle', input: {} });
  const current = value ? { ...localValue, ...value } : localValue;
  const actionState = state || localState;
  const [fallbackError, setFallbackError] = useState('');
  const sources = accounts.filter(account => account.is_active && (account.currency === 'CNY' || account.currency === 'USDT'));
  const rubAccounts = accounts.filter(account => account.is_active && account.currency === 'RUB');
  const sourceId = selectActiveAccountId(sources, current.source_account_id);
  const rubId = selectActiveAccountId(rubAccounts, current.rub_account_id);

  const update = (patch: Partial<ExchangeActionValue>) => {
    const next = { ...current, ...patch };
    if (!value) setLocalValue(next);
    onChange?.(patch);
  };

  const setActionState = (next: ActionState) => {
    if (!state) setLocalState(next);
  };

  const submitForm = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setFallbackError('');
    const payload: ExchangeActionPayload = {
      source_account_id: Number(sourceId),
      rub_account_id: Number(rubId),
      source_amount: current.source_amount,
      rub_amount: current.rub_amount,
      business_date: current.business_date,
    };
    if (!payload.source_account_id || !payload.rub_account_id || !payload.source_amount || !payload.rub_amount || !payload.business_date) {
      setFallbackError('请选择账户并填写换出、换入金额和业务日期');
      return;
    }
    setActionState({ status: 'loading', input: { ...current }, error: undefined });
    try {
      const result = submit ? await submit(payload) : onSubmit ? await onSubmit(payload) : await exchangeToRub(payload);
      setActionState({ status: 'success', input: { ...current }, result, error: undefined });
    } catch (requestError) {
      const parsed = parseAccountingApiError(requestError);
      const nextStatus = isConflict(parsed) ? 'conflict' : 'error';
      // 失败不清空 current，经营者可直接修正后重试。
      setActionState({ status: nextStatus, input: { ...current }, error: { code: parsed.code, message: parsed.message, details: parsed.details } });
    }
  };

  const errorMessage = fallbackError || actionState.error?.message;
  const busy = actionState.status === 'loading';
  return (
    <section tabIndex={-1} data-guide="accounting-actions-exchange" className="rounded-md border border-border bg-white shadow-sm">
      <div className="flex items-center justify-between border-b border-border px-5 py-4">
        <div><h2 className="font-display text-lg font-semibold">记录换汇</h2><p className="mt-0.5 text-xs text-muted">人民币或 USDT 换入卢布，按实际到账数量记账。</p></div>
        <span className="text-[11px] uppercase tracking-wider text-accent">Exchange</span>
      </div>
      <form onSubmit={submitForm} className="space-y-3 p-5">
        {errorMessage && <p role="alert" className={`rounded border px-3 py-2 text-sm ${actionState.status === 'conflict' ? 'border-amber-200 bg-amber-50 text-amber-800' : 'border-red-200 bg-red-50 text-red-700'}`}>{errorMessage}</p>}
        {actionState.status === 'success' && <p className="rounded border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-800">换汇已记录</p>}
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="block text-xs font-medium text-muted">转出账户<select required value={sourceId} onChange={event => update({ source_account_id: Number(event.target.value) })} className="mt-1.5 w-full rounded border border-border px-3 py-2 text-sm"><option value="" disabled>选择 CNY 或 USDT 账户</option>{sources.map(account => <option key={account.id} value={account.id}>{account.name} · {account.currency}</option>)}</select></label>
          <label className="block text-xs font-medium text-muted">转入账户<select required value={rubId} onChange={event => update({ rub_account_id: Number(event.target.value) })} className="mt-1.5 w-full rounded border border-border px-3 py-2 text-sm"><option value="" disabled>选择 RUB 账户</option>{rubAccounts.map(account => <option key={account.id} value={account.id}>{account.name} · RUB</option>)}</select></label>
          <label className="block text-xs font-medium text-muted">实际转出数量<input required value={current.source_amount} onChange={event => update({ source_amount: event.target.value })} inputMode="decimal" placeholder="例如 1000.00" className="mt-1.5 w-full rounded border border-border px-3 py-2 text-sm" /></label>
          <label className="block text-xs font-medium text-muted">实际转入数量（RUB）<input required value={current.rub_amount} onChange={event => update({ rub_amount: event.target.value })} inputMode="decimal" placeholder="例如 12000.00" className="mt-1.5 w-full rounded border border-border px-3 py-2 text-sm" /></label>
        </div>
        <label className="block text-xs font-medium text-muted">业务日期<input required type="date" value={current.business_date} onChange={event => update({ business_date: event.target.value })} className="mt-1.5 w-full rounded border border-border px-3 py-2 text-sm" /></label>
        <div className="flex items-center justify-between border-t border-border pt-3"><span className="text-xs text-muted">仅支持 CNY / USDT → RUB</span><button type="submit" disabled={busy || !sourceId || !rubId} className="rounded bg-accent px-4 py-2.5 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50">{busy ? '记录中…' : '记录换汇'}</button></div>
      </form>
    </section>
  );
}
