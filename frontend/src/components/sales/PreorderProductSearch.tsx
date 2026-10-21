import { useId, useRef, useState } from 'react';
import { Search } from 'lucide-react';
import type { PreorderSource } from '../../types';
import { preorderProductName, preorderUnitQuantity, type PreorderSelection } from './preorderState';

const normalize = (value: string) => value.normalize('NFKD').replace(/\p{M}/gu, '').toLocaleLowerCase();

/** Search only the source purchase's item/packaging pairs; keep results inside the native modal. */
export default function PreorderProductSearch({ source, rows, disabled, onSelect }: {
  source: PreorderSource; rows: PreorderSelection[]; disabled: boolean; onSelect: (index: number) => void;
}) {
  const id = useId();
  const input = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState<number | null>(null);
  const terms = normalize(query).trim().split(/\s+/).filter(Boolean);
  const results = source.items.map((item, index) => ({ item, index })).filter(({ item, index }) => {
    const text = normalize([item.cigar_name, item.cigar_brand, item.cigar_brand_cn, item.cigar_english_name, item.box_size || '散支'].join(' '));
    return !rows[index].selected && terms.every(term => text.includes(term));
  });
  const available = results.filter(({ item }) => preorderUnitQuantity(item, item.remaining_quantity) > 0);
  const select = (index: number) => {
    if (disabled || !source.can_create || rows[index].selected || !preorderUnitQuantity(source.items[index], source.items[index].remaining_quantity)) return;
    onSelect(index);
    setQuery(''); setOpen(false); setActive(null);
    input.current?.focus();
  };
  const expanded = open && !disabled && source.can_create;
  return <div className="relative">
    <label htmlFor={id} className="text-xs font-medium text-muted">搜索采购商品</label>
    <div className="relative mt-1.5"><Search className="absolute left-3 top-2.5 h-4 w-4 text-muted" />
      <input id={id} ref={input} role="combobox" aria-autocomplete="list" aria-expanded={expanded} aria-controls={`${id}-results`}
        aria-activedescendant={expanded && active !== null ? `${id}-item-${active}` : undefined}
        disabled={disabled || !source.can_create} autoComplete="off" placeholder="输入品牌、中文名、英文名或盒规" value={query}
        onFocus={() => setOpen(true)} onBlur={() => { setOpen(false); setActive(null); }}
        onChange={event => { setQuery(event.target.value); setOpen(true); setActive(null); }}
        onKeyDown={event => {
          if (event.nativeEvent.isComposing) return;
          if (event.key === 'Escape' && expanded) { event.preventDefault(); event.stopPropagation(); setOpen(false); setActive(null); }
          if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
            event.preventDefault(); setOpen(true);
            const current = available.findIndex(result => result.index === active);
            const next = available.length ? (current + (event.key === 'ArrowDown' ? 1 : current < 0 ? 0 : -1) + available.length) % available.length : -1;
            const index = available[next]?.index ?? null;
            setActive(index);
            if (index !== null) document.getElementById(`${id}-item-${index}`)?.scrollIntoView?.({ block: 'nearest' });
          }
          if (event.key === 'Enter') { event.preventDefault(); if (expanded && active !== null) select(active); }
        }} className="w-full rounded border border-border py-2 pl-9 pr-3 text-sm text-fg outline-none focus:border-gold disabled:bg-cream" />
    </div>
    {expanded && <div id={`${id}-results`} role="listbox" aria-label="采购商品搜索结果" className="absolute left-0 right-0 z-30 mt-1 max-h-64 overflow-y-auto overscroll-contain rounded border border-border bg-white shadow-lg">
      {results.map(({ item, index }) => {
        const remaining = preorderUnitQuantity(item, item.remaining_quantity);
        return <button id={`${id}-item-${index}`} key={index} type="button" role="option" aria-selected={active === index} disabled={!remaining}
          onMouseDown={event => event.preventDefault()} onClick={() => select(index)}
          className={`block w-full border-b border-border px-3 py-2 text-left text-sm last:border-0 hover:bg-cream disabled:opacity-50 ${active === index ? 'bg-cream' : ''}`}>
          <strong>{preorderProductName(item)} · {item.sale_unit === 'box' ? `${item.box_size} 支/盒` : '散支'}</strong>
          <small className="mt-0.5 block text-xs text-muted">{item.cigar_brand} {item.cigar_english_name} · 剩余可预售 {remaining} {item.sale_unit === 'box' ? '盒' : '支'}</small>
        </button>;
      })}
      {!results.length && <p role="status" className="p-3 text-xs text-muted">没有可添加的匹配商品，请更换关键词或检查已选商品。</p>}
    </div>}
  </div>;
}
