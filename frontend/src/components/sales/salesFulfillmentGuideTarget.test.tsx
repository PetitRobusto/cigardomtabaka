import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import SalesOrderCard from "./SalesOrderCard";
import type { SalesOrder } from "../../types";

const order: SalesOrder = {
  id: 7, order_number: "SO-0007", status: "confirmed", display_status: "已确认", fulfillment_status: "confirmed", payment_status: "unpaid", customer_id: null, customer_name: "测试客户", customer: null, goods_amount_cny: 100, customer_transport_fee_cny: 0, transport_payer: "company", amount_due_cny: 100, total_revenue: 100, total_cost: 40, total_profit: 60, fifo_cost: 40, contribution_profit: 60, actual_transport_cost_cny: 0, locked: true, created_at: "2026-08-14T00:00:00Z", confirmed_at: null, cancelled_at: null, note: "", items: [{ id: 1, cigar_id: 2, cigar_name: "测试雪茄", quantity: 1, sale_unit: "stick", sale_quantity: null, box_size: null, unit_price: 100, unit_cost: 40, revenue: 100, cost: 40, profit: 60, fulfillment_type: "stock", allocations: [] }], sales_shipment: null, sales_receipt: null, sales_refund: null, sales_transport_cost: null, available_actions: ["ship"],
};

describe("sales fulfillment guide target", () => {
  it("marks the real order-card expansion control", () => {
    const html = renderToStaticMarkup(<SalesOrderCard order={order} accounts={[]} onChanged={() => {}} />);
    expect(html).toMatch(/<button[^>]*data-guide="sales-fulfillment"/);
    expect(html).toContain("SO-0007");
  });
});
