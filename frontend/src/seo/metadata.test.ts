// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest';
import { findPublicPage, publicPages, site, structuredData, updateDocumentMetadata } from './metadata';

afterEach(() => { document.head.innerHTML = ''; delete document.documentElement.dataset.cdtStatus; delete document.documentElement.dataset.cdtPath; });

describe('public SEO metadata', () => {
  it('links only published equivalent translations and leaves canonical self-referencing', () => {
    for (const page of publicPages) {
      for (const path of Object.values(page.alternates)) expect(findPublicPage(path!)).toBeDefined();
    }
    updateDocumentMetadata('/ru/brand/cohiba', 'fallback');
    expect(document.documentElement.lang).toBe('ru');
    expect(document.querySelector('link[rel="canonical"]')?.getAttribute('href')).toBe(site.origin + '/ru/brand/cohiba');
    expect(document.querySelectorAll('link[hreflang]')).toHaveLength(4);
  });
  it('removes public metadata when navigating to private documents', () => {
    updateDocumentMetadata('/', 'home');
    updateDocumentMetadata('/p/private-token', '客户文档');
    expect(document.querySelector('meta[name="robots"]')?.getAttribute('content')).toContain('noindex');
    expect(document.querySelector('link[rel="canonical"]')).toBeNull();
    expect(document.querySelector('link[hreflang]')).toBeNull();
    expect(document.querySelector('script[data-seo-structured]')).toBeNull();
  });
  it('keeps server 404s excluded even when their path resembles a catalogue route', () => {
    document.documentElement.dataset.cdtStatus = '404';
    document.documentElement.dataset.cdtPath = '/brand/missing';
    updateDocumentMetadata('/brand/missing', '页面不存在');
    expect(document.querySelector('meta[name="robots"]')?.getAttribute('content')).toContain('noindex');
    expect(document.querySelector('link[rel="canonical"]')).toBeNull();
  });
  it('uses confirmed Moscow hours and makes no unheld specialist or product offer claim', () => {
    const data = structuredData(findPublicPage('/contacts')!);
    const business = data['@graph'][0];
    expect(JSON.stringify(business)).toContain('Sunday');
    expect(JSON.stringify(business)).toContain('13:00');
    expect(JSON.stringify(data)).not.toMatch(/Specialist|aggregateRating|offers|price/);
    expect(site.timezone).toBe('Europe/Moscow');
  });
});
