import type { PriceHistoryResponse } from '../../../types';
import type { OfferCounts } from './detailFormatters';

export function IdentityCard({ prices, counts, last }: {
  prices: PriceHistoryResponse; counts: OfferCounts; last: string;
}) {
  return (
    <section className="rd-identity">
      <div className="rd-eyebrow">{prices.cigar_brand_cn || prices.cigar_brand || 'PRICE DETAIL'}</div>
      <h1>{prices.cigar_name || `雪茄 #${prices.cigar_id}`}{prices.cigar_name_en && prices.cigar_name_en !== prices.cigar_name && (
        <> <span className="rd-en">{prices.cigar_name_en}</span></>
      )}</h1>
      <div className="rd-tags"><span>{prices.release_type_cn || '常规款'}</span><span>{prices.variants.length} 个来源 × 盒规报价</span></div>
      <div className="rd-cred">
        {([['在售报价', counts.in], ['售罄报价', counts.out], ['已下架', counts.delisted], ['无有效价格', counts.invalid], ['最近抓取', last]] as const).map(([label, value]) => (
          <div key={label}><small>{label}</small><strong>{value}</strong></div>
        ))}
      </div>
      <p className="rd-note">原币价格保留原始值，CNY 仅用于统一比较展示，不代表历史成本。</p>
    </section>
  );
}
