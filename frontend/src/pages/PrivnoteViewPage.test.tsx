// @vitest-environment jsdom
import { cleanup, fireEvent, render, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Link, MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, expect, it, vi } from 'vitest';
import { fetchPrivnote, submitPaymentEvidence } from '../api';
import PrivnoteViewPage from './PrivnoteViewPage';

const { setMeta } = vi.hoisted(() => ({ setMeta: vi.fn() }));
vi.mock('../hooks/usePageMeta', () => ({ usePageMeta: () => ({ setMeta }) }));
vi.mock('../api', () => ({ fetchPrivnote: vi.fn(), verifyPrivnotePassword: vi.fn(), submitPaymentEvidence: vi.fn() }));
afterEach(cleanup);

it('现货清单的空价显示未报价，并保留同页库存、已有价格和零值', async () => {
  const product = { name: '商品 A', english_name: 'A', vitola: 'Robusto', box_size: 25, full_boxes: 3, loose: 2, total_sticks: 77, thumb_url: '' };
  vi.mocked(fetchPrivnote).mockResolvedValue({
    title: '现货清单',
    data: {
      mode: 'inventory', empty: false, total_items: 2, total_boxes: 6, total_loose: 4,
      brand_groups: [{ brand: 'Brand', name: '品牌', logo_url: null, items: [
        { ...product, box_price: null, stick_price: null },
        { ...product, name: '商品 B', english_name: 'B', box_price: 1500, stick_price: 0 },
      ] }],
    },
  });
  const view = render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter initialEntries={['/p/inventory']}>
        <Routes><Route path="/p/:token" element={<PrivnoteViewPage />} /></Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  const unpriced = within(await view.findByRole('row', { name: /商品 A/ }));
  expect(unpriced.getAllByText('未报价')).toHaveLength(2);
  expect(unpriced.getByRole('cell', { name: '3' })).toBeTruthy();
  const priced = within(view.getByRole('row', { name: /商品 B/ }));
  expect(priced.getByText(`¥${(1500).toLocaleString()}`)).toBeTruthy();
  expect(priced.getByText('¥0')).toBeTruthy();
});

it('切换收款链接清空上一订单的截图，不能把旧凭证提交到新订单', async () => {
  vi.mocked(fetchPrivnote).mockImplementation(async token => ({
    title: token,
    data: {
      mode: 'payment', items: [], total: 100, extra_fees: [], extra_total: 0,
      grand_total: 100, customer_name: token, payment_methods: [], remark: '',
      payment_flow: { status: 'active', review_note: '', submitted_at: null },
    },
  }));
  const screen = render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={['/p/order-a']}>
        <Link to="/p/order-b">切换订单 B</Link>
        <Routes><Route path="/p/:token" element={<PrivnoteViewPage />} /></Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  await waitFor(() => expect(screen.getByText('order-a')).toBeTruthy());
  const file = new File(['image'], '订单A截图.png', { type: 'image/png' });
  fireEvent.change(screen.getByLabelText('付款凭证图片'), { target: { files: [file] } });
  expect(screen.getByRole('button', { name: '移除 订单A截图.png' })).toBeTruthy();
  fireEvent.click(screen.getByRole('link', { name: '切换订单 B' }));
  await waitFor(() => expect(screen.getByText('order-b')).toBeTruthy());
  expect(screen.queryByRole('button', { name: '移除 订单A截图.png' })).toBeNull();
  expect(screen.getByRole('button', { name: '提交凭证，等待核实' }).hasAttribute('disabled')).toBe(true);
  expect(submitPaymentEvidence).not.toHaveBeenCalled();
});
