import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import ExpenseAction from './ExpenseAction';

describe('经营费用动作卡 SSR 契约', () => {
  it('体现工资用 CNY、其他费用用 RUB 的分类过滤', () => {
    const html = renderToStaticMarkup(<ExpenseAction {...({ accounts: [{ id: 1, name: '人民币账户', currency: 'CNY', is_active: true }, { id: 3, name: '卢布银行卡', currency: 'RUB', is_active: true }], category: 'salary_expense', value: { amount: '10000.00', business_date: '2026-08-15' }, onChange: () => undefined, onSubmit: () => undefined } as never)} />);
    expect(html).toContain('工资');
    expect(html).toContain('CNY');
    expect(html).not.toContain('卢布银行卡');
  });

  it('显式 businessDate 应作为默认业务日期', () => {
    const html = renderToStaticMarkup(<ExpenseAction {...({
      accounts: [{ id: 1, name: '人民币账户', currency: 'CNY', is_active: true }],
      category: 'salary',
      businessDate: '2026-08-16',
    } as never)} />);
    expect(html).toContain('value="2026-08-16"');
  });
});

describe('经营费用默认业务日期', () => {
  it('省略 businessDate 时使用 Moscow 业务日而非 UTC 日期', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-08-13T23:00:00.000Z'));
    const html = renderToStaticMarkup(<ExpenseAction {...({ accounts: [] } as never)} />);
    expect(html).toContain('value="2026-08-14"');
    vi.useRealTimers();
  });
});
