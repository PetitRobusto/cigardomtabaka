// @vitest-environment jsdom
import React from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { renderToString } from "react-dom/server";
import { afterEach, describe, expect, it } from "vitest";
import { ProductCard } from "./ProductDisplay";
import { commerceCopy } from "./commerceCopy";
import { storeCopy } from "./copy";
import { backendPageFixture } from "./fixture";
import { detailImages, imageDescription, offerImages } from "./productImages";
import { Storefront } from "./Storefront";
import type { StoreProduct } from "./types";

afterEach(cleanup);
const product: StoreProduct = {
  ...backendPageFixture.product!,
  availability: "in_stock",
  image_url: "/single-thumb.jpg",
  images: ["/single.jpg", "/single-second.jpg", "/box10.jpg", "/box25.jpg", "/unknown-box.jpg"],
  image_kinds: { "/single.jpg": "cigar", "/single-second.jpg": "cigar", "/box10.jpg": "packaging", "/box25.jpg": "packaging" },
  image_variants: [
    { url: "/single.jpg", thumbnail_url: "/single-thumb.jpg", image_type: "cigar", box_size: null },
    { url: "/single-second.jpg", thumbnail_url: "/single-second-thumb.jpg", image_type: "cigar", box_size: null },
    { url: "/box10.jpg", thumbnail_url: "/box10-thumb.jpg", image_type: "packaging", box_size: 10 },
    { url: "/box25.jpg", thumbnail_url: "/box25-thumb.jpg", image_type: "packaging", box_size: 25 },
    { url: "/unknown-box.jpg", thumbnail_url: "/unknown-thumb.jpg", image_type: "packaging", box_size: null },
  ],
  offers: [
    { box_size: 10, price_rub: "100.00", in_stock: true },
    { box_size: 25, price_rub: "250.00", in_stock: false },
    { sale_unit: "stick", box_size: null, price_rub: null, in_stock: true },
  ],
};
const main = () => document.querySelector<HTMLImageElement>("[data-gallery-main]");

