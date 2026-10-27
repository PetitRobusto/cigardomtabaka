// @vitest-environment jsdom
import React from "react";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { HomeHero } from "./HomeHero";
import { Storefront } from "./Storefront";
import { backendPageFixture } from "./fixture";
import type { StoreHeroLinks } from "./types";

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

  it.each(["zh", "en", "ru"] as const)("uses localized published targets from the %s page payload", (locale) => {
    const prefix = locale === "zh" ? "" : `/${locale}`;
    const hero_links: StoreHeroLinks = {
      bhk56: `${prefix}/brand/cohiba`,
      siglo: `${prefix}/cigar/101/cohiba-siglo-vi`,
      casilda: `${prefix}/brand/trinidad`,
      bhk52: `${prefix}/brand/cohiba`,
      ingenios: `${prefix}/brand/trinidad`,
    };
    const page = { ...backendPageFixture, locale, kind: "home" as const, path: `${prefix}/`, product: null, hero_links };
    const { container } = render(<Storefront page={page} ageConfirmed />);
    const names = ["Cohiba BHK 56", "Cohiba Siglo VI", "Trinidad Casilda · Colección Habanos", "Cohiba BHK 52", "Trinidad Ingenios · Edición Limitada"];
    const links = Array.from(container.querySelectorAll<HTMLAnchorElement>(".store-home-hero__stage a"));
    expect(links.map((link) => link.getAttribute("href"))).toEqual(Object.values(hero_links));
    expect(links.map((link) => link.getAttribute("aria-label"))).toEqual(names);
    expect(links.every((link) => !link.querySelector("img")?.alt.includes("实拍"))).toBe(true);
  });
});
