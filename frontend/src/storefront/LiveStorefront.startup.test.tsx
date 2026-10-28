// @vitest-environment jsdom
import { act } from 'react';
import { hydrateRoot } from 'react-dom/client';
import { renderToString } from 'react-dom/server';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { CUSTOMER_AGE_KEY, useCustomerPreferences } from '../features/customer/preferences';
import { LiveStorefront } from './LiveStorefront';
import { Storefront } from './Storefront';
import { backendPageFixture } from './fixture';

(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
let root: ReturnType<typeof hydrateRoot> | undefined;
let consoleError: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  consoleError = vi.spyOn(console, 'error').mockImplementation(() => undefined);
  localStorage.clear();
  useCustomerPreferences.setState({ confirmedAt: null, denied: false });
  document.documentElement.dataset.cdtStarting = 'true';
  document.body.innerHTML = '<div id="store-root"></div>';
  vi.stubGlobal('requestAnimationFrame', () => 1);
});
afterEach(async () => {
  await act(async () => root?.unmount());
  root = undefined;
  vi.unstubAllGlobals();
  delete document.documentElement.dataset.cdtStarting;
  delete document.documentElement.dataset.cdtAppReady;
  document.body.innerHTML = '';
  localStorage.clear();
  expect(consoleError).not.toHaveBeenCalled();
  consoleError.mockRestore();
});

it.each(['zh', 'ru', 'en'] as const)('coordinates %s hydration, startup and first-visit age focus without delaying public refresh', async (locale) => {
  const page = { ...backendPageFixture, locale, path: locale === 'zh' ? '/' : `/${locale}/` };
  history.replaceState(null, '', page.path);
  const fetch = vi.fn(async (input: string) => ({ ok: true, status: 200, json: async () => input.includes('/auth/') ? { authenticated: false } : page }));
  vi.stubGlobal('fetch', fetch);
  const container = document.getElementById('store-root')!;
  container.innerHTML = renderToString(<Storefront page={page} />);
  const errors: unknown[] = [];
  await act(async () => { root = hydrateRoot(container, <LiveStorefront initialPage={page} />, { onRecoverableError: (error) => errors.push(error) }); });
  expect(errors).toEqual([]);
  expect(document.activeElement).not.toBe(container.querySelector('[data-age-confirm]'));
  expect(fetch.mock.calls.some(([url]) => url.includes('/page/'))).toBe(true);
  expect(fetch.mock.calls.some(([url]) => url.includes('/auth/') || url.includes('/rates/'))).toBe(false);
  await act(async () => {
    delete document.documentElement.dataset.cdtStarting;
    window.dispatchEvent(new Event('cdt:startup-finished'));
  });
  expect(document.activeElement).toBe(container.querySelector('[data-age-confirm]'));
  expect(fetch.mock.calls.filter(([url]) => url.includes('/auth/'))).toHaveLength(1);
  expect(fetch.mock.calls.some(([url]) => url.includes('/rates/'))).toBe(false);
});

it.each(['zh', 'ru', 'en'] as const)('keeps the confirmed %s age gate hidden on refresh and startup exit', async (locale) => {
  localStorage.setItem(CUSTOMER_AGE_KEY, String(Date.now()));
  const page = { ...backendPageFixture, locale, path: locale === 'zh' ? '/' : `/${locale}/` };
  history.replaceState(null, '', page.path);
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, status: 200, json: async () => page })));
  const container = document.getElementById('store-root')!;
  container.innerHTML = renderToString(<Storefront page={page} />);
  const errors: unknown[] = [];
  await act(async () => { root = hydrateRoot(container, <LiveStorefront initialPage={page} />, { onRecoverableError: (error) => errors.push(error) }); });
  expect(container.querySelector('[data-age-gate]')?.hasAttribute('hidden')).toBe(true);
  await act(async () => {
    delete document.documentElement.dataset.cdtStarting;
    window.dispatchEvent(new Event('cdt:startup-finished'));
  });
  expect(errors).toEqual([]);
  expect(container.querySelector('[data-age-gate]')?.hasAttribute('hidden')).toBe(true);
  expect(document.activeElement).not.toBe(container.querySelector('[data-age-confirm]'));
});

it.each(['zh', 'ru', 'en'] as const)('preserves %s home carousel and contact relationships across hydration', async (locale) => {
  const page = {
    ...backendPageFixture, locale, kind: 'home' as const,
    path: locale === 'zh' ? '/' : `/${locale}/`,
    products: [backendPageFixture.product!], latest_products: [backendPageFixture.product!],
  };
  history.replaceState(null, '', page.path);
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, status: 200, json: async () => page })));
  const container = document.getElementById('store-root')!;
  container.innerHTML = renderToString(<Storefront page={page} />);
  const relationships = () => [...container.querySelectorAll('[aria-controls]')].map((element) => element.getAttribute('aria-controls'));
  const original = relationships();
  const errors: unknown[] = [];
  await act(async () => { root = hydrateRoot(container, <LiveStorefront initialPage={page} />, { onRecoverableError: (error) => errors.push(error) }); });
  expect(errors).toEqual([]);
  expect(relationships()).toEqual(original);
  expect(original.length).toBeGreaterThanOrEqual(3);
  for (const button of container.querySelectorAll('.store-carousel [aria-controls]')) {
    expect(document.getElementById(button.getAttribute('aria-controls')!)).not.toBeNull();
  }
});
