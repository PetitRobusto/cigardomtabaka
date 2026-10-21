// @vitest-environment jsdom
import { useState } from 'react';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, expect, it, vi } from 'vitest';
import InventoryPurchasesPage from './InventoryPurchasesPage';
import { salesPreorderLabel } from '../components/sales/preorderState';
import SalesOrderStatusTags from '../components/sales/SalesOrderStatusTags';
import type { PurchaseAction, SalesOrder } from '../types';

const mocks = vi.hoisted(() => ({ fetchInventoryPurchases: vi.fn(), fetchInventoryPurchase: vi.fn(), fetchAccountingAccounts: vi.fn(), receivePurchaseOrder: vi.fn(), sales: vi.fn(), setMeta: vi.fn() }));
vi.mock('../api', async original => ({ ...await original<typeof import('../api')>(), ...mocks }));
vi.mock('../hooks/usePageMeta', () => ({ usePageMeta: () => ({ setMeta: mocks.setMeta }) }));
afterEach(() => { cleanup(); vi.clearAllMocks(); });
const salesKey = ['sales-orders', '', '2026-10-01', '2026-10-21', '', ''];
const orders = (reserved: boolean) => [25, 28].map(id => ({ id, order_number: `SO-${id}`, fulfillment_status: 'confirmed', items: [{ fulfillment_type: 'preorder', source_purchase_order_id: 9, preorder_reserved: reserved }] }) as SalesOrder);
function Orders() {
  const result = useQuery({ queryKey: salesKey, queryFn: mocks.sales });
  return <>{result.data?.map((order: SalesOrder) => <section aria-label={order.order_number} key={order.id}>{salesPreorderLabel(order)}<SalesOrderStatusTags order={order} /></section>)}</>;
}
function Flow() {
  const [showOrders, setShowOrders] = useState(false);
  return <><button onClick={() => setShowOrders(true)}>查看关联预售</button>{showOrders ? <Orders /> : <InventoryPurchasesPage />}</>;
}

it('采购到货后返回已缓存的销售页，两张关联预售立即更新为待出库', async () => {
  const purchase = { id: 9, order_number: 'PO-000009', status: 'in_transit', version: 1, business_date: '2026-10-21', rub_total: '1000', items: [] } as unknown as PurchaseAction;
  mocks.fetchInventoryPurchases.mockResolvedValue({ results: [purchase] });
  mocks.fetchInventoryPurchase.mockResolvedValue(purchase);
  mocks.fetchAccountingAccounts.mockResolvedValue([]);
  mocks.receivePurchaseOrder.mockResolvedValue([18]);
  mocks.sales.mockResolvedValue(orders(true));
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 300000, refetchOnWindowFocus: false } } });
  client.setQueryData(salesKey, orders(false));
  render(<QueryClientProvider client={client}><MemoryRouter><Flow /></MemoryRouter></QueryClientProvider>);
  fireEvent.click(await screen.findByRole('button', { name: /PO-000009/ }));
  fireEvent.click(await screen.findByRole('button', { name: '确认整单到货' }));
  fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: '确认整单到货' }));
  await screen.findByText(/整单到货完成/);
  fireEvent.click(screen.getByRole('button', { name: '查看关联预售' }));
  for (const id of [25, 28]) {
    const row = within(screen.getByRole('region', { name: `SO-${id}` }));
    expect(await row.findByText('待出库')).toBeTruthy();
    expect(row.getByText('预售单')).toBeTruthy();
  }
  expect(mocks.sales).toHaveBeenCalledTimes(1);
});
