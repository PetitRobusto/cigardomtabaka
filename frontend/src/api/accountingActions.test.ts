import { beforeEach, describe, expect, it, vi } from 'vitest';

// 资金动作必须把金额作为 Decimal 字符串传给后端，不能先转成 JS number。
const client = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
}));

vi.mock('axios', () => ({
  default: {
    create: () => client,
    isAxiosError: (value: unknown) => Boolean((value as { isAxiosError?: boolean })?.isAxiosError),
  },
}));

import {
  cancelPurchaseOrder,
  confirmReconciliation,
  confirmSalesOrder,
  confirmDividend,
  createDividend,
  createPurchaseOrder,
  createReconciliation,
  createSalesOrder,
  exchangeToRub,
  fetchAccountingActions,
  parseAccountingApiError,
  payPurchaseOrder,
  previewDividend,
  receivePurchaseOrder,
  recordExpense,
  updateDividend,
  updatePurchaseOrder,
  updateSalesOrder,
} from '../api';

const businessDate = '2026-08-15';

function response<T>(data: T) {
  return Promise.resolve({ data });
}

describe('accounting action API contracts', () => {
  beforeEach(() => vi.clearAllMocks());
  it('lists actions through an independent accounting actions endpoint', async () => {
    client.get.mockReturnValueOnce(response({ purchases: [], dividends: [] }));

    await expect(fetchAccountingActions()).resolves.toEqual({ purchases: [], dividends: [] });
    expect(client.get).toHaveBeenCalledWith('/accounting/actions/');
  });


  it('unwraps sales-order responses for create, update, and workflow actions', async () => {
    client.post
      .mockReturnValueOnce(response({ sales_order: { id: 61, status: 'draft' } }))
      .mockReturnValueOnce(response({ sales_order: { id: 61, status: 'confirmed' } }));
    client.patch.mockReturnValueOnce(response({ sales_order: { id: 61, status: 'draft', note: 'updated' } }));

    await expect(createSalesOrder({ items: [] })).resolves.toMatchObject({ id: 61, status: 'draft' });
    await expect(updateSalesOrder(61, { items: [], note: 'updated' })).resolves.toMatchObject({ id: 61, note: 'updated' });
    await expect(confirmSalesOrder(61)).resolves.toMatchObject({ id: 61, status: 'confirmed' });

    expect(client.post).toHaveBeenNthCalledWith(1, '/sales/orders/', { items: [] }, expect.anything());
    expect(client.patch).toHaveBeenCalledWith('/sales/orders/61/', { items: [], note: 'updated' }, expect.anything());
    expect(client.post).toHaveBeenNthCalledWith(2, '/sales/orders/61/confirm/', {}, expect.anything());
  });

  it('unwraps reconciliation responses for create and confirm', async () => {
    const payload = { account_id: 11, business_date: businessDate, actual_amount: '100.00', note: '' };
    client.post
      .mockReturnValueOnce(response({ reconciliation: { id: 71, status: 'pending' } }))
      .mockReturnValueOnce(response({ reconciliation: { id: 71, status: 'confirmed' } }));

    await expect(createReconciliation(payload)).resolves.toMatchObject({ id: 71, status: 'pending' });
    await expect(confirmReconciliation(71)).resolves.toMatchObject({ id: 71, status: 'confirmed' });

    expect(client.post).toHaveBeenNthCalledWith(1, '/accounting/reconciliations/', payload, expect.anything());
    expect(client.post).toHaveBeenNthCalledWith(2, '/accounting/reconciliations/71/confirm/', {}, expect.anything());
  });
  it('posts CNY or USDT to RUB with Decimal strings and an idempotency header', async () => {
    client.post.mockReturnValueOnce(response({ transaction: { id: 1 } }));

    await exchangeToRub({
      source_account_id: 11,
      rub_account_id: 22,
      source_amount: '100.00000000',
      rub_amount: '1200.00',
      business_date: businessDate,
    });

    expect(client.post).toHaveBeenCalledWith(
      '/accounting/exchanges/',
      {
        source_account_id: 11,
        rub_account_id: 22,
        source_amount: '100.00000000',
        rub_amount: '1200.00',
        business_date: businessDate,
      },
      expect.objectContaining({ headers: { 'Idempotency-Key': expect.any(String) } }),
    );
  });

  it('uses canonical purchase box fields for create and update', async () => {
    const item = {
      cigar_id: 7,
      box_size: 25,
      box_quantity: 2,
      unit_price_rub_per_box: '25000.00',
    };
    client.post.mockReturnValueOnce(response({ purchase_order: { id: 31 } }));
    client.patch.mockReturnValueOnce(response({ purchase_order: { id: 31, version: 2 } }));

    await createPurchaseOrder({ supplier_id: 3, business_date: businessDate, items: [item], note: '' });
    await updatePurchaseOrder(31, { expected_version: 1, items: [item], note: '' });

    expect(client.post).toHaveBeenCalledWith(
      '/accounting/purchases/',
      { supplier_id: 3, business_date: businessDate, items: [item], note: '' },
      expect.objectContaining({ headers: { 'Idempotency-Key': expect.any(String) } }),
    );
    expect(client.patch).toHaveBeenCalledWith(
      '/accounting/purchases/31/',
      { expected_version: 1, items: [item], note: '' },
      expect.objectContaining({ headers: { 'Idempotency-Key': expect.any(String) } }),
    );
  });

  it('supports one whole-order payment, receipt, and draft cancellation', async () => {
    client.post
      .mockReturnValueOnce(response({ purchase_order: { id: 31, status: 'in_transit' } }))
      .mockReturnValueOnce(response({ purchase_batches: [99] }))
      .mockReturnValueOnce(response({ purchase_order: { id: 32, status: 'cancelled' } }));

    await payPurchaseOrder(31, { rub_account_id: 22, business_date: businessDate });
    await receivePurchaseOrder(31, { business_date: businessDate, note: '' });
    await cancelPurchaseOrder(32, { expected_version: 1, note: '' });

    expect(client.post).toHaveBeenNthCalledWith(1, '/accounting/purchases/31/pay/', {
      rub_account_id: 22,
      business_date: businessDate,
    }, expect.objectContaining({ headers: { 'Idempotency-Key': expect.any(String) } }));
    expect(client.post).toHaveBeenNthCalledWith(2, '/accounting/purchases/31/receive/', {
      business_date: businessDate,
      note: '',
    }, expect.objectContaining({ headers: { 'Idempotency-Key': expect.any(String) } }));
    expect(client.post).toHaveBeenNthCalledWith(3, '/accounting/purchases/32/cancel/', {
      expected_version: 1,
      note: '',
    }, expect.objectContaining({ headers: { 'Idempotency-Key': expect.any(String) } }));
  });

  it('posts an expense with category-specific account and Decimal amount', async () => {
    client.post.mockReturnValueOnce(response({ expense: { id: 41, amount_cny: '88.00' } }));

    await recordExpense({
      category: 'rent',
      amount: '88.00',
      fund_account_id: 11,
      business_date: businessDate,
      note: '八月房租',
    });

    expect(client.post).toHaveBeenCalledWith('/accounting/expenses/', {
      category: 'rent', amount: '88.00', fund_account_id: 11, business_date: businessDate, note: '八月房租',
    }, expect.objectContaining({ headers: { 'Idempotency-Key': expect.any(String) } }));
  });

  it('supports dividend create, update, preview, and warning-confirm', async () => {
    client.post
      .mockReturnValueOnce(response({ dividend: { id: 51, status: 'draft' } }))
      .mockReturnValueOnce(response({
        preview: {
          retained_earnings_cny: '500.00',
          requested_cny: '1000.00',
          warning: {
            code: 'retained_earnings_exceeded',
            retained_earnings_cny: '500.00',
            requested_cny: '1000.00',
            fingerprint: 'fp',
          },
          warning_fingerprint: 'fp',
        },
      }))
      .mockReturnValueOnce(response({ dividend: { id: 51, status: 'confirmed' } }));
    client.patch.mockReturnValueOnce(response({ dividend: { id: 51, version: 2 } }));

    await createDividend({ total_cny: '1000.00', business_date: businessDate, note: '' });
    await updateDividend(51, {
      total_cny: '1000.00', partner_a_amount_cny: '500.00', partner_b_amount_cny: '500.00',
      partner_a_account_id: 11, partner_b_account_id: 12, expected_version: 1, note: '',
    });
    await previewDividend(51);
    await confirmDividend(51, { expected_version: 2, warning_fingerprint: 'fp', warning_ack: true });

    expect(client.post).toHaveBeenNthCalledWith(1, '/accounting/dividends/', {
      total_cny: '1000.00', business_date: businessDate, note: '',
    }, expect.objectContaining({ headers: { 'Idempotency-Key': expect.any(String) } }));
    expect(client.patch).toHaveBeenCalledWith('/accounting/dividends/51/', expect.objectContaining({ expected_version: 1 }), expect.anything());
    expect(client.post).toHaveBeenNthCalledWith(2, '/accounting/dividends/51/preview/', {}, expect.objectContaining({ headers: { 'Idempotency-Key': expect.any(String) } }));
    expect(client.post).toHaveBeenNthCalledWith(3, '/accounting/dividends/51/confirm/', {
      expected_version: 2, warning_fingerprint: 'fp', warning_ack: true,
    }, expect.objectContaining({ headers: { 'Idempotency-Key': expect.any(String) } }));
  });

  it('normalizes the stable error envelope without losing code or details', () => {
    expect(parseAccountingApiError({
      isAxiosError: true,
      response: { status: 409, data: { error: '余额不足', code: 'insufficient_balance', details: { account_id: '11' } } },
    })).toEqual({ code: 'insufficient_balance', message: '余额不足', details: { account_id: '11' }, status: 409 });
    expect(parseAccountingApiError(new Error('网络失败'))).toMatchObject({ code: 'unknown', message: '网络失败' });
  });
});
