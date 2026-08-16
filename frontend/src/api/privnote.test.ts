import { afterEach, describe, expect, it, vi } from 'vitest';
import { createPrivnote } from '../api';

function stubCreateResponse(body: unknown) {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    json: () => Promise.resolve(body),
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

describe('createPrivnote response boundary', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('returns a valid private-link response', async () => {
    const body = { url: '/p/token/', token: 'token' };
    const fetchMock = stubCreateResponse(body);

    await expect(createPrivnote(new FormData())).resolves.toEqual(body);
    expect(fetchMock).toHaveBeenCalledWith(
      '/privnote/create/',
      expect.objectContaining({ method: 'POST', credentials: 'same-origin' }),
    );
  });

  it('rejects a successful HTTP response without string url and token fields', async () => {
    // HTTP 成功不代表响应契约有效，页面只能接收完整链接。
    stubCreateResponse({ url: {}, token: 123 });

    await expect(createPrivnote(new FormData())).rejects.toThrow('服务器返回格式错误');
  });
});
