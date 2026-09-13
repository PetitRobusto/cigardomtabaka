import { describe, expect, it } from 'vitest';
import type { HistoryPoint, Variant } from '../../types';
import { currentBars, weeklyHistory } from './priceChartData';
import { eligibleVariant, unitPrice } from '../../utils/offerPricing';
import { statusOf } from './rebuild/detailFormatters';

const anomaly = { code: 'outlier', label: '价格异常', reason: '后端标记', exclude_from_aggregate: true } as const;
function point(price: number | null, changes: Partial<HistoryPoint> = {}): HistoryPoint {
  return { date: '2026-09-01T00:00:00Z', price, price_cny: price, original_price: null, in_stock: true, currency: 'USD', ...changes };
}
function variant(changes: Partial<Variant> = {}): Variant {
  return { source_slug: 'a', source_name: 'A', box_size: 10, box_label: '10支', currency: 'USD',
    in_stock: true, current_price: 100, current_price_cny: 700, points: [point(100)], ...changes };
}

describe('price detail statistics', () => {
  it('validates price and box size instead of trusting precomputed unit price', () => {
    for (const invalid of [null, 0, -1, NaN, Infinity]) {
      expect(unitPrice(invalid, 10)).toBeNull();
      expect(unitPrice(700, invalid)).toBeNull();
      expect(eligibleVariant(variant({ box_size: invalid, price_per_stick: 70 }))).toBe(false);
    }
    expect(unitPrice(700, 2.5)).toBeNull();
    expect(statusOf(variant({ box_size: null }))).toBe('invalid');
    expect(statusOf(variant({ in_stock: undefined }))).toBe('invalid');
    expect(statusOf(variant({ in_stock: false, current_price_cny: null }))).toBe('out');
    expect(statusOf(variant({ in_stock: false, delisted: true }))).toBe('delisted');
    expect(statusOf(variant({ anomaly }))).toBe('in');
    expect(eligibleVariant(variant({ anomaly }))).toBe(false);
  });

  it('sorts current bars and excludes unavailable, invalid and anomalous quotes', () => {
    const data = [variant(), variant({ source_slug: 'b', current_price_cny: 500 }),
      ...[{ in_stock: false }, { delisted: true }, { anomaly }, { current_price_cny: null }, { box_size: 0 }].map(changes => variant(changes))];
    expect(currentBars(data).map(row => row.price)).toEqual([50, 70]);
  });

  it('uses historical status rather than current status and preserves separate unavailable means', () => {
    const data = [
      variant({ in_stock: false }),
      variant({ source_slug: 'b', points: [point(500, { in_stock: false })] }),
      variant({ source_slug: 'c', points: [point(900, { delisted: true })] }),
      variant({ source_slug: 'd', points: [point(10000, { anomaly })] }),
    ];
    expect(weeklyHistory(data)[0]).toMatchObject({ active: 10, soldOut: 50, delisted: 90, sourceCount: 1 });
  });

  it('samples last quote in week and weights sources equally despite scrape frequency and variants', () => {
    const rows = weeklyHistory([
      variant({ points: [point(100), point(200, { date: '2026-09-02' }), point(300, { date: '2026-09-03' })] }),
      variant({ url: 'another', points: [point(500)] }),
      variant({ source_slug: 'b', points: [point(1000)] }),
    ]);
    // A = (30 + 50) / 2 = 40, B = 100; mean = 70, regardless of A's scrape count.
    expect(rows[0].active).toBe(70);
    expect(rows[0].sourceCount).toBe(2);
  });

  it('does not backfill a latest invalid observation or bridge missing weeks', () => {
    const data = [variant({ points: [
      point(100), point(null, { date: '2026-09-02' }), point(300, { date: '2026-09-15' }),
    ] })];
    expect(weeklyHistory(data).map(row => row.active)).toEqual([null, null, 30]);
  });

  it('keeps native currencies separate, including currency changes in historical points', () => {
    const data = [
      variant({ current_price: 100, points: [point(100, { currency: 'USD' }), point(500, { date: '2026-09-08', currency: 'CHF' })] }),
      variant({ source_slug: 'b', currency: 'CHF', current_price: 200, points: [point(200, { currency: 'CHF' })] }),
    ];
    expect(currentBars(data, 'USD', true).map(row => row.price)).toEqual([10]);
    expect(currentBars(data, 'CHF', true).map(row => row.price)).toEqual([20]);
    expect(weeklyHistory(data, 'USD', true).map(row => row.active)).toEqual([10]);
    expect(weeklyHistory(data, 'CHF', true).map(row => row.active)).toEqual([20, 50]);
  });

  it('does not manufacture prices for delisted records or unknown boxes', () => {
    expect(weeklyHistory([variant({ points: [point(null, { delisted: true })] })])[0].delisted).toBeNull();
    expect(weeklyHistory([variant({ box_size: null })])[0].active).toBeNull();
  });
});
