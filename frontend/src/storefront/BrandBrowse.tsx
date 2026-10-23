import { BRAND_LOGO_LOCAL } from "../utils/priceData";
import { browseUrl, catalogPath, emptyFilters, type BrowseFilters } from "./browsing";
import type { StorePageData } from "./types";

type Brand = NonNullable<StorePageData["navigation"]>["brands"][number];
export function BrandMark({ brand }: { brand: Brand }) {
  const logo = BRAND_LOGO_LOCAL[brand.english_name || ""];
  return <>{logo && <img className="store-brand-logo" src={logo} alt="" loading="lazy" />}<span>{brand.name}</span></>;
}

export function BrandBrowse({ page, labels, filters = emptyFilters }: { page: StorePageData; labels: Record<string, string>; filters?: BrowseFilters }) {
  const brands = page.navigation?.brands || [];
  if (!brands.length) return null;
  const base = catalogPath(page.locale);
  return <section className="store-brand-browser" aria-labelledby="store-brands-title"><div className="sec-h"><h2 id="store-brands-title">{labels.browseBrands}</h2><a href={browseUrl(base, { ...filters, brands: [] })}>{labels.allBrands}</a></div><div className="store-brand-logo-grid">{brands.map((brand) => {
    const selected = filters.brands.includes(brand.slug);
    const next = selected && filters.brands.length === 1 ? [] : [brand.slug];
    return <a className={`store-brand-logo-link${selected ? " on" : ""}`} key={brand.slug} href={browseUrl(base, { ...filters, brands: next })} aria-current={selected ? "true" : undefined}><BrandMark brand={brand} /></a>;
  })}</div></section>;
}
