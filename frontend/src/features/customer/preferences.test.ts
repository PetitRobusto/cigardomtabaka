// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { AGE_CONFIRMATION_TTL, CUSTOMER_AGE_KEY, CUSTOMER_LANGUAGE_KEY, detectCustomerLocale, isAgeConfirmationValid, isCustomerBrowsingPage, readCustomerPreferences, useCustomerPreferences } from './preferences';
import { brandCategoryLabel, catalogCount } from './messages';
import { catalogSectionLabel } from './catalogLabels';

beforeEach(() => { window.localStorage.clear(); window.sessionStorage.clear(); useCustomerPreferences.setState({ locale: 'en', confirmedAt: null, denied: false }); });
afterEach(() => vi.restoreAllMocks());

describe('customer preferences', () => {
  it.each([
    [['ru-RU', 'en-US'], 'ru'], [['zh-TW'], 'zh'], [['EN-gb'], 'en'],
    [['fr-FR', 'ru'], 'ru'], [['de-DE'], 'en'], [[], 'en'],
  ])('selects the first supported browser language %j', (languages, expected) => {
    expect(detectCustomerLocale(languages as string[])).toBe(expected);
  });

  it('remembers an explicit language and ignores invalid saved values', () => {
    vi.spyOn(navigator, 'languages', 'get').mockReturnValue(['ru-RU']);
    useCustomerPreferences.getState().selectLocale('zh');
    expect(window.localStorage.getItem(CUSTOMER_LANGUAGE_KEY)).toBe('zh');
    expect(readCustomerPreferences().locale).toBe('zh');
    window.localStorage.setItem(CUSTOMER_LANGUAGE_KEY, 'broken');
    expect(readCustomerPreferences().locale).toBe('ru');
  });

  it('expires age confirmation after 30 days and rejects malformed or future dates', () => {
    const now = Date.now();
    expect(isAgeConfirmationValid(now - AGE_CONFIRMATION_TTL + 1, now)).toBe(true);
    for (const timestamp of [null, 0, NaN, Infinity, now + 1, now - AGE_CONFIRMATION_TTL]) {
      expect(isAgeConfirmationValid(timestamp, now)).toBe(false);
    }
    for (const value of ['invalid', 'Infinity', String(now + 1000), String(now - AGE_CONFIRMATION_TTL)]) {
      window.localStorage.setItem(CUSTOMER_AGE_KEY, value);
      expect(readCustomerPreferences().confirmedAt).toBeNull();
    }
  });

  it('persists positive confirmation and retains denial on a same-tab refresh', () => {
    useCustomerPreferences.getState().confirmAge();
    expect(isAgeConfirmationValid(readCustomerPreferences().confirmedAt)).toBe(true);
    useCustomerPreferences.getState().denyAge();
    expect(readCustomerPreferences()).toMatchObject({ denied: true, confirmedAt: null });
    useCustomerPreferences.getState().reconsiderAge();
    expect(readCustomerPreferences()).toMatchObject({ denied: false, confirmedAt: null });
  });

  it('still works in memory when storage access is blocked', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('blocked'); });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('blocked'); });
    vi.spyOn(Storage.prototype, 'removeItem').mockImplementation(() => { throw new Error('blocked'); });
    expect(() => readCustomerPreferences()).not.toThrow();
    useCustomerPreferences.getState().selectLocale('ru');
    useCustomerPreferences.getState().confirmAge();
    expect(useCustomerPreferences.getState().locale).toBe('ru');
    expect(isAgeConfirmationValid(useCustomerPreferences.getState().confirmedAt)).toBe(true);
  });

  it('only enables the agreed browsing routes', () => {
    for (const path of ['/', '//', '/brand/cohiba', '/brand/cohiba/', '/Brand/cohiba', '/brand/cohiba//', '/%62rand/cohiba']) expect(isCustomerBrowsingPage(path)).toBe(true);
    for (const path of ['/login', '/admin/', '/cigar/1/cohiba', '/p/token', '/privnote', '/inventory', '/sales', '/accounting', '/prices', '/brand/cohiba/edit']) {
      expect(isCustomerBrowsingPage(path)).toBe(false);
    }
  });
});

describe('catalogue labels', () => {
  it('uses category keys without changing unknown categories', () => {
    expect(brandCategoryLabel('global', '全球品牌', 'ru')).toBe('Глобальные бренды');
    expect(brandCategoryLabel('future', 'Future category', 'en')).toBe('Future category');
  });

  it('translates known headings and preserves exact counts and unknown data', () => {
    expect(catalogSectionLabel('常规款 (17)', 'en')).toBe('Regular production (17)');
    expect(catalogSectionLabel('停产款 (0)', 'ru')).toBe('Снятые с производства (0)');
    expect(catalogSectionLabel('常规款 (17)', 'zh')).toBe('常规款 (17)');
    for (const label of ['', '未知系列 (3)', '常规款 (bad)', '常规款 (-2)']) expect(catalogSectionLabel(label, 'en')).toBe(label);
  });

  it('formats English and Russian plural forms', () => {
    expect(catalogCount(1, 'brands', 'en')).toBe('1 brand');
    expect(catalogCount(2, 'brands', 'en')).toBe('2 brands');
    expect(catalogCount(21, 'brands', 'ru')).toBe('21 бренд');
    expect(catalogCount(22, 'brands', 'ru')).toBe('22 бренда');
    expect(catalogCount(11, 'brands', 'ru')).toBe('11 брендов');
    expect(catalogCount(0, 'cigars', 'ru')).toBe('0 сигар');
  });
});
