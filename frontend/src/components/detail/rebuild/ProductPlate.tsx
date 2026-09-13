import { useState } from 'react';
import type { CigarDetailResponse, CigarImage } from '../../../types';

export function ProductPlate({ catalog, images, box }: {
  catalog?: CigarDetailResponse; images: CigarImage[]; box: string;
}) {
  const [failed, setFailed] = useState<string[]>([]);
  const c = catalog?.cigar;
  const candidates = [...images].sort((a, b) => Number(b.is_primary) - Number(a.is_primary));
  const img = candidates.find(i => i.image_type !== 'band' && !failed.includes(i.url))
    || candidates.find(i => !failed.includes(i.url));
  return (
    <section className="rd-plate">
      <div className="rd-image">
        {img ? <img src={img.url} alt={c?.name || c?.english_name || '商品图片'} onError={() => setFailed(previous => [...previous, img.url])} /> : <div className="rd-empty">暂无商品图片</div>}
        <span className="rd-brandmark">{catalog?.brand?.name || c?.brand || 'CIGAR'}</span>
      </div>
      <div className="rd-specgrid">
        {([
          ['品型', c?.vitola_cn || c?.vitola],
          ['长度 / 环径', c?.length && c?.ring_gauge ? `${c.length} mm / ${c.ring_gauge}` : '—'],
          ['报价盒规', box], ['产地', c?.origin], ['工艺', c?.production_method], ['图片', `${images.length} 张`],
        ] as const).map(([label, value]) => <div key={label}><small>{label}</small><b>{value || '—'}</b></div>)}
      </div>
    </section>
  );
}
