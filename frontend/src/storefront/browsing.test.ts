import { describe, expect, it } from "vitest";
import { browseUrl, filtersFromSearch, safeBrowsePath } from "./browsing";

describe("storefront browsing state", () => {
  it("round trips combined filters and safely encodes search without keeping stale page numbers", () => {
    const state = { q: "BHK & 52", brands: ["cohiba", "partagas"], boxes: ["10", "25"], sort: "length", length_min: "100", length_max: "160", ring_min: "40", ring_max: "56", price_min: "0", price_max: "12345.67", stock_only: true };
    const url = browseUrl("/catalog?page=3", state);
    expect(filtersFromSearch(url.split("?")[1])).toEqual(state);
    expect(url).not.toContain("page=");
  });
  it("ignores malformed ranges and only enables stock for the explicit flag", () => {
    for (const value of ['NaN', 'Infinity', '-1', '1e5', 'abc', '12345678901234567', '1.234']) {
      expect(filtersFromSearch(`price_min=${value}&length_max=${value}&stock_only=0`)).toEqual({ q: '', brands: [], boxes: [], sort: 'catalog' });
    }
  });
  it("keeps the same list and filters when switching languages", () => {
    expect(safeBrowsePath("/ru/brand/cohiba?q=BHK&box=10&sort=name&page=2", "en")).toBe("/en/brand/cohiba?q=BHK&box=10&sort=name");
    expect(safeBrowsePath("/ru/brand/cohiba?box=10&page=2", "ru")).toBe("/ru/brand/cohiba?box=10&page=2");
    expect(safeBrowsePath("/en/catalog?box=25", "zh")).toBe("/catalog?box=25");
    expect(safeBrowsePath("/", "ru")).toBe("/ru/");
  });
  it("rejects external links and unrelated routes from return-to-list state", () => {
    for (const value of ["https://evil.example/catalog", "//evil.example/catalog", "/\\evil.example/catalog", "/sales", "/cigar/5/slug", "/brand/cohiba/extra"]) expect(safeBrowsePath(value, "zh")).toBeNull();
    expect(filtersFromSearch("sort=price").sort).toBe("catalog");
  });
});
