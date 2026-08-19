import { useState, type FormEvent } from 'react';
import { Pencil, Plus, X } from 'lucide-react';
import { apiErrorMessage, createAccountingAccount, updateAccountingAccount } from '../../api';
import type { AccountingSummaryFundAccount, FundAccount } from '../../types';
import { formatCny, formatOriginalAmount } from '../sales/salesState';

interface Props {
  accounts?: FundAccount[];
  balances?: AccountingSummaryFundAccount[];
  accountsError?: string;
  summaryError?: string;
  onChanged: () => void;
}

type AccountForm = { name: string; currency: string; is_active: boolean };
const emptyForm: AccountForm = { name: '', currency: 'CNY', is_active: true };

/** 资金账户是公司资产入口；改名安全，币种和历史流水不允许在这里改动。 */
export default function FundAccountManager({ accounts = [], balances = [], accountsError, summaryError, onChanged }: Props) {
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<FundAccount | null>(null);
  const [form, setForm] = useState<AccountForm>(emptyForm);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const balanceById = new Map(balances.map(balance => [balance.account_id, balance]));

  const openCreate = () => {
    setEditing(null); setForm(emptyForm); setError(''); setFormOpen(true);
  };
  const openEdit = (account: FundAccount) => {
    setEditing(account); setForm({ name: account.name, currency: account.currency, is_active: account.is_active }); setError(''); setFormOpen(true);
  };
  const closeForm = () => { if (!busy) setFormOpen(false); };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const name = form.name.trim();
    if (!name) { setError('请输入账户名称'); return; }
    setBusy(true); setError('');
    try {
      if (editing) await updateAccountingAccount(editing.id, { name, is_active: form.is_active });
      else await createAccountingAccount({ name, currency: form.currency });
      setFormOpen(false); onChanged();
    } catch (requestError) { setError(apiErrorMessage(requestError, '资金账户保存失败')); }
    finally { setBusy(false); }
  };

  return (
    <section className="w-full rounded-md border border-border bg-white shadow-sm">
      <div className="flex items-center justify-between gap-3 border-b border-border px-5 py-4">
        <div><h2 className="font-display text-lg font-semibold">资金账户</h2><p className="text-xs text-muted">管理公司人民币、卢布和 USDT 账户；历史流水不会被改写。</p></div>
        <button type="button" onClick={openCreate} className="inline-flex items-center gap-1 rounded border border-border px-3 py-1.5 text-xs font-semibold hover:border-gold"><Plus className="h-3.5 w-3.5" />新建账户</button>
      </div>
      {(accountsError || summaryError) && <p className="px-5 py-3 text-xs text-red-700">{accountsError || summaryError}</p>}
      {!accountsError && !summaryError && accounts.length === 0 ? <p className="px-5 py-8 text-center text-sm text-muted">暂无资金账户</p> : <div className="divide-y divide-border">{accounts.map(account => {
        const balance = balanceById.get(account.id);
        const amount = balance ? (account.currency === 'CNY' ? formatCny(balance.cny_book_cost) : `${formatOriginalAmount(balance.original_balance, account.currency)} ${account.currency}`) : '—';
        return <div key={account.id} className="flex items-center justify-between gap-3 px-5 py-3">
          <div className="min-w-0"><p className="truncate text-sm font-semibold">{account.name} {!account.is_active && <span className="ml-1 text-xs font-normal text-muted">已停用</span>}</p><p className="text-[11px] text-muted">{account.currency}</p></div>
          <div className="flex items-center gap-3"><span className="font-mono text-sm">{amount}</span><button type="button" onClick={() => openEdit(account)} aria-label={`编辑${account.name}`} className="rounded p-1.5 text-muted hover:bg-accent-light hover:text-fg"><Pencil className="h-3.5 w-3.5" /></button></div>
        </div>;
      })}</div>}
      {formOpen && <div role="dialog" aria-modal="true" aria-labelledby="account-form-title" className="fixed inset-0 z-50 grid place-items-center bg-fg/30 p-4">
        <form onSubmit={submit} className="w-full max-w-md rounded-md border border-border bg-white shadow-lg">
          <div className="flex items-center justify-between border-b border-border px-5 py-4"><h2 id="account-form-title" className="font-display text-lg font-semibold">{editing ? '编辑资金账户' : '新建资金账户'}</h2><button type="button" aria-label="关闭账户表单" onClick={closeForm} className="text-muted"><X className="h-4 w-4" /></button></div>
          <div className="space-y-4 p-5">
            <label className="block text-xs font-medium text-muted">账户名称<input autoFocus required maxLength={120} value={form.name} onChange={event => setForm(current => ({ ...current, name: event.target.value }))} className="mt-1.5 w-full rounded border border-border bg-white px-3 py-2 text-sm text-fg" placeholder="例如：卢布银行卡" /></label>
            <label className="block text-xs font-medium text-muted">账户币种<select disabled={Boolean(editing) || busy} value={form.currency} onChange={event => setForm(current => ({ ...current, currency: event.target.value }))} className="mt-1.5 w-full rounded border border-border bg-white px-3 py-2 text-sm text-fg"><option value="CNY">人民币（CNY）</option><option value="RUB">卢布（RUB）</option><option value="USDT">USDT</option></select></label>
            {editing && <label className="flex items-center gap-2 text-sm text-fg"><input type="checkbox" checked={form.is_active} onChange={event => setForm(current => ({ ...current, is_active: event.target.checked }))} />启用这个账户</label>}
            {editing && <p className="rounded bg-cream px-3 py-2 text-xs text-muted">币种不能修改；如币种录错，请停用旧账户后新建正确账户。</p>}
            {error && <p role="alert" className="text-xs text-red-700">{error}</p>}
            <button type="submit" disabled={busy || !form.name.trim()} className="w-full rounded bg-accent px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">{busy ? '保存中…' : editing ? '保存修改' : '创建账户'}</button>
          </div>
        </form>
      </div>}
    </section>
  );
}
