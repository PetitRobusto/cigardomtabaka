export type SalesStatus = string;

export type TransportPayer = 'customer' | 'company';

export interface TransportSummary {
  goodsAmount: number;
  customerTransport: number;
  amountDue: number;
}

// Company-paid transport never becomes customer receivable, even when a draft contains a fee.
export function transportSummary(payer: TransportPayer, goodsAmount: number, transportFee: number): TransportSummary {
  const goods = Number.isFinite(Number(goodsAmount)) ? Number(goodsAmount) : 0;
  const transport = Number.isFinite(Number(transportFee)) ? Number(transportFee) : 0;
  const customerTransport = payer === 'company' ? 0 : transport;
  return { goodsAmount: goods, customerTransport, amountDue: goods + customerTransport };
}

export function cigarSearchParams(trigger: 'focus' | 'input', query = ''): { q: string; stock_only: boolean } {
  return { q: trigger === 'focus' ? '' : query.trim(), stock_only: true };
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

export function summarizeSalesOrders(orders: SalesOrderSummaryInput[]): SalesOrderSummary {
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
    const fulfillmentSummary = summary[fulfillment as keyof Pick<SalesOrderSummary, 'draft' | 'confirmed' | 'shipped' | 'cancelled'>];
    if (fulfillmentSummary) {
      fulfillmentSummary.count += 1;
      fulfillmentSummary.amount += amount;
    }
    const paymentSummary = fulfillment !== 'draft' && fulfillment !== 'cancelled' && payment === 'paid'
      ? summary.paid
      : fulfillment !== 'draft' && fulfillment !== 'cancelled' && payment === 'unpaid'
        ? summary.unpaid
        : undefined;
    if (paymentSummary) {
      paymentSummary.count += 1;
      paymentSummary.amount += amount;
    }
  }
  return summary;
}

export function statusLabel(status: string): string {
  return {
    draft: '草稿',
    confirmed: '已确认',
    shipped: '已出库',
    cancelled: '已取消',
    unpaid: '待收款',
    paid: '已收款',
    refund_pending: '待退款',
    refunded: '已退款',
  }[status] ?? status;
}

export function orderDisplayStatus(order: SalesOrderStateInput): string {
  if (order.fulfillment_status === 'cancelled') {
    return `已取消${order.payment_status === 'refund_pending' ? ' · 待退款' : order.payment_status === 'refunded' ? ' · 已退款' : ''}`;
  }
  const fulfillment = order.fulfillment_status === 'draft'
    ? '草稿'
    : order.fulfillment_status === 'confirmed'
      ? '已确认'
      : order.fulfillment_status === 'shipped'
        ? '已出库'
        : statusLabel(order.fulfillment_status);
  const payment = order.payment_status === 'paid'
    ? '已收款'
    : order.payment_status === 'unpaid'
      ? '待收款'
      : statusLabel(order.payment_status);
  if (order.fulfillment_status === 'draft') return fulfillment;
  return payment === '已收款' ? `${fulfillment} · ${payment}` : payment;
}

export function availableActions(order: SalesOrderStateInput): string[] {
  if (order.fulfillment_status === 'draft') return ['confirm'];
  if (order.fulfillment_status === 'confirmed') {
    return order.payment_status === 'unpaid' ? ['ship', 'cancel', 'receive'] : ['ship', 'cancel'];
  }
  if (order.fulfillment_status === 'shipped') {
    return order.payment_status === 'unpaid' ? ['receive', 'transport_cost'] : ['transport_cost'];
  }
  if (order.fulfillment_status === 'cancelled' && order.payment_status === 'refund_pending') return ['refund'];
  return [];
}

export function actionLabel(action: string): string {
  return {
    confirm: '确认订单',
    cancel: '取消订单',
    ship: '出库',
    receive: '收款',
    refund: '退款',
    transport_cost: '记录人肉成本',
  }[action] ?? action;
}

export function formatCny(value: number | string | null | undefined): string {
  const amount = amountOf(value);
  return `¥${amount.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function formatSignedCny(value: number | string | null | undefined): string {
  const amount = amountOf(value);
  return amount < 0 ? `-${formatCny(Math.abs(amount))}` : formatCny(amount);
}

export function validateMoneyInput(value: string): boolean {
  if (!value.trim() || !/^\d+(?:\.\d{1,2})?$/.test(value.trim())) return false;
  const amount = Number(value);
  return Number.isFinite(amount) && amount >= 0;
}

export function initialActionAmount(action: string, amountDue: number | string): string {
  return action === 'receive' ? String(amountDue ?? '') : '';
}

export function actionNeedsFundAccount(action: string): boolean {
  return action === 'receive' || action === 'transport_cost';
}

export function isSalesAccountingNavActive(target: string, hash: string): boolean {
  return target === '/sales#accounting' ? hash === 'accounting' : target === '/sales' && hash !== 'accounting';
}


export function transportPayerChange(currentFee: string, nextPayer: TransportPayer): { payer: TransportPayer; fee: string } {
  // Once company clears the field, switching back to customer keeps the cleared value.
  return { payer: nextPayer, fee: nextPayer === 'company' ? '0' : currentFee };
}

/** @deprecated Use transportPayerChange(currentFee, payer). */
export function transportPayerTransition(payer: TransportPayer, currentFee: string): { payer: TransportPayer; fee: string } {
  return transportPayerChange(currentFee, payer);
}
