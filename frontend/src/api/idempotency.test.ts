import { describe, expect, it } from 'vitest';
import {
  acquireIdempotencyKey,
  isRetryableWriteError,
  releaseIdempotencyKey,
} from './idempotency';

describe('idempotency registry', () => {
  it('reuses a key for the same scope and stable payload', () => {
    const first = acquireIdempotencyKey('create-sales-order', {
      customer_name: '烟友',
      lines: [{ cigar_id: 12, quantity: 2 }],
    });
    const second = acquireIdempotencyKey('create-sales-order', {
      lines: [{ quantity: 2, cigar_id: 12 }],
      customer_name: '烟友',
    });

    expect(second).toBe(first);
  });

  it('creates a new key after the pending key is released', () => {
    const payload = { account_id: 3, actual_amount: '100.00' };
    const first = acquireIdempotencyKey('create-reconciliation', payload);

    releaseIdempotencyKey('create-reconciliation', payload);

    expect(acquireIdempotencyKey('create-reconciliation', payload)).not.toBe(first);
  });

  it.each([
    ['network error without a response', { isAxiosError: true }],
    ['server error', { isAxiosError: true, response: { status: 500 } }],
    ['in-flight duplicate response', {
      isAxiosError: true,
      response: { status: 409, data: { error: '请求正在处理中，请稍后重试' } },
    }],
  ])('keeps the pending key for a retryable %s', (_label, error) => {
    expect(isRetryableWriteError(error)).toBe(true);
  });

  it.each([
    ['business validation error', { isAxiosError: true, response: { status: 400 } }],
    ['ordinary conflict', { isAxiosError: true, response: { status: 409, data: { error: '订单状态不允许' } } }],
  ])('releases the pending key for a definite %s', (_label, error) => {
    expect(isRetryableWriteError(error)).toBe(false);
  });
});
