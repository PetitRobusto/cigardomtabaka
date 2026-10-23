import type { StoreLocale, StoreRates } from "./types";

export type ReferenceCurrency = "CNY" | "USD";

export function isCurrentRate(rates: StoreRates | null, now = Date.now()): rates is StoreRates {
  if (!rates?.expires_at) return false;
  const expiresAt = Date.parse(rates.expires_at);
  return Number.isFinite(expiresAt) && expiresAt > now;
}

export function formatReferencePrice(amountRub: string, currency: ReferenceCurrency, locale: StoreLocale, rates: StoreRates | null, now = Date.now()): string | null {
  if (!isCurrentRate(rates, now)) return null;
  const amount = Number(amountRub);
  const rate = Number(currency === "CNY" ? rates.cny_per_rub : rates.usd_per_rub);
  if (!Number.isFinite(amount) || !Number.isFinite(rate) || rate <= 0) return null;
  const localeTag = locale === "zh" ? "zh-CN" : locale === "ru" ? "ru-RU" : "en";
  return new Intl.NumberFormat(localeTag, { style: "currency", currency, maximumFractionDigits: 2 }).format(amount * rate);
}
