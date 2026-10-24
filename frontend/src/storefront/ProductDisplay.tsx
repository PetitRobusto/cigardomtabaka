import { useRef, useState } from "react";
import type { StoreLocale, StorePageData, StoreProduct } from "./types";
import { catalogPath, emptyFilters, filtersFromSearch, matchingOffers, productLink, type BrowseFilters } from "./browsing";
import { useStoreModal } from "./Modal";
import { ReferencePrice } from "./ReferencePrice";
import { chooseOffer, offerImages } from "./productImages";

type Labels = Record<string, string>;
const languageTag = { zh: "zh-CN", ru: "ru-RU", en: "en" };
type Offer = StoreProduct["offers"][number];
function offerKey(offer: Offer) { return offer.sale_unit === "stick" ? "stick" : String(offer.box_size); }
function offerLabel(offer: Offer, labels: Labels) { return offer.sale_unit === "stick" ? labels.single : `${offer.box_size} ${labels.box}`; }
function priceUnit(offer: Offer | undefined, labels: Labels) { return offer?.sale_unit === "stick" ? labels.perStick : labels.perBox; }

export function Availability({ value, labels }: { value: StoreProduct["availability"]; labels: Labels }) {
  return <span className={`status store-availability store-availability-${value}`}>{value === "in_stock" ? labels.inStock : value === "out_of_stock" ? labels.outOfStock : labels.catalog}</span>;
}

export function Price({ amount, locale, labels }: { amount: string; locale: StoreLocale; labels: Labels }) {
  const number = Number(amount);
  const display = Number.isFinite(number) ? new Intl.NumberFormat(languageTag[locale], { style: "currency", currency: "RUB", currencyDisplay: "narrowSymbol", minimumFractionDigits: 0, maximumFractionDigits: 2 }).format(number) : amount;
  return <><span className="store-price-rub" data-price-rub={amount}>{display}</span><ReferencePrice amount={amount} locale={locale} label={labels.referenceShort} /></>;
}

function brandPath(product: StoreProduct, locale: StoreLocale) {
  return `${locale === "zh" ? "" : `/${locale}`}/brand/${product.brand_slug}`;
}

function rememberScroll() {
  try { sessionStorage.setItem(`cdt:store-scroll:${location.pathname}${location.search}`, String(window.scrollY)); } catch { /* Browsing still works without storage. */ }
}

function ProductImage({ src, alt, ...rest }: { src: string; alt: string; loading?: "lazy" | "eager"; fetchPriority?: "high"; "data-gallery-main"?: string }) {
  const [failedUrl, setFailedUrl] = useState<string | null>(null);
  return failedUrl === src ? <span className="store-image-failure" role="img" aria-label={alt}>{alt}</span> : <img src={src} alt={alt} onError={() => setFailedUrl(src)} {...rest} />;
}

export function ProductCard({ product, locale, labels, from, selectedBoxes = [], filters }: { product: StoreProduct; locale: StoreLocale; labels: Labels; from?: string; selectedBoxes?: string[]; filters?: BrowseFilters }) {
  const offers = matchingOffers(product.offers, filters || { ...emptyFilters, boxes: selectedBoxes });
  if (selectedBoxes.length && !offers.length) return null;
  const offer = chooseOffer(offers);
  const image = offerImages(product, offer)[0];
  const availability = product.availability === "catalog" ? "catalog" : offer ? offer.in_stock ? "in_stock" : "out_of_stock" : product.availability;
  const href = productLink(product.path, from);
  return <article className={`pcard store-product-card store-product-card-${availability}`}>
    <a className="pm store-product-image" href={href} onClick={rememberScroll}>{image ? <ProductImage src={image.thumbnail_url || image.url} alt={product.name} loading="lazy" /> : <span className="store-image-placeholder">{product.brand}</span>}</a>
    <div className="pcard-body store-product-copy">
      {product.brand_slug ? <a className="pcard-brand store-product-brand" href={brandPath(product, locale)}>{product.brand}</a> : <span className="pcard-brand">{product.brand}</span>}
      <h3><a className="pcard-name" href={href} onClick={rememberScroll}>{product.name}</a></h3>
      <div className="pcard-price"><span className="price-h">{labels.price}</span><strong className="price-v store-price">{offer?.price_rub ? <Price amount={offer.price_rub} locale={locale} labels={labels} /> : labels.ask}</strong><span className="price-u">RUB ₽ · {priceUnit(offer, labels)}</span></div>
      <div className="pcard-meta"><Availability value={availability} labels={labels} />{offers.map((item) => <span className="boxtag" key={offerKey(item)}>{offerLabel(item, labels)}</span>)}</div>
      <p className="pcard-spec store-product-spec">{product.vitola && <span>{product.vitola}</span>}<span>{[product.length !== null ? `${product.length} mm` : "", product.ring_gauge !== null ? `RG ${product.ring_gauge}` : ""].filter(Boolean).join(" · ")}</span></p>
    </div>
  </article>;
}

