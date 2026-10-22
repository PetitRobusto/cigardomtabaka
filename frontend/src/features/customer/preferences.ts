import { create } from 'zustand';
import { matchRoutes } from 'react-router-dom';
import type { CustomerLocale } from './messages';

export const CUSTOMER_LANGUAGE_KEY = 'cdt.customer.language';
export const CUSTOMER_AGE_KEY = 'cdt.customer.age-confirmed-at';
const DENIED_KEY = 'cdt.customer.age-denied';
export const AGE_CONFIRMATION_TTL = 30 * 24 * 60 * 60 * 1000;

export function detectCustomerLocale(languages: readonly string[]): CustomerLocale {
  for (const language of languages) {
    const base = language.toLowerCase().split('-')[0];
    if (base === 'zh' || base === 'en' || base === 'ru') return base;
  }
  return 'en';
}

export function isCustomerLocale(value: unknown): value is CustomerLocale {
  return value === 'zh' || value === 'en' || value === 'ru';
}

export function isAgeConfirmationValid(confirmedAt: number | null, now = Date.now()): boolean {
  return confirmedAt !== null && Number.isFinite(confirmedAt) && confirmedAt > 0 && confirmedAt <= now && now - confirmedAt < AGE_CONFIRMATION_TTL;
}

// Explicit page boundary: do not opt management, product detail or customer documents in by default.
export function isCustomerBrowsingPage(pathname: string): boolean {
  return matchRoutes([{ path: '/' }, { path: '/brand/:slug' }], pathname) !== null;
}

function readStorage(key: string, session = false): string | null {
  try { return (session ? window.sessionStorage : window.localStorage).getItem(key); } catch { return null; }
}

function writeStorage(key: string, value: string | null, session = false): void {
  try {
    const storage = session ? window.sessionStorage : window.localStorage;
    if (value === null) storage.removeItem(key);
    else storage.setItem(key, value);
  } catch { /* Memory state still works when browser storage is unavailable. */ }
}

export function readCustomerPreferences() {
  const storedLocale = readStorage(CUSTOMER_LANGUAGE_KEY);
  const locale = isCustomerLocale(storedLocale) ? storedLocale : detectCustomerLocale(
    typeof navigator === 'undefined' ? [] : navigator.languages?.length ? navigator.languages : [navigator.language],
  );
  const rawTimestamp = readStorage(CUSTOMER_AGE_KEY);
  const timestamp = rawTimestamp === null ? null : Number(rawTimestamp);
  return {
    locale,
    confirmedAt: isAgeConfirmationValid(timestamp) ? timestamp : null,
    denied: readStorage(DENIED_KEY, true) === 'true',
  };
}

interface CustomerPreferences {
  locale: CustomerLocale;
  confirmedAt: number | null;
  denied: boolean;
  selectLocale: (locale: CustomerLocale) => void;
  confirmAge: () => void;
  denyAge: () => void;
  reconsiderAge: () => void;
}

export const useCustomerPreferences = create<CustomerPreferences>((set) => ({
  ...readCustomerPreferences(),
  selectLocale: (locale) => {
    writeStorage(CUSTOMER_LANGUAGE_KEY, locale);
    set({ locale });
  },
  confirmAge: () => {
    const confirmedAt = Date.now();
    writeStorage(CUSTOMER_AGE_KEY, String(confirmedAt));
    writeStorage(DENIED_KEY, null, true);
    set({ confirmedAt, denied: false });
  },
  denyAge: () => {
    writeStorage(CUSTOMER_AGE_KEY, null);
    writeStorage(DENIED_KEY, 'true', true);
    set({ confirmedAt: null, denied: true });
  },
  reconsiderAge: () => {
    writeStorage(DENIED_KEY, null, true);
    set({ denied: false });
  },
}));
