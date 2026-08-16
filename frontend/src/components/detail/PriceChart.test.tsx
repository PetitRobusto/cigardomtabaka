import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import type { Variant } from '../../types';
import { PriceChart } from './PriceChart';

describe('PriceChart missing-price handling', () => {
  it('omits the per-stick bar when price or box size is unknown', () => {
    const variants = [{
      source_slug: 'source',
      source_name: '来源',
      box_size: null,
      box_label: '未知盒规',
      currency: 'USD',
      price_per_stick: null,
      points: [{
        date: '2026-08-16',
        price: null,
        original_price: null,
        price_cny: null,
        in_stock: true,
      }],
    }] satisfies Variant[];

    const html = renderToStaticMarkup(<PriceChart variants={variants} />);

    expect(html).not.toContain('单支价格对比');
    expect(html).toContain('原币种走势');
  });
});
