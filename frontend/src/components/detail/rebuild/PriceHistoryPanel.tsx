import type { HistoryRange, Variant } from '../../../types';
import { DaysFilter } from '../DaysFilter';
import { PriceChart } from '../PriceChart';

export function PriceHistoryPanel({ variants, days, onDays }: {
  variants: Variant[]; days: HistoryRange; onDays: (days: HistoryRange) => void;
}) {
  return (
    <section className="rd-history">
      <header><div><h2>价格历史</h2><p>当前报价与每周在售来源趋势</p></div><DaysFilter days={days} onChange={onDays} /></header>
      <PriceChart variants={variants} />
    </section>
  );
}
