// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest";
import { backendPageFixture } from "./fixture";
import { renderStorePage } from "./render";
import { clearStoreMetadata, storeStructuredData, updateStoreMetadata } from "./metadata";

function setUpHead() {
  document.head.innerHTML = `
    <title>Old title</title>
    <meta name="description" content="Old description">
    <meta property="og:title" content="Old OG title">
    <meta property="og:description" content="Old OG description">
    <meta property="og:url" content="https://old.example/old">
    <meta property="og:image" content="https://old.example/old.jpg">
    <link rel="canonical" href="https://old.example/old">
    <link rel="alternate" hreflang="en" href="https://old.example/en/old">
    <script type="application/ld+json">{"old":true}</script>`;
}

afterEach(() => {
  document.head.innerHTML = "";
  document.documentElement.lang = "";
});

describe("storefront metadata", () => {
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
    for (const property of ["og:title", "og:description", "og:url", "og:image"]) {
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
