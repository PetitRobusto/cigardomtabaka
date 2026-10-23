import type { StoreProduct } from "./types";

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
  return urls.map((url, index) => ({ url, thumbnail_url: index === 0 ? product.image_url || url : url }));
}
