import { SourceTag } from '../shared/SourceTag';
import { usePriceFormat } from '../../hooks/usePriceFormat';
import type { PriceSnapshot } from '../../types';

interface PriceRowProps {
  snap: PriceSnapshot;
}

export function PriceRow({ snap }: PriceRowProps) {
  const { formatPrice, formatBoxSize } = usePriceFormat();

  return (
    <div className="flex justify-between items-center py-1.5">
      <div className="flex items-center gap-2">
        <SourceTag slug={snap.source_slug} />
        <span className="text-xs font-semibold text-accent px-2 py-0.5 bg-accent-light rounded border border-accent">
          {formatBoxSize(snap.box_size)}
        </span>
      </div>
      {snap.in_stock ? (
        <span className="text-base font-bold text-fg font-mono tabular-nums">
          {formatPrice(snap.price, snap.currency)}
        </span>
      ) : (
        <span className="text-sm font-medium text-red-600">缺货</span>
      )}
    </div>
  );
}
