import { TrendingUp, TrendingDown, Package } from 'lucide-react';
import { BRAND_LOGO_LOCAL } from '../../utils/priceData';
import type { RecentPriceChange, RecentRestock } from '../../types';

interface Props {
  item: RecentPriceChange | RecentRestock;
  type: 'price_change' | 'restock';
  onClick: () => void;
}

function isPriceChange(item: RecentPriceChange | RecentRestock): item is RecentPriceChange {
  return 'change_pct' in item;
}

export function RecentChangeCard({ item, type, onClick }: Props) {
  const brandLogo = BRAND_LOGO_LOCAL[item.cigar_brand] || '';

  return (
    <div
      onClick={onClick}
      className="flex-shrink-0 w-[260px] bg-white rounded-xl border border-border overflow-hidden
        cursor-pointer hover:border-accent hover:shadow-lg transition-all duration-300"
    >
      <div className="relative w-full aspect-[16/10] bg-accent-light overflow-hidden">
        {item.cigar_image_url ? (
          <img
            src={item.cigar_image_url}
            alt={item.cigar_name}
            className="w-full h-full object-contain p-2"
            loading="lazy"
            onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
          />
        ) : brandLogo ? (
          <img
            src={brandLogo}
            alt={item.cigar_brand_cn || item.cigar_brand}
            className="w-12 h-12 object-contain opacity-30 m-auto"
            onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
          />
        ) : null}

        {type === 'price_change' && isPriceChange(item) && (
          <div className={`absolute top-2 left-2 flex items-center gap-1 px-2 py-0.5 rounded-full text-[0.65rem] font-bold
            ${item.change_direction === 'up'
              ? 'bg-red-50 text-red-700 border border-red-200'
              : 'bg-emerald-50 text-emerald-700 border border-emerald-200'
            }`}>
            {item.change_direction === 'up' ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
            {item.change_direction === 'up' ? '+' : ''}{item.change_pct}%
          </div>
        )}
        {type === 'restock' && (
          <div className="absolute top-2 left-2 flex items-center gap-1 px-2 py-0.5 rounded-full
            bg-amber-50 text-amber-700 border border-amber-200 text-[0.65rem] font-bold">
            <Package className="w-3 h-3" />
            补货
          </div>
        )}
      </div>

      <div className="p-3">
        <div className="flex items-center gap-1.5 mb-1">
          {brandLogo && (
            <img src={brandLogo} alt="" className="w-3.5 h-3.5 object-contain rounded-sm" />
          )}
          <span className="text-[0.65rem] text-muted uppercase tracking-wider font-medium">
            {item.cigar_brand_cn || item.cigar_brand}
          </span>
        </div>
        <h4 className="text-[0.85rem] font-bold text-fg leading-snug line-clamp-2 mb-1">
          {item.cigar_name}
        </h4>
        <div className="flex items-center justify-between text-[0.7rem] text-muted">
          <span>{item.source_short_name || item.source_name}</span>
          {item.box_size && <span>{item.box_size}支/盒</span>}
        </div>
        {type === 'price_change' && isPriceChange(item) && (
          <div className="mt-1.5 flex items-baseline gap-2 text-[0.75rem]">
            <span className="text-muted line-through">¥{item.old_price_cny?.toLocaleString() || '—'}</span>
            <span className={`font-bold font-mono ${item.change_direction === 'up' ? 'text-red-600' : 'text-emerald-600'}`}>
              ¥{item.new_price_cny?.toLocaleString() || '—'}
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
