import { useEffect, useState } from 'react';
import { searchCigars } from '../../api';
import type { SearchCigarResult } from '../../types';
import type { Day1InventoryInput } from '../../features/day1/day1State';
import { inventoryLineTotal } from '../../features/day1/day1State';

interface Props { inventory: Day1InventoryInput[]; onChange: (inventory: Day1InventoryInput[]) => void; readOnly?: boolean }

export default function Day1InventoryStep({ inventory, onChange, readOnly = false }: Props) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchCigarResult[]>([]);
  useEffect(() => {
    if (!query.trim() || readOnly) { setResults([]); return; }
    const timer = window.setTimeout(() => { searchCigars(query, false).then(setResults).catch(() => setResults([])); }, 220);
    return () => window.clearTimeout(timer);
  }, [query, readOnly]);
  const add = (cigar: SearchCigarResult) => {
    const boxSize = cigar.box_options[0]?.box_size || cigar.batches[0]?.box_size || 1;
    onChange([...inventory, { cigar_id: cigar.id, cigar_name: cigar.name, box_size: boxSize, box_quantity: 0, loose_sticks: 0, unit_cost_cny: String(cigar.batches[0]?.unit_cost_cny || '') }]);
    setQuery(''); setResults([]);
  };
  const update = (index: number, key: keyof Day1InventoryInput, value: string) => onChange(inventory.map((line, i) => i === index ? { ...line, [key]: key === 'cigar_name' ? value : (key === 'unit_cost_cny' ? value : Number(value)) } : line));
  const totals = inventory.reduce((result, line) => { const lineTotal = inventoryLineTotal(line); return { sticks: result.sticks + lineTotal.sticks, cost: (Number(result.cost) + Number(lineTotal.cost)).toFixed(2) }; }, { sticks: 0, cost: '0.00' });
  return <section className="rounded-md border border-border bg-white p-5 shadow-sm">
    <div className="mb-5"><p className="text-[11px] font-bold uppercase tracking-[.12em] text-accent">Step 3 · Stock</p><h2 className="mt-1 font-display text-2xl font-semibold">录入期初库存</h2><p className="mt-2 text-sm text-muted">只能从已有目录中选择雪茄；库存数量和单位成本均不能为负数。</p></div>
    {!readOnly && <div className="relative mb-5"><label className="text-xs font-medium text-muted">搜索目录雪茄<input value={query} onChange={event => setQuery(event.target.value)} placeholder="输入中文名或英文名" className="mt-1 w-full rounded border border-border px-3 py-2 text-sm text-fg" /></label>{results.length > 0 && <div className="absolute left-0 right-0 top-full z-10 mt-1 overflow-hidden rounded border border-border bg-white shadow-lg">{results.slice(0, 8).map(cigar => <button key={cigar.id} type="button" onClick={() => add(cigar)} className="flex w-full items-center justify-between border-b border-border px-3 py-2 text-left text-sm last:border-0 hover:bg-cream"><span><strong>{cigar.name}</strong><small className="ml-2 text-muted">{cigar.english_name}</small></span><span className="text-xs text-muted">{cigar.batches.length} 批次</span></button>)}</div>}</div>}
    {inventory.length === 0 ? <p className="rounded bg-cream px-4 py-6 text-center text-sm text-muted">尚未添加库存，完成初始化仍可提交空库存。</p> : <div className="space-y-3">{inventory.map((line, index) => <div key={`${line.cigar_id}-${index}`} className="rounded border border-border p-3"><div className="mb-3 flex items-center justify-between gap-2"><div><p className="font-medium text-fg">{line.cigar_name || `目录雪茄 #${line.cigar_id}`}</p><p className="text-xs text-muted">cigar_id: {line.cigar_id}</p></div>{!readOnly && <button type="button" onClick={() => onChange(inventory.filter((_, i) => i !== index))} className="text-xs text-accent">移除</button>}</div><div className="grid gap-2 sm:grid-cols-4"><label className="text-xs text-muted">盒规<input disabled={readOnly} type="number" min="1" step="1" value={line.box_size} onChange={event => update(index, 'box_size', event.target.value)} className="mt-1 w-full rounded border border-border px-2 py-2 text-sm" /></label><label className="text-xs text-muted">整盒数量<input disabled={readOnly} type="number" min="0" step="1" value={line.box_quantity} onChange={event => update(index, 'box_quantity', event.target.value)} className="mt-1 w-full rounded border border-border px-2 py-2 text-sm" /></label><label className="text-xs text-muted">散支数量<input disabled={readOnly} type="number" min="0" step="1" value={line.loose_sticks} onChange={event => update(index, 'loose_sticks', event.target.value)} className="mt-1 w-full rounded border border-border px-2 py-2 text-sm" /></label><label className="text-xs text-muted">单位成本 CNY<input disabled={readOnly} type="number" min="0" step="any" value={line.unit_cost_cny} onChange={event => update(index, 'unit_cost_cny', event.target.value)} className="mt-1 w-full rounded border border-border px-2 py-2 text-sm" /></label></div></div>)}</div>}
    <div className="mt-5 flex gap-6 border-t border-border pt-4 text-sm"><span>总支数 <strong>{totals.sticks}</strong></span><span>总成本 <strong>¥ {totals.cost}</strong></span></div>
  </section>;
}
