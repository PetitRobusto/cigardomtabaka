import { expect, it } from 'vitest';
import type { SalesOrder } from '../../types';
import { canEditDraft, draftGoodsCents, draftItemsPayload, draftProducts, moneyCents } from './salesDraftItems';

const order = { id: 1, draft_revision: 42, fulfillment_status: 'draft', payment_status: 'unpaid', locked: false,
  items: [{ id: 2, cigar_id: 3, cigar_name: '预售雪茄', sale_unit: 'box', sale_quantity: 2, quantity: 50, box_size: 25,
    unit_price: 100.01, fulfillment_type: 'preorder', source_purchase_order_id: 9, allocations: [] }] } as unknown as SalesOrder;

it('round-trips box prices and preorder source with a narrow guarded items payload', () => {
  expect(draftItemsPayload(order, draftProducts(order))).toEqual({ items_only: true, expected_revision: 42,
    items: [{ cigar_id: 3, sale_unit: 'box', sale_quantity: 2, quantity: 50, box_size: 25, unit_price: '100.01', fulfillment_type: 'preorder', source_purchase_order_id: 9 }] });
  expect(draftGoodsCents(draftProducts(order))).toBe(20002);
});

it('rejects invalid quantities, packaging, prices, empty carts and missing revision', () => {
  const rows = draftProducts(order);
  for (const patch of [{ quantity: '1.5' }, { quantity: '0' }, { boxSize: '0' }, { unitPrice: '' }, { unitPrice: '-1' }, { unitPrice: '1.001' }]) {
    expect(() => draftItemsPayload(order, [{ ...rows[0], ...patch }])).toThrow();
  }
  expect(() => draftItemsPayload(order, [])).toThrow('至少保留一个商品');
  expect(() => draftItemsPayload({ ...order, draft_revision: undefined }, rows)).toThrow('重新打开');
  expect(moneyCents('0.29')).toBe(29);
  expect(moneyCents('1e2')).toBeNull();
});

it('keeps source-less legacy preorders and distinguishes stock from preorder items', () => {
  const rows = draftProducts(order);
  const legacy = { ...rows[0], sourceId: undefined };
  expect(draftItemsPayload(order, [legacy]).items[0].fulfillment_type).toBe('preorder');
  const stock = { ...rows[0], fulfillmentType: 'in_stock' as const, saleUnit: 'stick' as const, quantity: '3' };
  expect(draftItemsPayload(order, [stock]).items[0]).toMatchObject({ quantity: 3, source_purchase_order_id: undefined, box_size: undefined });
});

it('does not allow confirmed, paid, locked or allocated orders', () => {
  for (const patch of [{ fulfillment_status: 'confirmed' }, { payment_status: 'paid' }, { locked: true }, { items: [{ ...order.items[0], allocations: [{ id: 5 }] }] }]) {
    expect(canEditDraft({ ...order, ...patch } as SalesOrder)).toBe(false);
  }
});
