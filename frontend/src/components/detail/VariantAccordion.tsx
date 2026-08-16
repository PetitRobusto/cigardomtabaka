import { useMemo } from 'react';
import { motion } from 'framer-motion';
import { ChevronDown } from 'lucide-react';
import type { Variant } from '../../types';

interface Props {
  variants: Variant[];
}

function StockBadgeMini({ inStock, delisted }: { inStock: boolean; delisted?: boolean }) {
  if (delisted) {
    return (
      <span className="inline-flex items-center gap-1 text-[0.6rem] text-gray-500 bg-gray-100 px-2 py-0.5 rounded-full">
        已下架
      </span>
    );
  }
  if (!inStock) {
    return (
      <span className="inline-flex items-center gap-1 text-[0.6rem] text-amber-800 bg-amber-50 px-2 py-0.5 rounded-full">
        售罄
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 text-[0.6rem] text-emerald-800 bg-emerald-50 px-2 py-0.5 rounded-full">
      在售
    </span>
  );
}

export function VariantAccordion({ variants }: Props) {
  const grouped: Record<string, Variant[]> = {};
  for (const v of variants) {
    const key = v.source_slug || v.source_name;
    if (!grouped[key]) grouped[key] = [];
    grouped[key].push(v);
  }

  const { bestPrice, worstPrice, closestAvgPrice, uniquePrices } = useMemo(() => {
    const active = variants.filter(v => !v.delisted && v.price_per_stick != null);
    if (active.length === 0) return { bestPrice: null, worstPrice: null, closestAvgPrice: null, uniquePrices: 0 };

    const prices = active.map(v => v.price_per_stick!);
    const best = Math.min(...prices);
    const worst = Math.max(...prices);
    const unique = new Set(prices).size;
    const avg = prices.reduce((a, b) => a + b, 0) / prices.length;

    let closest = prices[0];
    let closestDelta = Math.abs(prices[0] - avg);
    for (const p of prices) {
      const d = Math.abs(p - avg);
      if (d < closestDelta) { closestDelta = d; closest = p; }
    }

    return { bestPrice: best, worstPrice: worst, closestAvgPrice: closest, uniquePrices: unique };
  }, [variants]);

  if (variants.length === 0) return null;

  function getAnnotation(v: Variant): string | null {
    if (v.delisted || v.price_per_stick == null || uniquePrices <= 1) return null;
    if (v.price_per_stick === bestPrice) return '最低';
    if (v.price_per_stick === worstPrice && uniquePrices > 1) return '最高';
    if (v.price_per_stick === closestAvgPrice && uniquePrices >= 3) return '均价';
    return null;
  }

  return (
    <motion.div
      className="bg-white rounded-xl border border-border shadow-sm overflow-hidden mb-8 md:hidden"
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
    >
      <div className="px-4 py-3.5 bg-accent-light border-b border-border">
        <h3 className="text-[0.72rem] font-bold text-fg uppercase tracking-[0.18em]">各站价格</h3>
      </div>
      <div className="divide-y divide-border">
        {Object.entries(grouped).map(([source, items]) => {
          const hasInStock = items.some(v => v.in_stock !== false && !v.delisted);
          const allDelisted = items.every(v => v.delisted);
          const sourceLabel = items[0].source_short_name || items[0].source_name;
          return (
            <details key={source} className="group" open={hasInStock}>
              <summary className={`flex items-center justify-between px-4 py-3.5 cursor-pointer list-none hover:bg-accent/[0.03] transition-colors ${allDelisted ? 'opacity-50' : ''}`}>
                <div className="flex items-center gap-2.5">
                  <span className={`font-bold text-sm ${allDelisted ? 'text-muted' : 'text-fg'}`}>{sourceLabel}</span>
                  <span className="text-[0.7rem] text-muted font-normal">{items.length} 个规格</span>
                </div>
                <div className="flex items-center gap-2.5">
                  <StockBadgeMini inStock={hasInStock} delisted={allDelisted} />
                  <ChevronDown className="w-5 h-5 text-muted group-open:rotate-180 transition-transform duration-300" />
                </div>
              </summary>
              <div className="px-4 pb-3.5 space-y-2.5">
                {items.map(v => {
                  const isBest = bestPrice != null && v.price_per_stick === bestPrice && !v.delisted;
                  const isWorst = worstPrice != null && v.price_per_stick === worstPrice && !v.delisted && uniquePrices > 1;
                  const isClosestAvg = closestAvgPrice != null && v.price_per_stick === closestAvgPrice && !v.delisted && uniquePrices >= 3;
                  const tag = getAnnotation(v);
                  const leftBorder = isBest ? 'border-l-[3px] border-l-[#B87A3A]'
                    : isWorst ? 'border-l-[3px] border-l-red-400'
                    : isClosestAvg ? 'border-l-[3px] border-l-slate-400'
                    : '';
                  const rowBg = isBest ? 'bg-gradient-to-r from-[#b87a3a]/[0.06] to-transparent'
                    : isWorst ? 'bg-gradient-to-r from-red-50/60 to-transparent'
                    : isClosestAvg ? 'bg-gradient-to-r from-slate-50/70 to-transparent'
                    : 'bg-cream/50';
                  const tagStyle = isBest ? 'border-[#B87A3A] text-[#B87A3A] bg-[#b87a3a]/10'
                    : isWorst ? 'border-red-500 text-red-700 bg-red-50'
                    : isClosestAvg ? 'border-slate-500 text-slate-700 bg-slate-50'
                    : '';
                  return (
                    <div
                      key={v.box_size ?? v.box_label}
                      className={`flex items-center justify-between text-sm px-3 py-2 rounded-lg border border-border
                        ${v.delisted ? 'opacity-50' : ''}
                        ${leftBorder} ${rowBg}`}
                    >
                      <span className={`flex items-center gap-1.5 text-muted text-[0.78rem] ${v.delisted ? 'line-through' : ''}`}>
                        {isBest && (
                          <span className="inline-flex items-center justify-center w-[15px] h-[15px] rounded-full bg-[#B87A3A] text-white text-[7px] font-bold leading-none flex-shrink-0">
                            ●
                          </span>
                        )}
                        <span className="font-semibold">{v.box_label}</span>
                        {tag && (
                          <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[8px] font-bold border ${tagStyle}`}>
                            {tag}
                          </span>
                        )}
                      </span>
                      <span className={`flex items-center gap-1.5 font-mono font-bold text-[0.85rem] tabular-nums ${v.delisted ? 'text-muted line-through' : 'text-accent'}`}>
                        {v.price_per_stick != null ? `¥${v.price_per_stick.toLocaleString()}` : '—'}
                        <span className="font-normal text-[0.7rem] text-muted">/支</span>
                      </span>
                    </div>
                  );
                })}
              </div>
            </details>
          );
        })}
      </div>
    </motion.div>
  );
}
