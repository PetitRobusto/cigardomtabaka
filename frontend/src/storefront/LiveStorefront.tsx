import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { useAuthStore } from "../store/authStore";
import { NotFoundPage } from "../components/site/NotFoundPage";
import { localeForPath, notFoundCopy } from "../components/site/notFoundCopy";
import { AGE_CONFIRMATION_TTL, CUSTOMER_AGE_KEY, isAgeConfirmationValid as isPreferenceAgeConfirmationValid, useCustomerPreferences } from "../features/customer/preferences";
import "../components/shared/startup-loader.css";
import { isStartupPending, useStartupPending } from "../components/shared/useStartupPending";
import { Storefront } from "./Storefront";
import { storeCopy } from "./copy";
import { AGE_CONFIRMATION_KEY, isAgeConfirmationValid } from "./ageConfirmation";
import { isCurrentRate } from "./rates";
import { ReferencePrices } from "./ReferencePrice";
import { installStoreNavigation, savedStoreScroll, STORE_NAVIGATION_EVENT, type NavigationKind } from "./navigation";
import { clearStoreMetadata, markStoreNavigationFailure, updateStoreMetadata } from "./metadata";
import { browsingKeys } from "./browsing";
import type { StorePageData, StoreRates } from "./types";

const MAX_TIMEOUT_MS = 2_147_483_647;

function subscribeLocation(onChange: () => void) {
  window.addEventListener("popstate", onChange);
  window.addEventListener("hashchange", onChange);
  window.addEventListener(STORE_NAVIGATION_EVENT, onChange);
  return () => { window.removeEventListener("popstate", onChange); window.removeEventListener("hashchange", onChange); window.removeEventListener(STORE_NAVIGATION_EVENT, onChange); };
}
function locationSnapshot() { return window.location.pathname + window.location.search + window.location.hash; }

function getAgeConfirmationTimestamp(): number | null {
  const preferences = useCustomerPreferences.getState();
  if (preferences.denied) return null;
  const preferenceTimestamp = isPreferenceAgeConfirmationValid(preferences.confirmedAt) ? preferences.confirmedAt : null;
  try {
    const currentTimestamp = localStorage.getItem(CUSTOMER_AGE_KEY);
    const legacyTimestamp = localStorage.getItem(AGE_CONFIRMATION_KEY);
    const storedTimestamp = currentTimestamp ?? legacyTimestamp;
    if (storedTimestamp === null) return null;
    return isAgeConfirmationValid(storedTimestamp) ? Number(storedTimestamp) : null;
  } catch {
    return preferenceTimestamp;
  }
}

function subscribeAgeConfirmation(onChange: () => void) {
  let expiryTimer: number | undefined;
  const scheduleExpiryCheck = () => {
    if (expiryTimer !== undefined) window.clearTimeout(expiryTimer);
    const confirmedAt = getAgeConfirmationTimestamp();
    if (confirmedAt === null) return;
    const remaining = confirmedAt + AGE_CONFIRMATION_TTL - Date.now();
    if (remaining <= 0) return;
    expiryTimer = window.setTimeout(() => {
      expiryTimer = undefined;
      onChange();
      scheduleExpiryCheck();
    }, Math.min(remaining, MAX_TIMEOUT_MS));
  };
  const recheck = () => {
    onChange();
    scheduleExpiryCheck();
  };
  const onVisibilityChange = () => {
    if (document.visibilityState === "visible") recheck();
  };
  const unsubscribePreferences = useCustomerPreferences.subscribe(recheck);
  window.addEventListener("storage", recheck);
  window.addEventListener("cdt:store-age-confirmation", recheck);
  window.addEventListener("focus", recheck);
  document.addEventListener("visibilitychange", onVisibilityChange);
  scheduleExpiryCheck();
  return () => {
    if (expiryTimer !== undefined) window.clearTimeout(expiryTimer);
    unsubscribePreferences();
    window.removeEventListener("storage", recheck);
    window.removeEventListener("cdt:store-age-confirmation", recheck);
    window.removeEventListener("focus", recheck);
    document.removeEventListener("visibilitychange", onVisibilityChange);
  };
}

function getAgeConfirmationSnapshot() {
  return getAgeConfirmationTimestamp() !== null;
}

