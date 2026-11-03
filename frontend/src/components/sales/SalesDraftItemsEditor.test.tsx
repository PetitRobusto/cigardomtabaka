// @vitest-environment jsdom
import { cleanup, fireEvent, render, waitFor, within } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { fetchInventoryPurchases, fetchPreorderSource, fetchSalesOrder, updateSalesOrder } from '../../api';
import type { SalesOrder, SearchCigarResult } from '../../types';
import SalesDraftItemsEditor from './SalesDraftItemsEditor';
import SalesOrderWorkbench from './SalesOrderWorkbench';

vi.mock('../../api', async original => ({ ...await original<typeof import('../../api')>(),
  fetchSalesOrder: vi.fn(), updateSalesOrder: vi.fn(), fetchInventoryPurchases: vi.fn(), fetchPreorderSource: vi.fn(),
}));
afterEach(() => { cleanup(); vi.resetAllMocks(); vi.unstubAllGlobals(); });
const order = {
  id: 19, draft_revision: 42, order_number: 'SO-000019', customer_name: '草稿客户', customer_id: null,
  fulfillment_status: 'draft', payment_status: 'unpaid', locked: false, amount_due_cny: 310,
  goods_amount_cny: 300, customer_transport_fee_cny: 10, transport_payer: 'customer',
  available_actions: ['confirm', 'cancel'], created_at: '2026-11-03T00:00:00Z', note: '保留备注',
  items: [{ id: 40, cigar_id: 1, cigar_name: '预售商品', quantity: 50, unit_price: '100',
    sale_unit: 'box', sale_quantity: 2, box_size: 25, fulfillment_type: 'preorder',
    source_purchase_order_id: 5, source_purchase_order_number: 'PO-000005', allocations: [] },
  { id: 41, cigar_id: 2, cigar_name: '现货商品', cigar_brand: 'Partagás', cigar_brand_cn: '帕特加斯', quantity: 1, unit_price: '100',
    sale_unit: 'stick', sale_quantity: 1, box_size: null, fulfillment_type: 'in_stock', allocations: [] }],
} as unknown as SalesOrder;
const callbacks = () => ({ onSaved: vi.fn(), onCancel: vi.fn(), onStateChange: vi.fn() });

it('saves exact box units and sources, retains inputs on failure and prevents duplicate submissions', async () => {
  const props = callbacks();
  vi.mocked(updateSalesOrder).mockRejectedValueOnce(new Error('订单已被其他人修改'));
  const screen = render(<SalesDraftItemsEditor order={order} {...props} />);
  fireEvent.change(screen.getByLabelText('数量（盒）'), { target: { value: '3' } });
  fireEvent.change(screen.getByLabelText('单价（元/盒）'), { target: { value: '100.01' } });
  expect(screen.getByText('¥410.03')).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: '保存草稿' }));
  await waitFor(() => expect(screen.getByRole('alert')).toBe(document.activeElement));
  expect((screen.getByLabelText('数量（盒）') as HTMLInputElement).value).toBe('3');
  expect(props.onSaved).not.toHaveBeenCalled();
  let resolve!: (value: SalesOrder) => void;
  vi.mocked(updateSalesOrder).mockImplementationOnce(() => new Promise(done => { resolve = done; }));
  fireEvent.submit(screen.getByRole('form'));
  fireEvent.submit(screen.getByRole('form'));
  expect(updateSalesOrder).toHaveBeenCalledTimes(2);
  expect((screen.getByRole('button', { name: '放弃修改' }) as HTMLButtonElement).disabled).toBe(true);
  const saved = { ...order, draft_revision: 43 };
  resolve(saved);
  await waitFor(() => expect(props.onSaved).toHaveBeenCalledWith(saved));
  expect(updateSalesOrder).toHaveBeenLastCalledWith(19, {
    items_only: true, expected_revision: 42, items: [
      { cigar_id: 1, sale_unit: 'box', quantity: 75, sale_quantity: 3, box_size: 25, unit_price: '100.01', fulfillment_type: 'preorder', source_purchase_order_id: 5 },
      { cigar_id: 2, sale_unit: 'stick', quantity: 1, sale_quantity: undefined, box_size: undefined, unit_price: '100.00', fulfillment_type: 'in_stock', source_purchase_order_id: undefined },
    ],
  });
});

it('keeps existing packaging fixed and prevents saving an empty draft', () => {
  const screen = render(<SalesDraftItemsEditor order={order} {...callbacks()} />);
  expect(screen.queryByLabelText('销售单位')).toBeNull();
  expect(screen.queryByLabelText('盒规（支/盒）')).toBeNull();
  expect(screen.getByText('25 支/盒')).toBeTruthy();
  while (screen.queryAllByRole('button', { name: '移除' }).length) fireEvent.click(screen.getAllByRole('button', { name: '移除' })[0]);
  expect(screen.queryByRole('region', { name: '商品 1' })).toBeNull();
  expect((screen.getByRole('button', { name: '保存草稿' }) as HTMLButtonElement).disabled).toBe(true);
});

