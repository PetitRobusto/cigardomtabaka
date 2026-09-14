/** Monetary decisions use integer cents; never round binary floating point. */
export function dividendCents(value: string): bigint | null {
  if (!/^\d{1,20}(\.\d{1,2})?$/.test(value)) return null;
  const [whole, fraction = ''] = value.split('.');
  return BigInt(whole) * 100n + BigInt(fraction.padEnd(2, '0'));
}
