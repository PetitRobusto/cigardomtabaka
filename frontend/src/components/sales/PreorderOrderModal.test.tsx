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
  items: [{ cigar_id: 1, cigar_name: '测试雪茄', cigar_brand: 'Partagás', cigar_brand_cn: '帕特加斯', cigar_english_name: 'Serie D No. 4', sale_unit: 'box', box_size: 25, purchase_quantity: 250, committed_quantity: 50, remaining_quantity: 200 }],
};
function setup(data = source) {
  vi.mocked(fetchPreorderSource).mockResolvedValue(data);
  const created = vi.fn();
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><PreorderOrderModal purchaseId={5} onClose={vi.fn()} onCreated={created} /></QueryClientProvider>);
  return created;
}
async function options() {
  fireEvent.focus(await screen.findByRole('combobox'));
  return screen.findAllByRole('option');
}
async function fill() {
  fireEvent.click((await options())[0]);
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

it('没有剩余额度的商品不能选择保存', async () => {
  setup({ ...source, items: [{ ...source.items[0], committed_quantity: 250, remaining_quantity: 0 }] });
  expect(((await options())[0] as HTMLButtonElement).disabled).toBe(true);
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
  expect(screen.queryByRole('combobox')).toBeNull();
  expect(screen.queryByRole('button', { name: '保存草稿并查看' })).toBeNull();
  await act(async () => resolveSource({ ...source, items: [{ ...source.items[0], committed_quantity: 100, remaining_quantity: 150 }] }));
  fireEvent.click((await options())[0]);
  await screen.findByText('采购 10 盒 · 已确认预售 4 盒 · 剩余可预售 6 盒');
  expect((screen.getByLabelText('测试雪茄 25 数量') as HTMLInputElement).max).toBe('6');
  first.unmount();
  vi.mocked(fetchPreorderSource).mockResolvedValueOnce({ ...source, items: [{ ...source.items[0], committed_quantity: 250, remaining_quantity: 0 }] });
  render(modal);
  expect(((await options())[0] as HTMLButtonElement).disabled).toBe(true);
  expect(fetchPreorderSource).toHaveBeenCalledTimes(2);
});

it('额度刷新失败时不显示缓存表单，重试成功后使用新额度', async () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 300000 } } });
  client.setQueryData(['preorder-source', 5], source);
  vi.mocked(fetchPreorderSource).mockRejectedValueOnce(new Error('网络异常'));
  render(<QueryClientProvider client={client}><PreorderOrderModal purchaseId={5} onClose={vi.fn()} onCreated={vi.fn()} /></QueryClientProvider>);
  await screen.findByText('网络异常');
  expect(screen.queryByRole('combobox')).toBeNull();
  expect(screen.queryByRole('button', { name: '保存草稿并查看' })).toBeNull();
  vi.mocked(fetchPreorderSource).mockResolvedValueOnce({ ...source, items: [{ ...source.items[0], committed_quantity: 250, remaining_quantity: 0 }] });
  fireEvent.click(screen.getByRole('button', { name: '重新加载' }));
  expect(((await options())[0] as HTMLButtonElement).disabled).toBe(true);
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
  expect(screen.queryByRole('combobox')).toBeNull();
  expect(screen.queryByRole('button', { name: '保存草稿并查看' })).toBeNull();
  expect(fetchPreorderSource).not.toHaveBeenCalled();
  await act(async () => onlineManager.setOnline(true));
  expect(((await options())[0] as HTMLButtonElement).disabled).toBe(true);
  expect(fetchPreorderSource).toHaveBeenCalledTimes(1);
});

it('长采购单只展开已选商品，按中英文品牌、英文品名搜索并保留已填内容', async () => {
  setup({ ...source, items: [source.items[0], ...Array.from({ length: 30 }, (_, i) => ({
    ...source.items[0], cigar_id: i + 2, cigar_name: `其他雪茄${i}`, cigar_brand: 'Other', cigar_brand_cn: '其他品牌', cigar_english_name: `Other ${i}`,
  }))] });
  const search = await screen.findByRole('combobox');
  expect(screen.queryByLabelText('测试雪茄 25 数量')).toBeNull();
  for (const keyword of ['帕特加斯', 'partagas', 'SERIE d', '测试雪茄', 'partagas 25']) {
    fireEvent.change(search, { target: { value: keyword } });
    expect(screen.getAllByRole('option')).toHaveLength(1);
    expect(screen.getByRole('option').textContent).toContain('帕特加斯 测试雪茄');
  }
  fireEvent.click(screen.getByRole('option'));
  expect(screen.getByText('帕特加斯 测试雪茄 · 25 支/盒')).toBeTruthy();
  fireEvent.change(screen.getByLabelText('测试雪茄 25 数量'), { target: { value: '3' } });
  fireEvent.change(screen.getByLabelText('测试雪茄 25 单价'), { target: { value: '1500' } });
  fireEvent.change(search, { target: { value: '不在采购单里的商品' } });
  expect(screen.queryByRole('option')).toBeNull();
  expect(screen.getByRole('status').textContent).toContain('没有可添加的匹配商品');
  expect((screen.getByLabelText('测试雪茄 25 数量') as HTMLInputElement).value).toBe('3');
  expect((screen.getByLabelText('测试雪茄 25 单价') as HTMLInputElement).value).toBe('1500');
  fireEvent.change(search, { target: { value: '帕特加斯' } });
  expect(screen.queryByRole('option')).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: '移除 帕特加斯 测试雪茄 25' }));
  expect(screen.getAllByRole('option')).toHaveLength(1);
  fireEvent.click(screen.getByRole('option'));
  expect((screen.getByLabelText('测试雪茄 25 数量') as HTMLInputElement).value).toBe('3');
});

it('相同商品不同盒规分别选择，键盘跳过无额度商品且提交正确的包装', async () => {
  vi.mocked(createSalesOrder).mockResolvedValue({ id: 20 } as SalesOrder);
  const created = setup({ ...source, items: [
    { ...source.items[0], remaining_quantity: 0 },
    { ...source.items[0], box_size: 10, purchase_quantity: 50, committed_quantity: 0, remaining_quantity: 50 },
  ] });
  const search = await screen.findByRole('combobox');
  fireEvent.focus(search);
  expect(screen.getAllByRole('option')).toHaveLength(2);
  fireEvent.keyDown(search, { key: 'ArrowDown' });
  expect(screen.getByRole('option', { selected: true }).textContent).toContain('10 支/盒');
  fireEvent.keyDown(search, { key: 'Enter' });
  expect(createSalesOrder).not.toHaveBeenCalled();
  expect(screen.queryByLabelText('测试雪茄 25 数量')).toBeNull();
  fireEvent.change(screen.getByLabelText('客户名称'), { target: { value: '客户甲' } });
  fireEvent.change(screen.getByLabelText('测试雪茄 10 数量'), { target: { value: '2' } });
  fireEvent.change(screen.getByLabelText('测试雪茄 10 单价'), { target: { value: '500' } });
  fireEvent.click(screen.getByRole('button', { name: '保存草稿并查看' }));
  await waitFor(() => expect(created).toHaveBeenCalled());
  expect(createSalesOrder).toHaveBeenCalledWith(expect.objectContaining({ items: [expect.objectContaining({ cigar_id: 1, box_size: 10, quantity: 20, sale_quantity: 2 })] }));
});
