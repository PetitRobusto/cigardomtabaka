import { motion } from 'framer-motion';
import { usePriceFormat } from '../../hooks/usePriceFormat';
import type { Variant } from '../../types';

const COLORS = [
  '#8B6914', '#c0392b', '#2c3e50', '#27ae60', '#8e44ad',
  '#e67e22', '#2980b9', '#16a085', '#d35400', '#7f8c8d',
  '#1abc9c', '#9b59b6', '#f39c12', '#e74c3c', '#34495e',
];

interface VariantCardProps {
  variant: Variant;
  index: number;
}

export function VariantCard({ variant, index }: VariantCardProps) {
  const { formatPrice } = usePriceFormat();
  const points = variant.points || [];
  const latest = points[points.length - 1];
  // Prefer API-computed aggregates, fall back to client-side computation
  const min = variant.min_price ?? (points.length ? Math.min(...points.map((p) => p.price)) : null);
  const max = variant.max_price ?? (points.length ? Math.max(...points.map((p) => p.price)) : null);
  const recordCount = variant.record_count ?? points.length;
  const color = COLORS[index % COLORS.length];

  return (
    <motion.div
      className="bg-white rounded-md border border-[#E0E0E0] shadow-sm overflow-hidden hover:shadow-md hover:border-[#D2B48C] transition-all duration-200"
      style={{ borderLeftWidth: 4, borderLeftColor: color }}
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.05, duration: 0.3, ease: [0.4, 0, 0.2, 1] }}
    >
      {/* Header: source name left, packaging badge right */}
      <div className="px-4 py-3 bg-stone-100 border-b border-stone-100 flex items-center justify-between">
        <span className="text-sm font-semibold text-stone-900">{variant.source_name}</span>
        <span className="text-xs font-semibold text-gold-600 px-2 py-0.5 bg-gold-50 rounded border border-gold-200">
          {variant.box_label}
        </span>
      </div>

      {/* Body: price grid */}
      <div className="p-4">
        {latest ? (
          <div className="grid grid-cols-2 gap-3 mb-3">
            {/* Left column: current + lowest */}
            <div>
              <span className="block text-xs text-stone-500 uppercase tracking-wider mb-0.5">当前</span>
              <span className="text-lg font-bold text-[#D4AF37] font-serif">{formatPrice(latest.price, variant.currency)}</span>
            </div>
            <div>
              <span className="block text-xs text-stone-500 uppercase tracking-wider mb-0.5">最低</span>
              <span className="text-base font-semibold text-stone-900 font-serif">{formatPrice(min, variant.currency)}</span>
            </div>
            {/* Right column: highest + record count */}
            <div>
              <span className="block text-xs text-stone-500 uppercase tracking-wider mb-0.5">最高</span>
              <span className="text-base font-semibold text-stone-900 font-serif">{formatPrice(max, variant.currency)}</span>
            </div>
            <div>
              <span className="block text-xs text-stone-500 uppercase tracking-wider mb-0.5">记录</span>
              <span className="text-base font-semibold text-stone-900">{recordCount}条</span>
            </div>
          </div>
        ) : (
          <p className="text-sm text-stone-500 py-2">暂无价格数据</p>
        )}

        {/* Unified view source button */}
        {variant.url && (
          <a
            href={variant.url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 text-sm text-gold-600 hover:text-gold-700 transition-colors mt-1"
            onClick={(e) => e.stopPropagation()}
          >
            🔗 查看来源 →
          </a>
        )}
      </div>
    </motion.div>
  );
}
