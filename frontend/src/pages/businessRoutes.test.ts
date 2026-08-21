import { describe, expect, it } from 'vitest';
import { BUSINESS_ROUTE_PATHS, BUSINESS_STAFF_PATHS, resolveBusinessRoute } from './businessRoutes';

describe('business routes', () => {
  it('keeps sales and accounting as separate workspaces', () => {
    expect(resolveBusinessRoute('/sales', '')).toBe('/sales');
    expect(BUSINESS_STAFF_PATHS.salesCustomers).toBe('/sales/customers');
    expect(resolveBusinessRoute('/accounting', '')).toBe('/accounting');
  });

  it('keeps the legal Day 1 route alongside both business workspaces', () => {
    expect(BUSINESS_ROUTE_PATHS).toStrictEqual(BUSINESS_STAFF_PATHS);
  });

  it('redirects the legacy accounting hash to the accounting workspace', () => {
    expect(resolveBusinessRoute('/sales', '#accounting')).toBe('/accounting');
  });
});
