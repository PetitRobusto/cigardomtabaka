import { describe, expect, it } from 'vitest';
import { BUSINESS_ROUTE_PATHS, resolveBusinessRoute } from './businessRoutes';

describe('business routes', () => {
  it('keeps sales and accounting as separate workspaces', () => {
    expect(resolveBusinessRoute('/sales', '')).toBe('/sales');
    expect(resolveBusinessRoute('/accounting', '')).toBe('/accounting');
  });

  it('keeps the legal Day 1 route alongside both business workspaces', () => {
    expect(BUSINESS_ROUTE_PATHS).toEqual({ sales: '/sales', accounting: '/accounting', day1: '/accounting/day1' });
  });

  it('redirects the legacy accounting hash to the accounting workspace', () => {
    expect(resolveBusinessRoute('/sales', '#accounting')).toBe('/accounting');
  });
});
