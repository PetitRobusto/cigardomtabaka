import { describe, expect, it } from 'vitest';
import { decideStaffRoute } from './routeGuard';

describe('staff route guard', () => {
  it('does not render while authentication is loading', () => {
    expect(decideStaffRoute({ isLoading: true, isAuthenticated: false, isStaff: false })).toBe('loading');
  });

  it('sends anonymous users to login', () => {
    expect(decideStaffRoute({ isLoading: false, isAuthenticated: false, isStaff: false })).toBe('login');
  });

  it('sends authenticated non-staff users to the safe home page', () => {
    expect(decideStaffRoute({ isLoading: false, isAuthenticated: true, isStaff: false })).toBe('home');
  });

  it('allows authenticated staff users through', () => {
    expect(decideStaffRoute({ isLoading: false, isAuthenticated: true, isStaff: true })).toBe('allow');
  });
});
