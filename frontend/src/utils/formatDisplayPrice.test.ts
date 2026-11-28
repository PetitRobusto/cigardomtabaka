import { expect, it } from 'vitest';
import { formatDisplayPrice } from './formatDisplayPrice';

it.each([null, undefined, '', ' ', 'invalid', Infinity, NaN])('shows the placeholder without a currency or unit for %s', value => {
  expect(formatDisplayPrice(value, { prefix: '~¥', suffix: '/支' })).toBe('未报价');
});

it('formats decimal amounts and preserves an explicitly quoted zero', () => {
  expect(formatDisplayPrice('1234.56')).toBe(`¥${(1234.56).toLocaleString()}`);
  expect(formatDisplayPrice(0, { prefix: '~¥', suffix: '/支' })).toBe('~¥0/支');
});
