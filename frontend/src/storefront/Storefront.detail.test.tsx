// @vitest-environment jsdom
import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Storefront } from "./Storefront";
import { backendPageFixture } from "./fixture";

describe("storefront product detail", () => {
  it("shows one contain-ready source image and switches it with keyboard-operable thumbnails", () => {
    const page = {
      ...backendPageFixture,
      body: "Описание на русском языке",
      product: {
        ...backendPageFixture.product!,
        image_url: "/media/thumb.jpg",
        images: ["/media/original-one.jpg", "/media/original-two.jpg"],
      },
    };
    render(<Storefront page={page} ageConfirmed />);

    expect(screen.getByRole("img", { name: "Cohiba Robustos" }).getAttribute("src")).toBe("/media/original-one.jpg");
    expect(screen.getByRole("button", { name: "Product image 2" }).getAttribute("aria-pressed")).toBe("false");
    fireEvent.click(screen.getByRole("button", { name: "Product image 2" }));
    expect(screen.getByRole("img", { name: "Cohiba Robustos" }).getAttribute("src")).toBe("/media/original-two.jpg");
    expect(screen.getByRole("button", { name: "Product image 2" }).getAttribute("aria-pressed")).toBe("true");
    expect(document.querySelector('[data-gallery-main]')?.getAttribute("src")).not.toBe("/media/thumb.jpg");
  });

  it("passes backend-localized Russian copy through and renders contact details without buttons", () => {
    const page = {
      ...backendPageFixture,
      locale: "ru" as const,
      body: "Русское описание товара",
      product: { ...backendPageFixture.product!, brand: "Кохиба", description: "Русское описание товара", availability: "in_stock" as const, offers: backendPageFixture.product!.offers.map((offer) => ({ ...offer, in_stock: true })) },
    };
    const { container } = render(<Storefront page={page} ageConfirmed />);

    expect(container.querySelector(".store-product-detail-copy .store-product-brand")?.textContent).toBe("Кохиба");
    expect(screen.getByText("В наличии")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Цена" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Связаться" }).getAttribute("href")).toBe("#store-contact");
    expect(container.querySelector(".store-contact-details a[href^=tel]")?.getAttribute("href")).toBe("tel:+70000000000");
    expect(container.querySelector("#store-contact button")).toBeNull();
    expect(container.querySelector(".store-contact-details")?.textContent).toContain("cigar-contact");
    expect(container.querySelector(".store-description")?.textContent).toBe("Русское описание товара");
    const contactListener = vi.fn();
    window.addEventListener("cdt:store-contact", contactListener, { once: true });
    const phoneLink = container.querySelector<HTMLAnchorElement>(".store-contact-details a[href^=tel]")!;
    phoneLink.addEventListener("click", (event) => event.preventDefault(), { once: true });
    fireEvent.click(phoneLink);
    expect(contactListener.mock.calls[0]?.[0]).toMatchObject({ detail: { kind: "phone", locale: "ru", product_id: "5" } });
  });

  it("uses backend-provided Chinese brand names and concise detail labels", () => {
    const page = {
      ...backendPageFixture,
      locale: "zh" as const,
      product: { ...backendPageFixture.product!, brand: "高希霸", availability: "in_stock" as const, offers: backendPageFixture.product!.offers.map((offer) => ({ ...offer, in_stock: true })) },
      alternates: [{ locale: "zh" as const, path: "/" }],
    };
    const { container } = render(<Storefront page={page} ageConfirmed />);
    expect(container.querySelector(".store-product-detail-copy .store-product-brand")?.textContent).toBe("高希霸");
    expect(screen.getByText("现货")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "价格" })).toBeTruthy();
  });
});
