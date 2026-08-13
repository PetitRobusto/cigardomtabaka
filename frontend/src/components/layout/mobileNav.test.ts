import { describe, expect, it } from 'vitest';
import { mobileNavItems } from './mobileNav';

describe('mobile bottom navigation', () => {
  it('uses a menu action for more instead of linking to prices', () => {
    expect(mobileNavItems(true).at(-1)).toEqual({ kind: 'menu', label: '更多' });
    expect(mobileNavItems(true).some(item => 'to' in item && item.to === '/prices')).toBe(false);
  });
});
