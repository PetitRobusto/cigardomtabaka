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
        <div className="flex items-center gap-2 mb-3">
          <span
            className="inline-block text-[0.7rem] text-accent uppercase tracking-widest font-semibold
              px-3 py-1 bg-accent-light border border-accent rounded-full"
          >
            {data.cigar_brand_cn || data.cigar_brand}
          </span>
          {data.release_type_cn && (
            <span className="inline-block text-[0.65rem] font-bold text-amber-800 bg-amber-100 
              border border-amber-300 px-2.5 py-0.5 rounded-full uppercase tracking-wide">
              {data.release_type_cn}
            </span>
          )}
        </div>
      )}
      <h2 className="text-2xl md:text-3xl font-bold text-fg font-display leading-tight">
        {data.cigar_name || `Cigar #${data.cigar_id}`}
      </h2>
      {data.cigar_name_en && data.cigar_name_en !== data.cigar_name && (
        <p className="text-sm text-muted italic mt-2 font-display">
          {data.cigar_name_en}
        </p>
      )}
    </motion.div>
  );
}
