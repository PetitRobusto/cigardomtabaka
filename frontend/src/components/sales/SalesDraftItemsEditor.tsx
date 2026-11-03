import { useEffect, useRef, useState, type FormEvent } from 'react';
import { apiErrorMessage, updateSalesOrder } from '../../api';
import type { SalesOrder } from '../../types';
import { formatCny } from './salesState';
import DraftProductPicker from './DraftProductPicker';
import DraftNavigationGuard from './DraftNavigationGuard';
import { draftGoodsCents, draftItemsPayload, draftProducts, moneyCents, type DraftProduct } from './salesDraftItems';

export default function SalesDraftItemsEditor({ order, onSaved, onCancel, onStateChange }: {
  order: SalesOrder; onSaved: (order: SalesOrder) => void; onCancel: () => void;
  onStateChange: (state: { dirty: boolean; busy: boolean }) => void;
}) {
  const [original] = useState(() => draftProducts(order));
  const [rows, setRows] = useState(original);
  const [picker, setPicker] = useState<number | 'add' | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const errorRef = useRef<HTMLParagraphElement>(null);
  const inFlight = useRef(false);
  const dirty = JSON.stringify(rows) !== JSON.stringify(original);
  const goods = draftGoodsCents(rows);
  const transport = order.transport_payer === 'company' ? 0 : moneyCents(String(order.customer_transport_fee_cny));
  const total = goods !== null && transport !== null && Number.isSafeInteger(goods + transport) ? goods + transport : null;
  useEffect(() => { onStateChange({ dirty, busy }); }, [dirty, busy, onStateChange]);
  useEffect(() => { if (error) errorRef.current?.focus(); }, [error]);
  const update = (index: number, patch: Partial<DraftProduct>) => setRows(current => current.map((row, i) => i === index ? { ...row, ...patch } : row));
  const selectProduct = (row: DraftProduct) => {
    setRows(current => picker === 'add' ? [...current, row] : current.map((item, index) => index === picker ? row : item));
    setPicker(null);
  };
  const save = async (event: FormEvent) => {
    event.preventDefault();
    if (inFlight.current || picker !== null) return;
    setError('');
    try {
      const payload = draftItemsPayload(order, rows);
      inFlight.current = true; setBusy(true);
      const saved = await updateSalesOrder(order.id, payload);
      onSaved(saved);
    } catch (failure) { setError(apiErrorMessage(failure, '草稿保存失败，请重试')); }
    finally { inFlight.current = false; setBusy(false); }
  };
  const inputClass = 'mt-1 w-full min-w-0 rounded border border-border bg-white px-2 py-2 text-sm text-fg outline-none focus:border-gold';
  return <form onSubmit={save} noValidate aria-label="编辑草稿商品" className="space-y-3">
    <DraftNavigationGuard dirty={dirty} busy={busy} />
    <p className="text-xs leading-relaxed text-muted">修改后仍是草稿，不占库存和预售额度；确认订单时才校验并预留。预售数量合计超过来源剩余额度时将无法确认。</p>
    {error && <p ref={errorRef} role="alert" tabIndex={-1} className="rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</p>}
    <fieldset disabled={busy} className="min-w-0 space-y-3">
      {rows.map((row, index) => {
        const line = draftGoodsCents([row]);
        const unit = row.saleUnit === 'box' ? '盒' : '支';
        return <section key={index} aria-label={`商品 ${index + 1}`} className="grid grid-cols-2 gap-3 rounded border border-border p-3 xl:grid-cols-[minmax(160px,2fr)_minmax(120px,1fr)_80px_100px_90px]">
          <div className="col-span-2 min-w-0 xl:col-span-1"><strong className="block break-words text-sm">{row.name}</strong>
            <p className="mt-1 text-xs text-muted">{row.fulfillmentType === 'preorder' ? `预售 · ${row.sourceNumber || (row.sourceId ? `采购单 #${row.sourceId}` : '历史预售 · 未关联采购来源')}` : '现货'}</p>
            <div className="mt-2 flex gap-4 text-xs"><button type="button" onClick={() => setPicker(index)} className="text-accent underline">替换商品</button><button type="button" onClick={() => { setRows(current => current.filter((_, i) => i !== index)); setPicker(null); }} className="text-muted">移除</button></div>
          </div>
          {row.fulfillmentType === 'preorder' ? <div className="text-xs text-muted">包装<strong className="mt-2 block font-normal text-fg">{row.saleUnit === 'box' ? `${row.boxSize} 支/盒` : '散支'}</strong><span className="mt-1 block">换包装请点「替换商品」</span></div> : <div className="min-w-0"><label className="block text-xs text-muted">销售单位<select value={row.saleUnit} onChange={event => update(index, { saleUnit: event.target.value as 'box' | 'stick', quantity: '1', unitPrice: '' })} className={inputClass}><option value="box">整盒</option><option value="stick">散支</option></select></label>{row.saleUnit === 'box' && <label className="mt-2 block text-xs text-muted">盒规（支/盒）<input inputMode="numeric" value={row.boxSize} onChange={event => update(index, { boxSize: event.target.value, unitPrice: '' })} className={inputClass} /></label>}</div>}
          <label className="block min-w-0 text-xs text-muted">数量（{unit}）<input inputMode="numeric" value={row.quantity} onChange={event => update(index, { quantity: event.target.value })} className={inputClass} /></label>
          <label className="block min-w-0 text-xs text-muted">单价（元/{unit}）<input inputMode="decimal" value={row.unitPrice} placeholder="填写售价" onChange={event => update(index, { unitPrice: event.target.value })} className={inputClass} /></label>
          <div className="min-w-0 text-xs text-muted">小计<strong className="mt-3 block break-all font-mono text-sm text-fg">{line === null ? '待填写' : formatCny(line / 100)}</strong></div>
        </section>;
      })}
      {!rows.length && <p className="rounded border border-dashed border-border p-4 text-sm text-muted">至少添加一款商品后才能保存。</p>}
      {picker !== null ? <DraftProductPicker key={picker} initial={picker === 'add' ? undefined : rows[picker]} disabled={busy} onSelect={selectProduct} onClose={() => setPicker(null)} /> : <button type="button" onClick={() => setPicker('add')} className="rounded border border-border px-3 py-2 text-sm">＋ 添加商品</button>}
    </fieldset>
    <footer className="sticky bottom-0 z-10 flex flex-wrap items-end justify-between gap-3 rounded border border-border bg-[#FFFDFA] p-3">
      <div className="space-y-1 text-xs"><p>商品金额 <strong className="font-mono">{goods === null ? '待填写' : formatCny(goods / 100)}</strong> · 客户人肉费 {formatCny((transport ?? 0) / 100)}</p><p>订单合计 <strong className="font-mono text-base">{total === null ? '待填写' : formatCny(total / 100)}</strong> <span role="status" className="text-muted">{dirty ? '未保存' : '未修改'}</span></p></div>
      <div className="flex gap-2"><button type="button" disabled={busy} onClick={onCancel} className="rounded border border-border px-3 py-2 text-sm disabled:opacity-50">放弃修改</button><button disabled={busy || !dirty || !rows.length || picker !== null} className="rounded bg-accent px-3 py-2 text-sm font-semibold text-white disabled:opacity-50">{busy ? '保存中…' : '保存草稿'}</button></div>
    </footer>
  </form>;
}
