/** Preview only; the server validates and freezes the authoritative conversion. */
export function otherIncomeCny(amount: string, currency: 'CNY' | 'RUB', rate = ''): string | null {
  const scaled = (value: string, digits: number): bigint | null => {
    if (value.length > 32 || !new RegExp(`^\\d{1,12}(?:\\.\\d{1,${digits}})?$`).test(value)) return null;
    const [whole, fraction = ''] = value.split('.');
    return BigInt(whole + fraction.padEnd(digits, '0'));
  };
  const cents = scaled(amount, 2);
  if (cents === null || cents <= 0n || cents >= 100000000000000n) return null;
  const divisor = currency === 'CNY' ? 100000000n : scaled(rate, 8);
  if (divisor === null || divisor <= 0n || divisor >= 1000000000000000000n) return null;
  const numerator = cents * 100000000n;
  const result = (numerator * 2n + divisor) / (divisor * 2n);
  if (result <= 0n || result >= 100000000000000n) return null;
  return `${result / 100n}.${(result % 100n).toString().padStart(2, '0')}`;
}
