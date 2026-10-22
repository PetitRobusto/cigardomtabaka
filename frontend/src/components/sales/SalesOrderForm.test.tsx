// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { searchCigars } from '../../api';
import type { SearchCigarResult } from '../../types';
import SalesOrderForm from './SalesOrderForm';

vi.mock('../../api', async importOriginal => ({
  ...await importOriginal<typeof import('../../api')>(),
  searchCigars: vi.fn(),
}));

const cigar: SearchCigarResult = {
  id: 281, name: '乌普曼 2 号', english_name: 'Upmann No.2', brand: 'H. Upmann',
  brand_cn: '乌普曼', release_type: '', release_type_cn: '', is_regular: true,
  vitola: '', length: null, ring_gauge: null, thumb_url: null, packaging_sizes: [25],
  stock_qty: 75, box_options: [{ box_size: 25, available_boxes: 3 }],
  available_sticks: 0, batches: [],
};

beforeEach(() => {
  vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({ matches: false }));
});
afterEach(() => { cleanup(); vi.clearAllMocks(); vi.unstubAllGlobals(); });

async function selectCigar(result = cigar) {
  vi.mocked(searchCigars).mockResolvedValue([result]);
  fireEvent.focus(screen.getByPlaceholderText('输入品牌、中文名或英文名'));
  fireEvent.click(await screen.findByRole('button', { name: /Upmann No.2/ }));
}

it('整盒库存被选中后仍显示总可售和整盒数量，散支为零不代表缺货', async () => {
  const submit = vi.fn().mockResolvedValue(undefined);
  const { container } = render(<SalesOrderForm onSubmit={submit} />);
  await selectCigar();
  expect(screen.getByText('可售共 75 支')).toBeTruthy();
  expect(screen.getByText('整盒 25支×3盒 · 散支 0 支')).toBeTruthy();
  fireEvent.change(container.querySelector('[data-guide="sales-order-item-price"]')!, { target: { value: '6700' } });
  fireEvent.click(screen.getByRole('button', { name: '保存草稿' }));
  await waitFor(() => expect(submit).toHaveBeenCalledWith(expect.objectContaining({
    items: [{ cigar_id: 281, sale_unit: 'box', quantity: 25, sale_quantity: 1, box_size: 25, unit_price: '6700' }],
  })));
});

it('多盒规和散支分别保留库存，切换盒规不混用盒数', async () => {
  render(<SalesOrderForm onSubmit={vi.fn()} />);
  await selectCigar({ ...cigar, stock_qty: 88, available_sticks: 8,
    box_options: [{ box_size: 10, available_boxes: 3 }, { box_size: 25, available_boxes: 2 }] });
  expect(screen.getByText('可售共 88 支')).toBeTruthy();
  expect(screen.getByText('整盒 10支×3盒、25支×2盒 · 散支 8 支')).toBeTruthy();
  fireEvent.change(screen.getByLabelText('选择包装支数'), { target: { value: '25' } });
  expect((screen.getByLabelText('选择包装支数') as HTMLSelectElement).value).toBe('25');
  expect(screen.getByText('整盒 10支×3盒、25支×2盒 · 散支 8 支')).toBeTruthy();
});

it('只有散支时显示真实散支库存，不虚构整盒', async () => {
  render(<SalesOrderForm onSubmit={vi.fn()} />);
  await selectCigar({ ...cigar, stock_qty: 8, available_sticks: 8, box_options: [] });
  expect(screen.getByText('可售共 8 支')).toBeTruthy();
  expect(screen.getByText('散支 8 支')).toBeTruthy();
  expect(screen.queryByLabelText('选择包装支数')).toBeNull();
  expect((screen.getByLabelText('销售单位') as HTMLSelectElement).value).toBe('stick');
});
