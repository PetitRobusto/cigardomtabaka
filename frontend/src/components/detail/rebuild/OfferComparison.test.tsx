import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import type { Variant } from '../../../types';
import { OfferComparison } from './OfferComparison';
import { IdentityCard } from './IdentityCard';
import { PriceCard } from '../../dashboard/PriceCard';

const quote: Variant = {
  source_slug: 'a', source_name: '来源名称', box_size: 10, box_label: '10支', currency: 'USD',
  product_name: '真实款式名称', scraped_name: '旧别名', current_price: 100, current_price_cny: 700,
  in_stock: true, points: [], scraped_at: '2026-09-01T12:30:00Z', url: 'https://example.com/product',
};

describe('rebuilt detail presentation', () => {
  it('shows distinct product, status, raw currency, record count and real exchange configuration', () => {
    const html = renderToStaticMarkup(<OfferComparison variants={[{ ...quote, record_count: 12, source_currency: 'USD', source_exchange_rate: 7.1 }]} />);
    expect(html).toContain('真实款式名称');
    expect(html).not.toContain('旧别名');
    expect(html).toContain('USD 100');
    expect(html).toContain('¥700');
    expect(html).toContain('¥70');
    expect(html).toContain('12 条历史记录');
    expect(html).toContain('1 USD = 7.1 CNY');
    expect(html).toContain('dateTime="2026-09-01T12:30:00Z"');
    expect(html).toContain('aria-label="查看来源名称来源，核验报价"');
  });

  it('keeps delisted and anomalous offers visible without minimum-price highlighting', () => {
    const html = renderToStaticMarkup(<OfferComparison variants={[
      { ...quote, delisted: true },
      { ...quote, url: 'https://example.com/anomaly', snapshot_id: 7, anomaly: { code: 'outlier', label: '价格异常', reason: '已标记离群', exclude_from_aggregate: true } },
    ]} />);
    expect(html).toContain('已下架');
    expect(html).toContain('价格异常');
    expect(html).toContain('记录 #7');
    expect(html).not.toContain('最低在售价');
    expect(html).toContain('来源未提供参考汇率');
  });

  it('keeps both product names inside the main heading and avoids duplication', () => {
    const prices = { cigar_id: 1, cigar_name: '中文', cigar_name_en: 'English', variants: [quote] };
    const html = renderToStaticMarkup(<IdentityCard prices={prices} counts={{ in: 1, out: 0, delisted: 0, invalid: 0 }} last="—" />);
    expect(html).toMatch(/<h1>中文.*English.*<\/h1>/);
    expect(html).toContain('常规款');
  });

  it('Dashboard card computes only valid active unit prices and preserves card markup', () => {
    const source = { source_id: 1, source_slug: 'a', source_name: 'A', price: 100, original_price: null,
      currency: 'USD', price_cny: 700, box_size: 10, in_stock: true, url: '' };
    const sources = [source, { ...source, price_cny: 900, source_slug: 'b' },
      { ...source, in_stock: false }, { ...source, delisted: true },
      { ...source, price_cny: -100 }, { ...source, box_size: 0 }, { ...source, price_cny: null }];
    const html = renderToStaticMarkup(<PriceCard index={0} onClick={() => {}} cigar={{
      cigar_id: 1, cigar_name: '中文', cigar_name_en: 'English', cigar_brand: '', cigar_brand_cn: '',
      cigar_image_url: '', sources, in_stock: true, avg_per_stick_cny: 999,
    }} />);
    expect(html).toContain('在售均价/支');
    expect(html).toContain('¥80');
    expect(html).not.toContain('¥999');
    expect(html).toContain('aspect-[4/3]');
  });
});
