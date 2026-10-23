import type { StoreLocale, StorePageData } from "./types";

export type BrowseFilters = NonNullable<StorePageData["filters"]>;
export const emptyFilters: BrowseFilters = { q: "", brands: [], boxes: [], sort: "catalog" };

export function homePath(locale: StoreLocale): string { return locale === "zh" ? "/" : `/${locale}/`; }
export function catalogPath(locale: StoreLocale): string { return `${locale === "zh" ? "" : `/${locale}`}/catalog`; }

export function filtersFromSearch(search: string): BrowseFilters {
  const params = new URLSearchParams(search);
  const sort = params.get("sort") || "catalog";
  return { q: params.get("q") || "", brands: params.getAll("brand"), boxes: params.getAll("box"), sort: ["catalog", "name", "length"].includes(sort) ? sort : "catalog" };
}

export function browseUrl(path: string, filters: BrowseFilters): string {
  const params = new URLSearchParams();
  if (filters.q.trim()) params.set("q", filters.q.trim());
  filters.brands.forEach((brand) => params.append("brand", brand));
  filters.boxes.forEach((box) => params.append("box", box));
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
