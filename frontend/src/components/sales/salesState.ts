export type SalesStatus = string;

export type TransportPayer = "customer" | "company";

export interface TransportSummary {
  goodsAmount: number;
  customerTransport: number;
  amountDue: number;
}

// Company-paid transport never becomes customer receivable, even when a draft contains a fee.
export function transportSummary(
  payer: TransportPayer,
  goodsAmount: number,
  transportFee: number,
): TransportSummary {
  const goods = Number.isFinite(Number(goodsAmount)) ? Number(goodsAmount) : 0;
  const transport = Number.isFinite(Number(transportFee))
    ? Number(transportFee)
    : 0;
  const customerTransport = payer === "company" ? 0 : transport;
  return {
    goodsAmount: goods,
    customerTransport,
    amountDue: goods + customerTransport,
  };
}

export function cigarSearchParams(
  trigger: "focus" | "input",
  query = "",
): { q: string; stock_only: boolean } {
  return { q: trigger === "focus" ? "" : query.trim(), stock_only: true };
}

export interface SalesOrderSummaryInput {
  fulfillment_status: SalesStatus;
  payment_status: SalesStatus;
  amount_due_cny: number | string | null | undefined;
}

export interface SalesOrderStateInput {
  fulfillment_status: SalesStatus;
  payment_status: SalesStatus;
}

export interface SalesAmountSummary {
  count: number;
  amount: number;
}

export interface SalesOrderSummary {
  total: number;
  draft: SalesAmountSummary;
  confirmed: SalesAmountSummary;
  shipped: SalesAmountSummary;
  paid: SalesAmountSummary;
  unpaid: SalesAmountSummary;
  cancelled: SalesAmountSummary;
}

const amountOf = (value: number | string | null | undefined) => {
  const amount = Number(value ?? 0);
  return Number.isFinite(amount) ? amount : 0;
};

const empty = (): SalesAmountSummary => ({ count: 0, amount: 0 });

export function summarizeSalesOrders(
  orders: SalesOrderSummaryInput[],
): SalesOrderSummary {
  const summary: SalesOrderSummary = {
    total: orders.length,
    draft: empty(),
    confirmed: empty(),
    shipped: empty(),
    paid: empty(),
    unpaid: empty(),
    cancelled: empty(),
  };

  for (const order of orders) {
    const amount = amountOf(order.amount_due_cny);
    const fulfillment = order.fulfillment_status;
    const payment = order.payment_status;
    const fulfillmentSummary =
      summary[
        fulfillment as keyof Pick<
          SalesOrderSummary,
          "draft" | "confirmed" | "shipped" | "cancelled"
        >
      ];
    if (fulfillmentSummary) {
      fulfillmentSummary.count += 1;
      fulfillmentSummary.amount += amount;
    }
    const active = fulfillment === "confirmed" || fulfillment === "shipped";
    const paymentSummary =
      active && payment === "paid"
        ? summary.paid
        : active && payment === "unpaid"
          ? summary.unpaid
          : undefined;
    if (paymentSummary) {
      paymentSummary.count += 1;
      paymentSummary.amount += amount;
    }
  }
  return summary;
}

export function activeSalesAmount(orders: SalesOrderSummaryInput[]): number {
  return orders.reduce(
    (total, order) =>
      order.fulfillment_status === "confirmed" ||
      order.fulfillment_status === "shipped"
        ? total + amountOf(order.amount_due_cny)
        : total,
    0,
  );
}

export function activeSalesProfit<
  T extends SalesOrderSummaryInput & { contribution_profit?: number | string },
>(orders: T[]): number {
  return orders.reduce(
    (total, order) =>
      order.fulfillment_status === "confirmed" ||
      order.fulfillment_status === "shipped"
        ? total + amountOf(order.contribution_profit)
        : total,
    0,
  );
}

export function statusLabel(status: string): string {
  return (
    {
      draft: "草稿",
      confirmed: "已确认",
      shipped: "已出库",
      cancelled: "已取消",
      unpaid: "待收款",
      paid: "已收款",
      refund_pending: "待退款",
      refunded: "已退款",
      returned: "已退货",
      completed: "已完成",
    }[status] ?? status
  );
}

export function statusTagTone(status: string): string {
  return (
    {
      draft: "border-gray-200 bg-gray-100 text-gray-700",
      confirmed: "border-indigo-200 bg-indigo-50 text-indigo-700",
      shipped: "border-blue-200 bg-blue-50 text-blue-700",
      cancelled: "border-red-200 bg-red-50 text-red-700",
      returned: "border-purple-200 bg-purple-50 text-purple-700",
      unpaid: "border-amber-200 bg-amber-50 text-amber-800",
      paid: "border-green-200 bg-green-50 text-green-700",
      refund_pending: "border-orange-200 bg-orange-50 text-orange-800",
      refunded: "border-teal-200 bg-teal-50 text-teal-700",
    }[status] ?? "border-border bg-[#F5EFE8] text-muted"
  );
}

