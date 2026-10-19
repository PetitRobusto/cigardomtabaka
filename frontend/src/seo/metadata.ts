import content from '../../site-content.json';
import definitions from '../../seo/pages.json';

export type Locale = 'zh-CN' | 'ru' | 'en';
export interface PublicPage {
  path: string;
  locale: Locale;
  kind: 'home' | 'contacts' | 'brand' | 'cigar';
  title: string;
  description: string;
  alternates: Partial<Record<Locale, string>>;
  brandSlug?: string;
  cigarId?: number;
}
export const site = content;
export const publicPages = definitions as PublicPage[];
export const normalizedPath = (path: string) => path === '/' ? '/' : path.replace(/\/+$/, '') + (/^\/(ru|en)\/$/.test(path) ? '/' : '');
export function findPublicPage(path: string) {
  const normalized = normalizedPath(path);
  return publicPages.find(page => page.path === normalized || page.path === `${normalized}/`);
}
export function localeForPath(path: string): Locale {
  return /^\/ru(?:\/|$)/.test(path) ? 'ru' : /^\/en(?:\/|$)/.test(path) ? 'en' : 'zh-CN';
}
export function publicPath(path: string) {
  return Boolean(findPublicPage(path)) || /^\/(brand\/[^/]+|cigar\/\d+(?:\/[^/]+)?)\/?$/.test(path);
}
export function localeHome(locale: Locale) { return locale === 'zh-CN' ? '/' : `/${locale}/`; }
export function localeContacts(locale: Locale) { return locale === 'zh-CN' ? '/contacts' : `/${locale}/contacts`; }

export function structuredData(page: PublicPage) {
  const business = {
    '@type': 'Store', '@id': `${site.origin}/#store`, name: site.name, url: site.origin,
    telephone: site.phone, address: { '@type': 'PostalAddress', streetAddress: 'Молодёжная ул. 3', addressLocality: 'Москва', addressCountry: 'RU' },
    openingHoursSpecification: site.hours.map(hours => ({ '@type': 'OpeningHoursSpecification', dayOfWeek: hours.days, opens: hours.opens, closes: hours.closes })),
  };
  return { '@context': 'https://schema.org', '@graph': [
    business,
    { '@type': 'WebSite', '@id': `${site.origin}/#website`, name: site.name, url: site.origin, inLanguage: ['zh-CN', 'ru', 'en'] },
    { '@type': 'WebPage', '@id': site.origin + page.path, url: site.origin + page.path, name: page.title, description: page.description, inLanguage: page.locale, about: { '@id': `${site.origin}/#store` } },
    ...(page.kind === 'home' ? [] : [{ '@type': 'BreadcrumbList', itemListElement: [
      { '@type': 'ListItem', position: 1, name: site.locales[page.locale].catalog, item: site.origin + localeHome(page.locale) },
      { '@type': 'ListItem', position: 2, name: page.title.replace(` · ${site.name}`, ''), item: site.origin + page.path },
    ] }]),
  ] };
}

export function updateDocumentMetadata(path: string, fallbackTitle: string) {
  const page = findPublicPage(path);
  const initialNotFound = document.documentElement.dataset.cdtStatus === '404' && document.documentElement.dataset.cdtPath === path;
  const isPublic = !initialNotFound && !fallbackTitle.includes('页面不存在') && (page || publicPath(path));
  const description = page?.description || (isPublic ? `${fallbackTitle}。${site.locales['zh-CN'].notice}` : '');
  document.title = page?.title || fallbackTitle;
  document.documentElement.lang = page?.locale || 'zh-CN';
  const setMeta = (name: string, value: string) => {
    let tag = document.querySelector<HTMLMetaElement>(`meta[name="${name}"]`);
    if (!tag) { tag = document.createElement('meta'); tag.name = name; document.head.append(tag); }
    tag.content = value;
  };
  setMeta('description', description);
  setMeta('robots', isPublic ? 'index,follow' : 'noindex,nofollow');
  document.head.querySelectorAll('link[rel="canonical"],link[hreflang],script[data-seo-structured]').forEach(node => node.remove());
  const link = (rel: string, href: string, lang?: string) => {
    const tag = document.createElement('link'); tag.rel = rel; tag.href = href;
    if (lang) tag.hreflang = lang;
    document.head.append(tag);
  };
  if (isPublic) link('canonical', site.origin + (page?.path || normalizedPath(path)));
  if (page) {
    for (const [locale, alternate] of Object.entries(page.alternates)) link('alternate', site.origin + alternate, locale);
    if (page.alternates['zh-CN']) link('alternate', site.origin + page.alternates['zh-CN'], 'x-default');
    const tag = document.createElement('script'); tag.type = 'application/ld+json'; tag.dataset.seoStructured = 'true';
    tag.textContent = JSON.stringify(structuredData(page)); document.head.append(tag);
  }
}
