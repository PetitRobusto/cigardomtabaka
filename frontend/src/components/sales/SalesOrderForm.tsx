import { useEffect, useState } from 'react';
import { Plus, Search, Trash2 } from 'lucide-react';
import { searchCigars } from '../../api';
import type { SalesOrderPayload, SearchCigarResult } from '../../types';
import { formatCny, validateMoneyInput } from './salesState';

interface DraftItem {
  cigar_id: number;
  cigar_name: string;
  sale_unit: 'stick' | 'box';
  quantity: number;
  box_size: number;
  box_options: number[];
  unit_price: string;
}

interface Props {
  onSubmit: (payload: SalesOrderPayload) => Promise<void>;
  busy?: boolean;
  error?: string;
}

const today = () => { const date = new Date(); return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 10); };

export default function SalesOrderForm({ onSubmit, busy = false, error }: Props) {
  const [customerName, setCustomerName] = useState('');
  const [customerTransport, setCustomerTransport] = useState('0');
  const [note, setNote] = useState('');
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchCigarResult[]>([]);
  const [validationError, setValidationError] = useState('');
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState('');
  const [items, setItems] = useState<DraftItem[]>([]);

  useEffect(() => {
    let active = true;
    if (query.trim().length < 2) {
      setResults([]);
      setSearchError('');
      return () => { active = false; };
    }
    const timer = window.setTimeout(() => {
      setSearching(true); setSearchError('');
      searchCigars(query.trim(), true).then(value => {
        if (active) setResults(value.slice(0, 8));
      }).catch(() => {
        if (active) { setResults([]); setSearchError('雪茄搜索失败，请稍后重试'); }
      }).finally(() => {
        if (active) setSearching(false);
      });
    }, 250);
    return () => { active = false; window.clearTimeout(timer); };
  }, [query]);

  const addItem = (cigar: SearchCigarResult) => {
    setItems(current => {
      const existing = current.find(item => item.cigar_id === cigar.id);
      if (existing) return current.map(item => item.cigar_id === cigar.id ? { ...item, quantity: item.quantity + 1 } : item);
      const boxOptions = [...new Set(cigar.batches.map(batch => batch.box_size).filter(Boolean))];
      return [...current, { cigar_id: cigar.id, cigar_name: `${cigar.brand} · ${cigar.name}`, sale_unit: 'box', quantity: 1, box_size: boxOptions[0] || 25, box_options: boxOptions.length ? boxOptions : [25], unit_price: '' }];
    });
    setQuery('');
    setResults([]);
  };

  const total = items.reduce((sum, item) => sum + Number(item.quantity || 0) * Number(item.unit_price || 0), 0) + Number(customerTransport || 0);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (items.length === 0 || items.some(item => item.quantity < 1 || !validateMoneyInput(item.unit_price)) || !validateMoneyInput(customerTransport || '0')) {
      setValidationError('请填写非负、最多两位小数的金额，并确保数量大于 0');
      return;
    }
    setValidationError('');
    await onSubmit({
      items: items.map(item => ({ cigar_id: item.cigar_id, sale_unit: item.sale_unit, quantity: item.sale_unit === 'box' ? item.quantity * item.box_size : item.quantity, sale_quantity: item.sale_unit === 'box' ? item.quantity : undefined, box_size: item.sale_unit === 'box' ? item.box_size : undefined, unit_price: item.unit_price })),
      customer_name: customerName.trim(),
      customer_transport_fee_cny: customerTransport || '0',
      note: note.trim(),
    });
    setCustomerName(''); setCustomerTransport('0'); setNote(''); setItems([]);
  };

  return (
    <form data-guide="sales-orders" onSubmit={submit} className="rounded-md border border-border bg-white shadow-sm">
      <div className="flex items-center justify-between border-b border-border px-5 py-4">
        <div><h2 className="font-display text-lg font-semibold">新建销售单</h2><p className="mt-0.5 text-xs text-muted">先保存草稿，确认时才会预留库存。</p></div>
        <span className="text-[11px] uppercase tracking-wider text-accent">Draft</span>
      </div>
      <div className="space-y-4 p-5">
        {(error || validationError) && <div className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error || validationError}</div>}
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="text-xs font-medium text-muted">客户名称<input value={customerName} onChange={e => setCustomerName(e.target.value)} placeholder="散客或客户姓名" className="mt-1.5 w-full rounded border border-border px-3 py-2 text-sm outline-none focus:border-gold" /></label>
          <label className="text-xs font-medium text-muted">客户人肉费（CNY）<input type="number" min="0" step="0.01" value={customerTransport} onChange={e => setCustomerTransport(e.target.value)} className="mt-1.5 w-full rounded border border-border px-3 py-2 text-sm outline-none focus:border-gold" /></label>
        </div>
        <div className="relative">
          <label className="text-xs font-medium text-muted">添加雪茄</label>
          <div className="relative mt-1.5"><Search className="absolute left-3 top-2.5 h-4 w-4 text-muted" /><input value={query} onChange={e => setQuery(e.target.value)} placeholder="输入中文名、英文名或品牌搜索" className="w-full rounded border border-border py-2 pl-9 pr-3 text-sm outline-none focus:border-gold" /></div>
          {searching && <p className="mt-1 text-xs text-muted">搜索中…</p>}
          {searchError && <p className="mt-1 text-xs text-red-700">{searchError}</p>}
          {results.length > 0 && <div className="absolute z-20 mt-1 max-h-64 w-[calc(100%-2.5rem)] overflow-auto rounded border border-border bg-white shadow-lg">{results.map(result => <button type="button" key={result.id} onClick={() => addItem(result)} className="flex w-full items-center justify-between border-b border-border px-3 py-2 text-left text-sm last:border-0 hover:bg-accent-light"><span><b>{result.brand}</b> · {result.name}<small className="ml-2 text-xs text-muted">库存 {result.stock_qty} 支</small></span><Plus className="h-4 w-4 text-accent" /></button>)}</div>}
        </div>
        {items.length > 0 && <div className="overflow-x-auto rounded border border-border"><div className="grid min-w-[520px] grid-cols-[minmax(0,1fr)_110px_80px_120px_32px] gap-2 border-b border-border bg-[#F5EFE8] px-3 py-2 text-[11px] font-semibold text-muted"><span>商品</span><span>单位</span><span>数量</span><span>单价 CNY</span><span /></div>{items.map((item, index) => <div key={item.cigar_id} className="grid min-w-[520px] grid-cols-[minmax(0,1fr)_110px_80px_120px_32px] items-center gap-2 border-b border-border px-3 py-2 last:border-0"><span className="truncate text-sm">{item.cigar_name}<small className="ml-1 text-[10px] text-muted">{item.sale_unit === 'box' ? `每盒 ${item.box_size} 支` : ''}</small></span><div className="flex gap-1"><select value={item.sale_unit} onChange={e => setItems(current => current.map((entry, i) => i === index ? { ...entry, sale_unit: e.target.value as 'stick' | 'box' } : entry))} className="rounded border border-border px-1 py-1.5 text-xs"><option value="box">整盒</option><option value="stick">单支</option></select>{item.sale_unit === 'box' && item.box_options.length > 1 && <select aria-label="选择包装支数" value={item.box_size} onChange={e => setItems(current => current.map((entry, i) => i === index ? { ...entry, box_size: Number(e.target.value) } : entry))} className="w-16 rounded border border-border px-1 py-1.5 text-xs">{item.box_options.map(size => <option key={size} value={size}>{size}支</option>)}</select>}</div><input type="number" min="1" value={item.quantity} onChange={e => setItems(current => current.map((entry, i) => i === index ? { ...entry, quantity: Number(e.target.value) } : entry))} className="rounded border border-border px-2 py-1.5 text-sm" /><input type="number" min="0" step="0.01" value={item.unit_price} onChange={e => setItems(current => current.map((entry, i) => i === index ? { ...entry, unit_price: e.target.value } : entry))} className="rounded border border-border px-2 py-1.5 text-sm" /><button type="button" title="移除商品" onClick={() => setItems(current => current.filter((_, i) => i !== index))} className="text-muted hover:text-accent"><Trash2 className="h-4 w-4" /></button></div>)}</div>}
        <label className="block text-xs font-medium text-muted">备注<textarea value={note} onChange={e => setNote(e.target.value)} rows={2} placeholder="可选" className="mt-1.5 w-full resize-none rounded border border-border px-3 py-2 text-sm outline-none focus:border-gold" /></label>
        <div className="flex flex-col gap-3 border-t border-border pt-4 sm:flex-row sm:items-center sm:justify-between"><span className="text-xs text-muted">{items.length ? `${items.length} 个商品 · ${today()}` : '请至少添加一款雪茄'}<strong className="ml-2 font-mono text-sm text-fg">合计 {formatCny(total)}</strong></span><button disabled={busy || items.length === 0} className="rounded bg-accent px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-50">{busy ? '保存中…' : '保存草稿'}</button></div>
      </div>
    </form>
  );
}
