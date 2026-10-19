/** Monetary decisions use integer cents; never round binary floating point. */
export function dividendCents(value: string): bigint | null {
  if (!/^\d{1,20}(\.\d{1,2})?$/.test(value)) return null;
  const [whole, fraction = ''] = value.split('.');
  return BigInt(whole) * 100n + BigInt(fraction.padEnd(2, '0'));
}

export function dividendMoney(cents: bigint): string {
  return `${cents / 100n}.${(cents % 100n).toString().padStart(2, '0')}`;
}

export const dividendInputClass = 'mt-1 block w-full rounded border border-border bg-white p-2 text-sm disabled:bg-cream';
export const dividendButtonClass = 'rounded bg-accent px-4 py-2 text-sm font-semibold text-white disabled:opacity-50';
export const dividendSecondaryClass = 'rounded border border-border bg-white px-3 py-2 text-sm disabled:opacity-50';