function imageCaption(product: StoreProduct, image: string, labels: Labels) {
  return ({ cigar: labels.imgCigar, packaging: labels.imgPackaging, band: labels.imgBand, special: labels.imgSpecial })[product.image_kinds?.[image] || ""] || labels.productImage;
}

export function ProductPage({ product, page, labels, returnPath }: { product: StoreProduct; page: StorePageData; labels: Labels; returnPath?: string }) {
  const [activeImage, setActiveImage] = useState<{ selection: string; url: string } | null>(null);
  const [selectedOffer, setSelectedOffer] = useState<string | null>(null);
  const lightboxRef = useRef<HTMLDialogElement>(null);
  const lightbox = useStoreModal(lightboxRef);
  const requestedFilters = returnPath ? filtersFromSearch(new URL(returnPath, "https://store.invalid").search) : emptyFilters;
  const offer = product.offers.find((item) => offerKey(item) === selectedOffer) || chooseOffer(matchingOffers(product.offers, requestedFilters)) || chooseOffer(product.offers);
  const imageVariants = offerImages(product, offer);
  const images = imageVariants.map((item) => item.url);
  const selection = `${product.id}:${offer ? offerKey(offer) : "catalog"}`;
  const image = activeImage?.selection === selection && images.includes(activeImage.url) ? activeImage.url : images[0];
  const availability = product.availability === "catalog" ? "catalog" : offer ? offer.in_stock ? "in_stock" : "out_of_stock" : product.availability;
  const details = page.body || product.description;
  return <>
    <a className="backlink store-return-link" href={returnPath || catalogPath(page.locale)}>← {labels.previous}</a>
    <article className="detail store-product-detail">
      <div className="store-product-detail-gallery" aria-label={labels.productImages}>
        {image ? <button className="gal-main store-product-detail-media" type="button" onClick={lightbox.show} aria-label={labels.openImage}><ProductImage src={image} alt={product.name} loading="eager" fetchPriority="high" data-gallery-main="true" /></button> : <div className="gal-main store-image-placeholder">{product.brand}</div>}
        {image && <p className="gal-cap">{imageCaption(product, image, labels)}</p>}
        {images.length > 1 && <div className="thumbs store-gallery-thumbs" aria-label={labels.productImages}>{imageVariants.map(({ url: source, thumbnail_url }, index) => <button className={`thumb store-gallery-thumb${source === image ? " on" : ""}`} type="button" key={source} aria-label={`${imageCaption(product, source, labels)} ${index + 1}`} aria-pressed={source === image} onClick={() => setActiveImage({ selection, url: source })}><img src={thumbnail_url || source} alt="" loading="lazy" decoding="async" /></button>)}</div>}
      </div>
      <div className="d-info store-product-detail-copy">
        <p className="store-product-brand">{product.brand_slug ? <a className="d-brand" href={brandPath(product, page.locale)}>{product.brand}</a> : product.brand}</p>
        <h1>{product.name}</h1>
        <div className="d-status"><Availability value={availability} labels={labels} /></div>
        <section className="d-price"><h2>{labels.price}</h2><div className="pv"><strong className="store-price">{offer?.price_rub ? <Price amount={offer.price_rub} locale={page.locale} labels={labels} /> : labels.ask}</strong><span className="pu">RUB ₽ · {priceUnit(offer, labels)}</span></div></section>
        {product.offers.length > 0 && <section className="d-box store-offers"><h2 className="d-h">{labels.packaging}</h2><div className="store-box-options">{product.offers.length === 1 ? <span className="d-boxopt" aria-label={labels.selectedPackaging}>{offerLabel(offer, labels)}</span> : product.offers.map((item) => <button className="d-boxopt" type="button" key={offerKey(item)} aria-pressed={offerKey(offer) === offerKey(item)} onClick={() => { setSelectedOffer(offerKey(item)); setActiveImage(null); }}>{offerLabel(item, labels)}</button>)}</div></section>}
        <p className="d-contact"><a className="store-contact-link" href="#store-contact">{labels.contact}</a></p>
        <h2 className="d-h store-spec-title">{labels.details}</h2>
        <dl className="spec store-specs">{product.vitola && <div><dt>{labels.vitola}</dt><dd>{product.vitola}</dd></div>}{product.length !== null && <div><dt>{labels.length}</dt><dd>{product.length} mm</dd></div>}{product.ring_gauge !== null && <div><dt>{labels.ringGauge}</dt><dd>RG {product.ring_gauge}</dd></div>}{offer && <div><dt>{labels.packaging}</dt><dd>{offerLabel(offer, labels)}</dd></div>}</dl>
        {details && <section className="store-description-section"><h2 className="d-h">{labels.description}</h2><p className="store-description">{details}</p></section>}
      </div>
    </article>
    <dialog ref={lightboxRef} className="store-lightbox" aria-label={labels.productImages} onClose={lightbox.onClose} onClick={lightbox.onBackdropClick}>
      <button type="button" className="store-modal-close" aria-label={labels.close} onClick={lightbox.close}>×</button>
      {image && <><img src={image} alt={product.name} /><p>{imageCaption(product, image, labels)}</p></>}
    </dialog>
  </>;
}
