import { describe, expect, it } from 'vitest';
import type { Variant } from '../types';
import { buildChartData } from './priceData';

describe('buildChartData', () => {
  it('keeps a missing CNY price as null instead of inventing a zero price', () => {
    // 缺失价格代表“未知”，不能在图表或利润判断中伪造成零元。
    const variants = [{
      source_slug: 'source',
      source_name: '来源',
      box_size: 25,
      box_label: '25',
      currency: 'USD',
      points: [{
        date: '2026-08-16',
        price: 100,
        original_price: 100,
        price_cny: null,
        in_stock: true,
      }],
    }] satisfies Variant[];

    const rows = buildChartData(variants, 'cny_per_stick');

    expect(rows[0]['来源 25 · ¥']).toBeNull();
  });
});
