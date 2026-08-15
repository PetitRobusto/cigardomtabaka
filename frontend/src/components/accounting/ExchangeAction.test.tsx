import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import ExchangeAction, { selectActiveAccountId as selectExchangeAccountId } from './ExchangeAction';

describe('换汇动作卡 SSR 契约', () => {
  it('只显示 CNY/USDT 转入固定 RUB，并保留 Decimal 字符串输入', () => {
    const html = renderToStaticMarkup(<ExchangeAction {...({ accounts: [{ id: 1, name: '人民币账户', currency: 'CNY', is_active: true }, { id: 2, name: 'USDT 账户', currency: 'USDT', is_active: true }, { id: 3, name: '卢布银行卡', currency: 'RUB', is_active: true }], value: { source_account_id: 1, rub_account_id: 3, source_amount: '12.34567890', rub_amount: '140.00' }, state: { status: 'error', input: { source_amount: '12.34567890', rub_amount: '140.00' }, error: { code: 'busy', message: '动作区繁忙' } }, onChange: () => undefined, onSubmit: () => undefined } as never)} />);
    expect(html).toContain('CNY');
    expect(html).toContain('USDT');
    expect(html).toContain('RUB');
    expect(html).toContain('12.34567890');
    expect(html).toContain('140.00');
    expect(html).toContain('动作区繁忙');
  });

  it('显式 businessDate 应作为默认业务日期', () => {
    const html = renderToStaticMarkup(<ExchangeAction {...({
      accounts: [{ id: 1, name: '人民币账户', currency: 'CNY', is_active: true }, { id: 3, name: '卢布银行卡', currency: 'RUB', is_active: true }],
      businessDate: '2026-08-16',
    } as never)} />);
    expect(html).toContain('value="2026-08-16"');
  });

  it('stale 或非 active 的账户 id 回退到当前合法账户', () => {
    const accounts = [
      { id: 1, name: '已停用 CNY', currency: 'CNY', is_active: false },
      { id: 2, name: '当前 USDT', currency: 'USDT', is_active: true },
    ];
    expect(selectExchangeAccountId(accounts, 999)).toBe(2);
    expect(selectExchangeAccountId(accounts, 1)).toBe(2);
    expect(selectExchangeAccountId([], 999)).toBe('');
  });
});
