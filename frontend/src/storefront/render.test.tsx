import { describe, expect, it } from "vitest";
import { renderStorePage } from "./render";
import { backendPageFixture } from "./fixture";



describe("storefront server renderer", () => {
  it("renders localized SEO and supplied manifest assets without browser globals", () => {
    const html = renderStorePage({ page: backendPageFixture, origin: "https://shop.example", assets: { js: ["/static/assets/store-abc.js"], css: ["/static/assets/store-def.css"] } });
    expect(html).toContain('<html lang="en">');
    expect(html).toContain('<link rel="canonical" href="https://shop.example/en/cigar/5/cohiba-robustos">');
    expect(html).toContain('hreflang="ru" href="https://shop.example/ru/cigar/5/cohiba-robustos"');
    expect(html).toContain('href="/static/assets/store-def.css"');
    expect(html).toContain('src="/static/assets/store-abc.js"');
    expect(html).toContain('<h1>Cohiba Robustos</h1>');
    expect(html).toContain('name="description" content="A product description"');
  });

  it("safely escapes user content in HTML and embedded JSON-LD", () => {
    const html = renderStorePage({ page: backendPageFixture, origin: "https://shop.example", assets: { js: [], css: [] } });
    expect(html).toContain("&lt;strong&gt;bold&lt;/strong&gt;");
    expect(html).not.toContain("</script><script>alert(1)");
    expect(html).toContain("\\u003c/script>");
    expect(html).toContain('"@type":"Store"');
    expect(html).not.toContain('"@type":"Product"');
  });

  it("keeps page content in the DOM beneath the age overlay and retains priced out-of-stock offers", () => {
    const html = renderStorePage({ page: backendPageFixture, origin: "https://shop.example", assets: { js: [], css: [] } });
    expect(html).toContain('data-age-gate="true"');
    expect(html).toContain('aria-modal="true"');
    expect(html).toContain("A &lt;strong&gt;bold&lt;/strong&gt; cigar");
    expect(html).toContain('data-price-rub="12345.00"');
    expect(html).toContain("12345.00");
    expect(html).toContain("Temporarily unavailable");
    expect(html).not.toContain("openingHours");
  });

  it("shows an inquiry label when a box has no known RUB price", () => {
    const noPrice = { ...backendPageFixture, product: { ...backendPageFixture.product!, offers: [{ box_size: 25, price_rub: null, in_stock: false }] } };
    const html = renderStorePage({ page: noPrice, origin: "https://shop.example", assets: { js: [], css: [] } });
    expect(html).toContain("Ask for price");
    expect(html).not.toContain("12345.00");
  });

  it("uses the Chinese root URL and an available inquiry offer over a sold-out price", () => {
    const product = { ...backendPageFixture.product!, offers: [
      { box_size: 25, price_rub: "10000.00", in_stock: false },
      { box_size: 10, price_rub: null, in_stock: true },
    ] };
    const home = {
      ...backendPageFixture,
      locale: "zh" as const,
      kind: "home" as const,
      path: "/",
      title: "雪茄目录",
      body: "目录",
      products: [product],
      product: null,
      alternates: [{ locale: "zh" as const, path: "/" }, { locale: "ru" as const, path: "/ru/" }, { locale: "en" as const, path: "/en/" }],
      breadcrumbs: [],
    };
    const html = renderStorePage({ page: home, origin: "https://shop.example", assets: { js: [], css: [] } });
    expect(html).toContain('class="site-brand" href="/"');
    expect(html).toContain('class="btn-pri" href="/catalog"');
    expect(html).toContain('"item":"https://shop.example/"');
    expect(html).toContain("10");
    expect(html).toContain("询价");
    expect(html.split('<script id="store-data"')[0]).not.toContain("10000.00");
  });

  it("requires a title, description, and visible heading", () => {
    expect(() => renderStorePage({ page: { ...backendPageFixture, title: "  " }, origin: "https://shop.example", assets: { js: [], css: [] } })).toThrow("requires a title");
    expect(() => renderStorePage({ page: { ...backendPageFixture, description: "" }, origin: "https://shop.example", assets: { js: [], css: [] } })).toThrow("requires a description");
  });
});
