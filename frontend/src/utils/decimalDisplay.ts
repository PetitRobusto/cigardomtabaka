interface DecimalParts {
  negative: boolean;
  integer: string;
  fraction: string;
  coefficient: bigint;
  scale: number;
}

function parseDecimal(value: string): DecimalParts | null {
  const normalized = value.trim();
  if (normalized.length > 64) return null;
  const match = /^([+-]?)(\d+)(?:\.(\d+))?$/.exec(normalized);
  if (!match) return null;
  const integer = match[2].replace(/^0+(?=\d)/, '') || '0';
  const fraction = match[3] || '';
  return {
    negative: match[1] === '-',
    integer,
    fraction,
    coefficient: BigInt(`${integer}${fraction}`),
    scale: fraction.length,
  };
}

function groupedInteger(value: string): string {
  return value.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}

/** Format a backend Decimal string without converting it to an imprecise JS number. */
export function formatDecimalAmount(value: string, currency: string, absolute = false): string {
  const parsed = parseDecimal(value);
  if (!parsed) return value;
  const maximumDigits = currency === 'USDT' ? 8 : 2;
  const hasUnexpectedPrecision = /[1-9]/.test(parsed.fraction.slice(maximumDigits));
  let fraction = hasUnexpectedPrecision ? parsed.fraction : parsed.fraction.slice(0, maximumDigits);
  while (fraction.length > 2 && fraction.endsWith('0')) fraction = fraction.slice(0, -1);
  fraction = fraction.padEnd(2, '0');
  const sign = parsed.negative && !absolute ? '-' : '';
  return `${sign}${groupedInteger(parsed.integer)}.${fraction}`;
}

/** Return a rounded fixed-place ratio using integer arithmetic. */
export function formatDecimalRatio(numerator: string, denominator: string, places = 4): string | null {
  const top = parseDecimal(numerator);
  const bottom = parseDecimal(denominator);
  if (!top || !bottom || top.negative || bottom.negative || bottom.coefficient === 0n) return null;
  const scaledTop = top.coefficient * (10n ** BigInt(bottom.scale + places));
  const scaledBottom = bottom.coefficient * (10n ** BigInt(top.scale));
  const rounded = (scaledTop + scaledBottom / 2n) / scaledBottom;
  const divisor = 10n ** BigInt(places);
  const integer = (rounded / divisor).toString();
  const fraction = (rounded % divisor).toString().padStart(places, '0');
  return `${groupedInteger(integer)}.${fraction}`;
}
