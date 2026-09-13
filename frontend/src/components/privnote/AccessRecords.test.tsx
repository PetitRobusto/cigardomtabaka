// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import AccessRecords from './AccessRecords';

const api = vi.hoisted(() => ({
  fetchAccessNotes: vi.fn(),
  fetchAccessDetail: vi.fn(),
}));

vi.mock('../../api/privnoteAccess', () => ({
  fetchAccessNotes: api.fetchAccessNotes,
  fetchAccessDetail: api.fetchAccessDetail,
}));

const notes = {
  results: [{
    token: 'note-1', title: '第一链接', note_type: 'payment', created_at: '2026-09-12T10:00:00Z',
    view_count: 3, last_opened_at: null,
  }],
  page: 1, pages: 2, count: 2, retention_days: 30,
};
const detail = {
  note: notes.results[0],
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
});
afterEach(cleanup);

describe('AccessRecords', () => {
  it('从列表进入详情，隔离 audience/page 查询并可返回列表', async () => {
    renderRecords();
    await waitFor(() => expect(screen.getByText('第一链接')).toBeTruthy());

    fireEvent.click(screen.getByRole('button', { name: '查看记录' }));
    await waitFor(() => expect(screen.getByRole('heading', { name: '第一链接' })).toBeTruthy());
    expect(api.fetchAccessDetail).toHaveBeenLastCalledWith('note-1', 'customer', 1);

    fireEvent.change(screen.getByLabelText('记录范围'), { target: { value: 'all' } });
    await waitFor(() => expect(api.fetchAccessDetail).toHaveBeenLastCalledWith('note-1', 'all', 1));
    await waitFor(() => expect(screen.getByRole('button', { name: '下一页' })).toBeTruthy());
    fireEvent.click(screen.getByRole('button', { name: '下一页' }));
    await waitFor(() => expect(api.fetchAccessDetail).toHaveBeenLastCalledWith('note-1', 'all', 2));

    fireEvent.click(screen.getByRole('button', { name: '返回链接列表' }));
    expect(screen.getByLabelText('搜索标题或链接编号')).toBeTruthy();
  });

  it('搜索、类型筛选和分页各自形成列表查询条件', async () => {
    api.fetchAccessNotes.mockImplementation((q: string, type: string, page: number) => Promise.resolve({
      ...notes,
      results: q || type ? [{ ...notes.results[0], title: `${q}-${type}-${page}` }] : notes.results,
      page,
    }));
    renderRecords();
    await waitFor(() => expect(screen.getByText('第一链接')).toBeTruthy());

    fireEvent.change(screen.getByLabelText('搜索标题或链接编号'), { target: { value: '客户' } });
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
});
