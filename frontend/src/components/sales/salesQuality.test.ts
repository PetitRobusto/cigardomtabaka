import { describe, expect, it } from 'vitest';
import { salesActionBlockedByAccount } from './salesState';

describe('sales account error boundary', () => {
  it('blocks only fund-account actions while accounts are unavailable', () => {
    expect(salesActionBlockedByAccount('receive', '账户加载失败')).toBe(true);
    expect(salesActionBlockedByAccount('transport_cost', '账户加载失败')).toBe(true);
    expect(salesActionBlockedByAccount('ship', '账户加载失败')).toBe(false);
    expect(salesActionBlockedByAccount('receive', '')).toBe(false);
  });
});
