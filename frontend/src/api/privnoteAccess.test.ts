import { afterEach, describe, expect, it, vi } from 'vitest';
import { trackAccessAction } from './privnoteAccess';

describe('privnote access client', () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('只发送固定客户端事件，缺少 token 或 tracking token 时不发请求', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true });
    vi.stubGlobal('fetch', fetchMock);

    trackAccessAction('', 'visit', 'qr_open');
    trackAccessAction('note', undefined, 'qr_open');
    trackAccessAction('note', 'visit', 'submission' as 'qr_open');
    trackAccessAction('a/b', 'visit', 'copy_account');
    await Promise.resolve();

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/privnote/a%2Fb/events/',
      expect.objectContaining({
        method: 'POST',
        keepalive: true,
        body: JSON.stringify({ event: 'copy_account', tracking_token: 'visit' }),
      }),
    );
  });

  it('设备型号提示被拒绝、超时或返回有效型号时都不阻断加载', async () => {
    const original = Object.getOwnPropertyDescriptor(navigator, 'userAgentData');
    const loadFresh = async (value: unknown) => {
      vi.resetModules();
      Object.defineProperty(navigator, 'userAgentData', { configurable: true, value });
      const module = await import('./privnoteAccess');
      return module.privnoteDeviceHeaders();
    };

    try {
      await expect(loadFresh({ getHighEntropyValues: vi.fn().mockRejectedValue(new Error('拒绝')) })).resolves.toEqual({});

      const timedOut = loadFresh({ getHighEntropyValues: vi.fn(() => new Promise(() => undefined)) });
      await expect(timedOut).resolves.toEqual({});

      await expect(loadFresh({ getHighEntropyValues: vi.fn().mockResolvedValue({ model: 'Pixel 9' }) })).resolves.toEqual({
        'X-Privnote-Model': 'Pixel 9',
      });
    } finally {
      if (original) Object.defineProperty(navigator, 'userAgentData', original);
      else delete (navigator as Navigator & { userAgentData?: unknown }).userAgentData;
    }
  });
});
