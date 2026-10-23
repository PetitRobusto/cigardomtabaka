// @vitest-environment jsdom
import React from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { Storefront } from "./Storefront";
import { backendPageFixture } from "./fixture";
import type { StorePageData } from "./types";

afterEach(cleanup);
const brands = [
  ["Cohiba", "cohiba"], ["Montecristo", "montecristo"], ["Romeo y Julieta", "romeo-y-julieta"],
  ["Partagás", "partagas"], ["Hoyo de Monterrey", "hoyo-de-monterrey"], ["H. Upmann", "h-upmann"],
].map(([name, slug]) => ({ name, english_name: name, slug, path: `/en/catalog?brand=${slug}` }));

function catalog(): StorePageData {
  return { ...backendPageFixture, kind: "home", view: "catalog", path: "/en/catalog", product: null,
    title: "In-stock cigars", body: "", products: [backendPageFixture.product!], total_products: 1,
    navigation: { brands, box_sizes: [10, 25] }, filter_options: { brands, box_sizes: [10, 25] },
    alternates: [{ locale: "en", path: "/en/catalog" }, { locale: "ru", path: "/ru/catalog" }],
  };
}

describe("B2 commerce browsing", () => {
  it("places real six-brand logo filters before the product shelf", () => {
    const page = { ...catalog(), view: undefined, path: "/en/" };
    const { container } = render(<Storefront page={page} ageConfirmed />);
    const brandArea = container.querySelector(".store-brand-browser")!;
    const shelf = container.querySelector(".store-product-grid")!;
    expect(brandArea.compareDocumentPosition(shelf) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(Array.from(brandArea.querySelectorAll("img")).map((img) => img.getAttribute("src"))).toEqual(brands.map((brand) => `/media/brand_logos/${brand.slug}.jpg`));
    expect(Array.from(brandArea.querySelectorAll(".store-brand-logo-link")).map((link) => link.textContent)).toEqual(brands.map((brand) => brand.name));
    expect(container.querySelectorAll("#store-contact")).toHaveLength(1);
    expect(container.querySelector("#store-contact button")).toBeNull();
    expect(container.querySelector('[popoverTarget="store-box-menu"]')).toBeNull();
    expect(screen.queryByText("Browse by box size")).toBeNull();
  });

  it("submits combined criteria as native GET fields and keeps them through language switches", () => {
    const page = { ...catalog(), filters: { q: "BHK", brands: ["cohiba"], boxes: ["10"], sort: "length" } };
    const { container } = render(<Storefront page={page} currentUrl="/en/catalog?q=BHK&brand=cohiba&box=10&sort=length" ageConfirmed />);
    const sidebar = container.querySelector<HTMLFormElement>(".store-desktop-filters")!;
    fireEvent.click(sidebar.querySelector('input[value="partagas"]')!);
    expect(new FormData(sidebar).getAll("brand")).toEqual(["cohiba", "partagas"]);
    expect(new FormData(sidebar).getAll("box")).toEqual(["10"]);
    expect(new FormData(sidebar).get("q")).toBe("BHK");
    const href = container.querySelector<HTMLAnchorElement>('.store-header .store-languages a[lang="ru-RU"]')!.href;
    const url = new URL(href);
    expect(url.pathname).toBe("/ru/catalog");
    expect(url.searchParams.get("sort")).toBe("length");
    expect(url.searchParams.get("brand")).toBe("cohiba");
  });

  it("changes price and stock together when selecting an actual box offer", () => {
    const page = { ...backendPageFixture, product: { ...backendPageFixture.product!, availability: "in_stock" as const, offers: [
      { box_size: 10, price_rub: null, in_stock: true }, { box_size: 25, price_rub: "12345.00", in_stock: false },
    ] } };
    const { container } = render(<Storefront page={page} ageConfirmed />);
    expect(container.querySelector(".d-price")?.textContent).toContain("Ask for price");
    fireEvent.click(screen.getByRole("button", { name: "25 ct./box" }));
    expect(screen.getByText("Temporarily unavailable")).toBeTruthy();
    expect(container.querySelector('[data-price-rub="12345.00"]')).toBeTruthy();
  });

  it("uses the filtered box offer consistently on cards and when opening its detail", () => {
    const product = { ...backendPageFixture.product!, availability: "in_stock" as const, offers: [
      { box_size: 10, price_rub: "100.00", in_stock: true }, { box_size: 25, price_rub: "250.00", in_stock: false },
    ] };
    const page = { ...catalog(), products: [product], filters: { q: "", brands: [], boxes: ["25"], sort: "catalog" } };
    const { container, rerender } = render(<Storefront page={page} currentUrl="/en/catalog?box=25" ageConfirmed />);
    const card = container.querySelector(".store-product-card")!;
    expect(card.querySelector('[data-price-rub="250.00"]')).toBeTruthy();
    expect(card.querySelector('[data-price-rub="100.00"]')).toBeNull();
    expect(card.textContent).toContain("Temporarily unavailable");
    expect(card.querySelector(".boxtag")?.textContent).toBe("25 ct./box");
    rerender(<Storefront page={{ ...backendPageFixture, product }} currentUrl={`${product.path}?from=${encodeURIComponent("/en/catalog?box=25")}`} ageConfirmed />);
    expect(container.querySelector('.d-price [data-price-rub="250.00"]')).toBeTruthy();
  });

  it("resets translated list pagination while preserving all criteria", () => {
    const page = { ...catalog(), path: "/en/catalog?page=2", browsing_alternates: [{ locale: "en" as const, path: "/en/catalog" }, { locale: "ru" as const, path: "/ru/catalog" }] };
    const { container } = render(<Storefront page={page} currentUrl="/en/catalog?box=10&sort=length&page=2" ageConfirmed />);
    const url = new URL(container.querySelector<HTMLAnchorElement>('.store-header .store-languages a[lang="ru-RU"]')!.href);
    expect(url.searchParams.has("page")).toBe(false);
    expect(url.searchParams.get("box")).toBe("10");
    expect(url.searchParams.get("sort")).toBe("length");
  });

  it("keeps the same priced offer from a multi-box sold-out list through detail", () => {
    const product = { ...backendPageFixture.product!, offers: [{ box_size: 10, price_rub: null, in_stock: false }, { box_size: 25, price_rub: "250.00", in_stock: false }] };
    const page = { ...catalog(), products: [product], filters: { q: "", brands: [], boxes: ["10", "25"], sort: "catalog" } };
    const { container, rerender } = render(<Storefront page={page} currentUrl="/en/catalog?box=10&box=25" ageConfirmed />);
    expect(container.querySelector('.store-product-card [data-price-rub="250.00"]')).toBeTruthy();
    rerender(<Storefront page={{ ...backendPageFixture, product }} currentUrl={`${product.path}?from=${encodeURIComponent("/en/catalog?box=10&box=25")}`} ageConfirmed />);
    expect(container.querySelector('.d-price [data-price-rub="250.00"]')).toBeTruthy();
  });

  it("retains the list context and contact anchor when changing a product language", () => {
    const source = "/en/catalog?q=BHK&box=10&sort=length";
    const currentUrl = `${backendPageFixture.path}?${new URLSearchParams({ from: source })}#store-contact`;
    const { container } = render(<Storefront page={backendPageFixture} currentUrl={currentUrl} ageConfirmed />);
    expect(container.querySelector(".store-return-link")?.getAttribute("href")).toBe(source);
    const url = new URL(container.querySelector<HTMLAnchorElement>('.store-header .store-languages a[lang="ru-RU"]')!.href);
    expect(url.hash).toBe("#store-contact");
    expect(url.searchParams.get("from")).toBe("/ru/catalog?q=BHK&box=10&sort=length");
  });

  it("shows single-cigar packaging on the home shelf and as a list filter", () => {
    const product = { ...backendPageFixture.product!, availability: "in_stock" as const, offers: [
      { box_size: 10, price_rub: "100.00", in_stock: true },
      { sale_unit: "stick" as const, box_size: null, price_rub: null, in_stock: true },
    ] };
    const page = { ...catalog(), products: [product], filter_options: { brands, box_sizes: [10], has_sticks: true } };
    const { container, rerender } = render(<Storefront page={{ ...page, view: undefined, path: "/en/" }} ageConfirmed />);
    expect(container.querySelector(".store-product-card")?.textContent).toContain("Single cigar");
    expect(container.querySelector('[name="box"]')).toBeNull();
    rerender(<Storefront page={page} ageConfirmed />);
    const sidebar = container.querySelector<HTMLFormElement>(".store-desktop-filters")!;
    fireEvent.click(sidebar.querySelector('input[value="stick"]')!);
    expect(new FormData(sidebar).getAll("box")).toEqual(["stick"]);
  });

  it("keeps a single-cigar inquiry separate from a priced box through detail and selection", () => {
    const product = { ...backendPageFixture.product!, availability: "in_stock" as const, offers: [
      { box_size: 10, price_rub: "100.00", in_stock: true },
      { sale_unit: "stick" as const, box_size: null, price_rub: null, in_stock: true },
    ] };
    const filters = { q: "", brands: [], boxes: ["stick"], sort: "catalog" };
    const { container, rerender } = render(<Storefront page={{ ...catalog(), products: [product], filters }} currentUrl="/en/catalog?box=stick" ageConfirmed />);
    const card = container.querySelector(".store-product-card")!;
    expect(card.textContent).toContain("Ask for price");
    expect(card.textContent).toContain("per cigar");
    expect(card.querySelector("[data-price-rub]")).toBeNull();
    expect(card.querySelector(".boxtag")?.textContent).toBe("Single cigar");
    rerender(<Storefront page={{ ...backendPageFixture, product }} currentUrl={`${product.path}?from=${encodeURIComponent("/en/catalog?box=stick")}`} ageConfirmed />);
    expect(container.querySelector(".d-price")?.textContent).toContain("Ask for price");
    expect(container.querySelector(".d-price")?.textContent).toContain("per cigar");
    expect(screen.getByRole("button", { name: "Single cigar" }).getAttribute("aria-pressed")).toBe("true");
    fireEvent.click(screen.getByRole("button", { name: "10 ct./box" }));
    expect(container.querySelector('.d-price [data-price-rub="100.00"]')).toBeTruthy();
    expect(container.querySelector(".d-price")?.textContent).toContain("per box");
    fireEvent.click(screen.getByRole("button", { name: "Single cigar" }));
    expect(container.querySelector(".d-price [data-price-rub]")).toBeNull();
  });
});
