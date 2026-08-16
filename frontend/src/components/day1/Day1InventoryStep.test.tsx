import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import * as api from '../../api';
import type { CigarDetailResponse } from '../../types';
import Day1InventoryStep from './Day1InventoryStep';
import { applyIfDay1InventoryMounted, boxSizesFromCigarDetail, createBoxSizesLoader, createDay1InventoryMountGuard, fetchDeclaredBoxSizes, runDay1InventoryAdd } from './Day1InventoryStep.helpers';

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

  it('keeps an existing draft row in loading state before its detail response arrives', () => {
    // SSR has no effect pass, so this locks the first render against unsafe manual input.
    const html = renderToStaticMarkup(
      <Day1InventoryStep
        inventory={[{ cigar_id: 4, cigar_name: '已有草稿', box_size: 25, box_quantity: 1, loose_sticks: 0, unit_cost_cny: '10.00' }]}
        onChange={() => {}}
      />,
    );
    expect(html).toContain('正在读取目录包装规格');
    expect(html).not.toContain('min="1" step="1"');
    expect(html).not.toContain('<select');
  });

  it('loads existing draft rows from the real detail API response', async () => {
    // 使用完整响应夹具，让目录 API 变更能在编译期暴露。
    const detail = {
      cigar: {
        id: 4,
        brand: '测试品牌',
        english_name: 'Test Cigar',
        name: '测试雪茄',
        vitola: 'Robusto',
        vitola_cn: '罗布图',
        length: 124,
        ring_gauge: 50,
        common_name: '',
        common_name_cn: '',
        origin: 'Cuba',
        status: 'active',
        release_type: 'regular',
        release_type_cn: '常规',
        release_name: '',
        production_method: 'handmade',
        packagings: ['10', '25'],
        box_sizes: [10, 25],
      },
      brand: null,
      images_by_type: {},
      total_images: 0,
      related: [],
      children: [],
    } satisfies CigarDetailResponse;
    const fetchDetail = vi.spyOn(api, 'fetchCigarDetail').mockResolvedValue(detail);
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

  it('does not run inventory updates after the component has unmounted', () => {
    // Async detail completion must not mutate a form that navigation already removed.
    const update = vi.fn();
    expect(applyIfDay1InventoryMounted(false, update)).toBe(false);
    expect(update).not.toHaveBeenCalled();
    expect(applyIfDay1InventoryMounted(true, update)).toBe(true);
    expect(update).toHaveBeenCalledTimes(1);
  });

  it('restores mounted state across StrictMode setup cleanup setup replay', () => {
    // This is the effect's real setup/cleanup contract under React development replay.
    const guard = createDay1InventoryMountGuard();
    const firstCleanup = guard.setup();
    firstCleanup();
    const secondCleanup = guard.setup();
    const update = vi.fn();
    expect(guard.run(update)).toBe(true);
    expect(update).toHaveBeenCalledTimes(1);
    secondCleanup();
    expect(guard.run(update)).toBe(false);
    expect(update).toHaveBeenCalledTimes(1);
  });

  it('blocks resolve reject and finally updates after an async load unmounts', () => {
    // Each promise completion path uses the same production mount guard.
    const guard = createDay1InventoryMountGuard();
    const cleanup = guard.setup();
    cleanup();
    const onChange = vi.fn();
    const setState = vi.fn();
    [onChange, setState, setState].forEach(update => expect(guard.run(update)).toBe(false));
    expect(onChange).not.toHaveBeenCalled();
    expect(setState).not.toHaveBeenCalled();
  });

  it('drops resolve success and finally callbacks after the real add flow unmounts', async () => {
    // The production add chain must discard every completion after navigation cleanup.
    const guard = createDay1InventoryMountGuard();
    const cleanup = guard.setup();
    let resolve: (sizes: number[]) => void = () => {};
    const onSuccess = vi.fn();
    const onError = vi.fn();
    const onFinally = vi.fn();
    const pending = runDay1InventoryAdd({
      loadBoxSizes: () => new Promise<number[]>(res => { resolve = res; }),
      isMounted: guard.isMounted,
      run: guard.run,
      onSuccess,
      onError,
      onFinally,
    });
    cleanup();
    resolve([10, 25]);
    await pending;
    expect(onSuccess).not.toHaveBeenCalled();
    expect(onError).not.toHaveBeenCalled();
    expect(onFinally).not.toHaveBeenCalled();
  });

  it('drops reject error and finally callbacks after the real add flow unmounts', async () => {
    const guard = createDay1InventoryMountGuard();
    const cleanup = guard.setup();
    let reject: (reason: Error) => void = () => {};
    const onSuccess = vi.fn();
    const onError = vi.fn();
    const onFinally = vi.fn();
    const pending = runDay1InventoryAdd({
      loadBoxSizes: () => new Promise<number[]>((_, rej) => { reject = rej; }),
      isMounted: guard.isMounted,
      run: guard.run,
      onSuccess,
      onError,
      onFinally,
    });
    cleanup();
    reject(new Error('network'));
    await pending;
    expect(onSuccess).not.toHaveBeenCalled();
    expect(onError).not.toHaveBeenCalled();
    expect(onFinally).not.toHaveBeenCalled();
  });
});
