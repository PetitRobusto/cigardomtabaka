import { createContext, useContext } from "react";
import { formatReferencePrice } from "./rates";
import type { StoreLocale, StoreRates } from "./types";

const ReferencePriceContext = createContext<{ currency: "RUB" | "CNY" | "USD"; rates: StoreRates | null }>({ currency: "RUB", rates: null });

export function ReferencePrices({ currency, rates, children }: { currency: "RUB" | "CNY" | "USD"; rates: StoreRates | null; children: React.ReactNode }) {
  return <ReferencePriceContext.Provider value={{ currency, rates }}>{children}</ReferencePriceContext.Provider>;
}

export function ReferencePrice({ amount, locale, label }: { amount: string; locale: StoreLocale; label: string }) {
  const { currency, rates } = useContext(ReferencePriceContext);
  const converted = currency === "RUB" ? null : formatReferencePrice(amount, currency, locale, rates);
  return <span className="store-price-reference" data-reference-price="true" data-reference-label={label} aria-live="polite" hidden={converted === null}>{converted ? `≈ ${converted} · ${label}` : ""}</span>;
}
