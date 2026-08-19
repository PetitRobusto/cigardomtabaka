import type { ComponentProps } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import AccountingActionCenter from './AccountingActionCenter';

describe('账务动作中心 SSR 契约', () => {
  it('默认只渲染换汇表单，并保留全部操作入口', () => {
    const props = {
      accounts: [],
      purchases: [],
      dividends: [],
      businessDate: '2026-08-15',
      onChanged: () => undefined,
    } satisfies ComponentProps<typeof AccountingActionCenter>;
    const html = renderToStaticMarkup(<AccountingActionCenter {...props} />);
    for (const label of ['换汇', '采购', '记录费用', '分红', '账户对账']) {
      expect(html).toContain(label);
    }
    expect(html).toMatch(/<section(?=[^>]*data-guide="accounting-actions-exchange")(?=[^>]*tabindex="-1")[^>]*>/);
    expect(html).not.toContain('data-guide="accounting-actions-purchase"');
    expect(html).not.toContain('data-guide="accounting-actions-expense"');
    expect(html).not.toContain('data-guide="accounting-actions-dividend"');
  });

  it('可按帮助引导直接打开采购表单', () => {
    const html = renderToStaticMarkup(<AccountingActionCenter
      accounts={[]}
      businessDate="2026-08-15"
      initialAction="purchase"
    />);
    expect(html).toContain('data-guide="accounting-actions-purchase"');
    expect(html).not.toContain('data-guide="accounting-actions-exchange"');
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
    expect(html).toContain('12,345.67');
    expect(html).toContain('人民币账户');
    expect(html).not.toContain('当前接口未提供余额');
  });
});
