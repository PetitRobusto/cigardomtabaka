// @vitest-environment jsdom
import { cleanup, fireEvent, render, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, expect, it, vi } from 'vitest';
import { fetchAccountingAccounts, fetchSalesOrder, fetchSalesOrderList, updateSalesOrder } from '../api';
import type { SalesOrder, SalesOrderListResponse } from '../types';
import SalesPage from './SalesPage';

vi.mock('../api', async original => ({ ...await original<typeof import('../api')>(),
  fetchAccountingAccounts: vi.fn(), fetchSalesOrder: vi.fn(), fetchSalesOrderList: vi.fn(), updateSalesOrder: vi.fn(),
}));
const meta = vi.hoisted(() => ({ setMeta: vi.fn() }));
vi.mock('../hooks/usePageMeta', () => ({ usePageMeta: () => meta }));
afterEach(() => { cleanup(); vi.resetAllMocks(); });

it.each(['分页', '搜索'])('%s加载、失败、重试期间保留正在编辑的草稿及离开保护', async kind => {
  const order = { id: 19, draft_revision: 42, order_number: 'SO-000019', customer_name: '草稿客户',
    fulfillment_status: 'draft', payment_status: 'unpaid', locked: false, amount_due_cny: 100,
    goods_amount_cny: 100, customer_transport_fee_cny: 0, transport_payer: 'company', available_actions: ['confirm'],
    created_at: '2026-11-03T00:00:00Z', items: [{ id: 40, cigar_id: 1, cigar_name: '测试商品', quantity: 1,
      unit_price: '100', sale_unit: 'stick', sale_quantity: 1, fulfillment_type: 'in_stock', allocations: [] }],
  } as unknown as SalesOrder;
  const response = { results: [order], count: 40, page: 1, pages: 2, limit: 20 } as SalesOrderListResponse;
  vi.mocked(fetchSalesOrderList).mockResolvedValueOnce(response);
  vi.mocked(fetchAccountingAccounts).mockResolvedValue([]);
  vi.mocked(fetchSalesOrder).mockResolvedValue(order);
  let rejectLoad!: (error: Error) => void;
  vi.mocked(fetchSalesOrderList).mockImplementationOnce(() => new Promise((_resolve, reject) => { rejectLoad = reject; }));
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const screen = render(<QueryClientProvider client={client}><MemoryRouter initialEntries={['/sales?order=19']}><SalesPage /></MemoryRouter></QueryClientProvider>);
  fireEvent.click(await screen.findByRole('button', { name: '编辑商品' }));
  fireEvent.change(await screen.findByLabelText('数量（支）'), { target: { value: '3' } });
  if (kind === '分页') fireEvent.click(screen.getByRole('button', { name: '下一页' }));
  else fireEvent.change(screen.getByPlaceholderText('搜索订单号或客户'), { target: { value: '其他订单' } });
  await waitFor(() => expect(fetchSalesOrderList).toHaveBeenCalledTimes(2));
  expect((screen.getByLabelText('数量（支）') as HTMLInputElement).value).toBe('3');
  rejectLoad(new Error('订单列表加载失败'));
  await screen.findByText('订单列表加载失败');
  expect((screen.getByLabelText('数量（支）') as HTMLInputElement).value).toBe('3');
  let resolveRetry!: (result: SalesOrderListResponse) => void;
  vi.mocked(fetchSalesOrderList).mockImplementationOnce(() => new Promise(resolve => { resolveRetry = resolve; }));
  fireEvent.click(screen.getByRole('button', { name: '重试' }));
  await waitFor(() => expect(fetchSalesOrderList).toHaveBeenCalledTimes(3));
  expect((screen.getByLabelText('数量（支）') as HTMLInputElement).value).toBe('3');
  const leave = new Event('beforeunload', { cancelable: true });
  window.dispatchEvent(leave);
  expect(leave.defaultPrevented).toBe(true);
  const empty = { ...response, results: [], count: 0, page: 1, pages: 1 };
  resolveRetry(empty);
  await screen.findByText('共 0 条 · 每页 20 条 · 第 1 / 1 页');
  expect((screen.getByLabelText('数量（支）') as HTMLInputElement).value).toBe('3');
  vi.mocked(updateSalesOrder).mockResolvedValue({ ...order, draft_revision: 43 });
  vi.mocked(fetchSalesOrderList).mockResolvedValue(empty);
  fireEvent.click(screen.getByRole('button', { name: '保存草稿' }));
  await waitFor(() => expect(updateSalesOrder).toHaveBeenCalledWith(19, expect.objectContaining({
    expected_revision: 42, items_only: true, items: [expect.objectContaining({ quantity: 3 })],
  })));
  await waitFor(() => expect(screen.queryByRole('form', { name: '编辑草稿商品' })).toBeNull());
  client.clear();
});
