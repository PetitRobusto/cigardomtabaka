import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
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
