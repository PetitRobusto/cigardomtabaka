import type { StoreLocale, StorePageData } from "./types";
import { storeCopy } from "./copy";
import publicDetails from "../../../storefront/public_details.json";
import { chooseOffer, offerImages } from "./productImages";

export function storePageTitle(page: StorePageData): string {
  return page.seo_title?.trim() || page.title;
}

/** One source for SSR previews and metadata after client-side navigation. */
export function storeOpenGraph(page: StorePageData, origin: string): Array<[string, string]> {
  const locales = { zh: "zh_CN", ru: "ru_RU", en: "en_US" };
  const tags: Array<[string, string]> = [
    ["og:type", "website"], ["og:site_name", page.site.name],
    ["og:title", storePageTitle(page)], ["og:description", page.description],
    ["og:url", new URL(page.path, origin).toString()], ["og:locale", locales[page.locale]],
  ];
  for (const locale of new Set(page.alternates.map((item) => item.locale))) {
    if (locale !== page.locale) tags.push(["og:locale:alternate", locales[locale]]);
  }
  const product = page.product;
  const productImage = product ? offerImages(product, chooseOffer(product.offers))[0]?.url : null;
  const image = productImage || page.site.photo;
  if (image) {
    tags.push(["og:image", new URL(image, origin).toString()]);
    tags.push(["og:image:alt", productImage && product ? product.name : page.site.name]);
  }
  return tags;
}

export function storeStructuredData(page: StorePageData, origin: string): object {
  const homePath = page.locale === "zh" ? "/" : `/${page.locale}/`;
  const home = new URL(homePath, origin).toString();
  const itemListElement = [
    { "@type": "ListItem", position: 1, name: page.site.name, item: home },
    ...page.breadcrumbs.filter((item) => item.path !== homePath && item.label !== storeCopy[page.locale].home).map((item, index) => ({ "@type": "ListItem", position: index + 2, name: item.label, item: new URL(item.path, origin).toString() })),
  ];
  const result: Record<string, unknown>[] = itemListElement.length >= 2
    ? [{ "@context": "https://schema.org", "@type": "BreadcrumbList", itemListElement }] : [];
  // Language home pages describe one domain-level site, not separate sites.
  if (page.kind === "home" && page.path === homePath && page.view !== "catalog") {
    result.push({ "@context": "https://schema.org", "@type": "WebSite", name: page.site.name, url: new URL("/", origin).toString() });
  }
  if (page.site.address || page.site.phone || page.site.map_url || page.site.hours) {
    const store: Record<string, unknown> = { "@context": "https://schema.org", "@type": "Store", name: page.site.name, url: home };
    if (page.site.address) store.address = { "@type": "PostalAddress", streetAddress: page.site.address };
    if (page.site.phone) store.telephone = page.site.phone;
    if (page.site.map_url) store.hasMap = page.site.map_url;
    if (page.site.hours) store.openingHours = page.site.hours === publicDetails.hours[page.locale]
      ? publicDetails.openingHours : page.site.hours;
    result.push(store);
  }
  return result;
}

function meta(key: string, value: string | null, property = false) {
  const attribute = property ? "property" : "name";
  const existing = document.head.querySelector<HTMLMetaElement>(`meta[${attribute}="${key}"]`);
  if (value === null) { existing?.remove(); return; }
  const element = existing || document.createElement("meta");
  element.setAttribute(attribute, key); element.content = value;
  if (!existing) document.head.append(element);
}

export function updateStoreMetadata(page: StorePageData, origin: string, requested: URL) {
  const title = storePageTitle(page);
  document.title = title;
  document.documentElement.lang = page.locale === "zh" ? "zh-CN" : page.locale === "ru" ? "ru-RU" : "en";
  meta("description", page.description);
  const canonical = document.head.querySelector<HTMLLinkElement>('link[rel="canonical"]') || document.createElement("link");
  canonical.rel = "canonical"; canonical.href = new URL(page.path, origin).toString();
  if (!canonical.isConnected) document.head.append(canonical);
  document.head.querySelectorAll('link[rel="alternate"][hreflang]').forEach((element) => element.remove());
  const alternates = page.alternates.length ? [{ locale: "x-default", path: page.alternates.find((item) => item.locale === "zh")?.path || page.alternates[0].path }, ...page.alternates] : [];
  for (const item of alternates) {
    const link = document.createElement("link"); link.rel = "alternate";
    link.hreflang = item.locale === "zh" ? "zh-CN" : item.locale;
    link.href = new URL(item.path, origin).toString(); document.head.append(link);
  }
  meta("robots", page.indexable === false || ["q", "brand", "box", "sort"].some((key) => requested.searchParams.get(key)) ? "noindex, nofollow" : null);
  document.head.querySelectorAll('meta[property^="og:"]').forEach((element) => element.remove());
  for (const [property, content] of storeOpenGraph(page, origin)) {
    const element = document.createElement("meta");
    element.setAttribute("property", property); element.content = content;
    document.head.append(element);
  }
  const jsonLd = document.head.querySelector<HTMLScriptElement>('script[type="application/ld+json"]') || document.createElement("script");
  jsonLd.type = "application/ld+json"; jsonLd.textContent = JSON.stringify(storeStructuredData(page, origin));
  if (!jsonLd.isConnected) document.head.append(jsonLd);
}

export function clearStoreMetadata(title: string, locale?: StoreLocale) {
  if (locale) document.documentElement.lang = locale === "zh" ? "zh-CN" : locale === "ru" ? "ru-RU" : "en";
  document.title = title; meta("description", title); meta("robots", "noindex, nofollow");
  document.head.querySelectorAll('link[rel="canonical"], link[rel="alternate"][hreflang], script[type="application/ld+json"]').forEach((element) => element.remove());
  document.head.querySelectorAll('meta[property^="og:"]').forEach((element) => element.remove());
}

export function markStoreNavigationFailure() { meta("robots", "noindex, nofollow"); }
