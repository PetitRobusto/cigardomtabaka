import { describe, expect, it } from 'vitest';
import { decideStaffRoute } from '../utils/routeGuard';
import {
  dashboardDay1Action,
  dashboardStatDisplay,
  resolveBusinessRoute,
  supportQueryState,
} from './businessRoutes';
import { transportPayerTransition } from '../components/sales/salesState';

describe('business workspace review boundaries', () => {
  it('resolves the legacy hash and keeps all business entry paths staff-gated', () => {
    expect(resolveBusinessRoute('/sales', '#accounting')).toBe('/accounting');
    expect(['/sales', '/accounting', '/accounting/day1']).toEqual(expect.arrayContaining(['/sales', '/accounting', '/accounting/day1']));
    expect(decideStaffRoute({ isLoading: false, isAuthenticated: true, isStaff: false })).toBe('home');
  });

  it('selects the correct Day 1 action and preserves unknown stats as a dash', () => {
    expect(dashboardDay1Action('not_started')).toBe('start');
    expect(dashboardDay1Action('draft')).toBe('continue');
    expect(dashboardDay1Action('completed')).toBeNull();
    expect(dashboardStatDisplay(null)).toBe('—');
    expect(dashboardStatDisplay('0.00')).toBe('0.00');
  });

  it('marks supporting query errors for local rendering without treating missing data as zero', () => {
    expect(supportQueryState({ isError: true, hasData: false })).toBe('error');
    expect(supportQueryState({ isError: false, hasData: true })).toBe('ready');
    expect(dashboardStatDisplay(null)).not.toBe('¥0.00');
  });

  it('clears transport fee when company becomes payer and never restores it', () => {
    expect(transportPayerTransition('company', '80')).toEqual({ payer: 'company', fee: '0' });
    expect(transportPayerTransition('customer', '0')).toEqual({ payer: 'customer', fee: '0' });
  });
});