it('adds a preorder from its purchase source, and replacing it resets quantity and price', async () => {
  vi.mocked(fetchInventoryPurchases).mockResolvedValue({ results: [{ id: 7, order_number: 'PO-000007', status: 'in_transit', supplier_name: '供应商' }] } as Awaited<ReturnType<typeof fetchInventoryPurchases>>);
  vi.mocked(fetchPreorderSource).mockRejectedValueOnce(new Error('来源加载失败')).mockResolvedValue({
    purchase_order_id: 7, order_number: 'PO-000007', status: 'in_transit', can_create: true,
    items: [{ cigar_id: 3, cigar_name: '新预售', cigar_brand: 'Cohiba', cigar_brand_cn: '高希霸', sale_unit: 'box', box_size: 10, purchase_quantity: 100, remaining_quantity: 80 },
      { cigar_id: 4, cigar_name: '额度已用完', sale_unit: 'box', box_size: 25, purchase_quantity: 50, remaining_quantity: 0 }],
  } as Awaited<ReturnType<typeof fetchPreorderSource>>);
  const screen = render(<SalesDraftItemsEditor order={order} {...callbacks()} />);
  fireEvent.click(screen.getByRole('button', { name: '＋ 添加商品' }));
  fireEvent.click(screen.getByRole('button', { name: '采购来源预售' }));
  fireEvent.click(await screen.findByRole('button', { name: /PO-000007/ }));
  await screen.findByText('来源加载失败');
  fireEvent.click(screen.getByRole('button', { name: '重试' }));
  expect((await screen.findByRole('button', { name: /额度已用完/ }) as HTMLButtonElement).disabled).toBe(true);
  fireEvent.click(await screen.findByRole('button', { name: /高希霸 新预售 · 10 支\/盒/ }));
  const row = within(screen.getByRole('region', { name: '商品 3' }));
  expect(row.getByText('高希霸 新预售')).toBeTruthy();
  expect(row.getByText('预售 · PO-000007')).toBeTruthy();
  fireEvent.change(row.getByLabelText('数量（盒）'), { target: { value: '3' } });
  fireEvent.change(row.getByLabelText('单价（元/盒）'), { target: { value: '999' } });
  fireEvent.click(row.getByRole('button', { name: '替换商品' }));
  fireEvent.click(await screen.findByRole('button', { name: /高希霸 新预售 · 10 支\/盒/ }));
  expect((row.getByLabelText('数量（盒）') as HTMLInputElement).value).toBe('1');
  expect((row.getByLabelText('单价（元/盒）') as HTMLInputElement).value).toBe('');
});

it('loads the latest draft, protects dirty selection and survives filter refreshes', async () => {
  const other = { ...order, id: 20, order_number: 'SO-000020' };
  const props = { orders: [order, other], selectedId: 19, accounts: [], onSelect: vi.fn(), onChanged: vi.fn(), onCustomer: vi.fn() };
  vi.mocked(fetchSalesOrder).mockResolvedValue({ ...order, draft_revision: 45 });
  const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
  const screen = render(<SalesOrderWorkbench {...props} />);
  fireEvent.click(screen.getByRole('button', { name: '编辑商品' }));
  fireEvent.change(await screen.findByLabelText('数量（盒）'), { target: { value: '4' } });
  expect(screen.queryByRole('button', { name: '确认订单' })).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: /SO-000020/ }));
  expect(confirm).toHaveBeenCalledTimes(1);
  expect(props.onSelect).not.toHaveBeenCalled();
  screen.rerender(<SalesOrderWorkbench {...props} orders={[]} selectedId={null} />);
  expect((screen.getByLabelText('数量（盒）') as HTMLInputElement).value).toBe('4');
  screen.rerender(<SalesOrderWorkbench {...props} />);
  vi.mocked(updateSalesOrder).mockResolvedValue({ ...order, draft_revision: 46, amount_due_cny: 510, goods_amount_cny: 500 });
  fireEvent.click(screen.getByRole('button', { name: '保存草稿' }));
  await waitFor(() => expect(props.onChanged).toHaveBeenCalledOnce());
  expect(screen.queryByRole('form', { name: '编辑草稿商品' })).toBeNull();
  expect(screen.getAllByText('¥510.00').length).toBeGreaterThan(0);
  expect(vi.mocked(updateSalesOrder).mock.calls[0][1].expected_revision).toBe(45);
  confirm.mockRestore();
});


