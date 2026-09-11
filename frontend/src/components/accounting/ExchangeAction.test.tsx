import type { ComponentProps } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import type { FundAccount } from '../../types';
import ExchangeAction, { ExchangeConfirmationModal } from './ExchangeAction';
import { selectActiveAccountId as selectExchangeAccountId } from './ExchangeAction.logic';

describe('换汇动作卡 SSR 契约', () => {
  it('只显示 CNY/USDT 转入固定 RUB，并保留 Decimal 字符串输入', () => {
    const props = {
      accounts: [
        { id: 1, name: '人民币账户', currency: 'CNY', custodian_id: null, is_active: true },
        { id: 2, name: 'USDT 账户', currency: 'USDT', custodian_id: null, is_active: true },
        { id: 3, name: '卢布银行卡', currency: 'RUB', custodian_id: null, is_active: true },
      ],
      value: {
        source_account_id: 1,
        rub_account_id: 3,
        source_amount: '12.34567890',
        rub_amount: '140.00',
      },
      state: {
        status: 'error',
        input: { source_amount: '12.34567890', rub_amount: '140.00' },
        error: { code: 'busy', message: '动作区繁忙' },
      },
      onChange: () => undefined,
      onSubmit: () => undefined,
    } satisfies ComponentProps<typeof ExchangeAction>;
    const html = renderToStaticMarkup(<ExchangeAction {...props} />);
    expect(html).toContain('CNY');
    expect(html).toContain('USDT');
    expect(html).toContain('RUB');
    expect(html).toContain('12.34567890');
    expect(html).toContain('140.00');
    expect(html).toContain('动作区繁忙');
  });

  it('显式 businessDate 应作为默认业务日期', () => {
    const props = {
      accounts: [
        { id: 1, name: '人民币账户', currency: 'CNY', custodian_id: null, is_active: true },
        { id: 3, name: '卢布银行卡', currency: 'RUB', custodian_id: null, is_active: true },
      ],
      businessDate: '2026-08-16',
    } satisfies ComponentProps<typeof ExchangeAction>;
    const html = renderToStaticMarkup(<ExchangeAction {...props} />);
    expect(html).toContain('value="2026-08-16"');
  });

  it('stale 或非 active 的账户 id 回退到当前合法账户', () => {
    const accounts = [
      { id: 1, name: '已停用 CNY', currency: 'CNY', custodian_id: null, is_active: false },
      { id: 2, name: '当前 USDT', currency: 'USDT', custodian_id: null, is_active: true },
    ] satisfies FundAccount[];
    expect(selectExchangeAccountId(accounts, 999)).toBe(2);
    expect(selectExchangeAccountId(accounts, 1)).toBe(2);
    expect(selectExchangeAccountId([], 999)).toBe('');
  });
});

describe('换汇动作默认业务日期', () => {
  it('省略 businessDate 时使用 Moscow 业务日而非 UTC 日期', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-08-13T23:00:00.000Z'));
    const html = renderToStaticMarkup(<ExchangeAction accounts={[]} />);
    expect(html).toContain('value="2026-08-14"');
    vi.useRealTimers();
  });
});

describe('换汇二次确认', () => {
  it('在 modal 中逐项展示不可变提交快照和实际汇率', () => {
    const html = renderToStaticMarkup(<ExchangeConfirmationModal
      payload={{ source_account_id: 1, rub_account_id: 3, source_amount: '100.00', rub_amount: '1200.00', business_date: '2026-08-16' }}
      sourceLabel="人民币账户 · CNY"
      rubLabel="卢布银行卡 · RUB"
      sourceCurrency="CNY"
      busy={false}
      onCancel={() => undefined}
      onConfirm={() => undefined}
    />);

    expect(html).toContain('确认换汇');
    expect(html).toContain('人民币账户 · CNY');
    expect(html).toContain('卢布银行卡 · RUB');
    expect(html).toContain('100.00 CNY');
    expect(html).toContain('1,200.00 RUB');
    expect(html).toContain('12.0000 RUB / 原币');
    expect(html).toContain('确认换汇并入账');
  });
});
