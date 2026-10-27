// @vitest-environment jsdom
import React from "react";
import { cleanup, fireEvent, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { Storefront } from "./Storefront";
import { backendPageFixture } from "./fixture";
import { storeCopy } from "./copy";
import type { StoreLocale, StorePageData } from "./types";

afterEach(cleanup);

function catalog(locale: StoreLocale = "en"): StorePageData {
  return {
    ...backendPageFixture, locale, kind: "home", view: "catalog", product: null,
    path: `${locale === "zh" ? "" : `/${locale}`}/catalog`,
    products: [{ ...backendPageFixture.product!, offers: [{ box_size: 25, price_rub: null, in_stock: true }] }],
    total_products: 1,
    filter_options: { brands: [], box_sizes: [25], has_prices: false },
  };
}

describe("price filter availability", () => {
  it.each(["zh", "en", "ru"] as const)("keeps inquiry products and other filters without an empty price scale in %s", (locale) => {
    const { container } = render(<Storefront page={catalog(locale)} ageConfirmed />);
    for (const selector of [".store-desktop-filters", ".store-filter-dialog form"]) {
      const form = container.querySelector<HTMLFormElement>(selector)!;
      expect(form.querySelector(".numeric-price")).toBeNull();
      expect(form.textContent).not.toContain("₽0");
      expect(form.querySelector('input[name="stock_only"]')).not.toBeNull();
      expect(form.querySelector('input[name="box"][value="25"]')).not.toBeNull();
      expect(new FormData(form).has("price_min")).toBe(false);
      expect(new FormData(form).has("price_max")).toBe(false);
    }
    expect(container.querySelectorAll(".store-product-card")).toHaveLength(1);
    expect(container.querySelector(".store-product-card")?.textContent).toContain(storeCopy[locale].ask);
  });

  it("keeps price controls when the base catalogue has prices but this result page has none", () => {
    const page = catalog();
    const { container } = render(<Storefront page={{ ...page, products: [], total_products: 0,
      filter_options: { ...page.filter_options!, has_prices: true },
    }} ageConfirmed />);
    expect(container.querySelectorAll(".numeric-price")).toHaveLength(2);
  });

  it("lets visitors clear a saved price range after the last public price is removed", () => {
    const page = { ...catalog(), products: [], total_products: 0,
      filters: { q: "", brands: [], boxes: ["25"], sort: "catalog", price_min: "100", price_max: "500", stock_only: true },
    };
    const { container } = render(<Storefront page={page} ageConfirmed />);
    expect(container.querySelectorAll(".numeric-price")).toHaveLength(2);
    const sidebar = container.querySelector<HTMLFormElement>(".store-desktop-filters")!;
    expect(new FormData(sidebar).get("price_min")).toBe("100");
    expect(new FormData(sidebar).get("price_max")).toBe("500");
    const remove = container.querySelector<HTMLAnchorElement>('.chip[aria-label^="Remove filter: Price"]')!;
    expect(remove).not.toBeNull();
    const url = new URL(remove.href);
    expect(url.searchParams.has("price_min")).toBe(false);
    expect(url.searchParams.has("price_max")).toBe(false);
    expect(url.searchParams.get("stock_only")).toBe("1");
    expect(url.searchParams.get("box")).toBe("25");
    fireEvent.click(container.querySelector(".store-filter-dialog .store-filter-reset")!);
    const drawer = container.querySelector<HTMLFormElement>(".store-filter-dialog form")!;
    expect(drawer.querySelector(".numeric-price")).toBeNull();
    expect(new FormData(drawer).has("price_min")).toBe(false);
    expect(new FormData(drawer).has("price_max")).toBe(false);
  });

  it("retains filters for cached payloads without the new availability field", () => {
    const page = catalog();
    const { container } = render(<Storefront page={{ ...page,
      filter_options: { brands: [], box_sizes: [25] },
    }} ageConfirmed />);
    expect(container.querySelectorAll(".numeric-price")).toHaveLength(2);
  });
});
