// @vitest-environment jsdom
import React from "react";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { AGE_CONFIRMATION_KEY } from "./ageConfirmation";
import { AGE_CONFIRMATION_TTL } from "../features/customer/preferences";
import { backendPageFixture } from "./fixture";
import { LiveStorefront } from "./LiveStorefront";
import type { StorePageData } from "./types";

const catalogPage: StorePageData = {
  ...backendPageFixture,
  kind: "home",
  view: "catalog",
  path: "/en/catalog",
  title: "English catalog | CigarDomTabaka",
  description: "English catalog description",
  product: null,
  products: [backendPageFixture.product!],
  filters: { q: "", brands: [], boxes: [], sort: "catalog" },
  navigation: { brands: [{ name: "Cohiba", slug: "cohiba", path: "/en/brand/cohiba" }, { name: "Davidoff", slug: "davidoff", path: "/en/brand/davidoff" }], box_sizes: [10, 25] },
  filter_options: { brands: [{ name: "Cohiba", slug: "cohiba", path: "/en/brand/cohiba" }, { name: "Davidoff", slug: "davidoff", path: "/en/brand/davidoff" }], box_sizes: [10, 25] },
  alternates: [{ locale: "zh", path: "/catalog" }, { locale: "ru", path: "/ru/catalog" }, { locale: "en", path: "/en/catalog" }],
};

const russianProductPage: StorePageData = {
  ...backendPageFixture,
  locale: "ru",
  path: "/ru/cigar/5/cohiba-robustos",
  title: "Кохиба Робустос | CigarDomTabaka",
  description: "Описание на русском",
  body: "Текст страницы на русском",
  product: { ...backendPageFixture.product!, name: "Кохиба Робустос", path: "/ru/cigar/5/cohiba-robustos" },
  alternates: [{ locale: "zh", path: "/cigar/5/cohiba-robustos" }, { locale: "ru", path: "/ru/cigar/5/cohiba-robustos" }, { locale: "en", path: "/en/cigar/5/cohiba-robustos" }],
};

function response(data: unknown, status = 200) {
  return { ok: status >= 200 && status < 300, status, json: async () => data };
}

function pageFor(path: string): StorePageData {
  if (path === "/en/catalog") return catalogPage;
  if (path === "/ru/cigar/5/cohiba-robustos") return russianProductPage;
  if (path === "/en/cigar/5/cohiba-robustos") return backendPageFixture;
  return { ...catalogPage, path };
}

function makeFetch(overrides: (path: string) => Promise<unknown> | unknown = (path) => pageFor(path)) {
  return vi.fn(async (input: RequestInfo | URL) => {
    const url = new URL(String(input), location.origin);
    if (url.pathname.endsWith("/rates/")) return response({ source_updated_at: null, expires_at: null, cny_per_rub: null, usd_per_rub: null });
    const path = url.searchParams.get("path") || "/";
    const value = await overrides(path);
    return value && typeof value === "object" && "status" in value ? value as ReturnType<typeof response> : response(value);
  });
}

function mount(initialPage: StorePageData = backendPageFixture) {
  history.replaceState(null, "", initialPage.path);
  document.body.innerHTML = '<div id="store-root"></div>';
  document.head.replaceChildren();
  document.title = initialPage.title;
  vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => { callback(0); return 1; });
  vi.stubGlobal("scrollTo", vi.fn());
  vi.stubGlobal("scrollY", 0);
  return render(<LiveStorefront initialPage={initialPage} />, { container: document.getElementById("store-root")! });
}

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
  history.replaceState(null, "", "/en/cigar/5/cohiba-robustos");
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  localStorage.clear();
  sessionStorage.clear();
  history.replaceState(null, "", "/en/cigar/5/cohiba-robustos");
  document.body.innerHTML = "";
  document.head.replaceChildren();
  document.title = "";
});

