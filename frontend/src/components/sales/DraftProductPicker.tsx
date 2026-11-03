import { useEffect, useState } from 'react';
import { apiErrorMessage, fetchInventoryPurchases, fetchPreorderSource } from '../../api';
import type { PreorderSource, PurchaseAction } from '../../types';
import { CigarAutocomplete } from '../search';
import { catalogProduct, sourceProduct, type DraftProduct } from './salesDraftItems';

export default function DraftProductPicker({ initial, disabled, onSelect, onClose }: {
  initial?: DraftProduct; disabled: boolean; onSelect: (product: DraftProduct) => void; onClose: () => void;
}) {
  const [mode, setMode] = useState(initial?.fulfillmentType ?? 'in_stock');
  const [query, setQuery] = useState('');
  const [purchases, setPurchases] = useState<PurchaseAction[]>([]);
  const [sourceId, setSourceId] = useState(initial?.sourceId);
  const [source, setSource] = useState<PreorderSource | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    if (mode !== 'preorder') return;
    let active = true;
    const timer = window.setTimeout(async () => {
      setLoading(true); setError(''); setSource(null); setPurchases([]);
      try {
        if (sourceId) {
          const result = await fetchPreorderSource(sourceId);
          if (active) setSource(result);
        } else {
          const result = await fetchInventoryPurchases({ q: query.trim() || undefined, limit: 30 });
          if (active) setPurchases(result.results.filter(order => ['draft', 'in_transit', 'received'].includes(order.status)));
        }
      } catch (failure) { if (active) setError(apiErrorMessage(failure, '采购来源加载失败')); }
      finally { if (active) setLoading(false); }
    }, sourceId ? 0 : 200);
    return () => { active = false; window.clearTimeout(timer); };
  }, [mode, query, sourceId, retry]);
  const chooseSource = (id?: number) => { setSource(null); setError(''); setPurchases([]); setLoading(true); setSourceId(id); };
  return <section aria-label={initial ? '替换商品' : '添加商品'} className="space-y-3 rounded border border-gold/40 bg-[#FFFDFA] p-3">
    <div className="flex flex-wrap items-center justify-between gap-2">
      <strong className="text-sm">{initial ? `替换：${initial.name}` : '添加商品'}</strong>
      <button type="button" onClick={onClose} disabled={disabled} className="text-xs text-muted">关闭选择</button>
    </div>
    <div className="flex gap-2">{([['in_stock', '现货商品'], ['preorder', '采购来源预售']] as const).map(([value, label]) => <button key={value} type="button" disabled={disabled} aria-pressed={mode === value} onClick={() => setMode(value)} className={`rounded border px-3 py-2 text-xs ${mode === value ? 'border-gold bg-[#F5E8D8]' : 'border-border bg-white'}`}>{label}</button>)}</div>
    {mode === 'in_stock' ? <CigarAutocomplete disabled={disabled} stockOnly={false} searchOnFocus label="搜索并选择商品" onSelect={cigar => onSelect(catalogProduct(cigar))} /> : <>
      {sourceId ? <div className="flex flex-wrap justify-between gap-2 text-xs"><span>来源：{source?.order_number || `PO-${String(sourceId).padStart(6, '0')}`}</span><button type="button" disabled={disabled} onClick={() => chooseSource()} className="underline">更换采购来源</button></div> : <label className="block text-xs text-muted">搜索采购单<input value={query} disabled={disabled} onChange={event => { setQuery(event.target.value); setPurchases([]); }} placeholder="采购单号或供应商" className="mt-1 block w-full rounded border border-border px-3 py-2 text-sm text-fg" /></label>}
      {loading && <p role="status" className="text-xs text-muted">加载采购商品…</p>}
      {error && <div role="alert" className="text-xs text-accent">{error} <button type="button" disabled={disabled} onClick={() => setRetry(value => value + 1)} className="underline">重试</button></div>}
      {!loading && !error && !sourceId && <div className="max-h-52 overflow-y-auto">{purchases.map(order => <button key={order.id} type="button" disabled={disabled} onClick={() => chooseSource(order.id)} className="block w-full border-b border-border px-2 py-3 text-left text-xs hover:bg-cream">{order.order_number || `PO-${String(order.id).padStart(6, '0')}`} · {order.supplier_name || '未填写供应商'}{order.status === 'received' ? ' · 已到货' : ''}</button>)}{!purchases.length && <p className="text-xs text-muted">没有匹配的采购单，请更换关键词。</p>}</div>}
      {!loading && source && <div className="max-h-64 overflow-y-auto">
        {source.items.map((item, index) => <button key={index} type="button" disabled={disabled || item.remaining_quantity <= 0 || (!source.can_create && source.status !== 'received')} onClick={() => onSelect(sourceProduct(source, item))} className="block w-full border-b border-border px-2 py-3 text-left text-xs hover:bg-cream disabled:opacity-50">
          <strong>{item.cigar_name} · {item.sale_unit === 'box' ? `${item.box_size} 支/盒` : '散支'}</strong>
          <span className="mt-1 block text-muted">采购 {item.purchase_quantity / (item.box_size || 1)} {item.sale_unit === 'box' ? '盒' : '支'} · 当前剩余额度 {item.remaining_quantity / (item.box_size || 1)} {item.sale_unit === 'box' ? '盒' : '支'}</span>
        </button>)}
        {!source.items.length && <p className="text-xs text-muted">这张采购单暂无有效商品及包装。</p>}
        {!source.can_create && source.status !== 'received' && <p role="alert" className="text-xs text-accent">这张采购单当前不能用于预售。</p>}
      </div>}
      <p className="text-xs text-muted">草稿不占预售额度；同一来源的数量合计超过当前剩余额度时将无法确认，确认订单时重新校验。</p>
    </>}
    {initial && <p className="text-xs text-muted">更换商品或包装后，数量从 1 开始，售价需重新填写。</p>}
  </section>;
}
