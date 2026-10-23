import { hydrateRoot } from "react-dom/client";
import { LiveStorefront } from "./LiveStorefront";
import type { StorePageData } from "./types";
import "./storefront.css";

type BootData = { page: StorePageData; origin: string };
const root = document.getElementById("store-root");
const dataElement = document.getElementById("store-data");
if (!root || !dataElement?.textContent) throw new Error("Storefront page data is missing");
const boot = JSON.parse(dataElement.textContent) as BootData;

hydrateRoot(root, <LiveStorefront initialPage={boot.page} origin={boot.origin} />);
