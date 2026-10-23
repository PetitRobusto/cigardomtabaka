import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { Storefront } from "./Storefront";
import { storeCopy } from "./copy";
import { AGE_CONFIRMATION_KEY, isAgeConfirmationValid } from "./ageConfirmation";
import { isCurrentRate } from "./rates";
import { ReferencePrices } from "./ReferencePrice";
import { installStoreNavigation, savedStoreScroll, STORE_NAVIGATION_EVENT, type NavigationKind } from "./navigation";
import { clearStoreMetadata, markStoreNavigationFailure, updateStoreMetadata } from "./metadata";
import { homePath } from "./browsing";
import type { StorePageData, StoreRates } from "./types";

let ageConfirmedInMemory = false;

function subscribeLocation(onChange: () => void) {
  window.addEventListener("popstate", onChange);
  window.addEventListener("hashchange", onChange);
  window.addEventListener(STORE_NAVIGATION_EVENT, onChange);
  return () => { window.removeEventListener("popstate", onChange); window.removeEventListener("hashchange", onChange); window.removeEventListener(STORE_NAVIGATION_EVENT, onChange); };
}
function locationSnapshot() { return window.location.pathname + window.location.search + window.location.hash; }

function subscribeAgeConfirmation(onChange: () => void) {
  window.addEventListener("storage", onChange);
  window.addEventListener("cdt:store-age-confirmation", onChange);
  return () => {
    window.removeEventListener("storage", onChange);
    window.removeEventListener("cdt:store-age-confirmation", onChange);
  };
}

function getAgeConfirmationSnapshot() {
  try { return ageConfirmedInMemory || isAgeConfirmationValid(localStorage.getItem(AGE_CONFIRMATION_KEY)); }
  catch { return ageConfirmedInMemory; }
}