it("switches catalog → product → Russian page in place and updates rendered content and SEO metadata", async () => {
  vi.stubGlobal("fetch", makeFetch());
  mount();
  fireEvent.click(document.querySelector('[data-age-confirm]')!);
  fireEvent.click(document.querySelector('.catnav a[href="/en/catalog"]')!);
  await screen.findByRole("heading", { name: "English catalog | CigarDomTabaka", level: 1 });
  expect(location.pathname).toBe("/en/catalog");

  fireEvent.click(document.querySelector(".pcard-name")!);
  // The catalog card already has this heading; wait for the detail page H1
  // before opening a menu whose state intentionally closes on page changes.
  await screen.findByRole("heading", { name: "Cohiba Robustos", level: 1 });
  expect(location.pathname).toBe("/en/cigar/5/cohiba-robustos");
  fireEvent.click(screen.getByRole("button", { name: "Language" }));
  fireEvent.click(document.querySelector('.site-language-menu a[lang="ru"]')!);

  await screen.findByRole("heading", { name: "Кохиба Робустос", level: 1 });
  expect(location.pathname).toBe("/ru/cigar/5/cohiba-robustos");
  expect(document.documentElement.lang).toBe("ru-RU");
  expect(document.title).toBe(russianProductPage.title);
  expect(document.querySelector('meta[name="description"]')?.getAttribute("content")).toBe(russianProductPage.description);
  expect(document.querySelector('link[rel="canonical"]')?.getAttribute("href")).toBe(`${location.origin}${russianProductPage.path}`);
  expect(document.querySelector('meta[property="og:title"]')?.getAttribute("content")).toBe(russianProductPage.title);
  expect(localStorage.getItem(AGE_CONFIRMATION_KEY)).not.toBeNull();
  expect(document.querySelector('[data-age-gate]')?.hasAttribute("hidden")).toBe(true);
});

it("serializes combined repeated GET filters into the page-data request", async () => {
  const fetch = makeFetch();
  vi.stubGlobal("fetch", fetch);
  mount(catalogPage);
  await screen.findByRole("heading", { name: "English catalog | CigarDomTabaka" });

  fireEvent.click(document.getElementById("desktop-brand-cohiba")!);
  fireEvent.click(document.getElementById("desktop-brand-davidoff")!);
  fireEvent.click(document.getElementById("desktop-box-10")!);
  fireEvent.click(document.getElementById("desktop-box-25")!);
  const sidebar = document.querySelector('.store-desktop-filters')!;
  fireEvent.click(within(sidebar as HTMLElement).getByRole('button', { name: '120–145' }));
  fireEvent.click(within(sidebar as HTMLElement).getByRole('button', { name: '≤ 42' }));
  fireEvent.change(within(sidebar as HTMLElement).getByRole('slider', { name: /Min$/ }), { target: { value: '1' } });
  fireEvent.change(within(sidebar as HTMLElement).getByRole('slider', { name: /Max$/ }), { target: { value: '5' } });
  fireEvent.click(sidebar.querySelector('[name="stock_only"]')!);
  fireEvent.submit(document.querySelector(".store-desktop-filters")!);

  await waitFor(() => expect(fetch.mock.calls.some(([input]) => {
    const request = new URL(String(input), location.origin);
    return request.pathname === "/api/storefront/page/" && request.searchParams.getAll("brand").join(",") === "cohiba,davidoff" && request.searchParams.getAll("box").join(",") === "10,25"
      && request.searchParams.get('length_min') === '120' && request.searchParams.get('length_max') === '145' && request.searchParams.get('ring_max') === '42'
      && request.searchParams.get('price_min') === '5000' && request.searchParams.get('price_max') === '50000'
      && request.searchParams.get('stock_only') === '1';
  })).toBe(true));
});

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
}

it.each([404, 200])("ignores an outdated catalog response (%s) after a newer locale navigation", async (staleStatus) => {
  const stale = deferred<unknown>();
  const latest = deferred<unknown>();
  vi.stubGlobal("fetch", makeFetch((path) => {
    if (path === "/en/catalog") return stale.promise;
    if (path === "/ru/cigar/5/cohiba-robustos") return latest.promise;
    return pageFor(path);
  }));
  mount();
  await screen.findByRole("heading", { name: "Cohiba Robustos" });
  fireEvent.click(document.querySelector('.catnav a[href="/en/catalog"]')!);
  await waitFor(() => expect(location.pathname).toBe("/en/catalog"));
  fireEvent.click(screen.getByRole("button", { name: "Language" }));
  fireEvent.click(document.querySelector('.site-language-menu a[lang="ru"]')!);
  await waitFor(() => expect(location.pathname).toBe("/ru/cigar/5/cohiba-robustos"));

  latest.resolve(response(russianProductPage));
  await screen.findByRole("heading", { name: "Кохиба Робустос" });
  stale.resolve(response(staleStatus === 404 ? null : catalogPage, staleStatus));
  await new Promise((resolve) => setTimeout(resolve, 0));

  expect(screen.getByRole("heading", { name: "Кохиба Робустос" })).toBeTruthy();
  expect(document.title).toBe(russianProductPage.title);
  expect(location.pathname).toBe(russianProductPage.path);
});

