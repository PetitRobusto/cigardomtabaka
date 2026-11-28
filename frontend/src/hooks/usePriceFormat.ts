import { formatDisplayPrice } from '../utils/formatDisplayPrice';

const CURRENCY_SYMBOLS: Record<string, string> = {
  USD: '$',
  CHF: 'CHF ',
  EUR: '€',
};

export function usePriceFormat() {
  const formatPrice = (price: number | null | undefined, currency?: string) => {
    const symbol = (currency && CURRENCY_SYMBOLS[currency]) || '';
    return formatDisplayPrice(price, { prefix: symbol, unavailable: '-' });
  };

  const formatBoxSize = (boxSize: number | null | undefined) => {
    if (boxSize == null) return '25支';
    return `${boxSize}支`;
  };

  return { formatPrice, formatBoxSize };
}
