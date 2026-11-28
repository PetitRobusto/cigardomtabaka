type PriceDisplay = { prefix?: string; suffix?: string; unavailable?: string };

export function formatDisplayPrice(
  value: number | string | null | undefined,
  { prefix = '¥', suffix = '', unavailable = '未报价' }: PriceDisplay = {},
): string {
  if (value == null || (typeof value === 'string' && !value.trim())) return unavailable;
  const amount = Number(value);
  return Number.isFinite(amount) ? `${prefix}${amount.toLocaleString()}${suffix}` : unavailable;
}
