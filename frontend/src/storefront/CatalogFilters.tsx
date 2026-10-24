import { useRef, useState } from "react";
import type { StorePageData } from "./types";
import { browseUrl, emptyFilters, extraFilterFields, type BrowseFilters } from "./browsing";
import { useStoreModal } from "./Modal";
import { BrandMark } from "./BrandBrowse";
import { DimensionPresets, PriceRangeSlider } from "./NumericFilters";

type Props = { page: StorePageData; labels: Record<string, string>; filters: BrowseFilters };
function toggle(values: string[], value: string) { return values.includes(value) ? values.filter((item) => item !== value) : [...values, value]; }

function HiddenCriteria({ filters, omit }: { filters: BrowseFilters; omit?: "facets" | "sort" }) {
  return <>
    {filters.q && <input type="hidden" name="q" value={filters.q} />}
    {omit !== "facets" && <>{filters.brands.map((value) => <input type="hidden" name="brand" value={value} key={value} />)}{filters.boxes.map((value) => <input type="hidden" name="box" value={value} key={value} />)}</>}
    {omit !== "facets" && extraFilterFields(filters).map(({ name, value }) => <input type="hidden" name={name} value={value} key={name} />)}
    {omit !== "sort" && filters.sort !== "catalog" && <input type="hidden" name="sort" value={filters.sort} />}
  </>;
}

function FilterFields({ page, labels, draft, setDraft, prefix }: Omit<Props, "filters"> & { draft: BrowseFilters; setDraft: (value: BrowseFilters) => void; prefix: string }) {
  const brands = page.filter_options?.brands || page.navigation?.brands || [];
  const boxes = page.filter_options?.box_sizes || [];
  const hasSticks = page.filter_options?.has_sticks || false;
  const brandOption = (brand: typeof brands[number]) => <label key={brand.slug} htmlFor={`${prefix}-brand-${brand.slug}`}><input id={`${prefix}-brand-${brand.slug}`} type="checkbox" name="brand" value={brand.slug} checked={draft.brands.includes(brand.slug)} onChange={() => setDraft({ ...draft, brands: toggle(draft.brands, brand.slug) })} /><BrandMark brand={brand} /></label>;
  return <>
    <fieldset className="facet"><legend>{labels.brands}</legend>{page.kind === "brand" ? <p>{page.title}</p> : <>{brands.slice(0, 6).map(brandOption)}{brands.length > 6 && <details className="store-facet-more"><summary><span className="when-closed">{labels.expandBrands}</span><span className="when-open">{labels.collapseBrands}</span></summary>{brands.slice(6).map(brandOption)}</details>}</>}</fieldset>
    <fieldset className="facet"><legend>{labels.dimensions}</legend><DimensionPresets kind="length" filters={draft} onChange={setDraft} labels={labels} locale={page.locale} /><DimensionPresets kind="ring" filters={draft} onChange={setDraft} labels={labels} locale={page.locale} /></fieldset>
    <fieldset className="facet"><legend>{labels.priceRange}</legend><PriceRangeSlider filters={draft} onChange={setDraft} labels={labels} locale={page.locale} /></fieldset>
    <fieldset className="facet"><legend>{labels.availability}</legend><label><input type="checkbox" name="stock_only" value="1" checked={!!draft.stock_only} onChange={(event) => setDraft({ ...draft, stock_only: event.target.checked })} />{labels.stockOnly}</label></fieldset>
    {(hasSticks || boxes.length > 0) && <details className="facet store-packaging-filter"><summary>{labels.packaging}</summary>{hasSticks && <label htmlFor={`${prefix}-box-stick`}><input id={`${prefix}-box-stick`} type="checkbox" name="box" value="stick" checked={draft.boxes.includes("stick")} onChange={() => setDraft({ ...draft, boxes: toggle(draft.boxes, "stick") })} />{labels.single}</label>}{boxes.map((size) => <label key={size} htmlFor={`${prefix}-box-${size}`}><input id={`${prefix}-box-${size}`} type="checkbox" name="box" value={size} checked={draft.boxes.includes(String(size))} onChange={() => setDraft({ ...draft, boxes: toggle(draft.boxes, String(size)) })} />{size} {labels.box}</label>)}</details>}
  </>;
}

function DesktopFilters({ page, labels, filters }: Props) {
  const [draft, setDraft] = useState(filters);
  return <form method="get" action={page.path.split("?")[0]} className="facets store-desktop-filters" aria-label={labels.filters}>
    <HiddenCriteria filters={filters} omit="facets" />
    <FilterFields page={page} labels={labels} draft={draft} setDraft={setDraft} prefix="desktop" />
    <button type="submit" className="store-filter-apply">{labels.applyFilters}</button>
    <a className="store-filter-reset" href={page.path.split("?")[0]}>{labels.reset}</a>
  </form>;
}

