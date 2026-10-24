// @vitest-environment jsdom
import React from "react";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { HomeHero } from "./HomeHero";

afterEach(cleanup);

describe("storefront home hero", () => {
  it.each([
    ["zh", "在莫斯科，探索古巴雪茄的魅力"],
    ["en", "In Moscow, discover the charm of"],
    ["ru", "Откройте для себя в Москве"],
  ] as const)("renders the %s hero copy and five keyboard reachable catalog links", (locale, title) => {
    const catalogUrl = locale === "zh" ? "/catalog" : `/${locale}/catalog`;
    const stockUrl = `${catalogUrl}?stock_only=1`;
    const { container } = render(<HomeHero locale={locale} catalogUrl={catalogUrl} stockUrl={stockUrl} />);

    expect(screen.getByRole("heading", { level: 1 }).textContent).toContain(title);
    expect(container.querySelectorAll(".store-home-hero__stage img")).toHaveLength(5);
    expect(Array.from(container.querySelectorAll<HTMLAnchorElement>(".store-home-hero__stage a"))).toHaveLength(5);
    expect(Array.from(container.querySelectorAll<HTMLAnchorElement>(".store-home-hero__stage a")).every((link) => link.href.endsWith(catalogUrl))).toBe(true);
    expect(container.querySelector<HTMLAnchorElement>(".store-home-hero__primary")?.getAttribute("href")).toBe("#store-contact");
    expect(container.querySelector<HTMLAnchorElement>(".store-home-hero__secondary")?.getAttribute("href")).toBe(stockUrl);
    expect(screen.getByRole("link", { name: /Cohiba BHK 56/ })).toBeTruthy();
  });
});
