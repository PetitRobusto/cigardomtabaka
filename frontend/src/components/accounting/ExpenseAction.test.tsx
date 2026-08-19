import type { ComponentProps } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import ExpenseAction from './ExpenseAction';

describe('经营费用动作卡 SSR 契约', () => {
  it('费用类别不再强制绑定币种', () => {
    const props = {
      accounts: [
        { id: 1, name: '人民币账户', currency: 'CNY', custodian_id: null, is_active: true },
        { id: 3, name: '卢布银行卡', currency: 'RUB', custodian_id: null, is_active: true },
      ],
      category: 'salary_expense',
      value: { amount: '10000.00', business_date: '2026-08-15' },
      onChange: () => undefined,
      onSubmit: () => undefined,
    } satisfies ComponentProps<typeof ExpenseAction>;
    const html = renderToStaticMarkup(<ExpenseAction {...props} />);
    expect(html).toContain('工资');
    expect(html).toContain('支付币种');
    expect(html).toContain('人民币（CNY）');
  });
  it('选择任意费用时可使用卢布账户', () => {
    const html = renderToStaticMarkup(<ExpenseAction
      accounts={[
        { id: 1, name: '人民币账户', currency: 'CNY', custodian_id: null, is_active: true },
        { id: 3, name: '卢布银行卡', currency: 'RUB', custodian_id: null, is_active: true },
      ]}
      category="rent"
      value={{ fund_account_id: 3 }}
    />);
    expect(html).toContain('房租');
    expect(html).toContain('卢布银行卡');
    expect(html).toContain('value="3"');
  });
  it('显式 businessDate 应作为默认业务日期', () => {
    const props = {
      accounts: [{ id: 1, name: '人民币账户', currency: 'CNY', custodian_id: null, is_active: true }],
      category: 'salary',
      businessDate: '2026-08-16',
    } satisfies ComponentProps<typeof ExpenseAction>;
    const html = renderToStaticMarkup(<ExpenseAction {...props} />);
    expect(html).toContain('value="2026-08-16"');
  });
});

describe('经营费用默认业务日期', () => {
  it('省略 businessDate 时使用 Moscow 业务日而非 UTC 日期', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-08-13T23:00:00.000Z'));
    const html = renderToStaticMarkup(<ExpenseAction accounts={[]} />);
    expect(html).toContain('value="2026-08-14"');
    vi.useRealTimers();
  });
});
