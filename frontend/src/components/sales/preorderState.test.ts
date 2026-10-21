import { describe, expect, it } from 'vitest';
import { preorderItems, salesPreorderLabel, salesPreorderStage } from './preorderState';
import type { PreorderSource, SalesOrder, SalesOrderItem } from '../../types';

const source: PreorderSource = {
  purchase_order_id: 5, order_number: 'PO-000005', status: 'draft', can_create: true,
  items: [
    { cigar_id: 1, cigar_name: '25支装', sale_unit: 'box', box_size: 25, purchase_quantity: 250, committed_quantity: 200, remaining_quantity: 50 },
    { cigar_id: 1, cigar_name: '10支装', sale_unit: 'box', box_size: 10, purchase_quantity: 20, committed_quantity: 0, remaining_quantity: 20 },
  ],
};
describe('preorder input', () => {
  it('keeps different packaging separate and converts boxes to sticks', () => {
    const rows = preorderItems(source, [
      { selected: true, quantity: '2', unitPrice: '1500' },
      { selected: true, quantity: '1', unitPrice: '600' },
    ]);
    expect(rows.map(row => [row.quantity, row.sale_quantity, row.box_size, row.source_purchase_order_id, row.fulfillment_type])).toEqual([[50, 2, 25, 5, 'preorder'], [10, 1, 10, 5, 'preorder']]);
  });
  it.each(['0', '-1', '1.5', '3', 'Infinity', ''])('rejects invalid or excessive quantity %s', quantity => {
    expect(() => preorderItems(source, [{ selected: true, quantity, unitPrice: '1500' }])).toThrow('数量');
  });
  it.each(['', '-1', '1.234', 'NaN'])('rejects invalid prices %s', unitPrice => {
    expect(() => preorderItems(source, [{ selected: true, quantity: '1', unitPrice }])).toThrow('人民币单价');
  });
  it('rejects an unavailable source and empty selection', () => {
    expect(() => preorderItems({ ...source, can_create: false }, [])).toThrow('当前不能');
    expect(() => preorderItems(source, [])).toThrow('至少选择');
  });
});

describe('订单列表预售标识', () => {
  const preorder = { fulfillment_type: 'preorder', source_purchase_order_id: 5 } as SalesOrderItem;
  const order = (items: SalesOrderItem[], fulfillment_status = 'confirmed') => ({ items, fulfillment_status }) as SalesOrder;
  it('现货无标识，纯预售与混合订单区分', () => {
    const stock = { fulfillment_type: 'in_stock' } as SalesOrderItem;
    expect(salesPreorderLabel(order([stock]))).toBeNull();
    expect(salesPreorderLabel(order([preorder]))).toBe('预售单');
    expect(salesPreorderLabel(order([preorder, stock]))).toBe('含预售');
  });
  it('按全部预售明细判断进度，不把部分到货显示为可备货', () => {
    const reserved = { ...preorder, preorder_reserved: true };
    expect(salesPreorderStage(order([reserved, preorder]))).toBe('部分预留');
    expect(salesPreorderStage(order([reserved]))).toBe('待出库');
    expect(salesPreorderStage(order([{ ...reserved, preorder_prepared: true }]))).toBe('待出库');
    expect(salesPreorderStage(order([{ ...preorder, source_purchase_order_id: null }]))).toBe('待预留');
  });
  it.each(['draft', 'shipped', 'cancelled', 'returned'])('%s 保留预售身份，不再显示待到货进度', status => {
    expect(salesPreorderLabel(order([preorder], status))).toBe('预售单');
    expect(salesPreorderStage(order([preorder], status))).toBeNull();
  });
});
