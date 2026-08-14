import { describe, expect, it } from 'vitest';
import { day1ErrorMessage, day1WriteHeaders } from '../api';

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
});
