import { useEffect, useState } from 'react';
import { Plus, Search, X } from 'lucide-react';
import { createPurchaseSupplier, searchPurchaseSuppliers } from '../../api';
import type { PurchaseSupplier } from '../../types';

interface SupplierAutocompleteProps {
  value: PurchaseSupplier | null;
  onChange: (supplier: PurchaseSupplier | null) => void;
  disabled?: boolean;
}

export default function SupplierAutocomplete({ value, onChange, disabled = false }: SupplierAutocompleteProps) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<PurchaseSupplier[]>([]);
  const [open, setOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState('');
  const [phone, setPhone] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!open || value || disabled) return undefined;
    let active = true;
    const timer = window.setTimeout(() => {
      searchPurchaseSuppliers(query.trim()).then(next => {
        if (active) setResults(next);
      }).catch(() => {
        if (active) setError('供应商搜索失败，请稍后重试');
      });
    }, query.trim() ? 220 : 0);
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [disabled, open, query, value]);

  const create = async () => {
    if (!name.trim()) return;
    setBusy(true);
    setError('');
    try {
      const supplier = await createPurchaseSupplier({ name: name.trim(), phone: phone.trim() });
      onChange(supplier);
      setCreating(false);
      setName('');
      setPhone('');
      setOpen(false);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '供应商创建失败');
    } finally {
      setBusy(false);
    }
  };

  return <div className="relative">
    <label className="text-[11px] font-semibold tracking-wide text-muted">供应商</label>
    {value ? <div className="mt-1.5 flex items-center justify-between rounded border border-gold/40 bg-[#FFF9F0] px-3 py-2 text-sm">
      <span><strong>{value.name}</strong>{value.phone && <small className="ml-2 text-muted">{value.phone}</small>}</span>
      <button type="button" disabled={disabled} onClick={() => onChange(null)} aria-label="重新选择供应商" className="text-muted hover:text-accent"><X className="h-4 w-4" /></button>
    </div> : <>
      <div className="relative mt-1.5"><Search className="absolute left-3 top-2.5 h-4 w-4 text-muted" /><input disabled={disabled} value={query} onFocus={() => setOpen(true)} onBlur={() => window.setTimeout(() => setOpen(false), 120)} onChange={event => { setQuery(event.target.value); setError(''); setOpen(true); }} placeholder="搜索供应商名称或电话" className="w-full rounded border border-border py-2 pl-9 pr-3 text-sm outline-none focus:border-gold" /></div>
      {open && <div className="absolute z-30 mt-1 max-h-56 w-full overflow-auto rounded border border-border bg-white shadow-xl">
        {results.map(supplier => <button type="button" key={supplier.id} onMouseDown={event => event.preventDefault()} onClick={() => { onChange(supplier); setOpen(false); setQuery(''); }} className="flex w-full items-center justify-between border-b border-border px-3 py-2 text-left text-sm hover:bg-[#FFFCF4]"><span><strong>{supplier.name}</strong><small className="mt-0.5 block text-muted">{supplier.phone || '未填写电话'}</small></span></button>)}
        <button type="button" onMouseDown={event => event.preventDefault()} onClick={() => { setCreating(true); setOpen(false); setName(query); }} className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm font-semibold text-accent hover:bg-accent-light"><Plus className="h-4 w-4" /> 就地新建供应商</button>
      </div>}
    </>}
    {creating && !value && <div className="mt-2 rounded border border-dashed border-gold bg-[#FFFDF7] p-3">
      <p className="text-xs font-semibold text-gold">就地新建供应商</p>
      <div className="mt-2 grid gap-2 sm:grid-cols-2"><input value={name} onChange={event => setName(event.target.value)} placeholder="供应商名称 *" className="rounded border border-border px-3 py-2 text-sm outline-none focus:border-gold" /><input value={phone} onChange={event => setPhone(event.target.value)} placeholder="电话（选填）" className="rounded border border-border px-3 py-2 text-sm outline-none focus:border-gold" /></div>
      <div className="mt-2 flex justify-end gap-2"><button type="button" onClick={() => setCreating(false)} className="rounded border border-border px-3 py-1.5 text-xs">取消</button><button type="button" disabled={busy || !name.trim()} onClick={() => void create()} className="rounded bg-accent px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-50">{busy ? '保存中…' : '保存并选中'}</button></div>
    </div>}
    {error && <p role="alert" className="mt-1 text-xs text-red-700">{error}</p>}
  </div>;
}