it.each(['添加', '替换'])('%s现货通过共用 autocomplete 只搜索库存商品，选择前后均显示品牌', async action => {
  vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: false })));
  const stocked = { id: 8, name: 'D 4', english_name: 'Serie D No. 4', brand: 'Partagás', brand_cn: '帕特加斯',
    stock_qty: 50, packaging_sizes: [25], box_options: [{ box_size: 25, available_boxes: 2 }],
    available_sticks: 0, batches: [], is_regular: true, release_type: '', release_type_cn: '',
    vitola: '', length: 124, ring_gauge: 50, thumb_url: null } satisfies SearchCigarResult;
  const empty = { ...stocked, id: 9, name: '无库存型号', stock_qty: 0, box_options: [] };
  const requests: URL[] = [];
  vi.stubGlobal('fetch', vi.fn(async (input: string) => {
    const url = new URL(input, 'http://127.0.0.1');
    requests.push(url);
    const results = url.searchParams.get('stock_only') === '1' ? [stocked] : [stocked, empty];
    return new Response(JSON.stringify({ results }), { status: 200 });
  }));
  const screen = render(<SalesDraftItemsEditor order={order} {...callbacks()} />);
  expect(screen.getByText('帕特加斯 现货商品')).toBeTruthy();
  if (action === '添加') fireEvent.click(screen.getByRole('button', { name: '＋ 添加商品' }));
  else fireEvent.click(within(screen.getByRole('region', { name: '商品 2' })).getByRole('button', { name: '替换商品' }));
  const search = screen.getByPlaceholderText('输入品牌、中文名或英文名');
  fireEvent.focus(search);
  await screen.findByRole('button', { name: /帕特加斯 D 4/ });
  expect(screen.queryByText('帕特加斯 无库存型号')).toBeNull();
  fireEvent.change(search, { target: { value: 'D 4' } });
  const result = await screen.findByRole('button', { name: /帕特加斯 D 4/ });
  expect(result.textContent).toContain('Partagás Serie D No. 4');
  expect(screen.queryByText('帕特加斯 无库存型号')).toBeNull();
  expect(requests.map(url => url.searchParams.get('q'))).toEqual(['', 'D 4']);
  expect(requests.every(url => url.pathname === '/privnote/api/search-cigars/' && url.searchParams.get('stock_only') === '1')).toBe(true);
  fireEvent.click(result);
  const row = within(screen.getByRole('region', { name: action === '添加' ? '商品 3' : '商品 2' }));
  expect(row.getByText('帕特加斯 D 4')).toBeTruthy();
  expect(row.getByText('25 支/盒')).toBeTruthy();
  expect(row.queryByRole('combobox')).toBeNull();
  expect(row.queryByLabelText('盒规（支/盒）')).toBeNull();
  expect((row.getByLabelText('单价（元/盒）') as HTMLInputElement).value).toBe('');
});


it('offers only actual inventory packaging and resets price when changing an available specification', async () => {
  vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: false })));
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ results: [{ id: 8, name: 'D 4', brand: 'Partagás', brand_cn: '帕特加斯',
    packaging_sizes: [10, 25, 50], stock_qty: 77, box_options: [{ box_size: 25, available_boxes: 1 }, { box_size: 50, available_boxes: 1 }], available_sticks: 2 }] }), { status: 200 })));
  const screen = render(<SalesDraftItemsEditor order={order} {...callbacks()} />);
  fireEvent.click(screen.getByRole('button', { name: '＋ 添加商品' }));
  fireEvent.focus(screen.getByPlaceholderText('输入品牌、中文名或英文名'));
  fireEvent.click(await screen.findByRole('button', { name: /帕特加斯 D 4/ }));
  const row = within(screen.getByRole('region', { name: '商品 3' }));
  expect(row.getAllByRole('option').map(option => option.textContent)).toEqual(['25 支/盒', '50 支/盒', '散支']);
  fireEvent.change(row.getByLabelText('数量（盒）'), { target: { value: '2' } });
  fireEvent.change(row.getByLabelText('单价（元/盒）'), { target: { value: '100' } });
  fireEvent.change(row.getByLabelText('选择库存规格'), { target: { value: 'box:50' } });
  expect((row.getByLabelText('数量（盒）') as HTMLInputElement).value).toBe('1');
  expect((row.getByLabelText('单价（元/盒）') as HTMLInputElement).value).toBe('');
  fireEvent.change(row.getByLabelText('单价（元/盒）'), { target: { value: '200' } });
  vi.mocked(updateSalesOrder).mockResolvedValue(order);
  fireEvent.click(screen.getByRole('button', { name: '保存草稿' }));
  await waitFor(() => expect(updateSalesOrder).toHaveBeenCalled());
  expect(vi.mocked(updateSalesOrder).mock.calls[0][1].items[2]).toMatchObject({ sale_unit: 'box', box_size: 50, quantity: 50, sale_quantity: 1, unit_price: '200.00' });
});