export function LiveStorefront({ initialPage, origin }: { initialPage: StorePageData; origin?: string }) {
  const { user, isLoading: authLoading, checkAuth, logout } = useAuthStore();
  const starting = useStartupPending();
  useEffect(() => { if (!starting && !isStartupPending()) void checkAuth(); }, [checkAuth, starting]);
  useEffect(() => {
    document.documentElement.dataset.cdtAppReady = "true";
    window.dispatchEvent(new Event("cdt:app-ready"));
  }, []);
  const currentUrl = useSyncExternalStore(subscribeLocation, locationSnapshot, () => initialPage.path);
  const [page, setPage] = useState<StorePageData | null>(initialPage);
  const [rates, setRates] = useState<StoreRates | null>(null);
  const requestedRateCurrency = useRef<string | null>(null);
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
    if (ageConfirmed || !page || starting || isStartupPending()) return;
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
  }, [ageConfirmed, page, starting]);

  const confirmAge = () => {
    useCustomerPreferences.getState().confirmAge();
    window.dispatchEvent(new Event("cdt:store-age-confirmation"));
  };
  const declineAge = () => { useCustomerPreferences.getState().denyAge(); window.location.replace("about:blank"); };

  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    const requested = new URL(requestPath, location.origin);
    const kind = navigationKind.current;
    navigationKind.current = "initial";
    Promise.resolve().then(() => { if (active && kind !== "initial") { setLoading(true); setRefreshFailed(false); } });
    const params = new URLSearchParams({ path: requested.pathname });
    requested.searchParams.forEach((value, key) => { if (key === "page" || browsingKeys.includes(key)) params.append(key, value); });
    fetch(`/api/storefront/page/?${params.toString()}`, { headers: { Accept: "application/json" }, signal: controller.signal })
      .then(async (response) => {
        if (!active) return null;
        if (response.status === 404) {
          setPage(null);
          setLoading(false); setRefreshFailed(false);
          const locale = localeForPath(requested.pathname);
          clearStoreMetadata(notFoundCopy[locale].title, locale);
          window.requestAnimationFrame(() => {
            if (!active) return;
            const heading = document.querySelector<HTMLElement>("main h1");
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
    if (currency === "RUB") { requestedRateCurrency.current = null; return; }
    if (isCurrentRate(rates) || requestedRateCurrency.current === currency) return;
    requestedRateCurrency.current = currency;
    let active = true;
    const controller = new AbortController();
    fetch("/api/storefront/rates/", { headers: { Accept: "application/json" }, signal: controller.signal })
      .then((response) => response.ok ? response.json() as Promise<StoreRates> : Promise.reject())
      .then((data) => {
        if (!active) return;
        setRates(data);
      })
      .catch(() => undefined);
    return () => { active = false; controller.abort(); };
    // Retry on a new currency selection, not on an unavailable/expired response.
  }, [currency, rates]);

  useEffect(() => {
    const expiry = rates?.expires_at ? Date.parse(rates.expires_at) : NaN;
    if (!Number.isFinite(expiry)) return;
    const timer = window.setTimeout(() => setRates(null), Math.min(MAX_TIMEOUT_MS, Math.max(0, expiry - Date.now())));
    return () => window.clearTimeout(timer);
  }, [rates]);

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

  const locale = page?.locale || localeForPath(requestPath);
  const labels = storeCopy[locale];
  useEffect(() => { useCustomerPreferences.getState().selectLocale(locale); }, [locale]);
  return <>
    {page ? <ReferencePrices currency={currency} rates={rates}><Storefront page={page} user={authLoading ? null : user} onLogout={logout} currentUrl={displayedUrl} busy={loading} currency={currency} onCurrencyChange={setCurrency} ageConfirmed={ageConfirmed} onAgeConfirm={confirmAge} onAgeDecline={declineAge} /></ReferencePrices> : <NotFoundPage locale={locale} />}
    {loading && <><div className="store-navigation-progress" aria-hidden="true" /><span className="visually-hidden" role="status">{labels.loadingPage}</span></>}
    {refreshFailed && <p className="store-live-status" role="status">{labels.navigationError} <button type="button" onClick={() => { navigationKind.current = "push"; setRetryToken((value) => value + 1); }}>{labels.retry}</button></p>}
  </>;
}
