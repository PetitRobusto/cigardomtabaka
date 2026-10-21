import { useRef, useState, type FormEvent } from 'react';
import { useQuery } from '@tanstack/react-query';
import { X } from 'lucide-react';
import { apiErrorMessage, createSalesOrder, fetchPreorderSource } from '../../api';
import type { PreorderSource, SalesOrder, SalesOrderPayload } from '../../types';
import PaymentDialog from '../privnote/PaymentDialog';
import { CustomerAutocomplete, type CustomerSelection } from '../search';
import { formatCny, validateMoneyInput } from './salesState';
import { preorderItems, preorderUnitQuantity, type PreorderSelection } from './preorderState';

export default function PreorderOrderModal({ purchaseId, onClose, onCreated }: {
  purchaseId: number; onClose: () => void; onCreated: (order: SalesOrder) => void;
}) {
  const source = useQuery({ queryKey: ['preorder-source', purchaseId], queryFn: () => fetchPreorderSource(purchaseId), refetchOnWindowFocus: false });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const inFlight = useRef(false);
  const save = async (payload: SalesOrderPayload) => {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setError('');
    try { onCreated(await createSalesOrder(payload)); }
    catch (failure) { setError(apiErrorMessage(failure, '预售草稿保存失败')); }
    finally { inFlight.current = false; setBusy(false); }
  };
  return <PaymentDialog title="创建预售单" onClose={onClose} busy={busy} width="3xl">
    <header className="flex items-start justify-between gap-3 border-b border-border p-5">
      <div><h2 className="font-display text-xl font-semibold">创建预售单</h2><p className="mt-1 text-xs text-muted">来源 {source.data?.order_number || `采购单 #${purchaseId}`}</p></div>
      <button type="button" aria-label="关闭创建预售单" onClick={onClose} disabled={busy} className="rounded p-1 text-muted hover:bg-cream disabled:opacity-50"><X className="h-4 w-4" /></button>
    </header>
    {source.isLoading ? <p className="p-5 text-sm text-muted">加载商品与预售额度…</p> : source.error ? <div className="p-5"><p role="alert" className="text-sm text-accent">{apiErrorMessage(source.error, '采购商品加载失败')}</p><button className="mt-3 rounded border border-border px-3 py-2 text-xs" onClick={() => source.refetch()}>重新加载</button></div> : source.data && <PreorderForm key={JSON.stringify(source.data)} source={source.data} busy={busy} error={error} onSave={save} onClose={onClose} />}
  </PaymentDialog>;
}

