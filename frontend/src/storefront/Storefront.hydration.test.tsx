// @vitest-environment jsdom
import React, { act } from "react";
import { hydrateRoot } from "react-dom/client";
import { renderToString } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { Storefront } from "./Storefront";
import { backendPageFixture } from "./fixture";

(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

describe("storefront hydration", () => {
  it("hydrates backend-shaped localized product data without a workbench or auth context", async () => {
    const container = document.createElement("div");
    container.innerHTML = renderToString(<Storefront page={backendPageFixture} />);
    document.body.append(container);
    const errors: unknown[] = [];
    let root: ReturnType<typeof hydrateRoot>;
    await act(async () => {
      root = hydrateRoot(container, <Storefront page={backendPageFixture} />, { onRecoverableError: (error) => errors.push(error) });
    });
    expect(container.querySelector("h1")?.textContent).toBe("Cohiba Robustos");
    expect(container.querySelector('[data-age-gate="true"]')).not.toBeNull();
    expect(container.querySelector(".store-main")?.hasAttribute("inert")).toBe(true);
    expect(container.querySelector('.store-languages a[lang="en"]')?.textContent).toBe("English");
    expect(container.querySelector('[data-store-currency="RUB"]')?.getAttribute("aria-pressed")).toBe("true");
    expect(errors).toEqual([]);
    await act(async () => root!.unmount());
    container.remove();
  });
});
