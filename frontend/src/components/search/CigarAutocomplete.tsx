import { useEffect, useState, type ReactNode } from 'react';
import { Plus, Search } from 'lucide-react';
import { searchCigars } from '../../api';
import type { SearchCigarResult } from '../../types';
import { cigarSearchDisplayName, cigarSearchReleaseLabel } from '../../utils/cigarSearchDisplay';

interface CigarAutocompleteProps {
  onSelect: (cigar: SearchCigarResult) => boolean | void | Promise<boolean | void>;
  stockOnly?: boolean;
  searchOnFocus?: boolean;
  label?: string;
  placeholder?: string;
  dataGuide?: string;
  disabled?: boolean;
  limit?: number;
  resultDetail?: (cigar: SearchCigarResult) => ReactNode;
  search?: (query: string, stockOnly: boolean) => Promise<SearchCigarResult[]>;
}

function defaultDetail(cigar: SearchCigarResult): ReactNode {
  const boxes = cigar.box_options.map(option => `${option.box_size}支×${option.available_boxes}盒`).join('、');
  return `库存 ${cigar.stock_qty} 支${boxes ? ` · 整盒 ${boxes}` : ''}`;
}

export function CigarAutocompleteResult({ cigar, detail }: { cigar: SearchCigarResult; detail?: ReactNode }) {
  return <><span><span className="flex flex-wrap items-center gap-2"><strong>{cigarSearchDisplayName(cigar)}</strong><small className="rounded bg-cream px-1.5 py-0.5 text-[10px] font-semibold text-accent">{cigarSearchReleaseLabel(cigar)}</small></span><small className="mt-0.5 block text-xs text-muted">{cigar.brand} {cigar.english_name} · {detail ?? defaultDetail(cigar)}</small></span><Plus className="h-4 w-4 shrink-0 text-accent" /></>;
}

export default function CigarAutocomplete({
  onSelect,
  stockOnly = false,
  searchOnFocus = false,
  label = '搜索目录雪茄',
  placeholder = '输入品牌、中文名或英文名',
  dataGuide,
  disabled = false,
  limit = 20,
  resultDetail,
  search = searchCigars,
}: CigarAutocompleteProps) {
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);
  const [results, setResults] = useState<SearchCigarResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState('');
  const [selecting, setSelecting] = useState(false);

  useEffect(() => {
    const value = query.trim();
    if (!open || disabled || (!value && !searchOnFocus)) return undefined;
    let active = true;
    const timer = window.setTimeout(() => {
      setSearching(true);
      setSearchError('');
      search(value, stockOnly).then(nextResults => {
        if (active) setResults(nextResults.slice(0, limit));
      }).catch(() => {
        if (active) {
          setResults([]);
          setSearchError('雪茄搜索失败，请稍后重试');
        }
      }).finally(() => {
        if (active) setSearching(false);
      });
    }, value ? 220 : 0);
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [disabled, limit, open, query, search, searchOnFocus, stockOnly]);

  const select = async (cigar: SearchCigarResult) => {
    setSelecting(true);
    try {
      const accepted = await onSelect(cigar);
      if (accepted !== false) {
        setQuery('');
        setResults([]);
        setOpen(false);
      }
    } finally {
      setSelecting(false);
    }
  };

  const busy = disabled || selecting;
  return <div className="relative">
    <label className="text-xs font-medium text-muted">{label}</label>
    <div className="relative mt-1.5"><Search className="absolute left-3 top-2.5 h-4 w-4 text-muted" /><input data-guide={dataGuide} disabled={busy} value={query} onFocus={() => setOpen(true)} onBlur={() => setOpen(false)} onChange={event => { setQuery(event.target.value); setResults([]); setSearchError(''); setOpen(true); }} placeholder={placeholder} autoComplete="off" className="w-full rounded border border-border py-2 pl-9 pr-3 text-sm text-fg outline-none focus:border-gold disabled:bg-cream" /></div>
    {searching && <p className="mt-1 text-xs text-muted">搜索中…</p>}
    {searchError && <p className="mt-1 text-xs text-red-700">{searchError}</p>}
    {open && results.length > 0 && <div className="absolute z-20 mt-1 max-h-64 w-full overflow-auto rounded border border-border bg-white shadow-lg">{results.map(cigar => <button type="button" key={cigar.id} disabled={busy} onMouseDown={event => event.preventDefault()} onClick={() => { void select(cigar); }} className="flex w-full items-center justify-between gap-3 border-b border-border px-3 py-2 text-left text-sm last:border-0 hover:bg-accent-light disabled:opacity-50"><CigarAutocompleteResult cigar={cigar} detail={resultDetail?.(cigar)} /></button>)}</div>}
  </div>;
}
