import { useEffect } from 'react';
import { ArrowLeft, RefreshCw } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { Link, useSearchParams } from 'react-router-dom';
import { apiErrorMessage, fetchMonthlyBusinessReport } from '../api';
import ContributionRankingPanel from '../components/accounting/ContributionRankingPanel';
import { usePageMeta } from '../hooks/usePageMeta';
import { moscowBusinessMonth, recentMoscowBusinessMonths } from '../utils/businessDate';

function selectedMonth(value: string | null): string {
  return value && /^\d{4}-\d{2}$/.test(value) ? value : moscowBusinessMonth();
}

export default function ContributionRankingPage() {
  const { setMeta } = usePageMeta();
  const [searchParams, setSearchParams] = useSearchParams();
  const month = selectedMonth(searchParams.get('month'));
  const report = useQuery({ queryKey: ['monthly-business-report', month], queryFn: () => fetchMonthlyBusinessReport(month) });

  useEffect(() => { setMeta({ title: '经营贡献排行', breadcrumbs: [{ label: '首页', to: '/' }, { label: '月度经营报告', to: `/reports/monthly?month=${month}` }, { label: '经营贡献排行' }] }); }, [month, setMeta]);

  return <div className="w-full">
    <header className="mb-6 flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
      <div><Link to={`/reports/monthly?month=${month}`} className="mb-2 inline-flex items-center gap-1 text-xs font-semibold text-accent hover:underline"><ArrowLeft className="h-3.5 w-3.5" />返回月度经营报告</Link><h1 className="font-display text-3xl font-semibold tracking-tight sm:text-4xl">经营贡献排行</h1><p className="mt-2 text-sm text-muted">按品牌、商品和客户查看销售贡献。</p></div>
      <div className="flex items-center gap-2">
        <label><span className="sr-only">选择月份</span><select aria-label="选择月份" value={month} onChange={event => setSearchParams({ month: event.target.value })} className="rounded border border-border bg-white px-3 py-2 text-sm text-fg hover:border-gold">{recentMoscowBusinessMonths().map(option => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label>
        <button type="button" onClick={() => report.refetch()} className="inline-flex items-center gap-1 rounded border border-border bg-white px-3 py-2 text-sm hover:border-gold"><RefreshCw className={`h-4 w-4 ${report.isFetching ? 'animate-spin' : ''}`} />刷新</button>
      </div>
    </header>
    {report.isError ? <section className="rounded-md border border-red-200 bg-white px-5 py-12 text-center shadow-sm" role="alert"><p className="text-sm text-red-700">{apiErrorMessage(report.error, '经营贡献排行加载失败')}</p><button type="button" onClick={() => report.refetch()} className="mt-4 rounded bg-accent px-4 py-2 text-sm font-semibold text-white">重新加载</button></section>
      : !report.data ? <div aria-label="排行加载中" className="space-y-4"><div className="h-64 animate-pulse rounded-md bg-[#EDE6DC]" /><div className="h-44 animate-pulse rounded-md bg-[#EDE6DC]" /><div className="h-72 animate-pulse rounded-md bg-[#EDE6DC]" /></div>
        : <ContributionRankingPanel report={report.data} />}
  </div>;
}
