import { motion } from 'framer-motion';
import type { PriceHistoryResponse } from '../../types';

interface DetailHeaderProps {
  data: PriceHistoryResponse;
}

export function DetailHeader({ data }: DetailHeaderProps) {
  return (
    <motion.div
      className="mb-8"
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
    >
      {(data.cigar_brand_cn || data.cigar_brand) && (
        <span
          className="inline-block text-[0.7rem] text-gold-600 uppercase tracking-widest font-semibold
            px-3 py-1 bg-gold-50 border border-gold-200 rounded-full mb-3"
        >
          {data.cigar_brand_cn || data.cigar_brand}
        </span>
      )}
      <h2 className="text-2xl md:text-3xl font-bold text-stone-900 font-serif leading-tight">
        {data.cigar_name || `Cigar #${data.cigar_id}`}
      </h2>
      {data.cigar_name_en && data.cigar_name_en !== data.cigar_name && (
        <p className="text-sm text-stone-400 italic mt-2 font-serif">
          {data.cigar_name_en}
        </p>
      )}
    </motion.div>
  );
}
