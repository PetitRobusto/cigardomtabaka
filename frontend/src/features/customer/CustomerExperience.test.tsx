// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useAuthStore } from '../../store/authStore';
import { CUSTOMER_AGE_KEY, CUSTOMER_LANGUAGE_KEY, readCustomerPreferences, useCustomerPreferences } from './preferences';
import { AGE_CONFIRMATION_KEY } from '../../storefront/ageConfirmation';
import { backendPageFixture } from '../../storefront/fixture';
import { LiveStorefront } from '../../storefront/LiveStorefront';
import { Storefront } from '../../storefront/Storefront';

function createStorage(): Storage {
  const values = new Map<string, string>();
  return {
    get length() { return values.size; },
    clear: () => values.clear(),
    getItem: (key) => values.get(key) ?? null,
    key: (index) => Array.from(values.keys())[index] ?? null,
    removeItem: (key) => { values.delete(key); },
    setItem: (key, value) => { values.set(key, String(value)); },
  };
}

beforeEach(() => {
  Object.defineProperty(window, 'localStorage', { configurable: true, value: createStorage() });
  Object.defineProperty(window, 'sessionStorage', { configurable: true, value: createStorage() });
  useCustomerPreferences.setState({ locale: 'en', confirmedAt: null, denied: false });
  useAuthStore.setState({ user: null, isAuthenticated: false, isLoading: false });
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.localStorage.clear();
  window.sessionStorage.clear();
  document.body.innerHTML = '';
  document.head.replaceChildren();
});

function renderShop(user: Parameters<typeof Storefront>[0]['user'] = null, ageConfirmed = false, currentUrl = backendPageFixture.path) {
  return render(<Storefront page={backendPageFixture} currentUrl={currentUrl} user={user} ageConfirmed={ageConfirmed} />);
}

describe('customer storefront experience', () => {
  it.each([
    ['guest', null],
    ['ordinary account', { username: 'customer', is_staff: false, is_superuser: false }],
  ] as const)('%s sees the store without management navigation', (_label, user) => {
    renderShop(user);

    expect(screen.getByRole('heading', { name: 'Cohiba Robustos' })).not.toBeNull();
    expect(screen.getByRole('dialog', { name: 'Are you 18 or older?' })).not.toBeNull();
    expect(screen.queryByText('Management')).toBeNull();
    expect(screen.queryByText('管理工具')).toBeNull();
    expect(screen.queryByRole('navigation', { name: '移动应用导航' })).toBeNull();
    expect(screen.queryByRole('link', { name: '资料库' })).toBeNull();
    if (user) expect(screen.getByText('customer')).not.toBeNull();
    else expect(screen.getByRole('link', { name: 'Log in' })).not.toBeNull();
  });

  it('offers three language links, preserves the product return path, and saves the chosen preference', () => {
    renderShop(null, true, `${backendPageFixture.path}?from=%2Fen%2Fcatalog#store-contact`);

    fireEvent.click(screen.getByRole('button', { name: 'Language' }));
    const menu = document.getElementById('site-language-menu')!;
    const links = Array.from(menu.querySelectorAll<HTMLAnchorElement>('a'));
    expect(links.map((link) => link.lang)).toEqual(['ru', 'en', 'zh-CN']);
    expect(menu.querySelector('a[lang="ru"]')?.getAttribute('href'))
      .toBe('/ru/cigar/5/cohiba-robustos?from=%2Fru%2Fcatalog#store-contact');
    expect(menu.querySelector('a[lang="zh-CN"]')?.getAttribute('href'))
      .toBe('/zh/cigar/5/cohiba-robustos?from=%2Fcatalog#store-contact');

    const russian = menu.querySelector('a[lang="ru"]')!;
    russian.addEventListener('click', (event) => event.preventDefault(), { once: true });
    fireEvent.click(russian);
    expect(window.localStorage.getItem(CUSTOMER_LANGUAGE_KEY)).toBe('ru');
    expect(useCustomerPreferences.getState().locale).toBe('ru');
  });

  it('reads the shared age preference from the legacy storefront key', async () => {
    const legacyTimestamp = Date.now() - 1_000;
    window.localStorage.setItem(AGE_CONFIRMATION_KEY, String(legacyTimestamp));
    expect(readCustomerPreferences().confirmedAt).toBe(legacyTimestamp);
    useCustomerPreferences.setState(readCustomerPreferences());
    expect(useCustomerPreferences.getState().confirmedAt).toBe(legacyTimestamp);

    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = new URL(String(input), window.location.origin);
      if (url.pathname === '/api/auth/me/') return { ok: true, json: async () => ({ authenticated: false }) };
      if (url.pathname === '/api/storefront/rates/') return { ok: true, json: async () => ({ expires_at: null }) };
      return { ok: true, status: 200, json: async () => backendPageFixture };
    }));
    useAuthStore.setState({ isLoading: true });
    const container = document.createElement('div');
    container.id = 'store-root';
    document.body.append(container);

    render(<LiveStorefront initialPage={backendPageFixture} />, { container });
    await screen.findByRole('heading', { name: 'Cohiba Robustos' });

    expect(document.querySelector('[data-age-gate]')?.hasAttribute('hidden')).toBe(true);
    expect(window.localStorage.getItem(CUSTOMER_AGE_KEY)).toBeNull();
  });
});