describe("sale unit photos", () => {
  it.each([
    ['zh', '10支装雪茄盒', '单支雪茄'],
    ['ru', 'коробка на 10 сигар', 'одна сигара'],
    ['en', 'box of 10 cigars', 'single cigar'],
  ] as const)('describes the displayed photo in %s and changes with the photo', (locale, box, single) => {
    const { container } = render(<Storefront page={{ ...backendPageFixture, locale, product }} ageConfirmed />);
    expect(main()?.alt).toBe(`${product.name} — ${box}`);
    expect(container.querySelector<HTMLImageElement>('.store-lightbox img')?.alt).toBe(`${product.name} — ${box}`);
    fireEvent.click(container.querySelectorAll<HTMLButtonElement>('.store-gallery-thumb')[1]);
    expect(main()?.alt).toBe(`${product.name} — ${single}`);
    expect(container.querySelector<HTMLImageElement>('.store-lightbox img')?.alt).toBe(`${product.name} — ${single}`);
    // Labeled thumbnail buttons retain decorative image semantics.
    expect(Array.from(container.querySelectorAll<HTMLImageElement>('.store-gallery-thumb img')).every((img) => img.alt === '')).toBe(true);
  });

  it('uses exact photo metadata on a filtered card and avoids inventing a box size', () => {
    const { container } = render(<ProductCard product={product} locale="en" labels={commerceCopy.en} selectedBoxes={['25']} />);
    expect(container.querySelector<HTMLImageElement>('.store-product-image img')?.alt).toBe(`${product.name} — box of 25 cigars`);
    expect(imageDescription(product, '/unknown-box.jpg', 'en')).toBe(`${product.name} — packaging`);
    expect(imageDescription(product, '/unknown.jpg', 'en')).toBe(`${product.name} — product image`);
  });

  it('identifies the brand when the stored display name contains only the model', () => {
    expect(imageDescription({ ...product, name: 'Robustos', brand: 'Cohiba' }, '/single.jpg', 'en'))
      .toBe('Cohiba Robustos — single cigar');
    expect(imageDescription({ ...product, name: '罗布图', brand: '高希霸' }, '/box10.jpg', 'zh'))
      .toBe('高希霸 罗布图 — 10支装雪茄盒');
    expect(imageDescription({ ...product, name: 'Cohiba Robustos', brand: 'Cohiba' }, '/single.jpg', 'ru'))
      .toBe('Cohiba Robustos — одна сигара');
  });

  it("labels the card by the selected offer's availability", () => {
    const { container, rerender } = render(<ProductCard product={product} locale="en" labels={storeCopy.en} />);
    const card = container.querySelector(".store-product-card")!;
    expect(card.classList.contains("store-product-card-in_stock")).toBe(true);
    expect(card.querySelector(".store-availability")?.textContent).toBe(storeCopy.en.inStock);

    rerender(<ProductCard product={product} locale="en" labels={storeCopy.en} selectedBoxes={["25"]} />);
    expect(card.classList.contains("store-product-card-out_of_stock")).toBe(true);
    expect(card.querySelector(".store-availability")?.textContent).toBe(storeCopy.en.outOfStock);
  });

  it("uses the chosen offer's thumbnail on cards, including filtered single and box offers", () => {
    const { container, rerender } = render(<ProductCard product={product} locale="en" labels={commerceCopy.en} />);
    expect(container.querySelector(".store-product-image img")?.getAttribute("src")).toBe("/box10-thumb.jpg");
    rerender(<ProductCard product={product} locale="en" labels={commerceCopy.en} selectedBoxes={["stick"]} />);
    expect(container.querySelector(".store-product-image img")?.getAttribute("src")).toBe("/single-thumb.jpg");
    rerender(<ProductCard product={product} locale="en" labels={commerceCopy.en} selectedBoxes={["25"]} />);
    expect(container.querySelector(".store-product-image img")?.getAttribute("src")).toBe("/box25-thumb.jpg");
    expect(container.querySelector('[data-price-rub="250.00"]')).not.toBeNull();
  });

  it("synchronizes the gallery and full image with the selected unit and exact box size", () => {
    render(<Storefront page={{ ...backendPageFixture, product }} ageConfirmed />);
    expect(main()?.getAttribute("src")).toBe("/box10.jpg");
    expect(main()?.getAttribute("fetchpriority")).toBe("high");
    expect(main()?.getAttribute("loading")).toBe("eager");
    expect(Array.from(document.querySelectorAll('.store-gallery-thumb img')).map((img) => img.getAttribute('src')))
      .toEqual(['/box10-thumb.jpg', '/single-thumb.jpg', '/single-second-thumb.jpg']);
    fireEvent.click(screen.getByRole("button", { name: "Cigar 2" }));
    expect(main()?.getAttribute("src")).toBe("/single.jpg");
    expect(document.querySelector(".gal-cap")?.textContent).toBe("Cigar");
    expect(document.querySelector('.d-price [data-price-rub="100.00"]')).not.toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /^Single cigar/ }));
    expect(main()?.getAttribute("src")).toBe("/single.jpg");
    expect(document.querySelectorAll(".store-gallery-thumb")).toHaveLength(2);
    expect(Array.from(document.querySelectorAll('.store-gallery-thumb img')).map((img) => img.getAttribute('src')))
      .toEqual(['/single-thumb.jpg', '/single-second-thumb.jpg']);
    fireEvent.click(screen.getByRole("button", { name: "Cigar 2" }));
    expect(main()?.getAttribute("src")).toBe("/single-second.jpg");
    expect(document.querySelector(".store-lightbox img")?.getAttribute("src")).toBe("/single-second.jpg");
    fireEvent.click(screen.getByRole("button", { name: /^25 ct\.\/box/ }));
    expect(main()?.getAttribute("src")).toBe("/box25.jpg");
    expect(Array.from(document.querySelectorAll('.store-gallery-thumb img')).map((img) => img.getAttribute('src')))
      .toEqual(['/box25-thumb.jpg', '/single-thumb.jpg', '/single-second-thumb.jpg']);
    fireEvent.click(screen.getByRole("button", { name: /^Single cigar/ }));
    expect(main()?.getAttribute("src")).toBe("/single.jpg");
  });

  it("honors a single-cigar list context on the initial rendered detail", () => {
    const html = renderToString(<Storefront page={{ ...backendPageFixture, product }} currentUrl={`${product.path}?from=${encodeURIComponent("/en/catalog?box=stick")}`} ageConfirmed />);
    expect(html).toContain('src="/single.jpg"');
    expect(html).not.toContain('src="/box10.jpg"');
    expect(html).not.toContain('src="/box25.jpg"');
  });

  it("keeps a missing box photo blank until a cigar-only auxiliary view is chosen", () => {
    const missing = { ...product, image_kinds: undefined, image_variants: product.image_variants!.filter((image) => image.box_size !== 25 && image.url !== "/single-second.jpg") };
    const { container } = render(<Storefront page={{ ...backendPageFixture, product: missing }} ageConfirmed />);
    fireEvent.click(screen.getByRole("button", { name: /^25 ct\.\/box/ }));
    expect(main()).toBeNull();
    expect(container.querySelector(".store-product-detail-gallery .store-image-placeholder")).not.toBeNull();
    expect(container.querySelector(".store-lightbox img")).toBeNull();
    expect(Array.from(container.querySelectorAll('.store-gallery-thumb img')).map((img) => img.getAttribute('src')))
      .toEqual(['/single-thumb.jpg']);
    fireEvent.click(screen.getByRole("button", { name: "Cigar 1" }));
    expect(main()?.getAttribute("src")).toBe("/single.jpg");
    expect(container.querySelector(".gal-cap")?.textContent).toBe("Cigar");
    expect(container.querySelector('.d-price [data-price-rub="250.00"]')).not.toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /^10 ct\.\/box/ }));
    fireEvent.click(screen.getByRole("button", { name: /^25 ct\.\/box/ }));
    expect(main()).toBeNull();
    expect(offerImages({ ...product, image_variants: [] }, product.offers[0])).toEqual([]);
    expect(offerImages({ ...product, image_variants: product.image_variants!.filter((image) => image.image_type !== "cigar") }, product.offers[2])).toEqual([]);
  });

  it.each(["zh", "ru", "en"] as const)("renders matching packaging before cigar views without other boxes in %s", (locale) => {
    const html = renderToString(<Storefront page={{ ...backendPageFixture, locale, product }} ageConfirmed />);
    const page = new DOMParser().parseFromString(html, "text/html");
    expect(page.querySelector('[data-gallery-main]')?.getAttribute("src")).toBe("/box10.jpg");
    expect(Array.from(page.querySelectorAll('.store-gallery-thumb img')).map((img) => img.getAttribute('src')))
      .toEqual(['/box10-thumb.jpg', '/single-thumb.jpg', '/single-second-thumb.jpg']);
    expect(page.querySelector('.store-product-detail-gallery img[src*="box25"]')).toBeNull();
    expect(page.querySelector('.store-product-detail-gallery img[src*="unknown"]')).toBeNull();
  });

  it("deduplicates auxiliary images and excludes cigar photos associated with another box size", () => {
    const images = product.image_variants!;
    const extra = { ...product, image_variants: [...images, images[0], images[2],
      { url: "/other-box-cigar.jpg", thumbnail_url: "/other-box-thumb.jpg", image_type: "cigar", box_size: 25 },
    ] };
    expect(detailImages(extra, product.offers[0]).map((image) => image.url))
      .toEqual(["/box10.jpg", "/single.jpg", "/single-second.jpg"]);
    expect(offerImages(product, product.offers[0]).map((image) => image.url)).toEqual(["/box10.jpg"]);
  });

  it("retains unoffered catalogue images and supports previously rendered payloads", () => {
    expect(offerImages(product, undefined).map((image) => image.url)).toEqual(product.images);
    expect(offerImages(product, undefined).map((image) => image.thumbnail_url)).toEqual(product.image_variants!.map((image) => image.thumbnail_url));
    expect(offerImages({ ...product, image_variants: undefined }, product.offers[0])[0].url).toBe("/single.jpg");
  });

  it("falls back to the same original when a thumbnail is absent", () => {
    const noThumbnail = { ...product, offers: [product.offers[2]], image_variants: product.image_variants!.map((image) => ({ ...image, thumbnail_url: '' })) };
    const { container } = render(<Storefront page={{ ...backendPageFixture, product: noThumbnail }} ageConfirmed />);
    expect(Array.from(container.querySelectorAll('.store-gallery-thumb img')).map((img) => img.getAttribute('src')))
      .toEqual(['/single.jpg', '/single-second.jpg']);
    fireEvent.click(screen.getByRole('button', { name: 'Cigar 2' }));
    expect(main()?.getAttribute('src')).toBe('/single-second.jpg');
  });

  it("does not carry a single selection into another product opened from a box card", () => {
    const { rerender } = render(<Storefront page={{ ...backendPageFixture, product }} ageConfirmed />);
    fireEvent.click(screen.getByRole("button", { name: /^Single cigar/ }));
    expect(main()?.getAttribute("src")).toBe("/single.jpg");
    const next = { ...product, id: 6, path: "/en/cigar/6/another-cigar" };
    rerender(<Storefront page={{ ...backendPageFixture, path: next.path, product: next }} ageConfirmed />);
    expect(main()?.getAttribute("src")).toBe("/box10.jpg");
  });

  it("shows a failed selected photo without borrowing the other sale unit's image, then recovers on selection", () => {
    render(<Storefront page={{ ...backendPageFixture, product }} ageConfirmed />);
    fireEvent.error(main()!);
    expect(main()).toBeNull();
    expect(document.querySelector(".store-product-detail-gallery .store-image-failure")).not.toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /^Single cigar/ }));
    expect(main()?.getAttribute("src")).toBe("/single.jpg");
  });
});
