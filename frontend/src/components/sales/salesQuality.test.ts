import { describe, expect, it, vi } from 'vitest';
import { salesOrderActionBusinessDate, selectActiveCnyAccountId } from './SalesOrderCard';
import { salesActionBlockedByAccount } from './salesState';

describe('sales account error boundary', () => {
  it('blocks only fund-account actions while accounts are unavailable', () => {
    expect(salesActionBlockedByAccount('receive', '账户加载失败')).toBe(true);
    expect(salesActionBlockedByAccount('transport_cost', '账户加载失败')).toBe(true);
    expect(salesActionBlockedByAccount('ship', '账户加载失败')).toBe(false);
    expect(salesActionBlockedByAccount('receive', '')).toBe(false);
  });
});

describe('销售动作业务日期', () => {
  it('在 UTC 已跨日但 Moscow 尚未跨日时仍返回 Moscow 业务日', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-08-13T23:00:00.000Z'));
    expect(salesOrderActionBusinessDate()).toBe('2026-08-14');
    vi.useRealTimers();
  });
});

describe('销售动作账户刷新', () => {
  it('当前 CNY 账户停用后替换为 active CNY，且没有可用账户时清空', () => {
    const accounts = [
      { id: 10, name: '已停用', currency: 'CNY', is_active: false },
      { id: 20, name: '有效 CNY', currency: 'CNY', is_active: true },
      { id: 30, name: '有效 RUB', currency: 'RUB', is_active: true },
    ];
    expect(selectActiveCnyAccountId(accounts, 10)).toBe(20);
    expect(selectActiveCnyAccountId(accounts, 999)).toBe(20);
    expect(selectActiveCnyAccountId([], 10)).toBe(0);
  });
});
