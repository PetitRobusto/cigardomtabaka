import type { PaymentOrder } from '../types';

export function eligiblePaymentOrders(orders: PaymentOrder[]): PaymentOrder[] {
  return orders.filter(order =>
    (order.fulfillment_status === 'confirmed' || order.fulfillment_status === 'shipped') &&
    ['unpaid', 'partial'].includes(order.payment_status),
  );
}

export function paymentOrderSummary(order: PaymentOrder) {
  return {
    order_number: order.order_number || `SO-${order.id}`,
    customer_name: order.customer_name || order.customer?.name || '散客',
    amount_due_cny: order.amount_due_cny,
    received_amount_cny: order.received_amount_cny ?? 0,
    remaining_amount_cny: order.remaining_amount_cny ?? order.amount_due_cny,
    status: order.display_status || order.status,
    item_count: order.items.length,
    items: order.items.map(item => ({
      name: item.cigar_name,
      quantity: item.sale_quantity ?? item.quantity,
      sale_unit: item.sale_unit,
      unit_price: item.unit_price,
    })),
  };
}

export function canSubmitPayment(order: PaymentOrder | null, paymentMethodId: string): boolean {
  return Boolean(
    order &&
    (order.fulfillment_status === 'confirmed' || order.fulfillment_status === 'shipped') &&
    ['unpaid', 'partial'].includes(order.payment_status) &&
    paymentMethodId,
  );
}
