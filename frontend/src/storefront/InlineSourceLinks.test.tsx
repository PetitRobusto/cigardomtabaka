// @vitest-environment jsdom
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { InlineSourceLinks } from "./InlineSourceLinks";
import { backendPageFixture } from "./fixture";
import { renderStorePage } from "./render";

afterEach(cleanup);

describe("inline product sources", () => {
  it("renders HTTPS references in place while preserving paragraph whitespace", () => {
    const { container } = render(<p><InlineSourceLinks text={'First paragraph.\n\nRead [Award & source](https://reviews.example/2024?cigar=1&lang=en), then [manufacturer](https://maker.example/details).'} /></p>);
    const links = container.querySelectorAll("a");
    expect(links).toHaveLength(2);
    expect(links[0].href).toBe("https://reviews.example/2024?cigar=1&lang=en");
    expect(links[0].textContent).toBe("Award & source");
    expect(links[0].rel).toBe("noopener noreferrer");
    expect(container.textContent).toBe("First paragraph.\n\nRead Award & source, then manufacturer.");
  });

  it.each([
    "javascript:alert(1)", "JaVaScRiPt:alert%281%29", "data:text/html,boom", "vbscript:boom",
    "//reviews.example/award", "/award", "http://reviews.example/award", "https://",
    "https://user:password@reviews.example/award", "java\nscript:alert(1)",
  ])("leaves disallowed or invalid destinations as literal text: %s", (destination) => {
    const text = `[Source](${destination})`;
    const { container } = render(<InlineSourceLinks text={text} />);
    expect(container.querySelector("a")).toBeNull();
    expect(container.textContent).toBe(text);
  });

  it("escapes raw HTML both outside links and inside link labels", () => {
    const text = '<script>alert(1)</script> [<img src=x onerror=alert(2)>](https://reviews.example/award)';
    const { container } = render(<InlineSourceLinks text={text} />);
    expect(container.querySelector("script, img")).toBeNull();
    expect(container.querySelector("a")?.textContent).toBe("<img src=x onerror=alert(2)>");
    expect(container.textContent).toBe('<script>alert(1)</script> <img src=x onerror=alert(2)>');
  });

  it.each(["zh", "ru", "en"] as const)("includes real source anchors in the product SSR body in %s", (locale) => {
    const body = 'First paragraph.\n\n[2024 award](https://reviews.example/award) <strong>plain HTML</strong> [unsafe](javascript:boom)';
    const html = renderStorePage({ page: { ...backendPageFixture, locale, body }, origin: "https://shop.example", assets: { js: [], css: [] } });
    const page = new DOMParser().parseFromString(html, "text/html");
    const description = page.querySelector("p.store-description")!;
    expect(description.querySelectorAll("a")).toHaveLength(1);
    expect(description.querySelector("a")?.getAttribute("href")).toBe("https://reviews.example/award");
    expect(description.querySelector("strong")).toBeNull();
    expect(description.textContent).toBe('First paragraph.\n\n2024 award <strong>plain HTML</strong> [unsafe](javascript:boom)');
    expect(page.querySelectorAll(".store-description-section")).toHaveLength(1);
  });

  it.each(["zh", "ru", "en"] as const)("renders manufacturer references within the existing brand intro in %s", (locale) => {
    const body = "Brand history. [Manufacturer](https://maker.example/brand) <script>unsafe</script>";
    const html = renderStorePage({ page: { ...backendPageFixture, locale, kind: "brand", product: undefined,
      path: "/brand/example", body, products: [] }, origin: "https://shop.example", assets: { js: [], css: [] } });
    const page = new DOMParser().parseFromString(html, "text/html");
    const intro = page.querySelector(".cat-head .intro")!;
    expect(intro.querySelectorAll("a")).toHaveLength(1);
    expect(intro.querySelector("a")?.getAttribute("href")).toBe("https://maker.example/brand");
    expect(intro.querySelector("script")).toBeNull();
    expect(page.querySelectorAll(".cat-head .intro")).toHaveLength(1);
  });
});
