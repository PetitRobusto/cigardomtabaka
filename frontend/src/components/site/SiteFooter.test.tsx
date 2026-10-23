// @vitest-environment jsdom
import { cleanup, fireEvent, render, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { SiteFooter } from './SiteFooter';
import { Storefront } from '../../storefront/Storefront';
import { backendPageFixture } from '../../storefront/fixture';
import { storeStructuredData } from '../../storefront/metadata';
import publicDetails from '../../../../storefront/public_details.json';

afterEach(cleanup);

describe('shared site footer', () => {
  it.each([undefined, { name: ' ', address: '', phone: ' ', wechat: '', map_url: '', hours: ' ' }])('retains the original contact details and channels when store fields are absent (%j)', (site) => {
    const { container } = render(<SiteFooter site={site} />);
    const footer = within(container.querySelector('footer')!);
    expect(footer.getByRole('img', { name: 'CigarDomTabaka' })).toBeTruthy();
    expect(footer.getByText(publicDetails.address.zh)).toBeTruthy();
    expect(footer.getByRole('link', { name: publicDetails.address.zh }).getAttribute('href')).toBe('https://yandex.com/maps/-/CXVaV4nN');
    expect(footer.getByRole('link', { name: '+7 929 638-48-78' }).getAttribute('href')).toBe('tel:+79296384878');
    expect(footer.getByText('WeChat: cigardomtabaka')).toBeTruthy();
    expect(footer.getByRole('link', { name: 'Telegram: +79296384878' }).getAttribute('href')).toBe('https://t.me/+79296384878');
    expect(footer.getByRole('link', { name: 'WhatsApp: +79296384878' }).getAttribute('href')).toBe('https://wa.me/79296384878');
    expect(footer.getByRole('img', { name: 'Habanos Specialist' })).toBeTruthy();
  });

  it.each(['zh', 'ru', 'en'] as const)('shows the confirmed address and Moscow hours in %s with matching SEO data', (locale) => {
    const site = { ...backendPageFixture.site, address: publicDetails.address[locale], hours: publicDetails.hours[locale], phone: publicDetails.phone, map_url: publicDetails.map_url };
    const page = { ...backendPageFixture, locale, content_locale: locale, site };
    const { container } = render(<Storefront page={page} ageConfirmed />);
    const footer = within(container.querySelector('footer')!);
    expect(footer.getByText(publicDetails.address[locale])).toBeTruthy();
    expect(footer.getByRole('link', { name: publicDetails.address[locale] }).getAttribute('href')).toBe('https://yandex.com/maps/-/CXVaV4nN');
    expect(footer.getByText(publicDetails.hours[locale])).toBeTruthy();
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
    expect(footer.getByRole('link', { name: address }).getAttribute('href')).toBe(store.hasMap);
    expect(footer.getByText(String(store.openingHours))).toBeTruthy();
    const phone = footer.getByRole('link', { name: String(store.telephone) });
    expect(phone.getAttribute('href')).toBe('tel:+79991234567');
    expect(footer.getByText('WeChat: verified-store')).toBeTruthy();
    expect(footer.getByRole('link', { name: 'WeChat: verified-store' }).getAttribute('title')).toBe('WeChat: verified-store');
    expect(footer.getByRole('link', { name: 'Telegram: +79296384878' }).getAttribute('href')).toBe('https://t.me/+79296384878');
    expect(footer.getByRole('link', { name: 'WhatsApp: +79296384878' }).getAttribute('href')).toBe('https://wa.me/79296384878');
    expect(footer.getByRole('img', { name: 'Habanos Specialist' })).toBeTruthy();
    expect(container.querySelector('.site-footer-bottom')?.textContent).toContain('© Verified Store.');

    const contact = vi.fn();
    window.addEventListener('cdt:store-contact', contact, { once: true });
    phone.addEventListener('click', (event) => event.preventDefault(), { once: true });
    fireEvent.click(phone);
    expect(contact.mock.calls[0]?.[0]).toMatchObject({ detail: { kind: 'phone', locale: 'ru', product_id: '5' } });
  });
});
