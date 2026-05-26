import type { PriceHistoryResponse } from '../../types';

interface DetailHeaderProps {
  data: PriceHistoryResponse;
}

export function DetailHeader({ data }: DetailHeaderProps) {
  return (
    <div className="mb-6">
      {(data.cigar_brand_cn || data.cigar_brand) && (
        <span
          className="inline-block text-[0.7rem] text-brand-brown uppercase tracking-widest font-semibold
            px-3 py-1 bg-brand-tab-active border border-brand-brown/20 rounded-sm mb-3"
        >
          {data.cigar_brand_cn || data.cigar_brand}
        </span>
      )}
      <h2 className="text-2xl font-bold text-brand-brown font-serif leading-tight">
        {data.cigar_name || `Cigar #${data.cigar_id}`}
      </h2>
      {data.cigar_name_en && data.cigar_name_en !== data.cigar_name && (
        <p className="text-sm text-stone-500 italic mt-1 font-serif">
          {data.cigar_name_en}
        </p>
      )}
    </div>
  );
}
