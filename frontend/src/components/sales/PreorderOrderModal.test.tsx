// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { onlineManager, QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, expect, it, vi } from 'vitest';
import PreorderOrderModal from './PreorderOrderModal';
import { createSalesOrder, fetchPreorderSource } from '../../api';
import type { PreorderSource, SalesOrder } from '../../types';

vi.mock('../../api', async importOriginal => ({
  ...await importOriginal<typeof import('../../api')>(),
  createSalesOrder: vi.fn(), fetchPreorderSource: vi.fn(), searchCustomers: vi.fn().mockResolvedValue([]),
}));
afterEach(() => { cleanup(); onlineManager.setOnline(true); vi.clearAllMocks(); });
const source: PreorderSource = {
  purchase_order_id: 5, order_number: 'PO-000005', status: 'draft', can_create: true,
  items: [{ cigar_id: 1, cigar_name: '测试雪茄', sale_unit: 'box', box_size: 25, purchase_quantity: 250, committed_quantity: 50, remaining_quantity: 200 }],
};
function setup(data = source) {
  vi.mocked(fetchPreorderSource).mockResolvedValue(data);
  const created = vi.fn();
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><PreorderOrderModal purchaseId={5} onClose={vi.fn()} onCreated={created} /></QueryClientProvider>);
  return created;
}
async function fill() {
  fireEvent.click(await screen.findByRole('checkbox'));
  fireEvent.change(screen.getByLabelText('客户名称'), { target: { value: '预售客户' } });
  fireEvent.change(screen.getByLabelText('测试雪茄 25 数量'), { target: { value: '2' } });
  fireEvent.change(screen.getByLabelText('测试雪茄 25 单价'), { target: { value: '1500' } });
}

it('采购商品显示额度，按盒的人民币售价保存为原销售草稿并跳转', async () => {
  const order = { id: 19 } as SalesOrder;
  vi.mocked(createSalesOrder).mockResolvedValue(order);
  const created = setup();
  await fill();
  expect(screen.getByText('采购 10 盒 · 已确认预售 2 盒 · 剩余可预售 8 盒')).toBeTruthy();
  expect(screen.getByText('¥3,000.00')).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: '保存草稿并查看' }));
  await waitFor(() => expect(created).toHaveBeenCalledWith(order));
  expect(createSalesOrder).toHaveBeenCalledWith(expect.objectContaining({ customer_name: '预售客户', items: [{ cigar_id: 1, fulfillment_type: 'preorder', source_purchase_order_id: 5, sale_unit: 'box', quantity: 50, sale_quantity: 2, box_size: 25, unit_price: '1500' }] }));
});

it('保存失败保留填写内容，重复点击不会并发建单', async () => {
  let fail: (error: Error) => void = () => {};
  vi.mocked(createSalesOrder).mockImplementationOnce(() => new Promise((_, reject) => { fail = reject; }));
  const created = setup();
  await fill();
  const submit = screen.getByRole('button', { name: '保存草稿并查看' });
  fireEvent.click(submit); fireEvent.click(submit);
  expect(createSalesOrder).toHaveBeenCalledTimes(1);
  fail(new Error('采购数量已调整，请核对后重试'));
  await screen.findByText('采购数量已调整，请核对后重试');
  expect((screen.getByLabelText('测试雪茄 25 数量') as HTMLInputElement).value).toBe('2');
  expect((screen.getByLabelText('客户名称') as HTMLInputElement).value).toBe('预售客户');
  expect(created).not.toHaveBeenCalled();
});

it('没有剩余额度的商品不能勾选保存', async () => {
  setup({ ...source, items: [{ ...source.items[0], committed_quantity: 250, remaining_quantity: 0 }] });
  expect((await screen.findByRole('checkbox') as HTMLInputElement).disabled).toBe(true);
  expect((screen.getByRole('button', { name: '保存草稿并查看' }) as HTMLButtonElement).disabled).toBe(true);
  expect(createSalesOrder).not.toHaveBeenCalled();
});