it.each(["return", "pop"] as const)("restores saved catalog scroll on %s navigation", async (kind) => {
  vi.stubGlobal("fetch", makeFetch());
  mount();
  await screen.findByRole("heading", { name: "Cohiba Robustos" });
  sessionStorage.setItem("cdt:store-scroll:/en/catalog", "640");

  if (kind === "return") {
    fireEvent.click(document.querySelector(".store-return-link")!);
  } else {
    history.pushState(null, "", "/en/catalog");
    window.dispatchEvent(new PopStateEvent("popstate"));
  }

  await screen.findByRole("heading", { name: "English catalog | CigarDomTabaka" });
  await waitFor(() => expect(window.scrollTo).toHaveBeenCalledWith(0, 640));
});

it("keeps currency and age confirmation across navigation, then retries a failed page request", async () => {
  let catalogAttempts = 0;
  vi.stubGlobal("fetch", makeFetch((path) => {
    if (path === "/en/catalog" && ++catalogAttempts === 1) return Promise.reject(new Error("offline"));
    return pageFor(path);
  }));
  mount();
  fireEvent.click(document.querySelector('[data-age-confirm]')!);
  fireEvent.click(screen.getByRole("button", { name: "Reference currency" }));
  fireEvent.click(screen.getByRole("menuitemradio", { name: "CNY ¥" }));
  fireEvent.click(document.querySelector('.catnav a[href="/en/catalog"]')!);
  const retry = await screen.findByRole("button", { name: /try again/i });
  fireEvent.click(retry);
  await screen.findByRole("heading", { name: "English catalog | CigarDomTabaka" });

  expect(screen.getByRole("button", { name: "Reference currency" }).textContent).toContain("CNY ¥");
  expect(document.querySelector('[data-age-gate]')?.hasAttribute("hidden")).toBe(true);
  expect(catalogAttempts).toBe(2);
});


it("revokes an existing age confirmation when another tab clears storage", async () => {
  vi.stubGlobal("fetch", makeFetch());
  mount();
  fireEvent.click(document.querySelector('[data-age-confirm]')!);
  await waitFor(() => expect(document.querySelector('[data-age-gate]')?.hasAttribute("hidden")).toBe(true));
  localStorage.clear();
  fireEvent(window, new StorageEvent("storage", { key: null }));
  await waitFor(() => expect(document.querySelector('[data-age-gate]')?.hasAttribute("hidden")).toBe(false));
});

it("rechecks the age timestamp instead of retaining a permanent in-memory pass", async () => {
  vi.stubGlobal("fetch", makeFetch());
  mount();
  fireEvent.click(document.querySelector('[data-age-confirm]')!);
  await waitFor(() => expect(document.querySelector('[data-age-gate]')?.hasAttribute("hidden")).toBe(true));
  const expired = String(Date.now() - 31 * 24 * 60 * 60 * 1000);
  localStorage.setItem("cdt.customer.age-confirmed-at", expired);
  localStorage.setItem(AGE_CONFIRMATION_KEY, expired);
  fireEvent(window, new StorageEvent("storage", { key: AGE_CONFIRMATION_KEY }));
  await waitFor(() => expect(document.querySelector('[data-age-gate]')?.hasAttribute("hidden")).toBe(false));
});

it("reopens the age gate at natural expiry without a storage event", async () => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-10-23T12:00:00Z"));
  try {
    vi.stubGlobal("fetch", makeFetch());
    mount();
    fireEvent.click(document.querySelector('[data-age-confirm]')!);
    expect(document.querySelector('[data-age-gate]')?.hasAttribute("hidden")).toBe(true);

    await act(async () => { await vi.advanceTimersByTimeAsync(AGE_CONFIRMATION_TTL); });

    expect(document.querySelector('[data-age-gate]')?.hasAttribute("hidden")).toBe(false);
  } finally {
    vi.useRealTimers();
  }
});

it.each(["focus", "visibilitychange"] as const)("rechecks age confirmation when the page resumes by %s", async (eventName) => {
  vi.useFakeTimers();
  const now = new Date("2026-10-23T12:00:00Z");
  vi.setSystemTime(now);
  try {
    vi.stubGlobal("fetch", makeFetch());
    mount();
    fireEvent.click(document.querySelector('[data-age-confirm]')!);
    expect(document.querySelector('[data-age-gate]')?.hasAttribute("hidden")).toBe(true);
    vi.setSystemTime(now.getTime() + AGE_CONFIRMATION_TTL + 1);

    if (eventName === "focus") {
      fireEvent(window, new Event("focus"));
    } else {
      Object.defineProperty(document, "visibilityState", { configurable: true, value: "visible" });
      fireEvent(document, new Event("visibilitychange"));
    }

    expect(document.querySelector('[data-age-gate]')?.hasAttribute("hidden")).toBe(false);
  } finally {
    vi.useRealTimers();
  }
});
