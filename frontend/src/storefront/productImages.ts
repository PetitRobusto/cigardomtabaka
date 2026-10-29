import type { StoreLocale, StoreProduct } from "./types";

/** Describe the photo's reviewed metadata, independently of the selected offer. */
export function imageDescription(product: StoreProduct, url: string, locale: StoreLocale) {
  const image = product.image_variants?.find((item) => item.url === url);
  const kind = image?.image_type || product.image_kinds?.[url] || "";
  const size = image?.box_size;
  const descriptions: Record<StoreLocale, Record<string, string>> = {
    zh: { cigar: "单支雪茄", packaging: size ? `${size}支装雪茄盒` : "雪茄包装", band: "雪茄茄标", special: size ? `${size}支装特别包装` : "特别包装", unknown: "商品图片" },
    ru: { cigar: "одна сигара", packaging: size ? `коробка на ${size} сигар` : "упаковка", band: "сигарный бант", special: size ? `специальная упаковка на ${size} сигар` : "специальная упаковка", unknown: "изображение товара" },
    en: { cigar: "single cigar", packaging: size ? `box of ${size} cigars` : "packaging", band: "cigar band", special: size ? `special packaging of ${size} cigars` : "special packaging", unknown: "product image" },
  };
  const name = product.name.toLocaleLowerCase().includes(product.brand.toLocaleLowerCase())
    ? product.name : `${product.brand} ${product.name}`;
  return `${name} — ${descriptions[locale][kind] || descriptions[locale].unknown}`;
}

/** Shared default selection for the visible product and its canonical preview. */
export function chooseOffer(offers: StoreProduct["offers"]) {
  return offers.find((item) => item.in_stock) || offers.find((item) => item.price_rub) || offers[0];
}

/** Only reviewed metadata can associate a photo with a sale unit or box size. */
export function offerImages(product: StoreProduct, offer: StoreProduct["offers"][number] | undefined) {
  if (product.image_variants !== undefined && offer) {
    return product.image_variants.filter((image) => image.url && (
      offer.sale_unit === "stick"
        ? image.image_type === "cigar"
        : offer.box_size !== null && image.box_size === offer.box_size
          && (image.image_type === "packaging" || image.image_type === "special")
    ));
  }

  // Unoffered catalogue entries and cached payloads from before metadata support.
  const urls = product.images.length ? product.images : product.image_url ? [product.image_url] : [];
  return urls.map((url, index) => ({
    url,
    thumbnail_url: product.image_variants?.find((image) => image.url === url)?.thumbnail_url
      || (index === 0 ? product.image_url || url : url),
  }));
}

/** Detail views can also show this cigar, without borrowing another package's photo. */
export function detailImages(product: StoreProduct, offer: StoreProduct["offers"][number] | undefined) {
  const selected = offerImages(product, offer);
  if (!product.image_variants || !offer || offer.sale_unit === "stick") return selected;
  const auxiliary = product.image_variants.filter((image) => image.image_type === "cigar" && image.box_size === null);
  const seen = new Set<string>();
  return [...selected, ...auxiliary].filter((image) => {
    if (!image.url || seen.has(image.url)) return false;
    seen.add(image.url);
    return true;
  });
}
