// @vitest-environment jsdom
import React from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { Storefront } from "./Storefront";
import { BrandBrowse } from "./BrandBrowse";
import { storeCopy } from "./copy";
import { backendPageFixture } from "./fixture";
import type { StorePageData } from "./types";

afterEach(cleanup);
const brands = [
  ["Cohiba", "cohiba"], ["Montecristo", "montecristo"], ["Romeo y Julieta", "romeo-y-julieta"],
  ["Partagás", "partagas"], ["Hoyo de Monterrey", "hoyo-de-monterrey"], ["H. Upmann", "h-upmann"],
].map(([name, slug]) => ({ name, english_name: name, slug, path: `/en/brand/${slug}` }));

function catalog(): StorePageData {
  return { ...backendPageFixture, kind: "home", view: "catalog", path: "/en/catalog", product: null,
    title: "In-stock cigars", body: "", products: [backendPageFixture.product!], total_products: 1,
    navigation: { brands, box_sizes: [10, 25] }, filter_options: { brands, box_sizes: [10, 25] },
    alternates: [{ locale: "en", path: "/en/catalog" }, { locale: "ru", path: "/ru/catalog" }],
  };
}

describe("B2 commerce browsing", () => {
  it("keeps the brand browser hook order when brands arrive after an empty render", () => {
    const page = { ...catalog(), navigation: { brands: [], box_sizes: [] } };
    const { container, rerender } = render(<BrandBrowse page={page} labels={storeCopy.en} />);
    expect(container.querySelector(".store-brand-browser")).toBeNull();
    rerender(<BrandBrowse page={{ ...page, navigation: { brands, box_sizes: [] } }} labels={storeCopy.en} />);
    expect(container.querySelectorAll(".store-brand-logo-link")).toHaveLength(brands.length);
  });

  it("places six canonical brand links before the home product shelf", () => {
    const page = { ...catalog(), view: undefined, path: "/en/" };
    const { container } = render(<Storefront page={page} ageConfirmed />);
    const brandArea = container.querySelector(".store-brand-browser")!;
    const shelf = container.querySelector(".store-product-grid")!;
    expect(brandArea.compareDocumentPosition(shelf) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(Array.from(brandArea.querySelectorAll("img")).map((img) => img.getAttribute("src"))).toEqual(brands.map((brand) => `/media/brand_logos/${brand.slug}.jpg`));
    expect(Array.from(brandArea.querySelectorAll(".store-brand-logo-link")).map((link) => link.textContent)).toEqual(brands.map((brand) => brand.name));
    expect(Array.from(brandArea.querySelectorAll(".store-brand-logo-link")).map((link) => link.getAttribute("href"))).toEqual(brands.map((brand) => brand.path));
    expect(container.querySelectorAll("#store-contact")).toHaveLength(1);
    expect(container.querySelector("#store-contact button")).toBeNull();
    expect(container.querySelector('[popoverTarget="store-box-menu"]')).toBeNull();
    expect(screen.queryByText("Browse by box size")).toBeNull();
  });

  it.each(["zh", "ru", "en"] as const)("links home logos and the brand menu to localized brand pages in %s", (locale) => {
    const prefix = locale === "zh" ? "" : `/${locale}`;
    const localizedBrands = brands.map((brand) => ({ ...brand, path: `${prefix}/brand/${brand.slug}` }));
    const page = { ...catalog(), locale, view: undefined, path: `${prefix}/`, navigation: { brands: localizedBrands, box_sizes: [] } };
    const { container } = render(<Storefront page={page} ageConfirmed />);
    for (const selector of [".store-brand-logo-link", "#store-brands-menu a"]) {
      expect(Array.from(container.querySelectorAll(selector)).map((link) => link.getAttribute("href"))).toEqual(localizedBrands.map((brand) => brand.path));
    }
  });

  it("preserves search, packaging and sort when switching a catalog brand", () => {
    const filters = { q: "Robusto", brands: ["cohiba"], boxes: ["25"], sort: "length" };
    const { container } = render(<BrandBrowse page={{ ...catalog(), filters }} labels={storeCopy.en} filters={filters} />);
    const link = container.querySelector<HTMLAnchorElement>('.store-brand-logo-link[href*="montecristo"]')!;
    const url = new URL(link.href);
    expect(url.pathname).toBe("/en/catalog");
    expect(Object.fromEntries(url.searchParams)).toEqual({ q: "Robusto", brand: "montecristo", box: "25", sort: "length" });
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

  it("starts with ten brands and keeps the remaining brand links expandable and filterable", () => {
    const allBrands = [...brands, ...Array.from({ length: 14 }, (_, index) => ({
      name: `Brand ${index}`, english_name: `Brand ${index}`, slug: `brand-${index}`, path: `/en/brand/brand-${index}`,
    }))];
    const page = { ...catalog(), navigation: { brands: allBrands, box_sizes: [10, 25], has_sticks: true },
      filter_options: { brands: allBrands, box_sizes: [10, 25], has_sticks: true } };
    const { container, rerender } = render(<Storefront page={{ ...page, view: undefined, path: "/en/" }} ageConfirmed />);
    const brandArea = container.querySelector(".store-brand-browser")!;
    const visibleLinks = brandArea.querySelectorAll(":scope > .store-brand-logo-grid .store-brand-logo-link");
    const extraLinks = brandArea.querySelectorAll(".store-brand-extra .store-brand-logo-link");
    const toggle = screen.getByRole("button", { name: "Show more brands" });
    expect(visibleLinks).toHaveLength(10);
    expect(extraLinks).toHaveLength(10);
    expect(Array.from(visibleLinks).map((link) => link.textContent)).toEqual(allBrands.slice(0, 10).map((brand) => brand.name));
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    expect(toggle.getAttribute("aria-controls")).toBe("store-brand-extra");
    expect(brandArea.querySelector(".store-brand-extra")?.hasAttribute("inert")).toBe(true);
    fireEvent.click(toggle);
    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    expect(brandArea.querySelector(".store-brand-extra")?.hasAttribute("inert")).toBe(false);
    const lastBrandLink = Array.from(extraLinks).find((link) => link.textContent?.includes("Brand 13")) as HTMLAnchorElement;
    expect(new URL(lastBrandLink.href).pathname).toBe("/en/brand/brand-13");
    expect(new URL(lastBrandLink.href).search).toBe("");
    fireEvent.click(toggle);
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    expect(brandArea.querySelector(".store-brand-extra")?.hasAttribute("inert")).toBe(true);
    expect(container.querySelector('[popoverTarget="store-box-menu"]')).toBeNull();
    expect(container.querySelector("#store-box-menu")).toBeNull();
    rerender(<Storefront page={page} ageConfirmed />);
    const catalogLastBrandLink = Array.from(container.querySelectorAll<HTMLAnchorElement>(".store-brand-logo-link")).find((link) => link.textContent?.includes("Brand 13"))!;
    expect(new URL(catalogLastBrandLink.href).searchParams.get("brand")).toBe("brand-13");
    expect(container.querySelectorAll('.store-desktop-filters input[name="brand"]')).toHaveLength(20);
    expect(container.querySelector('.store-desktop-filters input[value="stick"]')).not.toBeNull();
    expect(container.querySelector('.store-desktop-filters input[value="25"]')).not.toBeNull();
    expect(container.querySelector('[popoverTarget="store-box-menu"]')).toBeNull();
  });

  it.each([
    ["en", "Show more brands", "Show fewer brands"],
    ["zh", "展开", "收起"],
    ["ru", "Показать ещё бренды", "Скрыть бренды"],
  ] as const)("localizes brand expansion controls in %s", (locale, expand, collapse) => {
    const allBrands = [...brands, ...Array.from({ length: 5 }, (_, index) => ({
      name: `Brand ${index}`, english_name: `Brand ${index}`, slug: `brand-${index}`, path: `/${locale}/brand/brand-${index}`,
    }))];
    const page = { ...catalog(), locale, navigation: { brands: allBrands, box_sizes: [] } };
    const { container } = render(<Storefront page={{ ...page, view: undefined, path: `/${locale}/` }} ageConfirmed />);
    expect(container.querySelectorAll(".store-brand-logo-link")).toHaveLength(11);
    const toggle = screen.getByRole("button", { name: expand });
    fireEvent.click(toggle);
    expect(screen.getByRole("button", { name: collapse }).getAttribute("aria-expanded")).toBe("true");
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
