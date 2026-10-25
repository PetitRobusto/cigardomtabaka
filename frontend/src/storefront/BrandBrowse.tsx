import { BRAND_LOGO_LOCAL } from "../utils/priceData";
import { useState } from "react";
import { catalogPath } from "./browsing";
import type { StorePageData } from "./types";

type Brand = NonNullable<StorePageData["navigation"]>["brands"][number];
export function BrandMark({ brand }: { brand: Brand }) {
  const logo = BRAND_LOGO_LOCAL[brand.english_name || ""];
  return <>{logo && <img className="store-brand-logo" src={logo} alt="" loading="lazy" />}<span>{brand.name}</span></>;
}

export function BrandBrowse({ page, labels }: { page: StorePageData; labels: Record<string, string> }) {
  const [expanded, setExpanded] = useState(false);
  const brands = page.navigation?.brands || [];
  if (page.kind === "brand" || !brands.length) return null;
  const base = catalogPath(page.locale);
  const visibleBrands = brands.slice(0, 6);
  const additionalBrands = brands.slice(6);
  const renderBrands = (items: Brand[]) => items.map((brand) =>
    <a className="store-brand-logo-link" key={brand.slug} href={brand.path}><BrandMark brand={brand} /></a>);
  return <section className="store-brand-browser" aria-labelledby="store-brands-title"><div className="sec-h"><h2 id="store-brands-title">{labels.browseBrands}</h2><a href={base}>{labels.allBrands}</a></div><div className="store-brand-logo-grid">{renderBrands(visibleBrands)}</div>{additionalBrands.length > 0 && <div className="store-brand-more"><button type="button" aria-controls="store-brand-extra" aria-expanded={expanded} onClick={() => setExpanded((open) => !open)}>{expanded ? labels.collapseBrands : labels.expandBrands}</button><div className="store-brand-extra" id="store-brand-extra" inert={!expanded}><div className="store-brand-logo-grid">{renderBrands(additionalBrands)}</div></div></div>}</section>;
}
