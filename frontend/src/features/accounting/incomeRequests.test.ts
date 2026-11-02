// @vitest-environment jsdom
import { installIncomeTestLocks } from './incomeTestLocks';
installIncomeTestLocks();

import { afterEach, describe, expect, it, vi } from 'vitest';
import { useAuthStore } from '../../store/authStore';
import { incomeCreateScope, isRetryableIncomeWriteError, pendingIncomeRequest, writeIncomeRequest } from './incomeRequests';

afterEach(() => { localStorage.clear(); useAuthStore.setState({ user: null }); });
const payload = { amount: '11000.00', exchange_rate: '11', business_date: '2026-11-02', note: '公司结息' };

describe('收入请求持久化恢复', () => {
  it('独立模块模拟两标签页同时提交，只使用一个持久化操作键', async () => {
    vi.resetModules();
    const otherTab = await import('./incomeRequests');
    let finish!: (value: { data: string }) => void;
    const response = new Promise<{ data: string }>(resolve => { finish = resolve; });
    const send = vi.fn(() => response);
    const first = writeIncomeRequest(incomeCreateScope, payload, send);
    const second = otherTab.writeIncomeRequest(incomeCreateScope, payload, send);
    await vi.waitFor(() => expect(send).toHaveBeenCalledTimes(2));
    expect(send.mock.calls[0]).toEqual(send.mock.calls[1]);
    finish({ data: 'ok' });
    await expect(Promise.all([first, second])).resolves.toEqual(['ok', 'ok']);
    expect(pendingIncomeRequest(incomeCreateScope)).toBeNull();
  });

  it('旧标签页迟到的成功响应不能清除另一笔新请求', async () => {
    let finish!: (value: { data: string }) => void;
    const slow = new Promise<{ data: string }>(resolve => { finish = resolve; });
    const send = vi.fn(() => slow);
    const original = writeIncomeRequest(incomeCreateScope, payload, send);
    await vi.waitFor(() => expect(send).toHaveBeenCalledOnce());
    await writeIncomeRequest(incomeCreateScope, payload, async () => ({ data: 'ok' }));
    const nextPayload = { ...payload, amount: '22000.00' };
    await expect(writeIncomeRequest(incomeCreateScope, nextPayload, async () => { throw new Error('timeout'); })).rejects.toThrow();
    finish({ data: 'ok' });
    await original;
    expect(pendingIncomeRequest(incomeCreateScope)?.payload).toEqual(nextPayload);
  });

  it('浏览器不支持跨标签锁时不发送，不误判为已发出且结果未知', async () => {
    Object.defineProperty(navigator, 'locks', { configurable: true, value: undefined });
    const request = vi.fn();
    try {
      await writeIncomeRequest(incomeCreateScope, payload, request);
      expect.fail('must reject');
    } catch (error) {
      expect(isRetryableIncomeWriteError(error)).toBe(false);
      expect(String(error)).toContain('HTTPS');
      expect(request).not.toHaveBeenCalled();
      expect(pendingIncomeRequest(incomeCreateScope)).toBeNull();
    } finally { installIncomeTestLocks(); }
  });

  it('服务端已提交但响应丢失时，模块重载后仍复用原键和原内容', async () => {
    const request = vi.fn().mockRejectedValueOnce(new Error('timeout'));
    await expect(writeIncomeRequest(incomeCreateScope, payload, request)).rejects.toThrow('timeout');
    const key = request.mock.calls[0][0].headers['Idempotency-Key'];
    vi.resetModules();
    const restored = await import('./incomeRequests');
    expect(restored.pendingIncomeRequest(incomeCreateScope)).toEqual({ key, payload });
    const retry = vi.fn().mockResolvedValue({ data: { income: { id: 1 } } });
    await expect(restored.writeIncomeRequest(incomeCreateScope, payload, retry)).resolves.toEqual({ income: { id: 1 } });
    expect(retry).toHaveBeenCalledExactlyOnceWith({ headers: { 'Idempotency-Key': key } });
    expect(restored.pendingIncomeRequest(incomeCreateScope)).toBeNull();
  });

  it('未确认请求阻止改内容再发；按操作用户隔离，明确拒绝后清除', async () => {
    useAuthStore.setState({ user: { username: 'owner-a', is_staff: true, is_superuser: false } });
    await expect(writeIncomeRequest(incomeCreateScope, payload, async () => { throw new Error('timeout'); })).rejects.toThrow();
    const changed = vi.fn();
    await expect(writeIncomeRequest(incomeCreateScope, { ...payload, amount: '999.00' }, changed)).rejects.toThrow('尚未确认');
    expect(changed).not.toHaveBeenCalled();
    useAuthStore.setState({ user: { username: 'owner-b', is_staff: true, is_superuser: false } });
    expect(pendingIncomeRequest(incomeCreateScope)).toBeNull();
    const secondOperator = vi.fn().mockResolvedValue({ data: {} });
    await writeIncomeRequest(incomeCreateScope, payload, secondOperator);
    const secondKey = secondOperator.mock.calls[0][0].headers['Idempotency-Key'];
    useAuthStore.setState({ user: { username: 'owner-a', is_staff: true, is_superuser: false } });
    expect(pendingIncomeRequest(incomeCreateScope)).not.toBeNull();
    expect(pendingIncomeRequest(incomeCreateScope)?.key).not.toBe(secondKey);
    const denied = { isAxiosError: true, response: { status: 409, data: { error: '该日期已对账' } } };
    await expect(writeIncomeRequest(incomeCreateScope, payload, async () => { throw denied; })).rejects.toBe(denied);
    expect(pendingIncomeRequest(incomeCreateScope)).toBeNull();
  });
});
