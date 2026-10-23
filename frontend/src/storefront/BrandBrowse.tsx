import { BRAND_LOGO_LOCAL } from "../utils/priceData";
import { useState } from "react";
import { browseUrl, catalogPath, emptyFilters, type BrowseFilters } from "./browsing";
import type { StorePageData } from "./types";

type Brand = NonNullable<StorePageData["navigation"]>["brands"][number];
export function BrandMark({ brand }: { brand: Brand }) {
  const logo = BRAND_LOGO_LOCAL[brand.english_name || ""];
  return <>{logo && <img className="store-brand-logo" src={logo} alt="" loading="lazy" />}<span>{brand.name}</span></>;
}

export function BrandBrowse({ page, labels, filters = emptyFilters }: { page: StorePageData; labels: Record<string, string>; filters?: BrowseFilters }) {
  const [expanded, setExpanded] = useState(false);
  const brands = page.navigation?.brands || [];
  if (!brands.length) return null;
  const base = catalogPath(page.locale);
  const isHome = page.kind === "home" && page.view !== "catalog" && !page.filters && page.pagination.page === 1;
  const visibleBrands = brands.slice(0, 10);
  const additionalBrands = brands.slice(10);
  const renderBrands = (items: Brand[]) => items.map((brand) => {
    const selected = filters.brands.includes(brand.slug);
    const next = selected && filters.brands.length === 1 ? [] : [brand.slug];
    return <a className={`store-brand-logo-link${selected ? " on" : ""}`} key={brand.slug} href={isHome ? brand.path : browseUrl(base, { ...filters, brands: next })} aria-current={selected ? "true" : undefined}><BrandMark brand={brand} /></a>;
  });
  return <section className="store-brand-browser" aria-labelledby="store-brands-title"><div className="sec-h"><h2 id="store-brands-title">{labels.browseBrands}</h2><a href={browseUrl(base, { ...filters, brands: [] })}>{labels.allBrands}</a></div><div className="store-brand-logo-grid">{renderBrands(visibleBrands)}</div>{additionalBrands.length > 0 && <div className="store-brand-more"><button type="button" aria-controls="store-brand-extra" aria-expanded={expanded} onClick={() => setExpanded((open) => !open)}>{expanded ? labels.collapseBrands : labels.expandBrands}</button><div className="store-brand-extra" id="store-brand-extra" inert={!expanded}><div className="store-brand-logo-grid">{renderBrands(additionalBrands)}</div></div></div>}</section>;
}
