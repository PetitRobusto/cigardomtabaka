// @vitest-environment jsdom
import { cleanup, fireEvent, render, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Link, MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, expect, it, vi } from 'vitest';
import { fetchPrivnote, submitPaymentEvidence } from '../api';
import PrivnoteViewPage from './PrivnoteViewPage';

const { setMeta } = vi.hoisted(() => ({ setMeta: vi.fn() }));
vi.mock('../hooks/usePageMeta', () => ({ usePageMeta: () => ({ setMeta }) }));
vi.mock('../api', () => ({ fetchPrivnote: vi.fn(), verifyPrivnotePassword: vi.fn(), submitPaymentEvidence: vi.fn() }));
afterEach(cleanup);

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