function PreorderForm({ source, busy, error, onSave, onClose }: {
  source: PreorderSource; busy: boolean; error: string;
  onSave: (payload: SalesOrderPayload) => Promise<void>; onClose: () => void;
}) {
  const [customer, setCustomer] = useState<CustomerSelection>({ customerId: null, name: '' });
  const [rows, setRows] = useState<PreorderSelection[]>(() => source.items.map(() => ({ selected: false, quantity: '1', unitPrice: '' })));
  const [transport, setTransport] = useState('0');
  const [note, setNote] = useState('');
  const [validation, setValidation] = useState('');
  const update = (index: number, patch: Partial<PreorderSelection>) => setRows(current => current.map((row, i) => i === index ? { ...row, ...patch } : row));
  const total = rows.reduce((sum, row) => sum + (row.selected ? Number(row.quantity) * Number(row.unitPrice) : 0), 0) + Number(transport);
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (busy) return;
    try {
      const items = preorderItems(source, rows);
      if (!customer.name.trim()) throw new Error('请填写客户名称');
      if (!validateMoneyInput(transport)) throw new Error('请填写非负、最多两位小数的客户人肉费');
      setValidation('');
      await onSave({ items, customer_id: customer.customerId, customer_name: customer.name.trim(), customer_transport_fee_cny: transport, transport_payer: 'customer', note: note.trim() });
    } catch (failure) { setValidation(apiErrorMessage(failure)); }
  };
  return <form onSubmit={submit}>
    <fieldset disabled={busy} className="min-w-0 space-y-4 p-5">
      <p className="text-xs leading-relaxed text-muted">确认订单后可收预付款；到货后在同一销售单备货、出库。</p>
      {(error || validation) && <p role="alert" className="rounded border border-red-200 bg-red-50 p-3 text-xs text-red-700">{error || validation}</p>}
      {!source.can_create && <p role="alert" className="text-sm text-accent">这张采购单当前不能创建预售单。</p>}
      <CustomerAutocomplete value={customer} onChange={setCustomer} disabled={busy} />
      {source.items.map((item, index) => {
        const unit = item.sale_unit === 'box' ? '盒' : '支';
        const remaining = preorderUnitQuantity(item, item.remaining_quantity);
        return <section key={`${item.cigar_id}-${item.sale_unit}-${item.box_size}`} className="rounded border border-border p-3">
          <label className="flex items-start gap-2 text-sm font-semibold"><input type="checkbox" checked={rows[index].selected} disabled={!source.can_create || !remaining || busy} onChange={event => update(index, { selected: event.target.checked })} className="mt-1 h-4 w-4 shrink-0 accent-accent" /><span>{item.cigar_name}{item.sale_unit === 'box' ? ` · ${item.box_size} 支/盒` : ' · 散支'}</span></label>
          <p className="my-2 text-xs leading-relaxed text-muted">采购 {preorderUnitQuantity(item, item.purchase_quantity)} {unit} · 已确认预售 {preorderUnitQuantity(item, item.committed_quantity)} {unit} · 剩余可预售 {remaining} {unit}</p>
          <div className="grid grid-cols-2 gap-3">
            <label className="text-xs text-muted">本次预售（{unit}）<input aria-label={`${item.cigar_name} ${item.box_size || '散支'} 数量`} type="number" min="1" max={remaining} step="1" value={rows[index].quantity} disabled={!rows[index].selected} onChange={event => update(index, { quantity: event.target.value })} className="mt-1.5 w-full min-w-0 rounded border border-border px-3 py-2 text-sm text-fg disabled:bg-cream" /></label>
            <label className="text-xs text-muted">单价 CNY / {unit}<input aria-label={`${item.cigar_name} ${item.box_size || '散支'} 单价`} type="number" min="0" step="0.01" value={rows[index].unitPrice} disabled={!rows[index].selected} onChange={event => update(index, { unitPrice: event.target.value })} className="mt-1.5 w-full min-w-0 rounded border border-border px-3 py-2 text-sm text-fg disabled:bg-cream" /></label>
          </div>
        </section>;
      })}
      {!source.items.length && <p className="rounded border border-dashed border-border p-3 text-sm text-muted">采购草稿还没有可预售的商品，请先补全商品、单位与数量。</p>}
      <label className="block text-xs text-muted">客户人肉费（CNY）<input type="number" min="0" step="0.01" value={transport} onChange={event => setTransport(event.target.value)} className="mt-1.5 w-full rounded border border-border px-3 py-2 text-sm text-fg" /></label>
      <label className="block text-xs text-muted">备注<textarea value={note} onChange={event => setNote(event.target.value)} rows={2} className="mt-1.5 w-full rounded border border-border px-3 py-2 text-sm text-fg" /></label>
      <div className="flex justify-between gap-3 rounded bg-cream p-3 text-sm"><span>应收合计</span><strong className="font-mono text-accent">{Number.isFinite(total) ? formatCny(total) : '—'}</strong></div>
      <p className="text-xs text-muted">草稿不占额度；确认时重新检查累计预售数量。</p>
    </fieldset>
    <footer className="flex flex-wrap justify-end gap-2 border-t border-border p-5">
      <button type="button" disabled={busy} onClick={onClose} className="rounded border border-border px-3 py-2 text-sm disabled:opacity-50">取消</button>
      <button disabled={busy || !source.can_create || !rows.some(row => row.selected)} className="rounded bg-accent px-3 py-2 text-sm font-semibold text-white disabled:opacity-50">{busy ? '保存中…' : '保存草稿并查看'}</button>
    </footer>
  </form>;
}
