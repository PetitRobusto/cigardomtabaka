// @vitest-environment jsdom
import { cleanup, fireEvent, render, waitFor, within } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import SalesOrderWorkbench from './SalesOrderWorkbench';
import type { SalesOrder } from '../../types';
import { shipSalesOrder } from '../../api';

vi.mock('../../api', async importOriginal => ({
  ...await importOriginal<typeof import('../../api')>(),
  shipSalesOrder: vi.fn().mockResolvedValue({}),
}));
afterEach(() => { cleanup(); vi.clearAllMocks(); });
const order = {
  id: 19, order_number: 'SO-000019', customer_name: '预售客户', customer_id: null,
  fulfillment_status: 'confirmed', payment_status: 'partial', amount_due_cny: 3000,
  goods_amount_cny: 3000, customer_transport_fee_cny: 0, transport_payer: 'customer',
  available_actions: ['prepare_preorder', 'receive'], created_at: '2026-10-21T00:00:00Z', note: '',
  items: [{ id: 40, cigar_id: 1, cigar_name: '预售商品', quantity: 50, unit_price: '1500',
    sale_unit: 'box', sale_quantity: 2, box_size: 25, fulfillment_type: 'preorder',
    source_purchase_order_id: 5, source_purchase_order_number: 'PO-000005', preorder_prepared: false, allocations: [] }],
} as unknown as SalesOrder;
const props = { selectedId: 19, accounts: [], onSelect: vi.fn(), onChanged: vi.fn(), onCustomer: vi.fn() };

it('已预留预售直接出库，失败保留日期且不出现备货动作', async () => {
  const reserved = { ...order, available_actions: ['ship'], items: order.items.map(item => ({ ...item, preorder_reserved: true })) };
  vi.mocked(shipSalesOrder).mockRejectedValueOnce(new Error('出库日期不能早于预售预留日期')).mockResolvedValueOnce(reserved);
  const screen = render(<SalesOrderWorkbench {...props} orders={[reserved]} />);
  expect(screen.queryByRole('button', { name: '备货' })).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: '出库' }));
  const modal = within(screen.getByRole('dialog', { name: '出库' }));
  fireEvent.change(modal.getByLabelText('业务日期'), { target: { value: '2026-10-21' } });
  fireEvent.click(modal.getByRole('button', { name: '确认执行' }));
  await modal.findByText('出库日期不能早于预售预留日期');
  expect(props.onChanged).not.toHaveBeenCalled();
  fireEvent.click(modal.getByRole('button', { name: '确认执行' }));
  await waitFor(() => expect(props.onChanged).toHaveBeenCalledTimes(1));
  expect(shipSalesOrder).toHaveBeenLastCalledWith(19, '2026-10-21');
});

it('未到货不显示出库，也隐藏旧缓存中的备货动作', () => {
  const screen = render(<SalesOrderWorkbench {...props} orders={[order]} />);
  expect(screen.queryByRole('button', { name: '备货' })).toBeNull();
  expect(screen.queryByRole('button', { name: '出库' })).toBeNull();
});

it('历史备货仍可出库，时间线保留原备货记录', () => {
  const prepared = { ...order, available_actions: ['ship'], preorder_preparation: { id: 1, business_date: '2026-10-21', item_ids: [40] },
    items: order.items.map(item => ({ ...item, preorder_prepared: true, allocations: [{ id: 1, batch_id: 9, quantity: 50, status: 'reserved', cost_cny: '1000' }] })) } as SalesOrder;
  const screen = render(<SalesOrderWorkbench {...props} orders={[prepared]} />);
  expect(screen.getByRole('button', { name: '出库' })).toBeTruthy();
  expect(screen.queryByRole('button', { name: '备货' })).toBeNull();
  expect(screen.getByText('预售 · 已预留 · 待出库')).toBeTruthy();
  expect(within(screen.getByRole('list', { name: '订单时间线' })).getByText(/预售商品 × 50 支 · 来源 PO-000005 · 批次 #9 × 50 支/)).toBeTruthy();
  screen.rerender(<SalesOrderWorkbench {...props} orders={[{ ...prepared, fulfillment_status: 'shipped', available_actions: [] }]} />);
  expect(screen.getByText('预售 · 已出库')).toBeTruthy();
  expect(screen.getByText('来源采购单 PO-000005')).toBeTruthy();
});

it('自动预留后直接显示出库动作，时间线记录预留数量', () => {
  const reserved = { ...order, available_actions: ['ship'], preorder_reservations: [{ id: 2, business_date: '2026-10-21', item_ids: [40] }], items: order.items.map(item => ({ ...item, preorder_reserved: true })) };
  const screen = render(<SalesOrderWorkbench {...props} orders={[reserved]} />);
  const listRow = within(screen.getByRole('button', { name: /SO-000019/ }));
  expect(listRow.getByText('预售单')).toBeTruthy();
  expect(listRow.getAllByText('待出库')).toHaveLength(1);
  expect(listRow.queryByText('已确认')).toBeNull();
  expect(listRow.queryByText('预售单 · 待出库')).toBeNull();
  expect(screen.getByText('预售 · 已预留 · 待出库')).toBeTruthy();
  expect(screen.getByRole('button', { name: '出库' })).toBeTruthy();
  expect(screen.queryByRole('button', { name: '备货' })).toBeNull();
  expect(within(screen.getByRole('list', { name: '订单时间线' })).getByText('预售商品 × 50 支 · PO-000005 · 已从可售库存预留')).toBeTruthy();
});
