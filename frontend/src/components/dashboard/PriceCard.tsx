import { motion } from 'framer-motion';
import { TrendingUp, TrendingDown, Minus } from 'lucide-react';
import { SourceTag } from '../shared/SourceTag';
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
  const sourceSlugs = [...new Set(cigar.sources.map(s => s.source_slug))];

  return (
    <motion.div
      className="group bg-white rounded-xl border border-stone-100 overflow-hidden cursor-pointer
        hover:border-gold-300 hover:shadow-lg transition-all duration-300"
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.03, duration: 0.35, ease: [0.4, 0, 0.2, 1] }}
      onClick={onClick}
      layout
    >
      {/* 雪茄图片区域 */}
      <div className="relative w-full aspect-[4/3] bg-stone-50 overflow-hidden">
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
              <span className="text-stone-300 text-4xl font-serif">雪茄</span>
            )}
          </div>
        )}

        {/* 在售徽章 */}
        {cigar.in_stock && (
          <div className="absolute top-2.5 right-2.5 flex items-center gap-1.5
            bg-stone-900/90 backdrop-blur-sm text-white text-[0.65rem] font-semibold
            px-2.5 py-1 rounded-full">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
            在售
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
          <span className="text-[0.7rem] text-stone-400 uppercase tracking-wider font-medium">
            {cigar.cigar_brand_cn || cigar.cigar_brand}
          </span>
        </div>

        {/* 品名 */}
        <h3 className="text-[0.95rem] font-bold text-stone-900 leading-snug mb-0.5 line-clamp-2 min-h-[2.4em]">
          {cigar.cigar_name}
        </h3>
        {cigar.cigar_name_en && cigar.cigar_name_en !== cigar.cigar_name && (
          <p className="text-[0.72rem] text-stone-400 italic mb-2.5 font-serif line-clamp-1">
            {cigar.cigar_name_en}
          </p>
        )}

        {/* 均价/支 (RMB) */}
        <div className="flex items-baseline gap-1 mb-2.5">
          <span className="text-[0.7rem] text-stone-400">均价/支</span>
          {cigar.avg_per_stick_cny != null ? (
            <span className="text-xl font-bold text-gold-500 font-serif tracking-tight">
              ¥{cigar.avg_per_stick_cny.toLocaleString()}
            </span>
          ) : (
            <span className="text-sm font-medium text-stone-400">暂无报价</span>
          )}
        </div>

        {/* 来源标签 */}
        <div className="flex flex-wrap gap-1">
          {sourceSlugs.map((slug) => (
            <SourceTag key={slug} slug={slug} shortName={slugNameMap[slug]} />
          ))}
        </div>
      </div>
    </motion.div>
  );
}