export function CatalogResults({ page, labels, filters, children }: Props & { children: React.ReactNode }) {
  const drawerRef = useRef<HTMLDialogElement>(null);
  const drawer = useStoreModal(drawerRef);
  const [draft, setDraft] = useState(filters);
  const base = page.path.split("?")[0];
  const brands = page.filter_options?.brands || page.navigation?.brands || [];
  const ranges = [
    { key: "length", min: "length_min", max: "length_max", label: labels.length, unit: " mm" },
    { key: "ring", min: "ring_min", max: "ring_max", label: labels.ringGauge, unit: "" },
    { key: "price", min: "price_min", max: "price_max", label: labels.priceRange, unit: "" },
  ] as const;
  const chips = [
    ...(filters.q ? [{ key: "q", label: `“${filters.q}”`, href: browseUrl(base, { ...filters, q: "" }) }] : []),
    ...filters.brands.map((slug) => ({ key: `brand-${slug}`, label: brands.find((b) => b.slug === slug)?.name || slug, href: browseUrl(base, { ...filters, brands: filters.brands.filter((b) => b !== slug) }) })),
    ...ranges.flatMap(({ key, min, max, label, unit }) => {
      const lower = filters[min], upper = filters[max];
      if (!lower && !upper) return [];
      const range = lower && upper ? (Number(lower) === Number(upper) ? lower : `${lower}–${upper}`) : lower ? `≥ ${lower}` : `≤ ${upper}`;
      return [{ key, label: `${label} ${range}${unit}`, href: browseUrl(base, { ...filters, [min]: undefined, [max]: undefined }) }];
    }),
    ...(filters.stock_only ? [{ key: "stock_only", label: labels.stockOnly, href: browseUrl(base, { ...filters, stock_only: undefined }) }] : []),
    ...filters.boxes.map((size) => ({ key: `box-${size}`, label: size === "stick" ? labels.single : `${size} ${labels.box}`, href: browseUrl(base, { ...filters, boxes: filters.boxes.filter((b) => b !== size) }) })),
  ];
  return <>
    <div className="toolband"><span className="count store-result-count" aria-live="polite">{page.total_products ?? page.products.length} {labels.results}</span><button className="fbtn" type="button" aria-haspopup="dialog" onClick={() => { setDraft(filters); drawer.show(); }}>{labels.filters}</button><span className="sp" />
      <form method="get" action={base} className="store-sort-form"><HiddenCriteria filters={filters} omit="sort" /><label className="sortl">{labels.sort}<select className="sortsel" name="sort" value={filters.sort} onChange={(event) => event.currentTarget.form?.requestSubmit()} aria-label={labels.sort}><option value="catalog">{labels.catalogOrder}</option><option value="name">{labels.nameOrder}</option><option value="length">{labels.lengthOrder}</option></select></label></form>
    </div>
    {chips.length > 0 && <nav className="chips" aria-label={labels.filters}>{chips.map((chip) => <a className="chip" key={chip.key} href={chip.href} aria-label={`${labels.removeFilter}: ${chip.label}`}>{chip.label}<span aria-hidden="true">×</span></a>)}<a className="chip chip-clear" href={base}>{labels.reset}</a></nav>}
    <div className="cat-layout"><DesktopFilters page={page} labels={labels} filters={filters} key={JSON.stringify(filters)} /><div className="store-results">{children}</div></div>
    <dialog ref={drawerRef} className="store-filter-dialog" aria-labelledby="store-filter-title" onClose={drawer.onClose} onClick={drawer.onBackdropClick}>
      <div className="store-drawer-heading"><h2 id="store-filter-title">{labels.filters}</h2><button className="store-modal-close" type="button" aria-label={labels.close} onClick={drawer.close}>×</button></div>
      <form method="get" action={base}><HiddenCriteria filters={filters} omit="facets" /><FilterFields page={page} labels={labels} draft={draft} setDraft={setDraft} prefix="drawer" /><div className="store-drawer-actions"><button type="button" className="store-filter-reset" onClick={() => setDraft({ ...emptyFilters, q: filters.q, sort: filters.sort })}>{labels.reset}</button><button className="store-filter-apply" type="submit">{labels.applyFilters}</button></div></form>
    </dialog>
  </>;
}
