import type { StoreLocale, StorePageData } from "./types";
import { storeCopy } from "./copy";

export function storeStructuredData(page: StorePageData, origin: string): object {
  const homePath = page.locale === "zh" ? "/" : `/${page.locale}/`;
  const home = new URL(homePath, origin).toString();
  const itemListElement = [
    { "@type": "ListItem", position: 1, name: page.site.name, item: home },
    ...page.breadcrumbs.filter((item) => item.path !== homePath && item.label !== storeCopy[page.locale].home).map((item, index) => ({ "@type": "ListItem", position: index + 2, name: item.label, item: new URL(item.path, origin).toString() })),
  ];
  const result: Record<string, unknown>[] = [{ "@context": "https://schema.org", "@type": "BreadcrumbList", itemListElement }];
  if (page.site.address || page.site.phone || page.site.map_url || page.site.hours) {
    const store: Record<string, unknown> = { "@context": "https://schema.org", "@type": "Store", name: page.site.name, url: home };
    if (page.site.address) store.address = { "@type": "PostalAddress", streetAddress: page.site.address };
    if (page.site.phone) store.telephone = page.site.phone;
    if (page.site.map_url) store.hasMap = page.site.map_url;
    if (page.site.hours) store.openingHours = page.site.hours;
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
  document.title = page.title;
  document.documentElement.lang = page.locale === "zh" ? "zh-CN" : page.locale === "ru" ? "ru-RU" : "en";
  meta("description", page.description);
  const canonical = document.head.querySelector<HTMLLinkElement>('link[rel="canonical"]') || document.createElement("link");
  canonical.rel = "canonical"; canonical.href = new URL(page.path, origin).toString();
  if (!canonical.isConnected) document.head.append(canonical);
  document.head.querySelectorAll('link[rel="alternate"][hreflang]').forEach((element) => element.remove());
  const alternates = [{ locale: "x-default", path: page.alternates.find((item) => item.locale === "zh")?.path || page.path }, ...page.alternates];
  for (const item of alternates) {
    const link = document.createElement("link"); link.rel = "alternate";
    link.hreflang = item.locale === "zh" ? "zh-CN" : item.locale;
    link.href = new URL(item.path, origin).toString(); document.head.append(link);
  }
  meta("robots", ["q", "brand", "box", "sort"].some((key) => requested.searchParams.get(key)) ? "noindex, nofollow" : null);
  meta("og:type", "website", true); meta("og:title", page.title, true);
  meta("og:description", page.description, true); meta("og:url", canonical.href, true);
  const image = page.product?.image_url || page.site.photo;
  meta("og:image", image ? new URL(image, origin).toString() : null, true);
  const jsonLd = document.head.querySelector<HTMLScriptElement>('script[type="application/ld+json"]') || document.createElement("script");
  jsonLd.type = "application/ld+json"; jsonLd.textContent = JSON.stringify(storeStructuredData(page, origin));
  if (!jsonLd.isConnected) document.head.append(jsonLd);
}

export function clearStoreMetadata(title: string, locale?: StoreLocale) {
  if (locale) document.documentElement.lang = locale === "zh" ? "zh-CN" : locale === "ru" ? "ru-RU" : "en";
  document.title = title; meta("description", title); meta("robots", "noindex, nofollow");
  document.head.querySelectorAll('link[rel="canonical"], link[rel="alternate"][hreflang], script[type="application/ld+json"]').forEach((element) => element.remove());
  for (const property of ["og:title", "og:description", "og:url", "og:image"]) meta(property, null, true);
}

export function markStoreNavigationFailure() { meta("robots", "noindex, nofollow"); }
