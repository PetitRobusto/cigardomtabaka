import type { Variant } from '../../../types';
import { positive, validBox } from '../../../utils/offerPricing';

export type OfferStatus = 'in' | 'out' | 'delisted' | 'invalid';
export type OfferCounts = Record<OfferStatus, number>;

export function statusOf(v: Variant): OfferStatus {
  if (v.delisted === true) return 'delisted';
  if (v.in_stock === false) return 'out';
  if (v.in_stock !== true || invalidReason(v)) return 'invalid';
  return 'in';
}

export function invalidReason(v: Variant): string {
  if (!validBox(v.box_size)) return '盒规缺失或无效，无法计算单支价';
  if (!positive(v.current_price_cny)) return '缺少有效 CNY 价格，无法统一比较';
  return '';
}

export const statusLabels: Record<OfferStatus, string> = {
  in: '在售', out: '售罄', delisted: '已下架', invalid: '无有效价格',
};

export function money(value: number | null | undefined, currency = 'CNY'): string {
  return !positive(value) ? '—' : `${currency === 'CNY' ? '¥' : currency + ' '}${value.toLocaleString('zh-CN', { maximumFractionDigits: 2 })}`;
}

export function timestamp(value?: string): string {
  if (!value || !Number.isFinite(Date.parse(value))) return '—';
  return new Date(value).toLocaleString('zh-CN', { hour12: false });
}
