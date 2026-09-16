import { useEffect } from 'react';
import { ArrowLeft, RefreshCw } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { Link, useSearchParams } from 'react-router-dom';
import { apiErrorMessage, fetchMonthlyBusinessReport } from '../api';
import MonthlyBusinessReportPanel from '../components/accounting/MonthlyBusinessReportPanel';
import { usePageMeta } from '../hooks/usePageMeta';
import { moscowBusinessMonth, recentMoscowBusinessMonths } from '../utils/businessDate';

function selectedMonth(value: string | null): string {
  return value && /^\d{4}-\d{2}$/.test(value) ? value : moscowBusinessMonth();
}

export default function MonthlyBusinessReportPage() {
  const { setMeta } = usePageMeta();
  const [searchParams, setSearchParams] = useSearchParams();
  const month = selectedMonth(searchParams.get('month'));
  const monthOptions = recentMoscowBusinessMonths();
  const report = useQuery({ queryKey: ['monthly-business-report', month], queryFn: () => fetchMonthlyBusinessReport(month) });

  useEffect(() => { setMeta({ title: '月度经营报告', breadcrumbs: [{ label: '首页', to: '/' }, { label: '账务工作台', to: '/accounting' }, { label: '月度经营报告' }] }); }, [setMeta]);

  return <div className="w-full">
    <header className="mb-6 flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
      <div><Link to="/accounting" className="mb-2 inline-flex items-center gap-1 text-xs font-semibold text-accent hover:underline"><ArrowLeft className="h-3.5 w-3.5" />返回账务工作台</Link><h1 className="font-display text-3xl font-semibold tracking-tight sm:text-4xl">月度经营报告</h1><p className="mt-2 text-sm text-muted">财务应用中的收入、成本、回款与库存月度分析。</p></div>
      <div className="flex flex-wrap items-center gap-2">
        <label className="text-xs font-semibold text-muted"><span className="sr-only">选择月份</span><select data-guide="accounting-profit-month" aria-label="选择月份" value={month} onChange={event => setSearchParams({ month: event.target.value })} className="rounded border border-border bg-white px-3 py-2 text-sm font-normal text-fg hover:border-gold">{monthOptions.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label>
        <button type="button" onClick={() => report.refetch()} className="inline-flex items-center gap-1 rounded border border-border bg-white px-3 py-2 text-sm hover:border-gold"><RefreshCw className={`h-4 w-4 ${report.isFetching ? 'animate-spin' : ''}`} />刷新</button>
        {report.data && <span className="w-full text-right font-mono text-[11px] text-muted">数据截止 {report.data.period.business_date_cutoff}</span>}
      </div>
    </header>
    <MonthlyBusinessReportPanel
      report={report.data}
      error={report.isError ? apiErrorMessage(report.error, '经营月报加载失败') : undefined}
      month={month}
      onRetry={() => report.refetch()}
    />
  </div>;
}
