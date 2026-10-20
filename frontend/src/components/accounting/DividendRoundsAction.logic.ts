/** Monetary decisions use integer cents; never round binary floating point. */
export function dividendCents(value: string): bigint | null {
  if (!/^\d{1,20}(\.\d{1,2})?$/.test(value)) return null;
  const [whole, fraction = ''] = value.split('.');
  return BigInt(whole) * 100n + BigInt(fraction.padEnd(2, '0'));
}

export function dividendMoney(cents: bigint): string {
  return `${cents / 100n}.${(cents % 100n).toString().padStart(2, '0')}`;
}

export function personalDividendAmounts(amount: string, bothPaid: boolean) {
  const cents = dividendCents(amount);
  // 自动翻倍后的分配流水也必须小于后端原币金额上限 10^12 元。
  if (cents === null || cents <= 0n || cents * 2n >= 100000000000000n) return null;
  return {
    individual: dividendMoney(cents), total: dividendMoney(cents * 2n),
    paid: dividendMoney(cents * (bothPaid ? 2n : 1n)),
    pending: dividendMoney(bothPaid ? 0n : cents),
    otherPaid: dividendMoney(bothPaid ? cents : 0n),
  };
}

export const dividendInputClass = 'mt-1 block min-h-11 w-full rounded border border-border bg-white p-2 text-sm disabled:bg-cream';
export const dividendButtonClass = 'min-h-11 rounded bg-accent px-4 py-2 text-sm font-semibold text-white transition-colors enabled:hover:bg-accent-hover disabled:opacity-50';
export const dividendSecondaryClass = 'min-h-11 rounded border border-border bg-white px-3 py-2 text-sm disabled:opacity-50';
