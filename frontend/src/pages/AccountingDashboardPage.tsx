import { useEffect, useMemo, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { apiErrorMessage, fetchAccountingAccounts, fetchAccountingDashboard, fetchAccountingSummary, fetchMonthlyProfit, fetchReconciliations } from '../api';
import { usePageMeta } from '../hooks/usePageMeta';
import AccountingPanel from '../components/sales/AccountingPanel';
import { formatCny, formatSignedCny } from '../components/sales/salesState';
import { dashboardDay1Action, dashboardRegionStates, dashboardStatDisplay } from './businessRoutes';

export default function AccountingDashboardPage() {
  const { setMeta } = usePageMeta();
  const queryClient = useQueryClient();
  const [month, setMonth] = useState(new Date().toISOString().slice(0, 7));
  useEffect(() => { setMeta({ title: '账务工作台', breadcrumbs: [{ label: '首页', to: '/' }, { label: '账务工作台' }] }); }, [setMeta]);
  const dashboard = useQuery({ queryKey: ['accounting-dashboard'], queryFn: fetchAccountingDashboard });
  const accounts = useQuery({ queryKey: ['accounting-accounts'], queryFn: fetchAccountingAccounts, enabled: Boolean(dashboard.data && !dashboard.data.requires_day1) });
  const summary = useQuery({ queryKey: ['accounting-summary'], queryFn: () => fetchAccountingSummary(new Date().toISOString().slice(0, 10)), enabled: Boolean(dashboard.data && !dashboard.data.requires_day1) });
  const profit = useQuery({ queryKey: ['monthly-profit', month], queryFn: () => fetchMonthlyProfit(month), enabled: Boolean(dashboard.data && !dashboard.data.requires_day1) });
  const reconciliations = useQuery({ queryKey: ['reconciliations'], queryFn: fetchReconciliations, enabled: Boolean(dashboard.data && !dashboard.data.requires_day1) });
  // Refresh the dashboard snapshot and its supporting action panels together.
  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ['accounting-dashboard'] });
    queryClient.invalidateQueries({ queryKey: ['accounting-accounts'] });
    queryClient.invalidateQueries({ queryKey: ['accounting-summary'] });
    queryClient.invalidateQueries({ queryKey: ['monthly-profit'] });
    queryClient.invalidateQueries({ queryKey: ['reconciliations'] });
  };
  const data = dashboard.data;
  const latest = useMemo(() => data?.reconciliation.latest || [], [data]);
  const regionStates = dashboardRegionStates({
    accounts: { isError: accounts.isError, hasData: Boolean(accounts.data) },
    summary: { isError: summary.isError, hasData: Boolean(summary.data) },
    profit: { isError: profit.isError, hasData: Boolean(profit.data) },
    reconciliation: { isError: reconciliations.isError, hasData: Boolean(reconciliations.data) },
  });
  return <div className="w-full animate-fade-in">
    <header className="mb-6 flex flex-col justify-between gap-4 sm:flex-row sm:items-end"><div><p className="text-[11px] font-bold uppercase tracking-[.12em] text-accent">Accounting desk</p><h1 className="mt-1 font-display text-3xl font-semibold tracking-tight sm:text-4xl">账务工作台</h1><p className="mt-2 text-sm text-muted">资金、库存成本、利润和对账的真实快照。</p></div><div className="flex gap-2"><input type="month" value={month} onChange={event => setMonth(event.target.value)} className="rounded border border-border bg-white px-3 py-2 text-sm" /><button type="button" onClick={refresh} className="inline-flex items-center gap-1 rounded border border-border bg-white px-3 py-2 text-sm hover:border-gold"><RefreshCw className="h-4 w-4" />刷新</button></div></header>
    {dashboard.error && <div className="mb-5 rounded border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{apiErrorMessage(dashboard.error, '账务数据加载失败')}</div>}
    {data && <><section className="mb-7 grid gap-3 sm:grid-cols-2 xl:grid-cols-4"><Stat label="人民币资金" value={moneyStat(data.stats.cny_funds_total)} /><Stat label="库存成本" value={moneyStat(data.stats.inventory_book_cost_cny)} /><Stat label="本月利润" value={signedMoneyStat(data.stats.month_net_profit_cny)} tone="text-success" /><Stat label="待收订单" value={moneyStat(data.stats.accounts_receivable_cny)} /></section>{data.requires_day1 ? <Day1Card status={data.day1_status} /> : <AccountingPanel
      accounts={regionStates.accounts === 'ready' ? accounts.data : undefined}
      summary={regionStates.summary === 'ready' ? summary.data : undefined}
      profit={regionStates.profit === 'ready' ? profit.data : undefined}
      reconciliations={regionStates.reconciliation === 'ready' ? reconciliations.data : undefined}
      accountsError={regionStates.accounts === 'error' ? apiErrorMessage(accounts.error, '资金账户数据加载失败') : undefined}
      summaryError={regionStates.summary === 'error' ? apiErrorMessage(summary.error, '库存与账务摘要加载失败') : undefined}
      profitError={regionStates.profit === 'error' ? apiErrorMessage(profit.error, '月度利润加载失败') : undefined}
      reconciliationError={regionStates.reconciliation === 'error' ? apiErrorMessage(reconciliations.error, '账户对账加载失败') : undefined}
      month={month} onChanged={refresh} showStats={false} />}</>}
  </div>;
}

function moneyStat(value: string | null): string { return dashboardStatDisplay(value == null ? null : formatCny(value)); }
function signedMoneyStat(value: string | null): string { return dashboardStatDisplay(value == null ? null : formatSignedCny(value)); }
function Stat({ label, value, tone = '' }: { label: string; value: string; tone?: string }) { return <div className="rounded-md border border-border bg-white p-4 shadow-sm"><p className="text-[11px] uppercase tracking-wider text-muted">{label}</p><p className={`mt-2 font-mono text-2xl font-semibold ${tone}`}>{value}</p></div>; }
function Day1Card({ status }: { status: string }) {
  const action = dashboardDay1Action(status);
  if (!action) return null;
  return <section className="rounded-md border border-gold/40 bg-[#FFFAF3] p-6 shadow-sm"><p className="text-[11px] font-bold uppercase tracking-wider text-accent">Day 1</p><h2 className="mt-2 font-display text-xl font-semibold">先完成一次性初始化</h2><p className="mt-2 max-w-xl text-sm text-muted">初始化完成后，资金、库存成本和利润才会显示为真实数据。</p><a href="/accounting/day1" className="mt-4 inline-flex rounded bg-accent px-4 py-2 text-sm font-semibold text-white">{action === 'continue' ? '继续初始化' : '开始初始化'}</a></section>;
}
