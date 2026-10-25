// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest";
import { backendPageFixture } from "./fixture";
import { renderStorePage } from "./render";
import { clearStoreMetadata, storeStructuredData, updateStoreMetadata } from "./metadata";
import { browsingKeys } from "./browsing";

function setUpHead() {
  document.head.innerHTML = `
    <title>Old title</title>
    <meta name="description" content="Old description">
    <meta property="og:title" content="Old OG title">
    <meta property="og:site_name" content="Old site name">
    <meta property="og:type" content="website">
    <meta property="og:description" content="Old OG description">
    <meta property="og:url" content="https://old.example/old">
    <meta property="og:image" content="https://old.example/old.jpg">
    <meta property="og:image:alt" content="Old image">
    <meta property="og:locale" content="zh_CN">
    <meta property="og:locale:alternate" content="ru_RU">
    <link rel="canonical" href="https://old.example/old">
    <link rel="alternate" hreflang="en" href="https://old.example/en/old">
    <script type="application/ld+json">{"old":true}</script>`;
}

afterEach(() => {
  document.head.innerHTML = "";
  document.documentElement.lang = "";
});

describe("storefront metadata", () => {
  it.each(browsingKeys)("blocks indexing for the %s filter and restores it on clean navigation", (key) => {
    const page = { ...backendPageFixture, indexable: true };
    updateStoreMetadata(page, "https://shop.example", new URL(`https://shop.example${page.path}?${key}=1`));
    expect(document.head.querySelector('meta[name="robots"]')?.getAttribute("content")).toBe("noindex, nofollow");
    updateStoreMetadata(page, "https://shop.example", new URL(`https://shop.example${page.path}`));
    expect(document.head.querySelector('meta[name="robots"]')).toBeNull();
  });
  it.each(['zh', 'ru', 'en'] as const)('keeps localized sharing metadata identical before and after hydration in %s', (locale) => {
    const page = { ...backendPageFixture, locale, product: { ...backendPageFixture.product!,
      name: 'Cigar & "box"', image_url: '/single-thumb.jpg', images: ['/single.jpg', '/box25.jpg'],
      image_variants: [
        { url: '/single.jpg', thumbnail_url: '/single-thumb.jpg', image_type: 'cigar', box_size: null },
        { url: '/box25.jpg', thumbnail_url: '/box25-thumb.jpg', image_type: 'packaging', box_size: 25 },
      ] } };
    const html = renderStorePage({ page, origin: 'https://shop.example', assets: { js: [], css: [] } });
    const server = new DOMParser().parseFromString(html, 'text/html');
    const tags = (root: ParentNode) => Array.from(root.querySelectorAll<HTMLMetaElement>('meta[property^="og:"]')).map((tag) => [tag.getAttribute('property'), tag.content]);
    const expected = tags(server);
    expect(expected).toContainEqual(['og:locale', { zh: 'zh_CN', ru: 'ru_RU', en: 'en_US' }[locale]]);
    expect(expected.filter(([key]) => key === 'og:locale:alternate')).toHaveLength(2);
    expect(expected).toContainEqual(['og:image', 'https://shop.example/box25.jpg']);
    expect(expected).toContainEqual(['og:image:alt', 'Cigar & "box"']);
    expect(server.querySelector('[data-gallery-main]')?.getAttribute('src')).toBe('/box25.jpg');
    setUpHead();
    updateStoreMetadata(page, 'https://shop.example', new URL('https://shop.example' + page.path));
    expect(tags(document.head)).toEqual(expected);
    updateStoreMetadata({ ...page, product: null, alternates: [] }, 'https://shop.example', new URL('https://shop.example/en/catalog'));
    expect(document.head.querySelector('meta[property="og:image"]')).toBeNull();
    expect(document.head.querySelector('meta[property="og:image:alt"]')).toBeNull();
    expect(document.head.querySelector('meta[property="og:locale:alternate"]')).toBeNull();
  });

  it('does not borrow an unrelated product photo when the selected packaging has no image', () => {
    const product = { ...backendPageFixture.product!, image_url: '/single-thumb.jpg', images: ['/single.jpg'],
      image_variants: [{ url: '/single.jpg', thumbnail_url: '/single-thumb.jpg', image_type: 'cigar', box_size: null }] };
    const page = { ...backendPageFixture, product };
    updateStoreMetadata(page, 'https://shop.example', new URL('https://shop.example' + page.path));
    expect(document.head.querySelector('meta[property="og:image"]')).toBeNull();
    updateStoreMetadata({ ...page, product: { ...product, offers: [] } }, 'https://shop.example', new URL('https://shop.example' + page.path));
    expect(document.head.querySelector<HTMLMetaElement>('meta[property="og:image"]')?.content).toBe('https://shop.example/single.jpg');
    updateStoreMetadata({ ...page, site: { ...page.site, photo: '/store.jpg' } }, 'https://shop.example', new URL('https://shop.example' + page.path));
    expect(document.head.querySelector<HTMLMetaElement>('meta[property="og:image"]')?.content).toBe('https://shop.example/store.jpg');
    expect(document.head.querySelector<HTMLMetaElement>('meta[property="og:image:alt"]')?.content).toBe(page.site.name);
  });
  it.each(['zh', 'ru', 'en'] as const)('keeps one domain-level site name on the %s homepage across server and client renders', (locale) => {
    const page = { ...backendPageFixture, kind: 'home' as const, locale,
      path: locale === 'zh' ? '/' : `/${locale}/`, product: null, breadcrumbs: [],
      site: { ...backendPageFixture.site, name: 'CigarDomTabaka & "Store"' } };
    const html = renderStorePage({ page, origin: 'https://shop.example', assets: { js: [], css: [] } });
    const server = new DOMParser().parseFromString(html, 'text/html');
    const structured = JSON.parse(server.querySelector('script[type="application/ld+json"]')!.textContent!);
    expect(structured.find((item: Record<string, unknown>) => item['@type'] === 'WebSite')).toEqual({
      '@context': 'https://schema.org', '@type': 'WebSite', name: page.site.name, url: 'https://shop.example/',
    });
    expect(structured.some((item: Record<string, unknown>) => item['@type'] === 'BreadcrumbList')).toBe(false);
    expect(server.querySelector<HTMLMetaElement>('meta[property="og:site_name"]')?.content).toBe(page.site.name);
    setUpHead();
    updateStoreMetadata(page, 'https://shop.example', new URL('https://shop.example' + page.path));
    expect(JSON.parse(document.head.querySelector('script[type="application/ld+json"]')!.textContent!)).toEqual(structured);
    expect(document.head.querySelector<HTMLMetaElement>('meta[property="og:site_name"]')?.content).toBe(page.site.name);
    updateStoreMetadata(backendPageFixture, 'https://shop.example', new URL('https://shop.example' + backendPageFixture.path));
    expect(document.head.querySelector('script[type="application/ld+json"]')!.textContent).not.toContain('"@type":"WebSite"');
  });

  it('does not identify paginated or catalog pages as the site homepage', () => {
    for (const path of ['/en/catalog', '/en/?page=2']) {
      const data = storeStructuredData({ ...backendPageFixture, kind: 'home', path, product: null }, 'https://shop.example') as Array<Record<string, unknown>>;
      expect(data.some((item) => item['@type'] === 'WebSite')).toBe(false);
    }
  });
  it.each(["Cohiba Robustos — specifications & prices | CigarDomTabaka", undefined, "  "])("keeps server and client search titles consistent without changing product headings (%s)", (seoTitle) => {
    const page = { ...backendPageFixture, seo_title: seoTitle };
    const html = renderStorePage({ page, origin: "https://shop.example", assets: { js: [], css: [] } });
    const serverDocument = new DOMParser().parseFromString(html, "text/html");
    const expected = seoTitle?.trim() || page.title;
    expect(serverDocument.title).toBe(expected);
    expect(serverDocument.querySelector<HTMLMetaElement>('meta[property="og:title"]')?.content).toBe(expected);
    expect(serverDocument.querySelector("h1")?.textContent).toBe(page.product!.name);

    document.head.innerHTML = serverDocument.head.innerHTML;
    updateStoreMetadata(page, "https://shop.example", new URL(`https://browser.example${page.path}`));
    expect(document.title).toBe(expected);
    expect(document.head.querySelector<HTMLMetaElement>('meta[property="og:title"]')?.content).toBe(expected);

    updateStoreMetadata({ ...page, seo_title: undefined, title: "Next page" }, "https://shop.example", new URL("https://browser.example/en/"));
    expect(document.title).toBe("Next page");
    expect(document.head.querySelector<HTMLMetaElement>('meta[property="og:title"]')?.content).toBe("Next page");
  });

  it("updates localized metadata and canonical origin without retaining stale social or language tags", () => {
    setUpHead();
    const requested = new URL("https://browser.example/ru/cigar/5/cohiba-robustos");
    const page = {
      ...backendPageFixture,
      locale: "ru" as const,
      path: "/ru/cigar/5/cohiba-robustos",
      title: "Сигары Cohiba Robustos",
      description: "Описание товара",
      product: { ...backendPageFixture.product!, image_url: "/media/robustos.jpg" },
      alternates: [
        { locale: "zh" as const, path: "/cigar/5/cohiba-robustos" },
        { locale: "ru" as const, path: "/ru/cigar/5/cohiba-robustos" },
        { locale: "en" as const, path: "/en/cigar/5/cohiba-robustos" },
      ],
    };

    updateStoreMetadata(page, "https://shop.example", requested);

    expect(document.title).toBe("Сигары Cohiba Robustos");
    expect(document.documentElement.lang).toBe("ru-RU");
    expect(document.head.querySelector<HTMLMetaElement>('meta[name="description"]')?.content).toBe("Описание товара");
    expect(document.head.querySelector<HTMLLinkElement>('link[rel="canonical"]')?.href).toBe("https://shop.example/ru/cigar/5/cohiba-robustos");
    expect(document.head.querySelector<HTMLMetaElement>('meta[property="og:url"]')?.content).toBe("https://shop.example/ru/cigar/5/cohiba-robustos");
    expect(document.head.querySelector<HTMLMetaElement>('meta[property="og:image"]')?.content).toBe("https://shop.example/media/robustos.jpg");
    expect(document.head.querySelectorAll<HTMLLinkElement>('link[rel="alternate"][hreflang]')).toHaveLength(4);
    expect(document.head.querySelector<HTMLLinkElement>('link[hreflang="x-default"]')?.href).toBe("https://shop.example/cigar/5/cohiba-robustos");
    expect(document.head.querySelector<HTMLLinkElement>('link[hreflang="en"]')?.href).toBe("https://shop.example/en/cigar/5/cohiba-robustos");
    expect(document.head.querySelector<HTMLScriptElement>('script[type="application/ld+json"]')?.textContent).not.toContain('"old":true');

    updateStoreMetadata({
      ...page,
      locale: "en",
      kind: "brand",
      path: "/en/catalog",
      title: "Cohiba catalog",
      description: "Browse Cohiba",
      product: null,
      site: { ...page.site, photo: "" },
      alternates: [{ locale: "zh", path: "/catalog" }, { locale: "en", path: "/en/catalog" }],
    }, "https://shop.example", new URL("https://browser.example/en/catalog"));
    expect(document.title).toBe("Cohiba catalog");
    expect(document.documentElement.lang).toBe("en");
    expect(document.head.querySelector<HTMLLinkElement>('link[rel="canonical"]')?.href).toBe("https://shop.example/en/catalog");
    expect(document.head.querySelector<HTMLMetaElement>('meta[property="og:image"]')).toBeNull();
    expect(document.head.querySelectorAll<HTMLLinkElement>('link[rel="alternate"][hreflang]')).toHaveLength(3);
    expect(document.head.querySelector('link[hreflang="ru"]')).toBeNull();
  });

  it("keeps the renderer's base canonical for filters and page path for unfiltered pagination", () => {
    setUpHead();
    const requested = new URL("https://browser.example/en/catalog?q=robusto&brand=cohiba&box=25&sort=price&page=2");
    const page = {
      ...backendPageFixture,
      kind: "brand" as const,
      path: "/en/catalog",
      title: "Cohiba catalog",
      filters: { q: "robusto", brands: ["cohiba"], boxes: ["25"], sort: "price" },
      pagination: { page: 2, total_pages: 3, previous: "/en/catalog?page=1", next: "/en/catalog?page=3" },
      product: null,
      site: { ...backendPageFixture.site, photo: "" },
    };

    updateStoreMetadata(page, "https://shop.example", requested);
    expect(document.head.querySelector<HTMLLinkElement>('link[rel="canonical"]')?.href).toBe("https://shop.example/en/catalog");
    expect(document.head.querySelector<HTMLMetaElement>('meta[name="robots"]')?.content).toBe("noindex, nofollow");
    expect(document.head.querySelector<HTMLMetaElement>('meta[property="og:image"]')).toBeNull();

    const unfilteredPageTwo = {
      ...page,
      path: "/en/catalog?page=2",
      filters: { q: "", brands: [], boxes: [], sort: "" },
    };
    updateStoreMetadata(unfilteredPageTwo, "https://shop.example", new URL("https://browser.example/en/catalog?page=2"));
    expect(document.head.querySelector<HTMLLinkElement>('link[rel="canonical"]')?.href).toBe("https://shop.example/en/catalog?page=2");
    expect(document.head.querySelector<HTMLMetaElement>('meta[name="robots"]')).toBeNull();
  });

  it("does not index English fallback content or invent language alternates", () => {
    setUpHead();
    const fallback = { ...backendPageFixture, indexable: false, alternates: [] };
    updateStoreMetadata(fallback, "https://shop.example", new URL("https://shop.example" + fallback.path));
    expect(document.head.querySelector<HTMLMetaElement>('meta[name="robots"]')?.content).toBe("noindex, nofollow");
    expect(document.head.querySelectorAll('link[rel="alternate"][hreflang]')).toHaveLength(0);
    updateStoreMetadata({ ...fallback, indexable: true }, "https://shop.example", new URL("https://shop.example" + fallback.path));
    expect(document.head.querySelector('meta[name="robots"]')).toBeNull();
  });

  it("clears stale SEO identity and blocks indexing after a client-side 404", () => {
    setUpHead();
    clearStoreMetadata("Page unavailable", "ru");

    expect(document.title).toBe("Page unavailable");
    expect(document.documentElement.lang).toBe("ru-RU");
    expect(document.head.querySelector<HTMLMetaElement>('meta[name="description"]')?.content).toBe("Page unavailable");
    expect(document.head.querySelector<HTMLMetaElement>('meta[name="robots"]')?.content).toBe("noindex, nofollow");
    expect(document.head.querySelector<HTMLLinkElement>('link[rel="canonical"]')).toBeNull();
    expect(document.head.querySelectorAll<HTMLLinkElement>('link[rel="alternate"][hreflang]')).toHaveLength(0);
    expect(document.head.querySelector<HTMLScriptElement>('script[type="application/ld+json"]')).toBeNull();
    for (const property of ["og:type", "og:site_name", "og:title", "og:description", "og:url", "og:image", "og:image:alt", "og:locale", "og:locale:alternate"]) {
      expect(document.head.querySelector<HTMLMetaElement>(`meta[property="${property}"]`)).toBeNull();
    }
  });

  it("preserves the shared structured data shape used by the server renderer", () => {
    const data = storeStructuredData(backendPageFixture, "https://shop.example") as Array<Record<string, unknown>>;
    expect(data[0]).toMatchObject({ "@context": "https://schema.org", "@type": "BreadcrumbList" });
    expect(data[1]).toMatchObject({ "@context": "https://schema.org", "@type": "Store", name: "CigarDomTabaka", url: "https://shop.example/en/" });
    expect(data.some((item) => item["@type"] === "Product")).toBe(false);
  });
});
