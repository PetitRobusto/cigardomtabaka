import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import AccountingPanel from "./AccountingPanel";
import { selectReconciliationAccountId } from "./AccountingPanel.logic";

describe("accounting guide target contract", () => {
  it("uses the first active account when the async account list arrives", () => {
    expect(selectReconciliationAccountId([{ id: 7, is_active: true }], 0)).toBe(7);
    expect(selectReconciliationAccountId([
      { id: 7, is_active: true },
      { id: 9, is_active: true },
    ], 9)).toBe(9);
    expect(selectReconciliationAccountId([{ id: 7, is_active: true }], 9)).toBe(7);
    expect(selectReconciliationAccountId([{ id: 9, is_active: false }, { id: 7, is_active: true }], 9)).toBe(7);
  });

  it("renders guide targets on the real reconciliation and profit regions", () => {
    const html = renderToStaticMarkup(<AccountingPanel month="2026-08" onChanged={() => {}} reconciliations={[]} />);
    expect(html).toMatch(/<section data-guide="accounting-reconciliation"/);
    expect(html).toMatch(/<div data-guide="accounting-profit"/);
  });
});
