import { describe, expect, it } from 'vitest';
import { appSectionForPath, appSkeletonVariantForPath, isAppNavPathActive } from './appSections';

describe('app section routing', () => {
  it.each([
    ['/', 'catalog'], ['/brand/cohiba', 'catalog'], ['/cigar/12', 'catalog'],
    ['/inventory/purchases', 'inventory'], ['/sales/customers', 'sales'],
    ['/accounting/day1', 'accounting'], ['/prices/cigar/12', 'prices'],
    ['/privnote', 'privnote'], ['/p/customer-note', 'privnote'], ['/help', 'help'],
  ] as const)('maps %s to %s', (path, section) => {
    expect(appSectionForPath(path)).toBe(section);
  });

  it('selects a stable skeleton family for each app', () => {
    expect(appSkeletonVariantForPath('/')).toBe('catalog');
    expect(appSkeletonVariantForPath('/p/customer-note')).toBe('panel');
    expect(appSkeletonVariantForPath('/sales')).toBe('table');
    expect(appSkeletonVariantForPath('/privnote')).toBe('panel');
  });

  it('keeps the top-level tab active on nested routes', () => {
    expect(isAppNavPathActive('/accounting/day1', '/accounting')).toBe(true);
    expect(isAppNavPathActive('/brand/cohiba', '/')).toBe(true);
    expect(isAppNavPathActive('/prices', '/')).toBe(false);
  });
});
