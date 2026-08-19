import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import AccountingPanel from "./AccountingPanel";
import FundAccountManager from "../accounting/FundAccountManager";
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

  it("可由工作台操作按钮打开现有对账弹窗", () => {
    const html = renderToStaticMarkup(<AccountingPanel month="2026-08" onChanged={() => {}} reconciliationOpen accounts={[{ id: 7, name: "人民币账户", currency: "CNY", custodian_id: null, is_active: true }]} reconciliations={[]} />);
    expect(html).toContain('role="dialog"');
    expect(html).toContain('新建账户对账');
  });
  it("资金账户原币余额不显示无意义尾数", () => {
    const html = renderToStaticMarkup(<FundAccountManager
      accounts={[{ id: 7, name: "卢布银行卡", currency: "RUB", custodian_id: null, is_active: true }]}
      balances={[{ account_id: 7, name: "卢布银行卡", currency: "RUB", original_balance: "1200.00000000", cny_book_cost: "100.00000000" }]}
      onChanged={() => {}}
    />);
    expect(html).toContain("1,200.00 RUB");
    expect(html).not.toContain("1200.00000000");
  });
});
