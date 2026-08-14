import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import * as api from '../../api';
import Day1InventoryStep, { boxSizesFromCigarDetail, createBoxSizesLoader, fetchDeclaredBoxSizes } from './Day1InventoryStep';

describe('Day1 inventory packaging contract', () => {
  it('renders a constrained selector from the real cigar detail response shape', () => {
    const detail = {
      cigar: { box_sizes: [10, 25] },
    };
    expect(boxSizesFromCigarDetail(detail)).toEqual([10, 25]);
    const html = renderToStaticMarkup(
      <Day1InventoryStep
        inventory={[{ cigar_id: 4, cigar_name: '测试雪茄', box_size: 25, box_quantity: 1, loose_sticks: 0, unit_cost_cny: '10.00' }]}
        declaredBoxSizesByCigar={{ 4: [10, 25] }}
        fieldErrors={{ 'inventory[0].box_size': '包装规格不在目录中' }}
        onChange={() => {}}
      />,
    );
    expect(html).toContain('<select');
    expect(html).toContain('10');
    expect(html).toContain('25');
    expect(html).toContain('包装规格不在目录中');
    expect(html).not.toContain('目录未声明包装规格');
  });

  it('allows manual entry only when the catalog declares no numeric sizes', () => {
    const html = renderToStaticMarkup(
      <Day1InventoryStep
        inventory={[{ cigar_id: 9, cigar_name: '无包装雪茄', box_size: 0, box_quantity: 0, loose_sticks: 3, unit_cost_cny: '10.00' }]}
        declaredBoxSizesByCigar={{ 9: [] }}
        onChange={() => {}}
      />,
    );
    expect(html).not.toContain('<select');
    expect(html).toContain('目录未声明包装规格，请按实物填写');
    expect(html).toContain('type="number"');
  });

  it('loads existing draft rows from the real detail API response', async () => {
    const fetchDetail = vi.spyOn(api, 'fetchCigarDetail').mockResolvedValue({
      cigar: { box_sizes: [10, 25] },
    } as never);
    await expect(fetchDeclaredBoxSizes(4)).resolves.toEqual([10, 25]);
    expect(fetchDetail).toHaveBeenCalledWith(4);
    fetchDetail.mockRestore();
  });

  it('shares in-flight detail requests and permits retry after failure', async () => {
    let calls = 0;
    let rejectFirst: (reason: Error) => void = () => {};
    const fetchSizes = vi.fn(() => {
      calls += 1;
      if (calls === 1) return new Promise<number[]>((_, reject) => { rejectFirst = reject; });
      return Promise.resolve([10, 25]);
    });
    const load = createBoxSizesLoader(fetchSizes);
    const first = load(4);
    const second = load(4);
    expect(fetchSizes).toHaveBeenCalledTimes(1);
    rejectFirst(new Error('network'));
    await expect(first).rejects.toThrow('network');
    await expect(second).rejects.toThrow('network');
    await expect(load(4)).resolves.toEqual([10, 25]);
    expect(fetchSizes).toHaveBeenCalledTimes(2);
  });
});
