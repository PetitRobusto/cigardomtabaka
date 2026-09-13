import type { PriceAnomaly, Variant } from '../types';

export function positive(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value) && value > 0;
}

export function validBox(value: unknown): value is number {
  return positive(value) && Number.isInteger(value);
}

export function unitPrice(price: unknown, boxSize: unknown): number | null {
  return positive(price) && validBox(boxSize) ? Math.round(price / boxSize * 100) / 100 : null;
}

type Quote = {
  in_stock?: boolean;
  delisted?: boolean;
  anomaly?: PriceAnomaly | null;
  price_cny?: number | null;
  box_size: number | null;
};

export function eligibleQuote(quote: Quote): boolean {
  return quote.in_stock === true && quote.delisted !== true
    && !quote.anomaly?.exclude_from_aggregate
    && unitPrice(quote.price_cny, quote.box_size) !== null;
}

export function eligibleVariant(variant: Variant): boolean {
  return eligibleQuote({ ...variant, price_cny: variant.current_price_cny });
}

export function average(values: number[]): number | null {
  return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null;
}

export function offerKey(variant: Variant): string {
  if (variant.snapshot_id != null) return String(variant.snapshot_id);
  return JSON.stringify([variant.source_slug, variant.box_size, variant.url || '']);
}