it('再次打开弹窗刷新五分钟内的缓存，加载期间不能使用旧额度', async () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 300000 } } });
  client.setQueryData(['preorder-source', 5], source);
  let resolveSource!: (value: PreorderSource) => void;
  vi.mocked(fetchPreorderSource).mockImplementationOnce(() => new Promise(resolve => { resolveSource = resolve; }));
  const modal = <QueryClientProvider client={client}><PreorderOrderModal purchaseId={5} onClose={vi.fn()} onCreated={vi.fn()} /></QueryClientProvider>;
  const first = render(modal);
  expect(screen.getByText('加载商品与预售额度…')).toBeTruthy();
  expect(screen.queryByRole('checkbox')).toBeNull();
  expect(screen.queryByRole('button', { name: '保存草稿并查看' })).toBeNull();
  await act(async () => resolveSource({ ...source, items: [{ ...source.items[0], committed_quantity: 100, remaining_quantity: 150 }] }));
  await screen.findByText('采购 10 盒 · 已确认预售 4 盒 · 剩余可预售 6 盒');
  expect((screen.getByLabelText('测试雪茄 25 数量') as HTMLInputElement).max).toBe('6');
  first.unmount();
  vi.mocked(fetchPreorderSource).mockResolvedValueOnce({ ...source, items: [{ ...source.items[0], committed_quantity: 250, remaining_quantity: 0 }] });
  render(modal);
  expect((await screen.findByRole('checkbox') as HTMLInputElement).disabled).toBe(true);
  expect(fetchPreorderSource).toHaveBeenCalledTimes(2);
});

it('额度刷新失败时不显示缓存表单，重试成功后使用新额度', async () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 300000 } } });
  client.setQueryData(['preorder-source', 5], source);
  vi.mocked(fetchPreorderSource).mockRejectedValueOnce(new Error('网络异常'));
  render(<QueryClientProvider client={client}><PreorderOrderModal purchaseId={5} onClose={vi.fn()} onCreated={vi.fn()} /></QueryClientProvider>);
  await screen.findByText('网络异常');
  expect(screen.queryByRole('checkbox')).toBeNull();
  expect(screen.queryByRole('button', { name: '保存草稿并查看' })).toBeNull();
  vi.mocked(fetchPreorderSource).mockResolvedValueOnce({ ...source, items: [{ ...source.items[0], committed_quantity: 250, remaining_quantity: 0 }] });
  fireEvent.click(screen.getByRole('button', { name: '重新加载' }));
  expect((await screen.findByRole('checkbox') as HTMLInputElement).disabled).toBe(true);
});

it('填写期间网络恢复不会触发刷新或清空客户与数量', async () => {
  setup();
  await fill();
  await act(async () => {
    onlineManager.setOnline(false);
    onlineManager.setOnline(true);
  });
  expect(fetchPreorderSource).toHaveBeenCalledTimes(1);
  expect((screen.getByLabelText('客户名称') as HTMLInputElement).value).toBe('预售客户');
  expect((screen.getByLabelText('测试雪茄 25 数量') as HTMLInputElement).value).toBe('2');
});

it('离线打开弹窗不提供旧额度，恢复连接后才能填写最新额度', async () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 300000 } } });
  client.setQueryData(['preorder-source', 5], source);
  onlineManager.setOnline(false);
  vi.mocked(fetchPreorderSource).mockResolvedValueOnce({ ...source, items: [{ ...source.items[0], committed_quantity: 250, remaining_quantity: 0 }] });
  render(<QueryClientProvider client={client}><PreorderOrderModal purchaseId={5} onClose={vi.fn()} onCreated={vi.fn()} /></QueryClientProvider>);
  expect(screen.getByText('网络已断开，恢复连接后重新获取预售额度…')).toBeTruthy();
  expect(screen.queryByRole('checkbox')).toBeNull();
  expect(screen.queryByRole('button', { name: '保存草稿并查看' })).toBeNull();
  expect(fetchPreorderSource).not.toHaveBeenCalled();
  await act(async () => onlineManager.setOnline(true));
  expect((await screen.findByRole('checkbox') as HTMLInputElement).disabled).toBe(true);
  expect(fetchPreorderSource).toHaveBeenCalledTimes(1);
});
