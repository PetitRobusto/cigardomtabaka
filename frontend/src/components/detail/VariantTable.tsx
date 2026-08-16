import { useMemo } from 'react';
import { motion } from 'framer-motion';
import { ArrowRight } from 'lucide-react';
import type { Variant } from '../../types';

interface Props {
  variants: Variant[];
}

function StockBadge({ delisted, inStock }: { delisted?: boolean; inStock: boolean }) {
  if (delisted) {
    return (
      <span className="inline-flex items-center gap-1.5 text-xs text-gray-500 bg-gray-100 border border-gray-200/60 px-2.5 py-1 rounded-full">
        <span className="w-1.5 h-1.5 rounded-full border border-gray-400 relative after:absolute after:left-1/2 after:top-1/2 after:-translate-x-1/2 after:-translate-y-1/2 after:w-1 after:h-px after:bg-gray-400" />
        已下架
      </span>
    );
  }
  if (!inStock) {
    return (
      <span className="inline-flex items-center gap-1.5 text-xs text-amber-800 bg-amber-50 border border-amber-200/50 px-2.5 py-1 rounded-full">
        <span className="w-1.5 h-1.5 rounded-full border-1.5 border-amber-500 bg-transparent" />
        售罄
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-emerald-800 bg-emerald-50 border border-emerald-200/50 px-2.5 py-1 rounded-full">
      <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 shadow-[0_0_0_1px_rgba(5,150,105,0.2)]" />
      在售
    </span>
  );
}

export function VariantTable({ variants }: Props) {
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

  // Annotation helper: return a label chip for the row
  function getAnnotation(v: Variant): { label: string; colorClass: string } | null {
    if (v.delisted || v.price_per_stick == null) return null;
    if (uniquePrices <= 1) return null;
    // Best (lowest) already has gold styling, don't override with worst/closest
    if (v.price_per_stick === bestPrice) return null;
    if (v.price_per_stick === worstPrice && uniquePrices > 1)
      return { label: '最高', colorClass: 'border-red-500 text-red-700 bg-red-50' };
    if (v.price_per_stick === closestAvgPrice && uniquePrices >= 3)
      return { label: '均价', colorClass: 'border-slate-500 text-slate-700 bg-slate-50' };
    return null;
  }

  return (
    <motion.div
      className="bg-white rounded-xl border border-border shadow-sm overflow-hidden mb-8 hidden md:block"
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
    >
      <div className="px-5 py-3.5 bg-accent-light border-b border-border flex items-center justify-between">
        <h3 className="text-[0.72rem] font-bold text-fg uppercase tracking-[0.18em]">各站价格对比</h3>
        <span className="text-[0.6rem] text-muted uppercase tracking-[0.12em] font-semibold">{variants.length} 个规格</span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-[0.6rem] text-muted uppercase tracking-[0.15em] font-semibold">
              <th className="px-4 py-3 text-left font-medium">来源</th>
              <th className="px-4 py-3 text-left font-medium">包装</th>
              <th className="px-4 py-3 text-right font-medium">单支 CNY</th>
              <th className="px-4 py-3 text-right font-medium">整盒</th>
              <th className="px-4 py-3 text-center font-medium">库存</th>
              <th className="px-4 py-3 text-right font-medium">最低</th>
              <th className="px-4 py-3 text-right font-medium">最高</th>
              <th className="px-4 py-3 text-center font-medium"></th>
            </tr>
          </thead>
          <tbody>
            {variants.map((v) => {
              const inStock = v.in_stock !== false && !v.delisted;
              const isBest = bestPrice != null && v.price_per_stick === bestPrice && !v.delisted;
              const isWorst = worstPrice != null && v.price_per_stick === worstPrice && !v.delisted && uniquePrices > 1;
              const isClosestAvg = closestAvgPrice != null && v.price_per_stick === closestAvgPrice && !v.delisted && uniquePrices >= 3;
              const annotation = getAnnotation(v);
              // Border color: best(gold) > worst(red) > closest(slate) — no overlap
              const leftBorder = isBest ? 'border-l-[3px] border-l-[#B87A3A]'
                : isWorst ? 'border-l-[3px] border-l-red-400'
                : isClosestAvg ? 'border-l-[3px] border-l-slate-400'
                : '';
              const rowBg = isBest ? 'bg-gradient-to-r from-[#b87a3a]/[0.06] via-[#b87a3a]/[0.015] to-transparent hover:from-[#b87a3a]/[0.12] hover:via-[#b87a3a]/[0.03]'
                : isWorst ? 'bg-gradient-to-r from-red-50/60 to-transparent hover:from-red-100/50'
                : isClosestAvg ? 'bg-gradient-to-r from-slate-50/70 to-transparent hover:from-slate-100/50'
                : '';
              return (
                <tr
                  key={`${v.source_slug}__${v.box_size}`}
                  className={`border-b border-border last:border-b-0 transition-colors cursor-pointer group
                    hover:bg-accent/5
                    ${v.delisted ? 'opacity-45 hover:opacity-60' : ''}
                    ${leftBorder} ${rowBg}`}
                >
                  <td className={`px-4 py-3.5 font-semibold ${v.delisted ? 'text-muted' : 'text-fg'}`}>
                    {v.source_short_name || v.source_name}
                    {annotation && (
                      <span className={`ml-2 inline-flex items-center px-1.5 py-0.5 rounded text-[9px] font-bold border ${annotation.colorClass}`}>
                        {annotation.label}
                      </span>
                    )}
                    {isBest && !annotation && (
                      <span className="ml-2 inline-flex items-center px-1.5 py-0.5 rounded text-[9px] font-bold border border-[#B87A3A] text-[#B87A3A] bg-[#b87a3a]/10">
                        最低
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3.5 text-muted">{v.box_label}</td>
                  <td className="px-4 py-3.5 text-right">
                    <span className={`font-mono font-bold tabular-nums ${v.delisted ? 'text-muted line-through' : 'text-accent'}`}>
                      {isBest && (
                        <span className="inline-flex items-center justify-center w-[17px] h-[17px] rounded-full bg-[#B87A3A] text-white text-[8px] font-bold leading-none mr-1 align-middle" title="最优价格">
                          ●
                        </span>
                      )}
                      {v.price_per_stick != null ? `¥${v.price_per_stick.toLocaleString()}` : '—'}
                    </span>
                  </td>
                  <td className="px-4 py-3.5 text-right">
                    <span className="font-mono text-xs text-muted tabular-nums">
                      {v.current_price_cny != null ? `¥${v.current_price_cny.toLocaleString()}` : '—'}
                    </span>
                  </td>
                  <td className="px-4 py-3.5 text-center">
                    <StockBadge delisted={v.delisted} inStock={inStock} />
                  </td>
                  <td className="px-4 py-3.5 text-right">
                    <span className="font-mono text-[0.68rem] text-muted tabular-nums">
                      {v.min_price != null ? `¥${Math.round(v.min_price).toLocaleString()}` : '—'}
                    </span>
                  </td>
                  <td className="px-4 py-3.5 text-right">
                    <span className="font-mono text-[0.68rem] text-muted tabular-nums">
                      {v.max_price != null ? `¥${Math.round(v.max_price).toLocaleString()}` : '—'}
                    </span>
                  </td>
                  <td className="px-4 py-3.5 text-center">
                    {v.url && !v.delisted ? (
                      <a
                        href={v.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        onClick={(e) => e.stopPropagation()}
                        className="inline-flex items-center justify-center w-[22px] h-[22px] rounded-full bg-accent-light border border-border text-muted group-hover:bg-accent group-hover:border-accent group-hover:text-white transition-all duration-200"
                        title="查看来源"
                      >
                        <ArrowRight className="w-2.5 h-2.5" />
                      </a>
                    ) : (
                      <span className="inline-flex items-center justify-center w-[22px] h-[22px] rounded-full bg-transparent border border-border opacity-30">
                        <ArrowRight className="w-2.5 h-2.5 text-muted" />
                      </span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </motion.div>
  );
}
