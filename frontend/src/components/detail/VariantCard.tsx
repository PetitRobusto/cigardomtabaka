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
  const min = variant.min_price ?? (points.length ? Math.min(...points.map((p) => p.price)) : null);
  const max = variant.max_price ?? (points.length ? Math.max(...points.map((p) => p.price)) : null);
  const recordCount = variant.record_count ?? points.length;
  const inStock = variant.in_stock ?? true;
  const priceCny = variant.current_price_cny;
  const pricePerStick = variant.price_per_stick;

  return (
    <motion.div
      className="bg-white rounded-xl border border-stone-100 shadow-sm overflow-hidden
        hover:shadow-lg hover:border-gold-300 transition-all duration-300"
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.06, duration: 0.35, ease: [0.4, 0, 0.2, 1] }}
    >
      {/* Header: source name + stock badge */}
      <div className="px-5 py-3.5 bg-stone-50 border-b border-stone-100 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-sm font-bold text-stone-900 tracking-wide">{variant.source_name}</span>
          <span className="text-xs text-stone-400 font-medium">· {variant.box_label}</span>
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
          <span className="text-amber-400 mr-1">🕷</span>
          原始品名: <span className="font-mono text-amber-800">{variant.scraped_name}</span>
        </div>
      )}

      {/* Body: price grid */}
      <div className="p-5">
        {latest ? (
          <div className="space-y-4">
            {/* Primary prices: per-stick + box */}
            <div className="flex items-baseline gap-4">
              {pricePerStick != null && (
                <div>
                  <span className="block text-[10px] text-gold-600 uppercase tracking-widest font-semibold mb-0.5">
                    单支
                  </span>
                  <span className="text-2xl font-bold text-gold-500 font-serif">
                    ¥{pricePerStick.toLocaleString()}
                  </span>
                </div>
              )}
              {priceCny != null && (
                <div className={pricePerStick != null ? 'border-l border-stone-100 pl-4' : ''}>
                  <span className="block text-[10px] text-stone-400 uppercase tracking-widest font-semibold mb-0.5">
                    整盒
                  </span>
                  <span className="text-xl font-bold text-stone-900 font-serif">
                    ¥{priceCny.toLocaleString()}
                  </span>
                </div>
              )}
              {!priceCny && !pricePerStick && (
                <div>
                  <span className="block text-[10px] text-stone-400 uppercase tracking-widest font-semibold mb-0.5">
                    当前
                  </span>
                  <span className="text-2xl font-bold text-gold-500 font-serif">
                    {formatPrice(latest.price, variant.currency)}
                  </span>
                </div>
              )}
            </div>

            {/* Secondary stats: min/max/records */}
            <div className="grid grid-cols-3 gap-2 pt-3 border-t border-stone-100">
              <div className="text-center">
                <span className="block text-[10px] text-stone-400 uppercase tracking-wider">最低</span>
                <span className="text-sm font-semibold text-stone-700">{formatPrice(min, variant.currency)}</span>
              </div>
              <div className="text-center border-l border-stone-100">
                <span className="block text-[10px] text-stone-400 uppercase tracking-wider">最高</span>
                <span className="text-sm font-semibold text-stone-700">{formatPrice(max, variant.currency)}</span>
              </div>
              <div className="text-center border-l border-stone-100">
                <span className="block text-[10px] text-stone-400 uppercase tracking-wider">记录</span>
                <span className="text-sm font-semibold text-stone-700">{recordCount}条</span>
              </div>
            </div>

            {/* Footer: source link + update time */}
            <div className="flex items-center justify-between pt-2">
              {variant.url && (
                <a
                  href={variant.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-xs text-gold-600 hover:text-gold-700 font-medium transition-colors"
                  onClick={(e) => e.stopPropagation()}
                >
                  <ExternalLink className="w-3.5 h-3.5" />
                  查看来源
                </a>
              )}
              {variant.scraped_at && (
                <span className="text-[11px] text-stone-400">
                  更新于 {formatDate(variant.scraped_at)}
                </span>
              )}
            </div>
          </div>
        ) : (
          <p className="text-sm text-stone-400 py-4 text-center">暂无价格数据</p>
        )}
      </div>
    </motion.div>
  );
}
