export const STORE_NAVIGATION_EVENT = "cdt:store-navigation";
export type NavigationKind = "push" | "return" | "pop";

export function isStorefrontUrl(url: URL, origin: string): boolean {
  return url.origin === origin && /^\/(?:ru\/|en\/)?(?:|catalog\/?|brand\/[a-z0-9_-]+\/?|cigar\/\d+\/[a-z0-9_-]+\/?)$/.test(url.pathname);
}

function scrollKey(url: URL) { return `cdt:store-scroll:${url.pathname}${url.search}${url.hash}`; }
export function savedStoreScroll(url: URL): number | null {
  try {
    const value = sessionStorage.getItem(scrollKey(url));
    return value !== null && Number.isFinite(Number(value)) ? Math.max(0, Number(value)) : null;
  } catch { return null; }
}

/** Enhance crawlable links and GET forms. Other destinations retain native browser behavior. */
export function installStoreNavigation(root: Document | HTMLElement, onNavigate: (kind: NavigationKind) => void) {
  let previousUrl = new URL(location.href);
  const previousRestoration = history.scrollRestoration;
  history.scrollRestoration = "manual";
  const saveScroll = () => {
    try { sessionStorage.setItem(scrollKey(previousUrl), String(window.scrollY)); } catch { /* Navigation also works without storage. */ }
  };
  const closeTransientUi = () => {
    root.querySelectorAll<HTMLDialogElement>("dialog[open]").forEach((dialog) => dialog.close());
    root.querySelectorAll<HTMLElement>("[popover]").forEach((popover) => { if (popover.hidePopover) popover.hidePopover(); });
  };
  const navigate = (url: URL, kind: NavigationKind) => {
    saveScroll();
    closeTransientUi();
    onNavigate(kind);
    if (url.href !== location.href) history.pushState(null, "", url.pathname + url.search + url.hash);
    else window.scrollTo(0, 0);
    previousUrl = url;
    window.dispatchEvent(new Event(STORE_NAVIGATION_EVENT));
  };
  const click = (event: MouseEvent) => {
    if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const anchor = event.target instanceof Element ? event.target.closest<HTMLAnchorElement>("a[href]") : null;
    if (!anchor || anchor.hasAttribute("download") || (anchor.target && anchor.target !== "_self") || anchor.relList.contains("external")) return;
    const url = new URL(anchor.href, location.href);
    if (!isStorefrontUrl(url, location.origin)) return;
    if (url.pathname === location.pathname && url.search === location.search && url.hash) { saveScroll(); return; }
    event.preventDefault();
    navigate(url, anchor.classList.contains("store-return-link") ? "return" : "push");
  };
  const submit = (event: SubmitEvent) => {
    if (event.defaultPrevented || !(event.target instanceof HTMLFormElement)) return;
    const form = event.target;
    const submitter = event.submitter instanceof HTMLButtonElement || event.submitter instanceof HTMLInputElement ? event.submitter : null;
    const method = submitter?.getAttribute("formmethod") || form.method;
    const target = submitter?.getAttribute("formtarget") || form.target;
    if (method.toLowerCase() !== "get" || (target && target !== "_self")) return;
    const url = new URL(submitter?.getAttribute("formaction") || form.action, location.href);
    if (!isStorefrontUrl(url, location.origin)) return;
    const params = new URLSearchParams();
    new FormData(form, submitter).forEach((value, name) => { if (typeof value === "string") params.append(name, value); });
    url.search = params.toString();
    event.preventDefault();
    navigate(url, "push");
  };
  const pop = () => {
    saveScroll(); closeTransientUi(); onNavigate("pop");
    const next = new URL(location.href);
    if (next.pathname === previousUrl.pathname && next.search === previousUrl.search) {
      if (next.hash === "#store-contact") document.getElementById("store-contact")?.scrollIntoView();
      else window.scrollTo(0, savedStoreScroll(next) ?? 0);
    }
    previousUrl = next;
  };
  const hash = () => { previousUrl = new URL(location.href); };
  root.addEventListener("click", click as EventListener);
  root.addEventListener("submit", submit as EventListener);
  window.addEventListener("popstate", pop);
  window.addEventListener("hashchange", hash);
  window.addEventListener("pagehide", saveScroll);
  return () => {
    root.removeEventListener("click", click as EventListener);
    root.removeEventListener("submit", submit as EventListener);
    window.removeEventListener("popstate", pop);
    window.removeEventListener("hashchange", hash);
    window.removeEventListener("pagehide", saveScroll);
    history.scrollRestoration = previousRestoration;
  };
}
