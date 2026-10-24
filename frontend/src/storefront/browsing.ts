import type { StoreLocale, StorePageData, StoreProduct } from "./types";

export type BrowseFilters = NonNullable<StorePageData["filters"]>;
export const emptyFilters: BrowseFilters = { q: "", brands: [], boxes: [], sort: "catalog" };
export const rangeKeys = ["length_min", "length_max", "ring_min", "ring_max", "price_min", "price_max"] as const;
export const browsingKeys = ["q", "brand", "box", "sort", ...rangeKeys, "stock_only"];

export function extraFilterFields(filters: BrowseFilters): Array<{ name: string; value: string }> {
  return [
    ...rangeKeys.flatMap((name) => filters[name] ? [{ name, value: filters[name]! }] : []),
    ...(filters.stock_only ? [{ name: "stock_only", value: "1" }] : []),
  ];
}

export function matchingOffers(offers: StoreProduct["offers"], filters: BrowseFilters) {
  return offers.filter((offer) => {
    const key = offer.sale_unit === "stick" ? "stick" : String(offer.box_size);
    if (filters.boxes.length && !filters.boxes.includes(key)) return false;
    if (filters.stock_only && !offer.in_stock) return false;
    if (filters.price_min || filters.price_max) {
      if (offer.price_rub === null || !Number.isFinite(Number(offer.price_rub))) return false;
      if (filters.price_min && Number(offer.price_rub) < Number(filters.price_min)) return false;
      if (filters.price_max && Number(offer.price_rub) > Number(filters.price_max)) return false;
    }
    return true;
  });
}

export function homePath(locale: StoreLocale): string { return locale === "zh" ? "/" : `/${locale}/`; }
export function catalogPath(locale: StoreLocale): string { return `${locale === "zh" ? "" : `/${locale}`}/catalog`; }

export function filtersFromSearch(search: string): BrowseFilters {
  const params = new URLSearchParams(search);
  const sort = params.get("sort") || "catalog";
  const ranges = Object.fromEntries(rangeKeys.flatMap((key) => {
    const value = params.get(key)?.trim();
    return value && /^(?:\d+(?:\.\d{1,2})?|\.\d{1,2})$/.test(value) && value.length <= 16 ? [[key, value]] : [];
  }));
  return { q: params.get("q") || "", brands: params.getAll("brand"), boxes: params.getAll("box"), sort: ["catalog", "name", "length"].includes(sort) ? sort : "catalog", ...ranges, ...(params.get("stock_only") === "1" ? { stock_only: true } : {}) };
}

export function browseUrl(path: string, filters: BrowseFilters): string {
  const params = new URLSearchParams();
  if (filters.q.trim()) params.set("q", filters.q.trim());
  filters.brands.forEach((brand) => params.append("brand", brand));
  filters.boxes.forEach((box) => params.append("box", box));
  extraFilterFields(filters).forEach(({ name, value }) => params.set(name, value));
  if (filters.sort !== "catalog") params.set("sort", filters.sort);
  return path.split("?")[0] + (params.size ? `?${params}` : "");
}

export function safeBrowsePath(value: string | null, locale: StoreLocale): string | null {
  if (!value || !value.startsWith("/") || value.startsWith("//")) return null;
  try {
    const url = new URL(value, "https://store.invalid");
    if (url.origin !== "https://store.invalid" || !/^\/(?:ru\/|en\/)?(?:catalog\/?|brand\/[^/]+\/?|)$/.test(url.pathname)) return null;
    const sourceLocale = url.pathname.startsWith("/ru/") ? "ru" : url.pathname.startsWith("/en/") ? "en" : "zh";
    if (sourceLocale !== locale) url.searchParams.delete("page");
    const path = url.pathname.replace(/^\/(?:ru|en)(?=\/|$)/, "") || "/";
    return (locale === "zh" ? path : `/${locale}${path}`) + url.search;
  } catch { return null; }
}

export function productLink(path: string, from?: string): string {
  return from ? `${path}?${new URLSearchParams({ from })}` : path;
}
