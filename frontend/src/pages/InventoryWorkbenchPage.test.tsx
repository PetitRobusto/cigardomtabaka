// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, expect, it, vi } from 'vitest';
import InventoryWorkbenchPage from './InventoryWorkbenchPage';

const mocks = vi.hoisted(() => ({ fetchInventory: vi.fn(), setMeta: vi.fn() }));
vi.mock('../api', () => ({ ...mocks, fetchInventoryAudit: vi.fn(), reverseInventoryAdjustment: vi.fn() }));
vi.mock('../hooks/usePageMeta', () => ({ usePageMeta: () => ({ setMeta: mocks.setMeta }) }));
afterEach(cleanup);

it('全数预购仍显示在库、零可售、待出库和完整账面成本', async () => {
  mocks.fetchInventory.mockResolvedValue({ cigars: [{ id: 1, name: '已预购商品', english_name: 'Reserved', brand: 'Test', brand_name: '测试', total_stock: 0, on_hand_quantity: 250, reserved_quantity: 250, preorder_waiting_quantity: 175, preorder_prepared_quantity: 75, total_cost: 10000, avg_cost: 40, latest_date: '2026-10-21' }], brands: ['Test'], brand_options: [], stats: { brand_count: 1, cigar_count: 1, total_qty: 0, total_cost: 10000 } });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><MemoryRouter><InventoryWorkbenchPage /></MemoryRouter></QueryClientProvider>);
  expect(await screen.findByText('可售 0 支')).toBeTruthy();
  expect(screen.getAllByText('在库 250 支 · 已预留 250 支').length).toBeGreaterThan(0);
  expect(screen.getAllByText('已预购 250 支 · 待出库').length).toBeGreaterThan(0);
  expect(screen.getAllByText('¥ 10,000').length).toBeGreaterThan(0);
});
