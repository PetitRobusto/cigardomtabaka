import React from "react";
import { SiteHeader, StaffDock } from "../components/site/SiteHeader";
import { SiteFooter } from "../components/site/SiteFooter";
import type { User } from "../store/authStore";
import type { StoreLocale, StorePageData } from "./types";
import { storeCopy } from "./copy";
import { catalogPath, filtersFromSearch, homePath, safeBrowsePath, type BrowseFilters } from "./browsing";
import { ProductCard, ProductPage } from "./ProductDisplay";
import { CatalogResults } from "./CatalogFilters";
import { BrandBrowse, BrandMark } from "./BrandBrowse";

const langTag: Record<StoreLocale, string> = { zh: "zh-CN", ru: "ru-RU", en: "en" };
type Labels = Record<string, string>;
type Props = { page: StorePageData; labels: Labels };

function languageLinks(page: StorePageData, currentUrl: string) {
  const current = new URL(currentUrl, "https://store.invalid");
  return (page.browsing_alternates || page.alternates).map((item) => {
    const url = new URL(item.path, "https://store.invalid");
    if (page.kind === "product") {
      const from = safeBrowsePath(current.searchParams.get("from"), item.locale);
      if (from) url.searchParams.set("from", from);
    } else {
      for (const key of ["q", "brand", "box", "sort"]) {
        const values = current.searchParams.getAll(key);
        if (values.length) { url.searchParams.delete(key); values.forEach((value) => url.searchParams.append(key, value)); }
      }
      // Reviewed catalogues can contain different numbers of pages in each language.
      url.searchParams.delete("page");
      if (item.locale === page.locale && current.searchParams.has("page")) url.searchParams.set("page", current.searchParams.get("page")!);
    }
    if (current.hash === "#store-contact") url.hash = current.hash;
    return { ...item, path: url.pathname + url.search + url.hash };
  });
}

function LanguageLinks({ page, links, labels }: { page: StorePageData; links: StorePageData["alternates"]; labels: Labels }) {
  return <nav className="locale store-languages" aria-label={labels.language}>{links.map((item) => <a key={item.locale} href={item.path} lang={langTag[item.locale]} aria-current={item.locale === page.locale ? "page" : undefined}>{item.locale === "zh" ? "中文" : item.locale === "ru" ? "Русский" : "English"}</a>)}</nav>;
}

export function Storefront({ page, currentUrl = page.path, ageConfirmed = false, busy = false, currency = "RUB", onCurrencyChange, onAgeConfirm, onAgeDecline, user = null, onLogout }: { user?: User | null; onLogout?: () => void; page: StorePageData; currentUrl?: string; ageConfirmed?: boolean; busy?: boolean; currency?: "RUB" | "CNY" | "USD"; onCurrencyChange?: (currency: "RUB" | "CNY" | "USD") => void; onAgeConfirm?: () => void; onAgeDecline?: () => void }) {
  const labels = storeCopy[page.locale];
  const current = new URL(currentUrl, "https://store.invalid");
  const filters = page.filters || filtersFromSearch(current.search);
  const links = languageLinks(page, currentUrl);
  const from = safeBrowsePath(current.searchParams.get("from"), page.locale);
  const product = page.product;
  const isHome = page.kind === "home" && page.view !== "catalog" && !page.filters && !current.searchParams.has("q") && page.pagination.page === 1;
  const crumbs = page.breadcrumbs.filter((crumb) => crumb.path !== homePath(page.locale));
  return <>
    <SiteHeader locale={page.locale} user={user} pathname={current.pathname} languages={links} query={filters.q}
      searchFields={[...filters.brands.map((value) => ({ name: 'brand', value })), ...filters.boxes.map((value) => ({ name: 'box', value })), ...(filters.sort !== 'catalog' ? [{ name: 'sort', value: filters.sort }] : [])]}
      inert={!ageConfirmed} onLogout={onLogout}>
      <div className="mast-r2"><nav className="catnav" aria-label={labels.catalogPage}><button type="button" popoverTarget="store-brands-menu">{labels.brands} ▾</button><a href={catalogPath(page.locale)}>{labels.stockProducts}</a><a href="#store-contact">{labels.storeContact}</a></nav><div className="store-reference-control" role="group" aria-label={labels.currency}>{(["RUB", "CNY", "USD"] as const).map((code) => <button key={code} type="button" data-store-currency={code} aria-pressed={currency === code} onClick={() => onCurrencyChange?.(code)}>{code}</button>)}</div></div>
      <nav popover="auto" id="store-brands-menu" className="store-category-menu" aria-label={labels.brands}>{page.navigation?.brands.map((brand) => <a key={brand.slug} href={brand.path}><BrandMark brand={brand} /></a>)}</nav>
      <small className="store-rates-note" data-rates-note hidden>{labels.ratesNote}</small>
    </SiteHeader>
    <main className="view store-main" inert={!ageConfirmed} aria-busy={busy || undefined}><div className="wrap" key={`${page.locale}:${page.kind}:${product?.id ?? page.path}:${current.search}`}>
      {!isHome && crumbs.length > 0 && <nav className="crumb store-breadcrumbs" aria-label={labels.breadcrumb}><a href={homePath(page.locale)}>{labels.home}</a>{crumbs.map((crumb) => <React.Fragment key={`${crumb.path}:${crumb.label}`}><span aria-hidden="true">/</span><a href={crumb.path}>{crumb.label}</a></React.Fragment>)}</nav>}
      {page.kind === "product" && product ? <><ProductPage product={product} page={page} labels={labels} returnPath={from || undefined} />{page.products.length > 0 && <section className="rel store-section"><div className="sec-h"><h2>{labels.relatedBrand}</h2></div><div className="grid store-product-grid">{page.products.map((item) => <ProductCard product={item} key={item.id} locale={page.locale} labels={labels} from={from || undefined} />)}</div></section>}</> : isHome ? <HomePage page={page} labels={labels} /> : <CatalogPage page={page} labels={labels} filters={filters} currentUrl={current.pathname + current.search} />}
    </div></main>
    <SiteFooter locale={page.locale} customerPage inert={!ageConfirmed} onPhoneContact={() => window.dispatchEvent(new CustomEvent("cdt:store-contact", { detail: { kind: "phone", locale: page.locale, ...(page.product ? { product_id: String(page.product.id) } : {}) } }))} />
    <StaffDock storeLocale={page.locale} user={user} pathname={current.pathname} inert={!ageConfirmed} />
    <AgeGate labels={labels} confirmed={ageConfirmed} onConfirm={onAgeConfirm} onDecline={onAgeDecline} page={page} links={links} />
  </>;
}