export function orderDisplayStatus(
  order: SalesOrderStateInput & { status?: string },
): string {
  if (order.status === "completed") return "已完成";
  if (order.fulfillment_status === "cancelled") {
    return `已取消${order.payment_status === "refund_pending" ? " · 待退款" : order.payment_status === "refunded" ? " · 已退款" : ""}`;
  }
  if (order.fulfillment_status === "returned") {
    return `已退货${order.payment_status === "refund_pending" ? " · 待退款" : order.payment_status === "refunded" ? " · 已退款" : ""}`;
  }
  const fulfillment =
    order.fulfillment_status === "draft"
      ? "草稿"
      : order.fulfillment_status === "confirmed"
        ? "已确认"
        : order.fulfillment_status === "shipped"
          ? "已出库"
          : statusLabel(order.fulfillment_status);
  const payment =
    order.payment_status === "paid"
      ? "已收款"
      : order.payment_status === "unpaid"
        ? "待收款"
        : statusLabel(order.payment_status);
  if (order.fulfillment_status === "draft") return fulfillment;
  return payment === "已收款" ? `${fulfillment} · ${payment}` : payment;
}

export function availableActions(order: SalesOrderStateInput): string[] {
  if (order.fulfillment_status === "draft") return ["confirm", "cancel"];
  if (order.fulfillment_status === "confirmed") {
    return order.payment_status === "unpaid"
      ? ["ship", "receive", "cancel"]
      : ["ship", "cancel"];
  }
  if (order.fulfillment_status === "shipped") {
    return order.payment_status === "unpaid"
      ? ["return", "receive", "transport_cost"]
      : ["return", "transport_cost"];
  }
  if (
    order.fulfillment_status === "cancelled" &&
    order.payment_status === "refund_pending"
  )
    return ["refund"];
  if (
    order.fulfillment_status === "returned" &&
    order.payment_status === "refund_pending"
  )
    return ["refund"];
  return [];
}

export function receiveAmountMatchesDue(
  value: string,
  amountDue: number | string,
): boolean {
  return validateMoneyInput(value) && Number(value) === Number(amountDue);
}

export function actionLabel(action: string): string {
  return (
    {
      confirm: "确认订单",
      cancel: "取消订单",
      ship: "出库",
      receive: "收款",
      refund: "退款",
      return: "整单退货",
      transport_cost: "记录人肉成本",
    }[action] ?? action
  );
}

export function formatCny(value: number | string | null | undefined): string {
  const amount = amountOf(value);
  return `¥${amount.toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

/** 账户原币显示按币种收口；RUB/CNY 固定两位，USDT 保留有效精度。 */
export function formatOriginalAmount(
  value: number | string | null | undefined,
  currency: string,
): string {
  const amount = amountOf(value);
  const digits =
    currency === "USDT"
      ? { minimumFractionDigits: 2, maximumFractionDigits: 8 }
      : { minimumFractionDigits: 2, maximumFractionDigits: 2 };
  return amount.toLocaleString("zh-CN", digits);
}

export function formatSignedCny(
  value: number | string | null | undefined,
): string {
  const amount = amountOf(value);
  return amount < 0 ? `-${formatCny(Math.abs(amount))}` : formatCny(amount);
}

export function validateMoneyInput(value: string): boolean {
  if (!value.trim() || !/^\d+(?:\.\d{1,2})?$/.test(value.trim())) return false;
  const amount = Number(value);
  return Number.isFinite(amount) && amount >= 0;
}

export function validatePositiveMoneyInput(value: string): boolean {
  return validateMoneyInput(value) && Number(value) > 0;
}

export function initialActionAmount(
  action: string,
  amountDue: number | string,
): string {
  return action === "receive" ? String(amountDue ?? "") : "";
}

export function actionNeedsFundAccount(action: string): boolean {
  return action === "receive" || action === "transport_cost";
}

export function salesActionBlockedByAccount(
  action: string,
  accountsError: string,
): boolean {
  return Boolean(accountsError) && actionNeedsFundAccount(action);
}

export function transportPayerChange(
  currentFee: string,
  nextPayer: TransportPayer,
): { payer: TransportPayer; fee: string } {
  // Once company clears the field, switching back to customer keeps the cleared value.
  return { payer: nextPayer, fee: nextPayer === "company" ? "0" : currentFee };
}

/** @deprecated Use transportPayerChange(currentFee, payer). */
export function transportPayerTransition(
  payer: TransportPayer,
  currentFee: string,
): { payer: TransportPayer; fee: string } {
  return transportPayerChange(currentFee, payer);
}
