import { motion } from 'framer-motion';
import type { BrandInfo } from '../../types';

interface BrandTabsProps {
  brands: BrandInfo[];
  activeBrand: string;
  onSelect: (brand: string) => void;
}

export function BrandTabs({ brands, activeBrand, onSelect }: BrandTabsProps) {
  return (
    <div className="flex flex-wrap gap-2 mb-6 p-2 bg-white rounded-xl border border-stone-100 shadow-sm">
      <button
        className={`relative px-4 py-2 rounded-full text-sm font-medium transition-all duration-200 ${
          !activeBrand
            ? 'bg-gold-500 text-white shadow-sm'
            : 'bg-transparent text-stone-500 hover:text-gold-600 hover:bg-stone-50'
        }`}
        onClick={() => onSelect('')}
      >
        全部品牌
      </button>
      {brands.map((b) => (
        <button
          key={b.name}
          className={`relative flex items-center gap-2 px-3 py-1.5 rounded-full text-sm font-medium transition-all duration-200 ${
            activeBrand === b.name
              ? 'bg-gold-500 text-white shadow-sm'
              : 'bg-transparent text-stone-500 hover:text-gold-600 hover:bg-stone-50'
          }`}
          onClick={() => onSelect(b.name)}
        >
          {b.logoUrl && (
            <img
              src={b.logoUrl}
              alt={b.name}
              className="w-5 h-5 object-contain rounded-sm"
              loading="lazy"
            />
          )}
          <span>{b.name}</span>
          {activeBrand === b.name && (
            <motion.div
              layoutId="activeBrandIndicator"
              className="absolute inset-0 bg-gold-500 rounded-full -z-10"
              transition={{ type: 'spring', bounce: 0.15, duration: 0.4 }}
            />
          )}
        </button>
      ))}
    </div>
  );
}
