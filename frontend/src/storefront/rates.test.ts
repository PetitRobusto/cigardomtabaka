import { describe, expect, it } from "vitest";
import { formatReferencePrice, isCurrentRate } from "./rates";
import type { StoreRates } from "./types";

const rates: StoreRates = {
  source_updated_at: "2026-10-22T12:00:00Z",
  expires_at: "2026-10-24T12:00:00Z",
  cny_per_rub: "0.08",
  usd_per_rub: "0.01",
};

describe("storefront reference rates", () => {
  it("keeps conversion available only before the explicit expiry time", () => {
    const beforeExpiry = Date.parse("2026-10-24T11:59:59Z");
    const atExpiry = Date.parse("2026-10-24T12:00:00Z");
    expect(isCurrentRate(rates, beforeExpiry)).toBe(true);
    expect(isCurrentRate(rates, atExpiry)).toBe(false);
    expect(formatReferencePrice("12345.67", "CNY", "en", rates, atExpiry)).toBeNull();
  });

  it("shows converted amounts as references while preserving fractional RUB source values", () => {
    expect(formatReferencePrice("12345.67", "CNY", "en", rates, Date.parse("2026-10-23T12:00:00Z"))).toContain("987.65");
    expect(formatReferencePrice("12345.67", "USD", "en", { ...rates, usd_per_rub: "0" }, Date.parse("2026-10-23T12:00:00Z"))).toBeNull();
  });
});
