import { useState, type FormEvent } from 'react';
import { Trash2, X } from 'lucide-react';
import type { SalesOrderPayload, SearchCigarResult } from '../../types';
import { CigarAutocomplete, CustomerAutocomplete, type CustomerSelection } from '../search';
import { cigarSearchDisplayName } from '../../utils/cigarSearchDisplay';
import { formatCny, transportPayerChange, transportSummary, validateMoneyInput, type TransportPayer } from './salesState';

interface DraftItem {
  cigar_id: number;
  cigar_name: string;
  sale_unit: 'stick' | 'box';
  quantity: number;
  box_size: number;
  box_options: number[];
  unit_price: string;
  available_sticks: number;
}

interface Props {
  onSubmit: (payload: SalesOrderPayload) => Promise<void>;
  busy?: boolean;
  error?: string;
  onCancel?: () => void;
}

const today = () => {
  const date = new Date();
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
};

export default function SalesOrderForm({ onSubmit, busy = false, error, onCancel }: Props) {
  const [customer, setCustomer] = useState<CustomerSelection>({ customerId: null, name: '' });
  const [transportPayer, setTransportPayer] = useState<TransportPayer>('customer');
  const [customerTransport, setCustomerTransport] = useState('0');
  const [note, setNote] = useState('');
  const [validationError, setValidationError] = useState('');
  const [items, setItems] = useState<DraftItem[]>([]);

  const addItem = (cigar: SearchCigarResult) => {
    setItems(current => {
      const existing = current.find(item => item.cigar_id === cigar.id);
      if (existing) return current.map(item => item.cigar_id === cigar.id ? { ...item, quantity: item.quantity + 1 } : item);
      const boxOptions = cigar.box_options.map(option => option.box_size).filter(Boolean);
      return [...current, {
        cigar_id: cigar.id,
        cigar_name: cigarSearchDisplayName(cigar),
        sale_unit: boxOptions.length ? 'box' : 'stick',
        quantity: 1,
        box_size: boxOptions[0] || 1,
        box_options: boxOptions.length ? boxOptions : [1],
        unit_price: '',
        available_sticks: cigar.available_sticks,
      }];
    });
  };

  const goodsAmount = items.reduce((sum, item) => sum + Number(item.quantity || 0) * Number(item.unit_price || 0), 0);
  const summary = transportSummary(transportPayer, goodsAmount, Number(customerTransport || 0));

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const transport = transportPayer === 'company' ? '0' : customerTransport || '0';
    if (items.length === 0 || items.some(item => item.quantity < 1 || !validateMoneyInput(item.unit_price)) || !validateMoneyInput(transport)) {
      setValidationError('请填写非负、最多两位小数的金额，并确保数量大于 0');
      return;
    }
    setValidationError('');
    await onSubmit({
      items: items.map(item => ({
        cigar_id: item.cigar_id,
        sale_unit: item.sale_unit,
        quantity: item.sale_unit === 'box' ? item.quantity * item.box_size : item.quantity,
        sale_quantity: item.sale_unit === 'box' ? item.quantity : undefined,
        box_size: item.sale_unit === 'box' ? item.box_size : undefined,
        unit_price: item.unit_price,
      })),
      customer_id: customer.customerId,
      customer_name: customer.name.trim(),
      customer_transport_fee_cny: transport,
      transport_payer: transportPayer,
      note: note.trim(),
    });
    setCustomer({ customerId: null, name: '' });
    setCustomerTransport('0');
    setTransportPayer('customer');
    setNote('');
    setItems([]);
  };

  return (
    <form data-guide="sales-orders" onSubmit={submit} className="rounded-md border border-border bg-white shadow-sm">
      <div className="flex items-center justify-between border-b border-border px-5 py-4">
        <div><h2 className="font-display text-lg font-semibold">新建销售单</h2><p className="mt-0.5 text-xs text-muted">先保存草稿，确认时才会预留库存。</p></div>
        <div className="flex items-center gap-2"><span className="text-[11px] uppercase tracking-wider text-accent">Draft</span>{onCancel && <button type="button" aria-label="收起新建销售单" onClick={onCancel} className="rounded p-1 text-muted hover:bg-cream hover:text-accent"><X className="h-4 w-4" /></button>}</div>
      </div>
      <div className="space-y-4 p-5">
        {(error || validationError) && <div className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error || validationError}</div>}
        <div className="grid gap-3 sm:grid-cols-2">
          <CustomerAutocomplete value={customer} onChange={setCustomer} dataGuide="sales-order-customer" />
          <fieldset data-guide="sales-order-transport-payer" className="text-xs font-medium text-muted"><legend>人肉费承担方</legend><div className="mt-1.5 flex gap-2"><label className="inline-flex items-center gap-1 rounded border border-border px-2 py-2"><input type="radio" name="transport-payer" value="customer" checked={transportPayer === 'customer'} onChange={() => setTransportPayer('customer')} />客户</label><label className="inline-flex items-center gap-1 rounded border border-border px-2 py-2"><input type="radio" name="transport-payer" value="company" checked={transportPayer === 'company'} onChange={() => { const change = transportPayerChange(customerTransport, 'company'); setTransportPayer(change.payer); setCustomerTransport(change.fee); }} />公司</label></div></fieldset>
        </div>
        <label className="block text-xs font-medium text-muted">客户人肉费（CNY）<input data-guide="sales-order-transport-fee" type="number" min="0" step="0.01" value={transportPayer === 'company' ? '0' : customerTransport} disabled={transportPayer === 'company'} onChange={event => setCustomerTransport(event.target.value)} className="mt-1.5 w-full rounded border border-border px-3 py-2 text-sm outline-none focus:border-gold disabled:cursor-not-allowed disabled:bg-[#f5f1ec]" /></label>
        <CigarAutocomplete label="添加雪茄" dataGuide="sales-order-item-search" stockOnly searchOnFocus disabled={busy} onSelect={addItem} />
        {items.length > 0 && <div className="overflow-x-auto rounded border border-border"><div className="grid min-w-[520px] grid-cols-[minmax(0,1fr)_110px_80px_120px_32px] gap-2 border-b border-border bg-[#F5EFE8] px-3 py-2 text-[11px] font-semibold text-muted"><span>商品</span><span>单位</span><span>数量</span><span>单价 CNY</span><span /></div>{items.map((item, index) => <div key={item.cigar_id} className="grid min-w-[520px] grid-cols-[minmax(0,1fr)_110px_80px_120px_32px] items-center gap-2 border-b border-border px-3 py-2 last:border-0"><span className="truncate text-sm">{item.cigar_name}<small className="ml-1 block text-[10px] text-muted">可售 {item.available_sticks} 支</small></span><div data-guide="sales-order-item-unit" className="flex gap-1"><select aria-label="销售单位" value={item.sale_unit} onChange={event => setItems(current => current.map((entry, i) => i === index ? { ...entry, sale_unit: event.target.value as 'stick' | 'box' } : entry))} className="rounded border border-border px-1 py-1.5 text-xs"><option value="box">整盒</option><option value="stick">单支</option></select>{item.sale_unit === 'box' && item.box_options.length > 0 && <select aria-label="选择包装支数" value={item.box_size} onChange={event => setItems(current => current.map((entry, i) => i === index ? { ...entry, box_size: Number(event.target.value) } : entry))} className="w-16 rounded border border-border px-1 py-1.5 text-xs">{item.box_options.map(size => <option key={size} value={size}>{size}支</option>)}</select>}</div><input data-guide="sales-order-item-quantity" type="number" min="1" value={item.quantity} onChange={event => setItems(current => current.map((entry, i) => i === index ? { ...entry, quantity: Number(event.target.value) } : entry))} className="rounded border border-border px-2 py-1.5 text-sm" /><input data-guide="sales-order-item-price" type="number" min="0" step="0.01" value={item.unit_price} onChange={event => setItems(current => current.map((entry, i) => i === index ? { ...entry, unit_price: event.target.value } : entry))} className="rounded border border-border px-2 py-1.5 text-sm" /><button type="button" title="移除商品" onClick={() => setItems(current => current.filter((_, i) => i !== index))} className="text-muted hover:text-accent"><Trash2 className="h-4 w-4" /></button></div>)}</div>}
        <label className="block text-xs font-medium text-muted">备注<textarea data-guide="sales-order-note" value={note} onChange={event => setNote(event.target.value)} rows={2} placeholder="可选" className="mt-1.5 w-full resize-none rounded border border-border px-3 py-2 text-sm outline-none focus:border-gold" /></label>
        <div className="grid grid-cols-3 gap-2 rounded border border-border bg-[#FFFDFA] p-3 text-xs"><div><span className="block text-muted">商品金额</span><strong className="mt-1 block font-mono">{formatCny(summary.goodsAmount)}</strong></div><div><span className="block text-muted">客户人肉费</span><strong className="mt-1 block font-mono">{formatCny(summary.customerTransport)}</strong></div><div><span className="block text-muted">应收</span><strong className="mt-1 block font-mono text-accent">{formatCny(summary.amountDue)}</strong></div></div>
        <div className="flex flex-col gap-3 border-t border-border pt-4 sm:flex-row sm:items-center sm:justify-between"><span className="text-xs text-muted">{items.length ? `${items.length} 个商品 · ${today()}` : '请至少添加一款雪茄'}</span><button data-guide="sales-order-save" disabled={busy || items.length === 0} className="rounded bg-accent px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-50">{busy ? '保存中…' : '保存草稿'}</button></div>
      </div>
    </form>
  );
}
