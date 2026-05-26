import { motion } from 'framer-motion';
import { PriceRow } from './PriceRow';
import type { CigarGroup } from '../../types';

interface PriceCardProps {
  cigar: CigarGroup;
  index: number;
  onClick: () => void;
}

function getBrandLogoUrl(brandName: string): string | null {
  const slug = brandName
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '');
  if (!slug) return null;
  return `/media/brand_logos/${slug}.jpg`;
}

export function PriceCard({ cigar, index, onClick }: PriceCardProps) {
  // 用英文品牌名查 logo，否则中文 slugify 会匹配不到文件
  const brandLogo = getBrandLogoUrl(cigar.brand_en || cigar.brand);

  return (
    <motion.div
      className="bg-white rounded-md border border-stone-100 shadow-sm overflow-hidden cursor-pointer hover:-translate-y-1 hover:shadow-lg hover:border-gold-500 transition-all duration-200"
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.04, duration: 0.3, ease: [0.4, 0, 0.2, 1] }}
      onClick={onClick}
      layout
    >
      <div className="px-4 py-2.5 bg-stone-100 border-b border-stone-100 flex items-center gap-2">
        {brandLogo && (
          <img
            src={brandLogo}
            alt={cigar.brand}
            className="w-5 h-5 object-contain rounded-sm"
            onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
          />
        )}
        <span className="text-[0.7rem] text-stone-500 uppercase tracking-widest font-semibold">
          {cigar.brand_cn || cigar.brand}
        </span>
      </div>
      <div className="p-4">
        <h3 className="text-base font-semibold text-stone-900 leading-snug mb-1">
          {cigar.name}
        </h3>
        {cigar.name_en && cigar.name_en !== cigar.name && (
          <p className="text-[0.78rem] text-stone-500 italic mb-2 font-serif">
            {cigar.name_en}
          </p>
        )}
        {cigar.image_url && (
          <img
            src={cigar.image_url}
            alt={cigar.name}
            className="w-full h-40 object-contain rounded mt-2 opacity-90 hover:opacity-100 transition-opacity bg-stone-50"
            loading="lazy"
          />
        )}
        <div className="flex flex-col gap-1 mt-3">
          {cigar.prices.map((snap, i) => (
            <PriceRow key={i} snap={snap} />
          ))}
        </div>
      </div>
    </motion.div>
  );
}
