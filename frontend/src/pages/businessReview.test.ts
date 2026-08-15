import { describe, expect, it } from 'vitest';
import { decideStaffRoute } from '../utils/routeGuard';
import {
  dashboardDay1Action,
  BUSINESS_STAFF_PATHS,
  dashboardStatDisplay,
  dashboardRegionStates,
  resolveBusinessRoute,
} from './businessRoutes';
import { transportPayerChange } from '../components/sales/salesState';

describe('business workspace review boundaries', () => {
  it('resolves the legacy hash and keeps all business entry paths staff-gated', () => {
    expect(resolveBusinessRoute('/sales', '#accounting')).toBe('/accounting');
    expect(BUSINESS_STAFF_PATHS).toStrictEqual({ sales: '/sales', accounting: '/accounting', day1: '/accounting/day1' });
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
    expect(dashboardRegionStates({ accounts: { isError: false, hasData: true }, summary: { isError: false, hasData: true }, profit: { isError: true, hasData: false }, reconciliation: { isError: false, hasData: true } })).toEqual({ accounts: 'ready', summary: 'ready', profit: 'error', reconciliation: 'ready' });
    expect(dashboardRegionStates({ accounts: { isError: true, hasData: false }, summary: { isError: false, hasData: true }, profit: { isError: false, hasData: true }, reconciliation: { isError: false, hasData: true } }).profit).toBe('ready');
    expect(dashboardStatDisplay(null)).not.toBe('¥0.00');
  });

  it('clears transport fee when company becomes payer and never restores it', () => {
    expect(transportPayerChange('80', 'company')).toEqual({ payer: 'company', fee: '0' });
    expect(transportPayerChange('0', 'customer')).toEqual({ payer: 'customer', fee: '0' });
  });
});
