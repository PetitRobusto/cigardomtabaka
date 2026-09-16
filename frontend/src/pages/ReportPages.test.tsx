// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import MonthlyBusinessReportPage from './MonthlyBusinessReportPage';
import ContributionRankingPage from './ContributionRankingPage';

const api = vi.hoisted(() => ({
  fetchMonthlyBusinessReport: vi.fn(),
  apiErrorMessage: (_error: unknown, fallback: string) => fallback,
  setMeta: vi.fn(),
}));

vi.mock('../api', () => api);
vi.mock('../hooks/usePageMeta', () => ({ usePageMeta: () => ({ setMeta: api.setMeta }) }));
vi.mock('../components/accounting/MonthlyBusinessReportPanel', () => ({ default: ({ month }: { month: string }) => <div>月报面板：{month}</div> }));
vi.mock('../components/accounting/ContributionRankingPanel', () => ({ default: () => <div>贡献排行面板</div> }));

afterEach(() => { cleanup(); vi.clearAllMocks(); });

function renderPage(page: React.ReactNode, path: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[path]}>{page}</MemoryRouter></QueryClientProvider>);
}

describe('独立月报页面', () => {
  it('从 URL 读取月份并加载月报', async () => {
    api.fetchMonthlyBusinessReport.mockResolvedValue({ period: { business_date_cutoff: '2026-08-31' } });
    renderPage(<MonthlyBusinessReportPage />, '/reports/monthly?month=2026-08');

    expect(await screen.findByText('月报面板：2026-08')).toBeTruthy();
    expect(api.fetchMonthlyBusinessReport).toHaveBeenCalledWith('2026-08');
    expect(screen.getByRole('heading', { name: '月度经营报告' })).toBeTruthy();
  });

  it('经营贡献排行保持同一月份并提供返回入口', async () => {
    api.fetchMonthlyBusinessReport.mockResolvedValue({ rankings: {} });
    renderPage(<ContributionRankingPage />, '/reports/contributions?month=2026-08');

    expect(await screen.findByText('贡献排行面板')).toBeTruthy();
    expect(api.fetchMonthlyBusinessReport).toHaveBeenCalledWith('2026-08');
    expect(screen.getByRole('link', { name: /返回月度经营报告/ }).getAttribute('href')).toBe('/reports/monthly?month=2026-08');
  });
});
