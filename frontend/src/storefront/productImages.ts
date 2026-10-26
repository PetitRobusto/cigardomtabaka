import type { StoreProduct } from "./types";

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
