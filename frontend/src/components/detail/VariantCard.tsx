import { motion } from 'framer-motion';
import { ExternalLink, TrendingDown, TrendingUp, Minus } from 'lucide-react';
import { usePriceFormat } from '../../hooks/usePriceFormat';
import type { Variant } from '../../types';

interface VariantCardProps {
  variant: Variant;
  index: number;
}

function formatDate(iso: string | undefined): string {
  if (!iso) return '';
  const d = new Date(iso);
  return d.toLocaleDateString('zh-CN', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function VariantCard({ variant, index }: VariantCardProps) {
  const { formatPrice } = usePriceFormat();
  const points = variant.points || [];
  const latest = points[points.length - 1];
  const minCny = points.length ? Math.min(...points.map((p) => p.price_cny ?? Infinity)) : null;
  const maxCny = points.length ? Math.max(...points.map((p) => p.price_cny ?? -Infinity)) : null;
  const recordCount = variant.record_count ?? points.length;
  const inStock = variant.in_stock ?? true;
  const priceCny = variant.current_price_cny;
  const pricePerStick = variant.price_per_stick;
  const boxSize = variant.box_size;
  const sourceLabel = variant.source_short_name || variant.source_name;

  return (
    <motion.div
      className="bg-white rounded-xl border border-border shadow-sm overflow-hidden
        hover:shadow-lg hover:border-accent transition-all duration-300"
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.06, duration: 0.35, ease: [0.4, 0, 0.2, 1] }}
    >
      {/* Header: source name + box size (prominent) + stock badge */}
      <div className="px-5 py-3.5 bg-accent-light border-b border-border flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="text-sm font-bold text-fg tracking-wide">{sourceLabel}</span>
          {boxSize != null && (
            <span className="text-lg font-extrabold text-accent font-mono tabular-nums tracking-tight">
              {boxSize}<span className="text-xs text-muted font-normal ml-0.5">支/盒</span>
            </span>
          )}
        </div>
        <span
          className={`text-[11px] font-bold px-2.5 py-1 rounded-full uppercase tracking-wider ${
            inStock
              ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
              : 'bg-red-50 text-red-600 border border-red-200'
          }`}
        >
          {inStock ? '现货' : '缺货'}
        </span>
      </div>

      {/* Scraped name — 原始爬虫品名 */}
      {variant.scraped_name && (
        <div className="px-5 py-1.5 bg-amber-50/60 border-b border-amber-100 text-xs text-amber-700">
         原始品名: <span className="font-mono text-amber-800">{variant.scraped_name}</span>
        </div>
      )}

      {/* Body: price grid */}
      <div className="p-5">
        {latest ? (
          <div className="space-y-4">
            {/* Primary: per-stick CNY + box CNY */}
            <div className="flex items-baseline gap-4">
              {pricePerStick != null && (
                <div>
                  <span className="block text-[10px] text-accent uppercase tracking-widest font-semibold mb-0.5">
                    单支
                  </span>
                  <span className="text-2xl font-bold text-accent font-mono tabular-nums">
                    ¥{pricePerStick.toLocaleString()}
                  </span>
                </div>
              )}
              {priceCny != null && (
                <div className={pricePerStick != null ? 'border-l border-border pl-4' : ''}>
                  <span className="block text-[10px] text-muted uppercase tracking-widest font-semibold mb-0.5">
                    整盒 CNY
                  </span>
                  <span className="text-xl font-bold text-fg font-mono tabular-nums">
                    ¥{priceCny.toLocaleString()}
                  </span>
                </div>
              )}
            </div>

            {/* Original currency price row */}
            {latest.price != null && (
              <div className="text-xs text-muted flex items-center gap-1">
                <span>原价</span>
                <span className="font-mono font-semibold text-muted">
                  {formatPrice(latest.price, variant.currency)}
                </span>
              </div>
            )}

            {/* Secondary stats: min/max/records (all in CNY) */}
            <div className="grid grid-cols-3 gap-2 pt-3 border-t border-border">
              <div className="text-center">
                <span className="block text-[10px] text-muted uppercase tracking-wider">最低</span>
                <span className="text-sm font-semibold text-fg">
                  {minCny != null && minCny !== Infinity ? `¥${minCny.toLocaleString()}` : '-'}
                </span>
              </div>
              <div className="text-center border-l border-border">
                <span className="block text-[10px] text-muted uppercase tracking-wider">最高</span>
                <span className="text-sm font-semibold text-fg">
                  {maxCny != null && maxCny !== -Infinity ? `¥${maxCny.toLocaleString()}` : '-'}
                </span>
              </div>
              <div className="text-center border-l border-border">
                <span className="block text-[10px] text-muted uppercase tracking-wider">记录</span>
                <span className="text-sm font-semibold text-fg">{recordCount}条</span>
              </div>
            </div>

            {/* Footer: source link + update time */}
            <div className="flex items-center justify-between pt-2">
              {variant.url && (
                <a
                  href={variant.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-xs text-accent hover:text-accent-hover font-medium transition-colors"
                  onClick={(e) => e.stopPropagation()}
                >
                  <ExternalLink className="w-3.5 h-3.5" />
                  查看来源
                </a>
              )}
              {variant.scraped_at && (
                <span className="text-[11px] text-muted">
                  更新于 {formatDate(variant.scraped_at)}
                </span>
              )}
            </div>
          </div>
        ) : (
          <p className="text-sm text-muted py-4 text-center">暂无价格数据</p>
        )}
      </div>
    </motion.div>
  );
}
