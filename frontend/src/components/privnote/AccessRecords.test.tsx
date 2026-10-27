// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import AccessRecords from './AccessRecords';

const api = vi.hoisted(() => ({
  fetchAccessNotes: vi.fn(),
  fetchAccessDetail: vi.fn(),
  createPrivnoteQrImage: vi.fn(),
}));

vi.mock('../../api/privnoteAccess', () => ({
  fetchAccessNotes: api.fetchAccessNotes,
  fetchAccessDetail: api.fetchAccessDetail,
}));
vi.mock('../../lib/privnoteQr', () => ({
  createPrivnoteQrImage: api.createPrivnoteQrImage,
}));

const notes = {
  results: [{
    token: 'note-1', title: '第一链接', note_type: 'payment', created_at: '2026-09-12T10:00:00Z',
    view_count: 3, last_opened_at: null,
    customer_name: '王先生',
  }],
  page: 1, pages: 2, count: 2, retention_days: 30,
};
const detail = {
  note: {
    ...notes.results[0], url: 'https://example.com/p/note-1/',
    expires_at: '2026-09-13T10:00:00Z', created_by: '店员', order_number: 'SO-001',
    has_password: true, burn_after_read: false, max_views: 0,
  },
  summary: { opens: 2, visitors: 1, revisits: 1, last_opened_at: '2026-09-12T12:00:00Z' },
  results: [{
    id: 8, created_at: '2026-09-12T12:00:00Z', visitor: 'abc123', ip: '192.0.2.10',
    device: 'iPhone', browser: '微信', actor: 'customer', event: 'open', is_revisit: false,
  }],
  page: 1, pages: 2, count: 2, retention_days: 30,
};

