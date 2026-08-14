import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const accountingPanelSource = readFileSync(new URL("./AccountingPanel.tsx", import.meta.url), "utf8");

describe("accounting guide target contract", () => {
  it("keeps guide targets attached to the real accounting regions", () => {
    expect(accountingPanelSource).toContain("data-guide=\"accounting-reconciliation\"");
    expect(accountingPanelSource).toContain("data-guide=\"accounting-profit\"");
  });
});