function HomePage({ page, labels }: Props) {
  return <>
    <section className="home-head"><div><div className="kicker">{page.site.name}</div><h1>{page.title}</h1>{(page.body || page.description) && <p>{page.body || page.description}</p>}</div><a className="btn-pri" href={catalogPath(page.locale)}>{labels.browseStock} →</a></section>
    <BrandBrowse page={page} labels={labels} />
    <section className="sec store-section"><div className="sec-h"><h2>{labels.stockProducts}</h2><a href={catalogPath(page.locale)}>{labels.allProducts} →</a></div><div className="grid store-product-grid">{page.products.map((product) => <ProductCard key={product.id} product={product} locale={page.locale} labels={labels} from={homePath(page.locale)} />)}</div>{page.products.length === 0 && <p className="store-empty-note">{labels.noResults}</p>}</section>
    <Pagination page={page} labels={labels} />
  </>;
}

function CatalogPage({ page, labels, filters, currentUrl }: Props & { filters: BrowseFilters; currentUrl: string }) {
  return <>
    <section className="cat-head"><h1>{filters.q ? `${labels.searchResults}: “${filters.q}”` : page.title}</h1>{page.kind === "brand" && (page.body || page.description) && <p className="intro">{page.body || page.description}</p>}</section>
    <BrandBrowse page={page} labels={labels} filters={filters} />
    <CatalogResults page={page} labels={labels} filters={filters}>{page.products.length > 0 ? <div className="grid store-product-grid">{page.products.map((product) => <ProductCard key={product.id} product={product} locale={page.locale} labels={labels} from={currentUrl} selectedBoxes={filters.boxes} />)}</div> : <section className="empty"><h2>{labels.noResults}</h2><p>{labels.noResultsBody}</p><a className="store-filter-reset" href={page.path.split("?")[0]}>{labels.reset}</a></section>}<Pagination page={page} labels={labels} /></CatalogResults>
  </>;
}

function Pagination({ page, labels }: Props) {
  if (page.pagination.total_pages < 2) return null;
  return <nav className="store-pagination" aria-label={labels.page}>{page.pagination.previous && <a rel="prev" href={page.pagination.previous}>{labels.prev}</a>}<span>{page.pagination.page} / {page.pagination.total_pages}</span>{page.pagination.next && <a rel="next" href={page.pagination.next}>{labels.next}</a>}</nav>;
}

function AgeGate({ labels, confirmed, onConfirm, onDecline, page, links }: { labels: Labels; confirmed: boolean; onConfirm?: () => void; onDecline?: () => void; page: StorePageData; links: StorePageData["alternates"] }) {
  return <section className="store-age-gate" aria-label={labels.ageTitle} data-age-gate="true" hidden={confirmed}><div className="store-age-dialog" role="dialog" aria-modal="true" aria-labelledby="store-age-title"><LanguageLinks page={page} labels={labels} links={links} /><h2 id="store-age-title">{labels.ageTitle}</h2><p>{labels.ageText}</p><div className="store-age-actions"><button type="button" data-age-confirm="true" onClick={onConfirm}>{labels.confirm}</button><button type="button" data-age-decline="true" onClick={onDecline}>{labels.decline}</button></div></div></section>;
}
