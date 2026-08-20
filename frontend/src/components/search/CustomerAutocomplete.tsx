import { useEffect, useState } from 'react';
import { searchCustomers } from '../../api';
import type { CustomerResult } from '../../types';

export interface CustomerSelection {
  customerId: number | null;
  name: string;
}

interface CustomerAutocompleteProps {
  value: CustomerSelection;
  onChange: (value: CustomerSelection) => void;
  label?: string;
  placeholder?: string;
  dataGuide?: string;
  disabled?: boolean;
  search?: (query: string) => Promise<CustomerResult[]>;
}

export default function CustomerAutocomplete({
  value,
  onChange,
  label = '客户名称',
  placeholder = '输入已有客户或填写散客姓名',
  dataGuide,
  disabled = false,
  search = searchCustomers,
}: CustomerAutocompleteProps) {
  const [open, setOpen] = useState(false);
  const [results, setResults] = useState<CustomerResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState('');

  useEffect(() => {
    const query = value.name.trim();
    if (!open || disabled) return undefined;
    let active = true;
    const timer = window.setTimeout(() => {
      setSearching(true);
      setSearchError('');
      search(query).then(nextResults => {
        if (active) setResults(nextResults.slice(0, 20));
      }).catch(() => {
        if (active) {
          setResults([]);
          setSearchError('客户搜索失败，请稍后重试');
        }
      }).finally(() => {
        if (active) setSearching(false);
      });
    }, query ? 200 : 0);
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [disabled, open, search, value.name]);

  return <div className="relative text-xs font-medium text-muted">
    <label>{label}<input data-guide={dataGuide} value={value.name} disabled={disabled} onFocus={() => setOpen(true)} onBlur={() => setOpen(false)} onChange={event => { onChange({ customerId: null, name: event.target.value }); setResults([]); setSearchError(''); setOpen(true); }} placeholder={placeholder} autoComplete="off" className="mt-1.5 w-full rounded border border-border px-3 py-2 text-sm text-fg outline-none focus:border-gold disabled:bg-cream" /></label>
    {value.customerId && <span className="mt-1 block text-[11px] text-success">已关联客户档案</span>}
    {searching && <span className="mt-1 block text-[11px]">搜索客户中…</span>}
    {searchError && <span className="mt-1 block text-[11px] text-red-700">{searchError}</span>}
    {open && results.length > 0 && <div className="absolute left-0 right-0 z-30 mt-1 overflow-hidden rounded border border-border bg-white shadow-lg">{results.map(customer => <button key={customer.id} type="button" onMouseDown={event => event.preventDefault()} onClick={() => { onChange({ customerId: customer.id, name: customer.name }); setResults([]); setOpen(false); }} className="flex w-full items-center justify-between border-b border-border px-3 py-2 text-left text-sm text-fg last:border-0 hover:bg-cream"><strong>{customer.name}</strong><span className="text-xs text-muted">{customer.phone || '未填写电话'}</span></button>)}</div>}
  </div>;
}
