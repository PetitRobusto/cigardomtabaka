import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import AccountingPanel from "./AccountingPanel";

describe("accounting guide target contract", () => {
  it("renders guide targets on the real reconciliation and profit regions", () => {
    const html = renderToStaticMarkup(<AccountingPanel month="2026-08" onChanged={() => {}} reconciliations={[]} />);
    expect(html).toMatch(/<section data-guide="accounting-reconciliation"/);
    expect(html).toMatch(/<div data-guide="accounting-profit"/);
  });
});
