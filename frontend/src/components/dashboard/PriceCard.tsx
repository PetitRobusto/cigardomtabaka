import { motion } from 'framer-motion';
import { PriceRow } from './PriceRow';
import type { CigarGroup } from '../../types';

interface PriceCardProps {
  cigar: CigarGroup;
  index: number;
  onClick: () => void;
}

export function PriceCard({ cigar, index, onClick }: PriceCardProps) {
  return (
    <motion.div
      className="bg-white rounded-md border border-stone-100 shadow-sm overflow-hidden cursor-pointer hover:-translate-y-1 hover:shadow-lg hover:border-gold-500 transition-all duration-200"
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.04, duration: 0.3, ease: [0.4, 0, 0.2, 1] }}
      onClick={onClick}
      layout
    >
      <div className="px-4 py-2.5 bg-stone-100 border-b border-stone-100">
        <span className="text-[0.7rem] text-stone-500 uppercase tracking-widest font-semibold">
          {cigar.brand}
        </span>
      </div>
      <div className="p-4">
        <h3 className="text-base font-semibold text-stone-900 leading-snug mb-1">
          {cigar.name}
        </h3>
        {cigar.name_en && cigar.name_en !== cigar.name && (
          <p className="text-[0.78rem] text-stone-500 italic mb-3 font-serif">
            {cigar.name_en}
          </p>
        )}
        <div className="flex flex-col gap-1">
          {cigar.prices.map((snap, i) => (
            <PriceRow key={i} snap={snap} />
          ))}
        </div>
      </div>
    </motion.div>
  );
}
