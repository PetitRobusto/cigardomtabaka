import { describe, expect, it } from 'vitest';
import { clearDay1ValidationDetails, day1ErrorMessage, day1ValidationDetails, day1WriteHeaders } from '../api';

describe('Day 1 API contract helpers', () => {
  it('builds optimistic version and idempotency headers', () => {
    expect(day1WriteHeaders(7, 'confirm-7')).toEqual({ 'If-Match': '7', 'Idempotency-Key': 'confirm-7' });
    expect(day1WriteHeaders(0)).toEqual({ 'If-Match': '0' });
  });

  it('explains stale shared drafts without exposing a generic conflict', () => {
    const error = Object.assign(new Error('conflict'), {
      isAxiosError: true,
      response: { status: 409, data: { code: 'version_conflict', error: '版本冲突' } },
    });
    expect(day1ErrorMessage(error)).toBe('另一位经营者已更新，请刷新');
  });

  it('exposes backend validation details for step and row rendering', () => {
    const error = Object.assign(new Error('invalid'), {
      isAxiosError: true,
      response: { status: 400, data: { details: { business_date: '不能晚于当前业务日', 'inventory[1]': '库存数量必须大于零' } } },
    });
    expect(day1ValidationDetails(error)).toEqual({
      business_date: '不能晚于当前业务日',
      'inventory[1]': '库存数量必须大于零',
    });
  });

  it('clears stale details when the corresponding local section is edited', () => {
    expect(clearDay1ValidationDetails({
      business_date: '日期错误',
      'inventory[1].box_size': '包装错误',
      'accounts[0].name': '账户错误',
    }, 'inventory')).toEqual({
      business_date: '日期错误',
      'accounts[0].name': '账户错误',
    });
  });
});
