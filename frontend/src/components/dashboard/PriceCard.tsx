import { motion } from 'framer-motion';
import { BRAND_LOGO_LOCAL } from '../../utils/priceData';
import type { CigarListItem } from '../../types';

interface PriceCardProps {
  cigar: CigarListItem;
  index: number;
  onClick: () => void;
}

export function PriceCard({ cigar, index, onClick }: PriceCardProps) {
  const brandLogo = BRAND_LOGO_LOCAL[cigar.cigar_brand] || '';
  // Build slug→short_name map from source entries
  const slugNameMap: Record<string, string> = {};
  cigar.sources.forEach(s => {
    slugNameMap[s.source_slug] = s.source_short_name || s.source_name;
  });

  return (
    <motion.div
      className={`group bg-white rounded-xl border border-border overflow-hidden cursor-pointer
        hover:border-accent hover:shadow-lg transition-all duration-300
        ${!cigar.in_stock ? 'opacity-60' : ''}`}
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.03, duration: 0.35, ease: [0.4, 0, 0.2, 1] }}
      onClick={onClick}
      layout
    >
      {/* 雪茄图片区域 */}
      <div className="relative w-full aspect-[4/3] bg-accent-light overflow-hidden">
        {cigar.cigar_image_url ? (
          <img
            src={cigar.cigar_image_url}
            alt={cigar.cigar_name}
            className="w-full h-full object-contain p-3 group-hover:scale-105 transition-transform duration-500"
            loading="lazy"
            onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center">
            {brandLogo ? (
              <img
                src={brandLogo}
                alt={cigar.cigar_brand_cn || cigar.cigar_brand}
                className="w-16 h-16 object-contain opacity-30"
                onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
              />
            ) : (
              <span className="text-muted text-4xl font-display">雪茄</span>
            )}
          </div>
        )}

        {/* 特别款标识 */}
        {cigar.release_type_cn && (
          <div className="absolute top-2.5 left-2.5
            bg-amber-100 text-amber-800 border border-amber-300 text-[0.6rem] font-bold
            px-2 py-0.5 rounded-full uppercase tracking-wide">
            {cigar.release_type_cn}
          </div>
        )}

        {/* 库存状态徽章 */}
        {cigar.in_stock ? (
          <div className="absolute top-2.5 right-2.5 flex items-center gap-1.5
            bg-emerald-50 text-emerald-700 border border-emerald-200 text-[0.65rem] font-semibold
            px-2.5 py-1 rounded-full">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
            在售
          </div>
        ) : (
          <div className="absolute top-2.5 right-2.5 flex items-center gap-1.5
            bg-red-50 text-red-600 border border-red-200 text-[0.65rem] font-semibold
            px-2.5 py-1 rounded-full">
            缺货
          </div>
        )}
      </div>

      {/* 信息区域 */}
      <div className="p-3.5">
        {/* 品牌行 */}
        <div className="flex items-center gap-1.5 mb-1.5">
          {brandLogo && (
            <img
              src={brandLogo}
              alt={cigar.cigar_brand_cn || cigar.cigar_brand}
              className="w-4 h-4 object-contain rounded-sm"
              onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
            />
          )}
          <span className="text-[0.7rem] text-muted uppercase tracking-wider font-medium">
            {cigar.cigar_brand_cn || cigar.cigar_brand}
          </span>
        </div>

        {/* 品名 */}
        <h3 className="text-[0.95rem] font-bold text-fg leading-snug mb-0.5 line-clamp-2 min-h-[2.4em]">
          {cigar.cigar_name || `${cigar.cigar_brand_cn || cigar.cigar_brand} #${cigar.cigar_id}`}
        </h3>
        {cigar.cigar_name_en && cigar.cigar_name_en !== cigar.cigar_name && (
          <p className="text-[0.72rem] text-muted italic mb-2.5 font-display line-clamp-1">
            {cigar.cigar_name_en}
          </p>
        )}

        {/* 均价/支 (RMB) */}
        <div className="flex items-baseline gap-1 mb-2.5">
          <span className="text-[0.7rem] text-muted">均价/支</span>
          {cigar.avg_per_stick_cny != null ? (
            <span className={`text-xl font-bold font-mono tracking-tight tabular-nums
              ${cigar.in_stock ? 'text-accent' : 'text-muted line-through'}`}>
              ¥{cigar.avg_per_stick_cny.toLocaleString()}
            </span>
          ) : (
            <span className="text-sm font-medium text-muted">暂无报价</span>
          )}
        </div>

        {/* 来源计数 — 只计算在售的唯一网站 */}
        <div className="flex items-center gap-1.5 text-[0.7rem] text-muted">
          <span className="font-semibold text-accent">{new Set(cigar.sources.filter(s => s.in_stock).map(s => s.source_slug)).size}</span>
          <span>个网站有售</span>
          {cigar.sources.some(s => s.original_price) && (
            <span className="ml-1 px-1.5 py-0.5 rounded bg-amber-100 text-amber-700 font-bold text-[0.6rem] border border-amber-300">
              折
            </span>
          )}
        </div>
      </div>
    </motion.div>
  );
}
