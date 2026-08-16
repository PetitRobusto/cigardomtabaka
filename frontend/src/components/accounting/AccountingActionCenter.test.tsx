import type { ComponentProps } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import AccountingActionCenter from './AccountingActionCenter';

describe('账务动作中心 SSR 契约', () => {
  it('四张动作卡使用可聚焦的稳定引导 section', () => {
    const props = {
      accounts: [],
      purchases: [],
      dividends: [],
      businessDate: '2026-08-15',
      onChanged: () => undefined,
    } satisfies ComponentProps<typeof AccountingActionCenter>;
    const html = renderToStaticMarkup(<AccountingActionCenter {...props} />);
    for (const target of ['exchange', 'purchase', 'expense', 'dividend']) {
      expect(html).toMatch(new RegExp(`<section(?=[^>]*data-guide="accounting-actions-${target}")(?=[^>]*tabindex="-1")[^>]*>`));
    }
    // 引导定位不能落在提交按钮上，避免误触真实账务动作。
    expect(html).not.toMatch(/<button[^>]*data-guide=/);
  });

  it('摘要账户应优先使用带余额的 summaryAccounts 数据', () => {
    const props = {
      accounts: [{ id: 1, name: '人民币账户', currency: 'CNY', custodian_id: null, is_active: true }],
      summaryAccounts: [{ id: 1, name: '人民币账户', currency: 'CNY', custodian_id: null, is_active: true, original_balance: '12345.67', cny_book_cost: '12345.67' }],
      purchases: [],
      dividends: [],
      businessDate: '2026-08-15',
      onChanged: () => undefined,
    } satisfies ComponentProps<typeof AccountingActionCenter>;
    const html = renderToStaticMarkup(<AccountingActionCenter {...props} />);
    expect(html).toContain('12345.67');
    expect(html).toContain('人民币账户');
    expect(html).not.toContain('当前接口未提供余额');
  });
});
