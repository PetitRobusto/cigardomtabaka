// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import DividendSummaryCard from './DividendSummaryCard';

const api = vi.hoisted(() => ({ fetchDividendRounds: vi.fn(), parseAccountingApiError: (error: Error) => error }));
vi.mock('../../api', () => api);
afterEach(cleanup);
beforeEach(() => vi.resetAllMocks());
const summary = { allocated_cny: '20000.00', paid_cny: '5000.00', pending_cny: '15000.00', partners: [
  { id: 1, name: '张三', allocated_cny: '10000.00', paid_cny: '5000.00', pending_cny: '5000.00' },
  { id: 2, name: '李四', allocated_cny: '10000.00', paid_cny: '0.00', pending_cny: '10000.00' },
] };
function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><DividendSummaryCard /></QueryClientProvider>);
  return client;
}
it('展示全部记录的两人汇总，记账刷新后更新待领合计', async () => {
  api.fetchDividendRounds.mockResolvedValue({ summary });
  const client = mount();
  expect(screen.getByRole('status').textContent).toContain('加载中');
  await screen.findByText('¥15,000.00');
  expect(api.fetchDividendRounds).toHaveBeenCalledWith();
  const partner = screen.getByRole('heading', { name: '李四' }).parentElement!;
  expect(within(partner).getByText('¥0.00')).toBeTruthy();
  expect(within(partner).getAllByText('¥10,000.00')).toHaveLength(2);
  api.fetchDividendRounds.mockResolvedValue({ summary: { ...summary, paid_cny: '10000.00', pending_cny: '10000.00' } });
  await client.invalidateQueries({ queryKey: ['dividend-rounds'] });
  await waitFor(() => expect(screen.queryByText('¥15,000.00')).toBeNull());
  expect(screen.getByText('待领合计').nextElementSibling?.textContent).toBe('¥10,000.00');
});
it('请求失败和缺少汇总字段不显示虚假的零，可重试', async () => {
  api.fetchDividendRounds.mockRejectedValueOnce(new Error('总览加载失败')).mockResolvedValueOnce({});
  mount();
  await screen.findByRole('alert');
  expect(screen.queryByText('¥0.00')).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: '重新加载' }));
  await screen.findByText('分红总览暂不可用，请重新加载。');
  expect(screen.queryByText('¥0.00')).toBeNull();
});
it('没有确认轮次时显示空态，不猜合伙人身份', async () => {
  api.fetchDividendRounds.mockResolvedValue({ summary: { partners: [], allocated_cny: '0.00', paid_cny: '0.00', pending_cny: '0.00' } });
  mount();
  await screen.findByText('暂无已确认分红轮次');
  expect(screen.getByText('¥0.00')).toBeTruthy();
  expect(screen.queryByText('张三')).toBeNull();
});
