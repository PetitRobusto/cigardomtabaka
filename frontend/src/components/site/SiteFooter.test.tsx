// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, within } from '@testing-library/react';
import { renderToString } from 'react-dom/server';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { SiteFooter } from './SiteFooter';
import { Storefront } from '../../storefront/Storefront';
import { backendPageFixture } from '../../storefront/fixture';
import { storeStructuredData } from '../../storefront/metadata';
import publicDetails from '../../../../storefront/public_details.json';

let approach: IntersectionObserverCallback;
const disconnect = vi.fn();
const observe = vi.fn();
beforeEach(() => {
  observe.mockClear(); disconnect.mockClear();
  vi.stubGlobal('IntersectionObserver', class {
    constructor(callback: IntersectionObserverCallback) { approach = callback; }
    observe = observe;
    disconnect = disconnect;
  });
});
function approachMap() {
  act(() => approach([{ isIntersecting: true } as IntersectionObserverEntry], {} as IntersectionObserver));
}
afterEach(() => { cleanup(); vi.unstubAllGlobals(); delete document.documentElement.dataset.cdtStarting; });

describe('shared site footer', () => {
  it('keeps the map network request out of SSR and first paint, retaining the route link', () => {
    const markup = renderToString(<SiteFooter />);
    expect(markup).not.toMatch(/<iframe[^>]*\bsrc=/);
    expect(markup).toContain(publicDetails.map_url);
    const { container } = render(<SiteFooter />);
    const map = container.querySelector('iframe')!;
    expect(map.hasAttribute('src')).toBe(false);
    act(() => approach([{ isIntersecting: false } as IntersectionObserverEntry], {} as IntersectionObserver));
    expect(map.hasAttribute('src')).toBe(false);
    approachMap();
    expect(map.getAttribute('src')).toContain('https://yandex.com/map-widget/');
    expect(disconnect).toHaveBeenCalled();
  });

  it('waits for both startup exit and age confirmation before observing the map', () => {
    document.documentElement.dataset.cdtStarting = 'true';
    const { container, rerender } = render(<SiteFooter inert />);
    expect(observe).not.toHaveBeenCalled();
    rerender(<SiteFooter />);
    expect(observe).not.toHaveBeenCalled();
    act(() => {
      delete document.documentElement.dataset.cdtStarting;
      window.dispatchEvent(new Event('cdt:startup-finished'));
    });
    expect(observe).toHaveBeenCalledTimes(1);
    expect(container.querySelector('iframe')?.hasAttribute('src')).toBe(false);
    approachMap();
    expect(container.querySelector('iframe')?.getAttribute('src')).toContain('map-widget');
  });

  it('loads on scroll near the contact area when IntersectionObserver is unavailable', () => {
    vi.stubGlobal('IntersectionObserver', undefined);
    const bounds = vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({ top: 3000, bottom: 3330 } as DOMRect);
    const { container, unmount } = render(<SiteFooter />);
    expect(container.querySelector('iframe')?.hasAttribute('src')).toBe(false);
    bounds.mockReturnValue({ top: 500, bottom: 830 } as DOMRect);
    fireEvent.scroll(window);
    expect(container.querySelector('iframe')?.getAttribute('src')).toContain('map-widget');
    unmount();
    bounds.mockRestore();
  });

  it.each([undefined, { name: ' ', address: '', phone: ' ', wechat: '', map_url: '', hours: ' ' }])('retains the original contact details and channels when store fields are absent (%j)', (site) => {
    const { container } = render(<SiteFooter site={site} />);
    approachMap();
    const footer = within(container.querySelector('footer')!);
    expect(footer.getByRole('img', { name: 'CigarDomTabaka' })).toBeTruthy();
    expect(footer.getByText(publicDetails.address.zh)).toBeTruthy();
    expect(footer.queryByRole('link', { name: publicDetails.address.zh })).toBeNull();
    expect(new URL(footer.getByTitle('门店位置地图').getAttribute('src')!).searchParams.get('pt')).toBe(`${publicDetails.map_point.join(',')},pm2rdm`);
    expect(footer.getByRole('link', { name: '在 Yandex 地图中打开' }).getAttribute('href')).toBe(publicDetails.map_url);
    expect(footer.getByRole('link', { name: '+7 929 638-48-78' }).getAttribute('href')).toBe('tel:+79296384878');
    expect(footer.getByText('cigardomtabaka')).toBeTruthy();
    expect(footer.getByRole('link', { name: 'Telegram: +79296384878' }).getAttribute('href')).toBe('https://t.me/+79296384878');
    expect(footer.getByRole('link', { name: 'WhatsApp: +79296384878' }).getAttribute('href')).toBe('https://wa.me/79296384878');
    expect(footer.queryByRole('img', { name: 'Habanos Specialist' })).toBeNull();
  });

  it.each(['zh', 'ru', 'en'] as const)('shows the confirmed address and Moscow hours in %s with matching SEO data', (locale) => {
    const site = { ...backendPageFixture.site, address: publicDetails.address[locale], hours: publicDetails.hours[locale], phone: publicDetails.phone, map_url: publicDetails.map_url };
    const page = { ...backendPageFixture, locale, content_locale: locale, site };
    const { container } = render(<Storefront page={page} ageConfirmed />);
    approachMap();
    const footer = within(container.querySelector('footer')!);
    expect(footer.getByText(publicDetails.address[locale])).toBeTruthy();
    expect(footer.queryByRole('link', { name: publicDetails.address[locale] })).toBeNull();
    const map = container.querySelector('iframe')!;
    const embed = new URL(map.getAttribute('src')!);
    expect(embed.searchParams.get('pt')).toBe(`${publicDetails.map_point.join(',')},pm2rdm`);
    expect(embed.searchParams.get('ll')).toBe(publicDetails.map_point.join(','));
    expect(embed.searchParams.get('lang')).toBe(locale === 'ru' ? 'ru_RU' : 'en_RU');
    expect(map.getAttribute('loading')).toBe('lazy');
    expect(map.getAttribute('title')).toBeTruthy();
    expect(footer.getByText(publicDetails.hours[locale])).toBeTruthy();
    expect(container.querySelector('.site-footer-credential')).toBeNull();
    expect(footer.queryByRole('img', { name: 'Habanos Specialist' })).toBeNull();
    expect(footer.getByRole('link', { name: publicDetails.phone }).getAttribute('href')).toBe('tel:+79296384878');
    expect(footer.getByRole('link', { name: 'WhatsApp: +79296384878' }).getAttribute('href')).toBe('https://wa.me/79296384878');
    const structured = storeStructuredData(page, 'https://shop.example') as Array<Record<string, unknown>>;
    expect(structured.find((item) => item['@type'] === 'Store')).toMatchObject({
      address: { streetAddress: publicDetails.address[locale] },
      telephone: '+7 929 638-48-78',
      hasMap: 'https://yandex.com/maps/-/CXVaV4nN',
      openingHours: ['Mo-Sa 12:00-20:00', 'Su 12:00-16:00'],
    });
  });

  it('shows verified storefront facts used by structured data while preserving independent social accounts', () => {
    const site = {
      ...backendPageFixture.site,
      name: 'Verified Store', address: 'Москва, Тестовая ул. 12', phone: '+7 (999) 123-45-67',
      wechat: 'verified-store', map_url: 'https://maps.example/verified-store', hours: 'Mo-Sa 10:00-19:00',
    };
    const page = { ...backendPageFixture, locale: 'ru' as const, site };
    const { container } = render(<Storefront page={page} ageConfirmed />);
    const footer = within(container.querySelector('footer')!);
    const structured = storeStructuredData(page, 'https://shop.example') as Array<Record<string, unknown>>;
    const store = structured.find((item) => item['@type'] === 'Store')!;
    expect(footer.getByRole('img', { name: String(store.name) })).toBeTruthy();
    const address = (store.address as { streetAddress: string }).streetAddress;
    expect(footer.getByText(address)).toBeTruthy();
    expect(footer.queryByRole('link', { name: address })).toBeNull();
    expect(container.querySelector('iframe')).toBeNull();
    expect(footer.getByText(String(store.openingHours))).toBeTruthy();
    const phone = footer.getByRole('link', { name: String(store.telephone) });
    expect(phone.getAttribute('href')).toBe('tel:+79991234567');
    expect(footer.getByText('verified-store')).toBeTruthy();
    expect(footer.queryByRole('link', { name: 'verified-store' })).toBeNull();
    expect(footer.getByRole('link', { name: 'Telegram: +79296384878' }).getAttribute('href')).toBe('https://t.me/+79296384878');
    expect(footer.getByRole('link', { name: 'WhatsApp: +79296384878' }).getAttribute('href')).toBe('https://wa.me/79296384878');
    expect(footer.queryByRole('img', { name: 'Habanos Specialist' })).toBeNull();
    expect(container.querySelector('.site-footer-bottom')?.textContent).toContain('© Verified Store.');

    const contact = vi.fn();
    window.addEventListener('cdt:store-contact', contact, { once: true });
    phone.addEventListener('click', (event) => event.preventDefault(), { once: true });
    fireEvent.click(phone);
    expect(contact.mock.calls[0]?.[0]).toMatchObject({ detail: { kind: 'phone', locale: 'ru', product_id: '5' } });
  });

  it.each(['https://maps.example/store', 'https://yandex.com.evil.example/maps/-/CXVaV4nN', 'javascript:alert(1)', 'invalid-url'])('retains readable contact details without embedding an unsupported map URL (%s)', (map_url) => {
    const { container } = render(<SiteFooter site={{ address: 'Verified address', map_url }} />);
    expect(within(container).getByText('Verified address')).toBeTruthy();
    expect(container.querySelector('iframe')).toBeNull();
  });

  it('shows the configured WeChat account on hover, focus and touch, then dismisses it without leaving the page', () => {
    const { container } = render(<SiteFooter site={{ wechat: 'verified-wechat' }} />);
    const footer = within(container.querySelector('footer')!);
    const trigger = footer.getByRole('button', { name: '微信' });
    expect(trigger.querySelector('svg.wechat-icon')).toBeTruthy();
    expect(footer.queryByRole('tooltip')).toBeNull();
    fireEvent.mouseEnter(trigger.parentElement!);
    expect(within(footer.getByRole('tooltip')).getByText('verified-wechat')).toBeTruthy();
    fireEvent.mouseLeave(trigger.parentElement!);
    expect(footer.queryByRole('tooltip')).toBeNull();
    fireEvent.focus(trigger);
    expect(footer.getByRole('tooltip')).toBeTruthy();
    fireEvent.keyDown(trigger, { key: 'Escape' });
    expect(footer.queryByRole('tooltip')).toBeNull();
    fireEvent.click(trigger);
    expect(footer.getByRole('tooltip')).toBeTruthy();
    fireEvent.pointerDown(document.body);
    expect(footer.queryByRole('tooltip')).toBeNull();
  });
});
