import { describe, expect, it } from "vitest";
import { browseUrl, filtersFromSearch, safeBrowsePath } from "./browsing";

describe("storefront browsing state", () => {
  it("round trips combined filters and safely encodes search without keeping stale page numbers", () => {
    const state = { q: "BHK & 52", brands: ["cohiba", "partagas"], boxes: ["10", "25"], sort: "length" };
    const url = browseUrl("/catalog?page=3", state);
    expect(filtersFromSearch(url.split("?")[1])).toEqual(state);
    expect(url).not.toContain("page=");
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
