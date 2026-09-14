// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { SalesOrder } from '../types';
import SalesPage from './SalesPage';

const mocks = vi.hoisted(() => ({ fetchSalesOrders: vi.fn(), fetchAccountingAccounts: vi.fn(), setMeta: vi.fn() }));
vi.mock('../api', () => ({ ...mocks, apiErrorMessage: (error: Error) => error.message, createSalesOrder: vi.fn() }));
vi.mock('../hooks/usePageMeta', () => ({ usePageMeta: () => ({ setMeta: mocks.setMeta }) }));
vi.mock('../components/sales/SalesCustomerModal', () => ({ default: () => null }));
vi.mock('../components/sales/SalesOrderForm', () => ({ default: () => null }));
vi.mock('../components/sales/SalesOrderWorkbench', () => ({ default: ({ selectedId, onSelect, onChanged }: {
  selectedId: number | null; onSelect: (id: number) => void; onChanged: () => void;
}) => <div><span>选中 {selectedId || '无'}</span><button onClick={() => onSelect(1)}>选订单</button><button onClick={onChanged}>动作成功</button><button>动作失败</button></div> }));
afterEach(cleanup);

describe('销售动作后的查询刷新', () => {
  it('刷新所有关联缓存，包括非活动收款单、客户列表；保留筛选和选单', async () => {
    const order: SalesOrder = {
      id: 1, order_number: 'SO-1', status: 'confirmed', display_status: '已确认',
      fulfillment_status: 'confirmed', payment_status: 'unpaid', customer_id: null, customer_name: '客户甲',
      goods_amount_cny: 10, customer_transport_fee_cny: 0, transport_payer: 'company', amount_due_cny: 10,
      total_revenue: 10, total_cost: 0, total_profit: 10, fifo_cost: 0, contribution_profit: 10,
      actual_transport_cost_cny: 0, locked: true, created_at: null, confirmed_at: null, cancelled_at: null,
      note: '', items: [], sales_shipment: null, sales_receipt: null, sales_refund: null, sales_transport_cost: null, available_actions: [],
    };
    mocks.fetchSalesOrders.mockResolvedValue([order]);
    mocks.fetchAccountingAccounts.mockResolvedValue([]);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 300000 } } });
    const keys = ['inventory', 'accounting-dashboard', 'accounting-summary', 'monthly-profit', 'accounting-actions', 'sales-customer', 'sales-customers', 'sales-receipts', 'dividend-rounds'];
    for (const key of keys) client.setQueryData([key], { old: true });
    render(<QueryClientProvider client={client}><MemoryRouter><SalesPage /></MemoryRouter></QueryClientProvider>);
    await screen.findByRole('button', { name: '选订单' });
    fireEvent.change(screen.getByPlaceholderText('搜索订单号或客户'), { target: { value: '客户甲' } });
    fireEvent.change(screen.getByLabelText('订单日期'), { target: { value: '2026-09-01' } });
    fireEvent.change(screen.getByLabelText('结束日期'), { target: { value: '2026-09-14' } });
    fireEvent.change(screen.getByLabelText('付款'), { target: { value: 'unpaid' } });
    await screen.findByRole('button', { name: '选订单' });
    fireEvent.click(screen.getByRole('button', { name: '选订单' }));
    expect(screen.getByText('选中 1')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: '动作失败' }));
    for (const key of keys) expect(client.getQueryState([key])?.isInvalidated).toBe(false);
    const calls = mocks.fetchSalesOrders.mock.calls.length;
    fireEvent.click(screen.getByRole('button', { name: '动作成功' }));
    await waitFor(() => expect(mocks.fetchSalesOrders.mock.calls.length).toBeGreaterThan(calls));
    for (const key of keys) expect(client.getQueryState([key])?.isInvalidated).toBe(true);
    expect(screen.getByDisplayValue('客户甲')).toBeTruthy();
    expect(screen.getByDisplayValue('2026-09-01')).toBeTruthy();
    expect(screen.getByDisplayValue('2026-09-14')).toBeTruthy();
    expect((screen.getByLabelText('付款') as HTMLSelectElement).value).toBe('unpaid');
    expect(screen.getByText('选中 1')).toBeTruthy();
    const freshReceipts = vi.fn().mockResolvedValue({ fresh: true });
    await expect(client.fetchQuery({ queryKey: ['sales-receipts'], queryFn: freshReceipts })).resolves.toEqual({ fresh: true });
    expect(freshReceipts).toHaveBeenCalledTimes(1);
  });
});
