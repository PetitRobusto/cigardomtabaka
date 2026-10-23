// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { installStoreNavigation, isStorefrontUrl, savedStoreScroll, STORE_NAVIGATION_EVENT } from "./navigation";

afterEach(() => {
  sessionStorage.clear();
  history.replaceState(null, "", "/en/cigar/5/cohiba-robustos");
  vi.restoreAllMocks();
});

describe("store navigation enhancement", () => {
  it("only enhances same-origin storefront routes", () => {
    expect(isStorefrontUrl(new URL("https://shop.example/ru/catalog"), "https://shop.example")).toBe(true);
    expect(isStorefrontUrl(new URL("https://shop.example/cigar/5/cohiba"), "https://shop.example")).toBe(true);
    expect(isStorefrontUrl(new URL("https://shop.example/admin/"), "https://shop.example")).toBe(false);
    expect(isStorefrontUrl(new URL("https://other.example/catalog"), "https://shop.example")).toBe(false);
  });

  it("intercepts a regular storefront link, saves the prior scroll, and emits navigation kind", () => {
    history.replaceState(null, "", "/en/catalog?brand=cohiba");
    const root = document.createElement("div");
    root.innerHTML = '<a class="store-return-link" href="/en/cigar/5/cohiba-robustos?from=%2Fen%2Fcatalog%3Fbrand%3Dcohiba">Cohiba</a>';
    document.body.append(root);
    vi.stubGlobal("scrollY", 321);
    const onNavigate = vi.fn();
    const eventListener = vi.fn();
    window.addEventListener(STORE_NAVIGATION_EVENT, eventListener);
    const uninstall = installStoreNavigation(root, onNavigate);
    const click = new MouseEvent("click", { bubbles: true, cancelable: true, button: 0 });
    root.querySelector("a")!.dispatchEvent(click);

    expect(click.defaultPrevented).toBe(true);
    expect(location.pathname).toBe("/en/cigar/5/cohiba-robustos");
    expect(onNavigate).toHaveBeenCalledWith("return");
    expect(eventListener).toHaveBeenCalledOnce();
    expect(savedStoreScroll(new URL("https://localhost/en/catalog?brand=cohiba"))).toBe(321);

    uninstall();
    window.removeEventListener(STORE_NAVIGATION_EVENT, eventListener);
    root.remove();
  });

  it("serializes repeated GET-form fields without intercepting offsite submissions", () => {
    history.replaceState(null, "", "/en/catalog");
    const root = document.createElement("div");
    root.innerHTML = '<form method="get" action="/en/catalog"><input name="brand" value="cohiba"><input name="brand" value="davidoff"><input name="box" value="10"><input name="box" value="25"><input name="sort" value="name"><button type="submit">Apply</button></form><form method="get" action="https://other.example/catalog"><button>Offsite</button></form>';
    document.body.append(root);
    const onNavigate = vi.fn();
    const uninstall = installStoreNavigation(root, onNavigate);
    const form = root.querySelector("form")!;
    const submit = new Event("submit", { bubbles: true, cancelable: true });
    form.dispatchEvent(submit);

    expect(submit.defaultPrevented).toBe(true);
    expect(location.pathname).toBe("/en/catalog");
    expect(location.search).toBe("?brand=cohiba&brand=davidoff&box=10&box=25&sort=name");
    expect(onNavigate).toHaveBeenCalledWith("push");
    const offsiteSubmit = new Event("submit", { bubbles: true, cancelable: true });
    root.querySelectorAll("form")[1].dispatchEvent(offsiteSubmit);
    expect(offsiteSubmit.defaultPrevented).toBe(false);
    expect(onNavigate).toHaveBeenCalledOnce();

    uninstall();
    root.remove();
  });
});
