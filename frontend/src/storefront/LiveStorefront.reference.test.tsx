// @vitest-environment jsdom
import React from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { LiveStorefront } from "./LiveStorefront";
import { backendPageFixture } from "./fixture";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it("recalculates reference prices when switching boxes and single-cigar inquiry", async () => {
  const page = { ...backendPageFixture, product: { ...backendPageFixture.product!, offers: [
    { box_size: 10, price_rub: "100.00", in_stock: true },
    { box_size: 25, price_rub: "250.00", in_stock: true },
    { sale_unit: "stick" as const, box_size: null, price_rub: null, in_stock: true },
  ] } };
  const now = Date.now();
  vi.stubGlobal("fetch", vi.fn(async (url: string) => ({ ok: true, status: 200, json: async () => url.includes("/rates/") ? {
    source_updated_at: new Date(now).toISOString(), expires_at: new Date(now + 3600000).toISOString(),
    cny_per_rub: "0.1", usd_per_rub: "0.02",
  } : page })));
  vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => setTimeout(() => callback(0), 0));
  const { container } = render(<LiveStorefront initialPage={page} />);
  fireEvent.click(container.querySelector('[data-age-confirm]')!);
  fireEvent.click(container.querySelector('[data-store-currency="CNY"]')!);
  await waitFor(() => expect(container.querySelector(".d-price [data-reference-price]")?.textContent).toContain("10.00"));
  fireEvent.click(screen.getByRole("button", { name: "25 ct./box" }));
  expect(container.querySelector(".d-price [data-reference-price]")?.textContent).toContain("25.00");
  fireEvent.click(screen.getByRole("button", { name: "Single cigar" }));
  expect(container.querySelector(".d-price [data-reference-price]")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "10 ct./box" }));
  expect(container.querySelector(".d-price [data-reference-price]")?.textContent).toContain("10.00");
  fireEvent.click(container.querySelector('[data-store-currency="USD"]')!);
  expect(container.querySelector(".d-price [data-reference-price]")?.textContent).toContain("2.00");
  fireEvent.click(screen.getByRole("button", { name: "25 ct./box" }));
  expect(container.querySelector(".d-price [data-reference-price]")?.textContent).toContain("5.00");
});
