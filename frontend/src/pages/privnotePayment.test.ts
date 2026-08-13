import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  eligiblePaymentOrders,
  paymentOrderSummary,
  canSubmitPayment,
} from './privnotePayment';
import type { PaymentOrder } from '../types';

const order = (overrides: Partial<PaymentOrder> = {}): PaymentOrder => ({
  id: 1,
  order_number: 'SO-001',
  status: 'confirmed',
  display_status: '已确认 · 待收款',
  fulfillment_status: 'confirmed',
  payment_status: 'unpaid',
  customer_id: 8,
  customer_name: '王先生',
  customer: null,
  goods_amount_cny: 100,
  customer_transport_fee_cny: 0,
  amount_due_cny: 100,
  total_revenue: 100,
  total_cost: 60,
  total_profit: 40,
  fifo_cost: 60,
  contribution_profit: 40,
  actual_transport_cost_cny: 0,
  locked: true,
  created_at: '2026-08-12T00:00:00Z',
  confirmed_at: '2026-08-12T00:00:00Z',
  cancelled_at: null,
  note: '',
  items: [],
  sales_shipment: null,
  sales_receipt: null,
  sales_refund: null,
  sales_transport_cost: null,
  available_actions: [],
  ...overrides,
});

describe('privnote payment helpers', () => {
  it('keeps only confirmed or shipped unpaid orders', () => {
    expect(eligiblePaymentOrders([
      order(),
      order({ id: 2, fulfillment_status: 'shipped' }),
      order({ id: 3, fulfillment_status: 'draft' }),
      order({ id: 4, fulfillment_status: 'cancelled' }),
      order({ id: 5, payment_status: 'paid' }),
    ]).map(item => item.id)).toEqual([1, 2]);
  });

  it('builds a selected-order summary for display and preview', () => {
    const selected = order({
      items: [{
        id: 10,
        cigar_id: 22,
        cigar_name: '雪茄 A',
        sale_unit: 'stick',
        quantity: 2,
        sale_quantity: 2,
        unit_price: 50,
        box_size: null,
        allocations: [],
      }],
    });

    expect(paymentOrderSummary(selected)).toMatchObject({
      order_number: 'SO-001',
      customer_name: '王先生',
      amount_due_cny: 100,
      item_count: 1,
      items: [{ name: '雪茄 A', quantity: 2 }],
    });
  });

  it('allows submit only with an eligible order and payment method', () => {
    expect(canSubmitPayment(order(), '12')).toBe(true);
    expect(canSubmitPayment(null, '12')).toBe(false);
    expect(canSubmitPayment(order({ payment_status: 'paid' }), '12')).toBe(false);
    expect(canSubmitPayment(order(), '')).toBe(false);
  });
});

describe('privnote payment orders API', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('loads the dedicated eligible-orders endpoint without a 100-row client limit', async () => {
    const response = { orders: [order({ id: 42 })] };
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(response),
    });
    vi.stubGlobal('document', { cookie: '' });
    vi.stubGlobal('fetch', fetchMock);
    const { fetchEligiblePaymentOrders } = await import('../api');

    await expect(fetchEligiblePaymentOrders()).resolves.toEqual(response.orders);
    expect(fetchMock).toHaveBeenCalledWith(
      '/privnote/api/payment-orders/',
      expect.objectContaining({ credentials: 'same-origin' }),
    );
    expect(fetchMock.mock.calls[0][0]).not.toContain('limit=100');
  });
});
