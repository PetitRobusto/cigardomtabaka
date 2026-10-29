import { describe, expect, it } from "vitest";
import { renderStorePage } from "./render";
import { backendPageFixture } from "./fixture";
import { homeHeroFirstImageSizes, homeHeroFirstImageSrcSet } from "./HomeHero.images";
import publicDetails from "../../../storefront/public_details.json";



describe("storefront server renderer", () => {
  it("discovers the startup image in the head before the deferred loader requests it", () => {
    const html = renderStorePage({ page: backendPageFixture, origin: "https://shop.example", assets: { js: [], css: [] } });
    const head = html.split('</head>')[0];
    const loaderImage = html.match(/<img[^>]+class="cdt-startup__logo"[^>]*>/)![0];
    const motionUrl = loaderImage.match(/data-motion-src="([^"]+)"/)![1];
    const preloads = (head.match(/<link[^>]+rel="preload"[^>]*>/g) || [])
      .filter(link => link.includes(`href="${motionUrl}"`));
    expect(preloads).toHaveLength(1);
    expect(preloads[0]).toContain('as="image"');
    expect(preloads[0]).toContain('type="image/svg+xml"');
    expect(motionUrl).toBe('/static/frontend/logo-opening-motion-v2.svg');
    expect(loaderImage).not.toMatch(/\ssrc=/);
  });
  it("renders each packaging price without JavaScript while the default stocked box remains inquiry-only", () => {
    const page = { ...backendPageFixture, product: { ...backendPageFixture.product!, availability: "in_stock" as const, offers: [
      { box_size: 10, price_rub: "108000.00", in_stock: false },
      { box_size: 25, price_rub: null, in_stock: true },
      { sale_unit: "stick" as const, box_size: null, price_rub: null, in_stock: true },
    ] } };
    const html = renderStorePage({ page, origin: "https://shop.example", assets: { js: [], css: [] } });
    const visible = html.split('<script id="store-data"')[0];
    const options = visible.match(/<button class="d-boxopt"[\s\S]*?<\/button>/g)!;
    expect(options).toHaveLength(3);
    expect(options[0]).toContain('10 ct./box');
    expect(options[0]).toContain('data-price-rub="108000.00"');
    expect(options[0]).toContain('Temporarily unavailable');
    expect(options[0]).toContain('aria-pressed="false"');
    expect(options[1]).toContain('25 ct./box');
    expect(options[1]).toContain('aria-pressed="true"');
    expect(options[1]).not.toContain('data-price-rub');
    expect(options[2]).not.toContain('data-price-rub');
    const selectedPrice = visible.match(/<section class="d-price">[\s\S]*?<\/section>/)![0];
    expect(selectedPrice).toContain('Ask for price');
    expect(selectedPrice).not.toContain('data-price-rub');
  });
  it.each(['zh', 'ru', 'en'] as const)("renders confirmed contact details and machine-readable hours without JavaScript in %s", (locale) => {
    const page = { ...backendPageFixture, locale, content_locale: locale, site: { ...backendPageFixture.site,
      address: publicDetails.address[locale], hours: publicDetails.hours[locale] } };
    const html = renderStorePage({ page, origin: "https://shop.example", assets: { js: [], css: [] } });
    expect(html).toContain(publicDetails.address[locale]);
    expect(html).toContain(publicDetails.hours[locale]);
    expect(html).toContain('"openingHours":["Mo-Sa 12:00-20:00","Su 12:00-16:00"]');
  });
  it("renders localized SEO and supplied manifest assets without browser globals", () => {
    const html = renderStorePage({ page: backendPageFixture, origin: "https://shop.example", assets: { js: ["/static/assets/store-abc.js"], css: ["/static/assets/store-def.css"] } });
    expect(html).toContain('<html lang="en">');
    expect(html).toContain('<link rel="icon" type="image/png" sizes="96x96" href="/static/frontend/favicon-96.png">');
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
    expect(html).toContain('class="store-home-hero__secondary" href="/catalog?stock_only=1"');
    expect(html).toContain('"@type":"WebSite","name":"CigarDomTabaka","url":"https://shop.example/"');
    expect(html).not.toContain('"@type":"BreadcrumbList"');
    expect(html).toContain("10");
    expect(html).toContain("询价");
    expect(html.split('<script id="store-data"')[0]).not.toContain("10000.00");
  });

  it("preloads the first responsive home image with the same srcset and sizes as the image", () => {
    const home = {
      ...backendPageFixture,
      locale: "zh" as const,
      kind: "home" as const,
      path: "/",
      product: null,
      alternates: [{ locale: "zh" as const, path: "/" }],
      breadcrumbs: [],
    };
    const html = renderStorePage({ page: home, origin: "https://shop.example", assets: { js: [], css: [] } });
    expect(html).toContain(`imageSrcSet="${homeHeroFirstImageSrcSet}"`);
    expect(html).toContain(`imageSizes="${homeHeroFirstImageSizes}"`);
    expect(html).toContain('fetchPriority="high"');
  });

  it("requires a title, description, and visible heading", () => {
    expect(() => renderStorePage({ page: { ...backendPageFixture, title: "  " }, origin: "https://shop.example", assets: { js: [], css: [] } })).toThrow("requires a title");
    expect(() => renderStorePage({ page: { ...backendPageFixture, description: "" }, origin: "https://shop.example", assets: { js: [], css: [] } })).toThrow("requires a description");
  });
});
