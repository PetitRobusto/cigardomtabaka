import { describe, expect, it } from "vitest";
import { isAgeConfirmationValid } from "./ageConfirmation";

describe("storefront age confirmation", () => {
  it("accepts confirmation for 30 days and rejects expired, missing, or future timestamps", () => {
    const now = Date.parse("2026-10-22T12:00:00Z");
    expect(isAgeConfirmationValid(String(now - 29 * 24 * 60 * 60 * 1000), now)).toBe(true);
    expect(isAgeConfirmationValid(String(now - 30 * 24 * 60 * 60 * 1000), now)).toBe(false);
    expect(isAgeConfirmationValid(null, now)).toBe(false);
    expect(isAgeConfirmationValid(String(now + 1000), now)).toBe(false);
  });
});