function renderRecords(initialToken = '') {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <AccessRecords initialToken={initialToken} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  api.fetchAccessNotes.mockResolvedValue(notes);
  api.fetchAccessDetail.mockResolvedValue(detail);
  api.createPrivnoteQrImage.mockResolvedValue('data:image/png;base64,note-1-qr');
  vi.stubGlobal('fetch', vi.fn());
  vi.spyOn(window, 'open').mockImplementation(() => null);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('AccessRecords', () => {
  it('从列表进入详情，隔离 audience/page 查询并可返回列表', async () => {
    renderRecords();
    await waitFor(() => expect(screen.getByText('第一链接')).toBeTruthy());
    expect(screen.getByText('客户：王先生')).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: '查看记录' }));
    await waitFor(() => expect(screen.getByRole('heading', { name: '第一链接' })).toBeTruthy());
    expect(api.fetchAccessDetail).toHaveBeenLastCalledWith('note-1', 'customer', 1);
    expect(screen.getByText('客户：王先生 · 关联销售单：SO-001')).toBeTruthy();
    expect(screen.getByRole('link', { name: detail.note.url }).getAttribute('href')).toBe(detail.note.url);
    expect(screen.getByText(/创建人：店员 · 到期时间：/)).toBeTruthy();
    expect(screen.getByText('密码保护：已开启 · 阅后即焚：未开启 · 查看次数限制：不限次数')).toBeTruthy();

    fireEvent.change(screen.getByLabelText('记录范围'), { target: { value: 'all' } });
    await waitFor(() => expect(api.fetchAccessDetail).toHaveBeenLastCalledWith('note-1', 'all', 1));
    await waitFor(() => expect(screen.getByRole('button', { name: '下一页' })).toBeTruthy());
    fireEvent.click(screen.getByRole('button', { name: '下一页' }));
    await waitFor(() => expect(api.fetchAccessDetail).toHaveBeenLastCalledWith('note-1', 'all', 2));

    fireEvent.click(screen.getByRole('button', { name: '返回链接列表' }));
    expect(screen.getByLabelText('搜索客户名、标题或链接编号')).toBeTruthy();
  });

  it('搜索、类型筛选和分页各自形成列表查询条件', async () => {
    api.fetchAccessNotes.mockImplementation((q: string, type: string, page: number) => Promise.resolve({
      ...notes,
      results: q || type ? [{ ...notes.results[0], title: `${q}-${type}-${page}` }] : notes.results,
      page,
    }));
    renderRecords();
    await waitFor(() => expect(screen.getByText('第一链接')).toBeTruthy());

    fireEvent.change(screen.getByLabelText('搜索客户名、标题或链接编号'), { target: { value: '客户' } });
    await waitFor(() => expect(api.fetchAccessNotes).toHaveBeenLastCalledWith('客户', '', 1));
    fireEvent.change(screen.getByLabelText('链接类型'), { target: { value: 'payment' } });
    await waitFor(() => expect(api.fetchAccessNotes).toHaveBeenLastCalledWith('客户', 'payment', 1));
    fireEvent.click(screen.getByRole('button', { name: '下一页' }));
    await waitFor(() => expect(api.fetchAccessNotes).toHaveBeenLastCalledWith('客户', 'payment', 2));
  });

  it('列表请求失败可通过重试恢复，详情请求错误也提供重试入口', async () => {
    api.fetchAccessNotes.mockRejectedValueOnce(new Error('列表暂不可用')).mockResolvedValueOnce(notes);
    renderRecords();
    await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('列表暂不可用'));
    fireEvent.click(screen.getByRole('button', { name: /重试/ }));
    await waitFor(() => expect(screen.getByText('第一链接')).toBeTruthy());

    api.fetchAccessDetail.mockRejectedValueOnce(new Error('详情暂不可用')).mockResolvedValueOnce(detail);
    fireEvent.click(screen.getByRole('button', { name: '查看记录' }));
    await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('详情暂不可用'));
    fireEvent.click(screen.getByRole('button', { name: /重试/ }));
    await waitFor(() => expect(screen.getByRole('heading', { name: '第一链接' })).toBeTruthy());
  });

  it('无客户和创建人时显示占位，保留有限查看次数', async () => {
    api.fetchAccessDetail.mockResolvedValue({
      ...detail, note: { ...detail.note, customer_name: '', created_by: '', order_number: '', burn_after_read: true, max_views: 1 },
    });
    renderRecords('note-1');
    await waitFor(() => expect(screen.getByText('客户：未填写')).toBeTruthy());
    expect(screen.getByText(/创建人：未记录/)).toBeTruthy();
    expect(screen.getByText(/查看次数限制：1 次/)).toBeTruthy();
    expect(screen.queryByText(/关联销售单/)).toBeNull();
  });

  it('详情二维码使用完整链接并可保存，不打开客户链接或增加访问请求', async () => {
    renderRecords();
    await screen.findByText('第一链接');
    fireEvent.click(screen.getByRole('button', { name: '查看记录' }));

    const qr = await screen.findByRole('img', { name: '链接二维码' });
    expect(api.createPrivnoteQrImage).toHaveBeenCalledWith(detail.note.url);
    expect(qr.getAttribute('src')).toBe('data:image/png;base64,note-1-qr');
    const download = screen.getByRole('link', { name: '保存二维码' });
    expect(download.getAttribute('href')).toBe('data:image/png;base64,note-1-qr');
    expect(download.getAttribute('download')).toBe('CigarDomTabaka-二维码.png');
    expect(api.fetchAccessDetail).toHaveBeenCalledTimes(1);
    expect(window.open).not.toHaveBeenCalled();
    expect(fetch).not.toHaveBeenCalled();
  });

  it('放大二维码后按 Escape 关闭并恢复触发按钮焦点', async () => {
    renderRecords('note-1');
    await screen.findByRole('img', { name: '链接二维码' });
    const trigger = screen.getByRole('button', { name: '放大链接二维码' });
    trigger.focus();
    fireEvent.click(trigger);

    const dialog = screen.getByRole('dialog', { name: '链接二维码' });
    expect(dialog.contains(document.activeElement)).toBe(true);
    fireEvent.keyDown(document, { key: 'Escape' });

    expect(screen.queryByRole('dialog')).toBeNull();
    expect(document.activeElement).toBe(trigger);
    expect(api.fetchAccessDetail).toHaveBeenCalledTimes(1);
    expect(window.open).not.toHaveBeenCalled();
    expect(fetch).not.toHaveBeenCalled();
  });

  it('二维码失败后只重试本地生成，不重新请求详情或打开客户链接', async () => {
    api.createPrivnoteQrImage
      .mockRejectedValueOnce(new Error('本地二维码生成失败'))
      .mockResolvedValueOnce('data:image/png;base64,retried-qr');
    renderRecords('note-1');

    await screen.findByText('二维码生成失败，链接仍可使用。');
    expect(api.fetchAccessDetail).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole('button', { name: '重试二维码' }));

    const qr = await screen.findByRole('img', { name: '链接二维码' });
    expect(qr.getAttribute('src')).toBe('data:image/png;base64,retried-qr');
    expect(api.createPrivnoteQrImage).toHaveBeenCalledTimes(2);
    expect(api.createPrivnoteQrImage).toHaveBeenNthCalledWith(1, detail.note.url);
    expect(api.createPrivnoteQrImage).toHaveBeenNthCalledWith(2, detail.note.url);
    expect(api.fetchAccessDetail).toHaveBeenCalledTimes(1);
    expect(window.open).not.toHaveBeenCalled();
    expect(fetch).not.toHaveBeenCalled();
  });

  it('返回列表选择另一个 token 时不展示前一个链接的二维码', async () => {
    const secondNote = { ...notes.results[0], token: 'note-2', title: '第二链接' };
    let resolveSecondQr!: (source: string) => void;
    api.fetchAccessNotes.mockResolvedValue({ ...notes, results: [...notes.results, secondNote] });
    api.fetchAccessDetail.mockImplementation(async token => ({
      ...detail,
      note: {
        ...detail.note,
        token,
        title: token === 'note-1' ? '第一链接' : '第二链接',
        url: `https://example.com/p/${token}/`,
      },
    }));
    api.createPrivnoteQrImage.mockImplementation(url =>
      url.endsWith('note-1/')
        ? Promise.resolve('data:image/png;base64,note-1-qr')
        : new Promise(resolve => { resolveSecondQr = resolve; }),
    );
    renderRecords();
    await screen.findByText('第二链接');
    fireEvent.click(screen.getAllByRole('button', { name: '查看记录' })[0]);
    await screen.findByRole('img', { name: '链接二维码' });
    expect(screen.getByRole('img', { name: '链接二维码' }).getAttribute('src')).toBe('data:image/png;base64,note-1-qr');

    fireEvent.click(screen.getByRole('button', { name: '返回链接列表' }));
    await screen.findByLabelText('搜索客户名、标题或链接编号');
    fireEvent.click(screen.getAllByRole('button', { name: '查看记录' })[1]);

    await screen.findByText('二维码生成中…');
    expect(screen.queryByRole('img', { name: '链接二维码' })).toBeNull();
    resolveSecondQr('data:image/png;base64,note-2-qr');
    const secondQr = await screen.findByRole('img', { name: '链接二维码' });
    expect(secondQr.getAttribute('src')).toBe('data:image/png;base64,note-2-qr');
    expect(api.createPrivnoteQrImage).toHaveBeenNthCalledWith(1, 'https://example.com/p/note-1/');
    expect(api.createPrivnoteQrImage).toHaveBeenNthCalledWith(2, 'https://example.com/p/note-2/');
  });
});
