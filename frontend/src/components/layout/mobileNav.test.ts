import { describe, expect, it } from 'vitest';
import { mobileNavItems } from './mobileNav';

describe('mobile bottom navigation', () => {
  it('uses the Day 1 business labels without exposing admin or Day 1 navigation', () => {
    const items = mobileNavItems(true);
    expect(items.map(item => item.label)).toEqual(['品牌', '库存', '订单', '账务', '更多']);
    expect(items[items.length - 1]).toEqual({ kind: 'menu', label: '更多' });
    expect(items.some(item => 'to' in item && (item.to === '/prices' || item.to === '/admin/' || item.to.includes('day1')))).toBe(false);
  });
});
