import { hydrateRoot } from "react-dom/client";
import { LiveStorefront } from "./LiveStorefront";
import { StorefrontErrorBoundary } from "../components/shared/PageError";
import { renderStartupError } from "../components/shared/renderStartupError";
import type { StorePageData } from "./types";
import "./storefront.css";

type BootData = { page: StorePageData; origin: string };
function readBootData(): BootData | null {
  const json = document.getElementById("store-data")?.textContent;
  if (!json) return null;
  try {
    const data = JSON.parse(json) as BootData | null;
    return data?.page ? data : null;
  } catch {
    return null;
  }
}

const root = document.getElementById("store-root");
const boot = readBootData();
if (root && boot) {
  hydrateRoot(root, <StorefrontErrorBoundary>
    <LiveStorefront initialPage={boot.page} origin={boot.origin} />
  </StorefrontErrorBoundary>);
} else {
  renderStartupError(root);
}
