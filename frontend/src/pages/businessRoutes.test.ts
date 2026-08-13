import { describe, expect, it } from 'vitest';
import { resolveBusinessRoute } from './businessRoutes';

describe('business routes', () => {
  it('keeps sales and accounting as separate workspaces', () => {
    expect(resolveBusinessRoute('/sales', '')).toBe('/sales');
    expect(resolveBusinessRoute('/accounting', '')).toBe('/accounting');
  });

  it('redirects the legacy accounting hash to the accounting workspace', () => {
    expect(resolveBusinessRoute('/sales', '#accounting')).toBe('/accounting');
  });
});