export function LiveStorefront({ initialPage, origin }: { initialPage: StorePageData; origin?: string }) {
  const currentUrl = useSyncExternalStore(subscribeLocation, locationSnapshot, () => initialPage.path);
  const [page, setPage] = useState<StorePageData | null>(initialPage);
  const [rates, setRates] = useState<StoreRates | null>(null);
  const [currency, setCurrency] = useState<"RUB" | "CNY" | "USD">("RUB");
  const [refreshFailed, setRefreshFailed] = useState(false);
  const [loading, setLoading] = useState(false);
  const [retryToken, setRetryToken] = useState(0);
  const [loadedUrl, setLoadedUrl] = useState(initialPage.path);
  const navigationKind = useRef<NavigationKind | "initial">("initial");
  const requestPath = currentUrl.split("#")[0];
  const displayedUrl = requestPath === loadedUrl.split("#")[0] ? currentUrl : loadedUrl;
  const ageConfirmed = useSyncExternalStore(subscribeAgeConfirmation, getAgeConfirmationSnapshot, () => false);

  useEffect(() => installStoreNavigation(document.getElementById("store-root") || document, (kind) => { navigationKind.current = kind; }), []);

  useEffect(() => {
    if (ageConfirmed || !page) return;
    const root = document.getElementById("store-root");
    const gate = root?.querySelector<HTMLElement>("[data-age-gate]");
    gate?.querySelector<HTMLElement>("[data-age-confirm]")?.focus();
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const keydown = (event: KeyboardEvent) => {
      if (!gate) return;
      if (event.key === "Escape") { event.preventDefault(); event.stopImmediatePropagation(); return; }
      if (event.key !== "Tab") return;
      const focusable = Array.from(gate.querySelectorAll<HTMLElement>('button:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])'));
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    document.addEventListener("keydown", keydown);
    return () => { document.removeEventListener("keydown", keydown); document.body.style.overflow = previousOverflow; };
  }, [ageConfirmed, page]);

  const confirmAge = () => {
    try { localStorage.setItem(AGE_CONFIRMATION_KEY, String(Date.now())); } catch { /* Continue for this page even when storage is unavailable. */ }
    ageConfirmedInMemory = true;
    window.dispatchEvent(new Event("cdt:store-age-confirmation"));
  };
  const declineAge = () => window.location.replace("about:blank");

  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    const requested = new URL(requestPath, location.origin);
    const kind = navigationKind.current;
    navigationKind.current = "initial";
    Promise.resolve().then(() => { if (active && kind !== "initial") { setLoading(true); setRefreshFailed(false); } });
    const params = new URLSearchParams({ path: requested.pathname });
    requested.searchParams.forEach((value, key) => { if (["q", "brand", "box", "sort", "page"].includes(key)) params.append(key, value); });
    fetch(`/api/storefront/page/?${params.toString()}`, { headers: { Accept: "application/json" }, signal: controller.signal })
      .then(async (response) => {
        if (!active) return null;
        if (response.status === 404) {
          setPage(null);
          setLoading(false); setRefreshFailed(false);
          const locale = requested.pathname.startsWith("/ru/") ? "ru" : requested.pathname.startsWith("/en/") ? "en" : "zh";
          clearStoreMetadata(storeCopy[locale].pageUnavailable, locale);
          window.requestAnimationFrame(() => {
            if (!active) return;
            const heading = document.querySelector<HTMLElement>(".store-main h1");
            if (heading) { heading.tabIndex = -1; heading.focus({ preventScroll: true }); }
            window.scrollTo(0, 0);
          });
          return null;
        }
        if (!response.ok) throw new Error("page refresh failed");
        return response.json() as Promise<StorePageData>;
      })
      .then((data) => {
        if (!active || !data) return;
        const canonicalPath = data.path.split("?")[0];
        if (canonicalPath !== requested.pathname) {
          requested.pathname = canonicalPath;
          history.replaceState(history.state, "", requested.pathname + requested.search + location.hash);
          window.dispatchEvent(new Event(STORE_NAVIGATION_EVENT));
        }
        setPage(data); setLoadedUrl(requested.pathname + requested.search + location.hash);
        setRefreshFailed(false); setLoading(false);
        updateStoreMetadata(data, origin || location.origin, requested);
        window.requestAnimationFrame(() => {
          if (!active) return;
          if (kind !== "initial" && getAgeConfirmationSnapshot()) {
            const heading = document.querySelector<HTMLElement>(".store-main h1");
            if (heading) { heading.tabIndex = -1; heading.focus({ preventScroll: true }); }
          }
          if (window.location.hash === "#store-contact") { document.getElementById("store-contact")?.scrollIntoView(); return; }
          const saved = ["initial", "pop", "return"].includes(kind) ? savedStoreScroll(requested) : null;
          if (saved !== null) window.scrollTo(0, saved);
          else if (kind !== "initial") window.scrollTo(0, 0);
        });
      })
      .catch(() => { if (active) { setRefreshFailed(true); setLoading(false); if (kind !== "initial") markStoreNavigationFailure(); } });
    return () => { active = false; controller.abort(); };
  }, [requestPath, retryToken, origin]);

  useEffect(() => {
    let active = true;
    let expiryTimer: number | undefined;
    fetch("/api/storefront/rates/", { headers: { Accept: "application/json" } })
      .then((response) => response.ok ? response.json() as Promise<StoreRates> : Promise.reject())
      .then((data) => {
        if (!active) return;
        setRates(data);
        const expiry = data.expires_at ? Date.parse(data.expires_at) : NaN;
        if (Number.isFinite(expiry)) expiryTimer = window.setTimeout(() => setRates(null), Math.max(0, expiry - Date.now()));
      })
      .catch(() => undefined);
    return () => { active = false; if (expiryTimer !== undefined) window.clearTimeout(expiryTimer); };
  }, []);

  useEffect(() => {
    const locale = page?.locale || initialPage.locale;
    const labels = storeCopy[locale];
    const ratesCurrent = isCurrentRate(rates);
    const rateNote = document.querySelector<HTMLElement>("[data-rates-note]");
    if (rateNote) {
      rateNote.hidden = currency === "RUB";
      const localeTag = locale === "zh" ? "zh-CN" : locale === "ru" ? "ru-RU" : "en";
      const validUntil = ratesCurrent ? new Intl.DateTimeFormat(localeTag, { dateStyle: "short", timeStyle: "short" }).format(Date.parse(rates?.expires_at || "")) : "";
      rateNote.textContent = ratesCurrent ? `${labels.ratesNote} ${labels.updated}: ${rates?.source_updated_at || "—"} · ${labels.validUntil}: ${validUntil}` : labels.ratesUnavailable;
    }
  }, [currency, page, rates, initialPage.locale]);

  const locale = page?.locale || (requestPath.startsWith("/ru/") ? "ru" : requestPath.startsWith("/en/") ? "en" : "zh");
  const labels = storeCopy[locale];
  return <>
    {page ? <ReferencePrices currency={currency} rates={rates}><Storefront page={page} currentUrl={displayedUrl} busy={loading} currency={currency} onCurrencyChange={setCurrency} ageConfirmed={ageConfirmed} onAgeConfirm={confirmAge} onAgeDecline={declineAge} /></ReferencePrices> : <main className="view store-main"><section className="wrap store-section"><h1>{labels.pageUnavailable}</h1><a href={homePath(locale)}>{labels.home}</a></section></main>}
    {loading && <><div className="store-navigation-progress" aria-hidden="true" /><span className="visually-hidden" role="status">{labels.loadingPage}</span></>}
    {refreshFailed && <p className="store-live-status" role="status">{labels.navigationError} <button type="button" onClick={() => { navigationKind.current = "push"; setRetryToken((value) => value + 1); }}>{labels.retry}</button></p>}
  </>;
}
