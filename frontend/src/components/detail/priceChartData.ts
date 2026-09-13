import type { HistoryPoint, Variant } from '../../types';
import { average, eligibleVariant, offerKey, unitPrice } from '../../utils/offerPricing';

export type ChartCurrency = 'CNY' | string;
export type HistoryStatus = 'active' | 'soldOut' | 'delisted';
export interface WeeklyPrice {
  date: string;
  active: number | null;
  soldOut: number | null;
  delisted: number | null;
  sourceCount: number;
}

export function currentBars(variants: Variant[], currency = 'CNY', original = false) {
  return variants.filter(eligibleVariant)
    .filter(v => !original || v.currency === currency)
    .flatMap(v => {
      const price = unitPrice(original ? v.current_price : v.current_price_cny, v.box_size);
      return price === null ? [] : [{
        key: offerKey(v), name: `${v.source_short_name || v.source_name} · ${v.box_label}`,
        product: v.product_name || v.scraped_name || '', price,
      }];
    }).sort((a, b) => a.price - b.price);
}

function weekOf(value: string): string | null {
  const time = Date.parse(value);
  if (!Number.isFinite(time)) return null;
  const date = new Date(time);
  // UTC Monday, kept explicit in the chart's statistical note.
  date.setUTCHours(0, 0, 0, 0);
  date.setUTCDate(date.getUTCDate() - (date.getUTCDay() + 6) % 7);
  return date.toISOString().slice(0, 10);
}

export function weeklyHistory(variants: Variant[], currency = 'CNY', original = false): WeeklyPrice[] {
  const weeks = new Map<string, Record<HistoryStatus, Map<string, number[]>>>();
  for (const variant of variants) {
    const lastInWeek = new Map<string, HistoryPoint>();
    for (const point of variant.points) {
      if (original && (point.currency || variant.currency) !== currency) continue;
      const week = weekOf(point.date);
      if (!week) continue;
      const previous = lastInWeek.get(week);
      if (!previous || Date.parse(point.date) >= Date.parse(previous.date)) lastInWeek.set(week, point);
    }
    for (const [week, point] of lastInWeek) {
      const row = weeks.get(week) || { active: new Map(), soldOut: new Map(), delisted: new Map() };
      weeks.set(week, row); // Retain an empty observed week: never connect through invalid observations.
      const value = unitPrice(original ? point.price : point.price_cny, variant.box_size);
      if (value === null || point.anomaly?.exclude_from_aggregate) continue;
      const status: HistoryStatus | null = point.delisted === true ? 'delisted'
        : point.in_stock === false ? 'soldOut' : point.in_stock === true ? 'active' : null;
      if (!status) continue;
      const sourceValues = row[status].get(variant.source_slug) || [];
      sourceValues.push(value);
      row[status].set(variant.source_slug, sourceValues);
    }
  }
  const sorted = [...weeks.keys()].sort();
  if (!sorted.length) return [];
  const rows: WeeklyPrice[] = [];
  const end = Date.parse(sorted[sorted.length - 1]);
  for (let day = Date.parse(sorted[0]); day <= end; day += 7 * 86400000) {
    const date = new Date(day).toISOString().slice(0, 10);
    const row = weeks.get(date);
    const mean = (status: HistoryStatus) => row
      ? average([...row[status].values()].map(values => average(values)!)) : null;
    rows.push({ date, active: mean('active'), soldOut: mean('soldOut'), delisted: mean('delisted'), sourceCount: row?.active.size || 0 });
  }
  return rows;
}
