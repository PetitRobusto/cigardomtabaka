// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, useNavigate } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import AccountingDashboardPage from './AccountingDashboardPage';

const api = vi.hoisted(() => ({
  fetchAccountingDashboard: vi.fn(), fetchAccountingAccounts: vi.fn(), fetchAccountingActions: vi.fn(),
  fetchAccountingSummary: vi.fn(), fetchMonthlyProfit: vi.fn(), fetchReconciliations: vi.fn(),
  fetchAccountingExpenses: vi.fn(), fetchAccountingExchangeTransactions: vi.fn(), recordExpense: vi.fn(),
  exchangeToRub: vi.fn(), reverseExpense: vi.fn(), reverseExchange: vi.fn(), setMeta: vi.fn(),
  apiErrorMessage: (error: Error) => error.message,
  parseAccountingApiError: (error: Error) => ({ code: 'unknown', message: error.message }),
}));
vi.mock('../api', () => api);
vi.mock('../hooks/usePageMeta', () => ({ usePageMeta: () => ({ setMeta: api.setMeta }) }));
vi.mock('../components/sales/AccountingPanel', () => ({ default: () => null }));
vi.mock('../components/accounting/MonthlyProfitSummary', () => ({ default: () => null }));
vi.mock('../components/accounting/ExpenseDetails', () => ({ default: () => null }));
vi.mock('../components/accounting/ExchangeDetails', () => ({ default: () => null }));
vi.mock('../components/accounting/PurchaseAction', () => ({ default: () => null }));
vi.mock('../components/accounting/DividendRoundsAction', () => ({ default: () => <p>新分红轮次</p> }));
afterEach(cleanup);

function GuideNavigation() {
  const navigate = useNavigate();
  return <button onClick={() => navigate('/accounting', { state: { guideTourId: 'accounting-actions-exchange' } })}>启动换汇引导</button>;
}

describe('财务默认动作及刷新', () => {
  it('默认费用；成功更新相关查询不重置月份和输入；同页换汇引导仍能打开', async () => {
    vi.clearAllMocks();
    const accounts = [{ id: 1, name: '公司人民币', currency: 'CNY', custodian_id: null, is_active: true }];
    api.fetchAccountingDashboard.mockResolvedValue({ day1_status: 'completed', requires_day1: false, accounts,
      stats: { total_funds_cny: '100.00', inventory_book_cost_cny: '0.00', month_net_profit_cny: '0.00', accounts_receivable_cny: '0.00' } });
    api.fetchAccountingAccounts.mockResolvedValue(accounts);
    api.fetchAccountingActions.mockResolvedValue({ purchases: [], dividends: [] });
    api.fetchAccountingSummary.mockResolvedValue({});
    api.fetchMonthlyProfit.mockResolvedValue({ net_profit_cny: '0.00' });
    api.fetchReconciliations.mockResolvedValue([]);
    api.fetchAccountingExpenses.mockResolvedValue({ expenses: [] });
    api.fetchAccountingExchangeTransactions.mockResolvedValue([]);
    api.recordExpense.mockResolvedValue({ id: 3 });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 300000 } } });
    client.setQueryData(['dividend-rounds', 2], { old: true });
    render(<QueryClientProvider client={client}><MemoryRouter initialEntries={['/accounting']}><GuideNavigation /><AccountingDashboardPage /></MemoryRouter></QueryClientProvider>);
    await screen.findByRole('heading', { name: '记录经营费用' });
    expect(screen.getByRole('button', { name: '记录费用', pressed: true })).toBeTruthy();
    const month = screen.getByLabelText('报表月份') as HTMLSelectElement;
    const chosenMonth = month.options[1].value;
    fireEvent.change(month, { target: { value: chosenMonth } });
    fireEvent.change(screen.getByLabelText('金额（CNY）'), { target: { value: '10.00' } });
    fireEvent.change(screen.getByLabelText('备注'), { target: { value: '保留输入' } });
    fireEvent.click(within(document.querySelector('[data-guide="accounting-actions-expense"]') as HTMLElement).getByRole('button', { name: '记录费用' }));
    expect(api.recordExpense).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: '确认费用并入账' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    await waitFor(() => expect(api.fetchAccountingDashboard.mock.calls.length).toBeGreaterThan(1));
    expect((screen.getByLabelText('报表月份') as HTMLSelectElement).value).toBe(chosenMonth);
    expect(screen.getByDisplayValue('保留输入')).toBeTruthy();
    expect(screen.getByDisplayValue('10.00')).toBeTruthy();
    expect(client.getQueryState(['dividend-rounds', 2])?.isInvalidated).toBe(true);
    fireEvent.click(screen.getByRole('button', { name: '启动换汇引导' }));
    await waitFor(() => expect(screen.getByRole('button', { name: '换汇', pressed: true })).toBeTruthy());
    expect(document.querySelector('[data-guide="accounting-actions-exchange"]')).toBeTruthy();
  });
});
