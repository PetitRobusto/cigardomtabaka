import { describe, expect, it } from 'vitest';
import { decideStaffRoute, isStaffPath, resolveStorefrontTarget, safeLoginDestination } from './routeGuard';

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

describe('login next destination', () => {
  it.each(['//example.com/path', 'https://example.com/path', '/\\\\example.com/path'])('rejects unsafe destination %s', next => {
    expect(safeLoginDestination(next, true)).toBe('/');
  });

  it('preserves safe same-origin paths and query strings', () => {
    expect(safeLoginDestination('/inventory/purchases?tab=open#latest', true))
      .toBe('/inventory/purchases?tab=open#latest');
  });

  it('does not send non-staff users into the management app', () => {
    expect(safeLoginDestination('/prices/alerts', false)).toBe('/');
    expect(safeLoginDestination('/pr%69ces/alerts', false)).toBe('/');
    expect(isStaffPath('/library/brand/cohiba')).toBe(true);
    expect(isStaffPath('/p/customer-token')).toBe(false);
  });
});

describe('storefront bridge destination', () => {
  const sameOrigin = {
    enabled: true,
    djangoOrigin: 'https://shop.example',
    currentOrigin: 'https://shop.example',
  };

  it('uses the configured Django origin only when storefront is enabled', () => {
    expect(resolveStorefrontTarget('/catalog?lang=en', sameOrigin))
      .toBe('https://shop.example/catalog?lang=en');
    expect(resolveStorefrontTarget('/catalog', { ...sameOrigin, enabled: false })).toBeNull();
  });

  it('does not navigate from Vite without an explicit Django origin', () => {
    expect(resolveStorefrontTarget('/', {
      enabled: true,
      djangoOrigin: '',
      currentOrigin: 'http://localhost:5173',
      allowConfiguredCrossOrigin: true,
    })).toBeNull();
  });

  it('allows an explicitly configured Django origin for Vite development', () => {
    expect(resolveStorefrontTarget('/brand/cohiba', {
      enabled: true,
      djangoOrigin: 'http://127.0.0.1:8000',
      currentOrigin: 'http://127.0.0.1:5173',
      allowConfiguredCrossOrigin: true,
    })).toBe('http://127.0.0.1:8000/brand/cohiba');
  });

  it('rejects external paths and external Django origins from a Django shell', () => {
    expect(resolveStorefrontTarget('//attacker.example', sameOrigin)).toBeNull();
    expect(resolveStorefrontTarget('/catalog', {
      ...sameOrigin,
      djangoOrigin: 'https://attacker.example',
    })).toBeNull();
  });
});
