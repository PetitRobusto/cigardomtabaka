import DateField from '../components/DateField';
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { ChartColumn, Plus, RefreshCw, Search, SlidersHorizontal, UserPlus, X } from 'lucide-react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { apiErrorMessage, createSalesOrder, fetchAccountingAccounts, fetchSalesOrderList } from '../api';
import { usePageMeta } from '../hooks/usePageMeta';
import SalesOrderForm from '../components/sales/SalesOrderForm';
import SalesOrderWorkbench from '../components/sales/SalesOrderWorkbench';
import SalesCustomerModal from '../components/sales/SalesCustomerModal';
import SalesSectionNav from '../components/sales/SalesSectionNav';
import { formatCny } from '../components/sales/salesState';
import { shanghaiBusinessDate, shiftIsoDate } from '../utils/businessDate';

type QuickDate = 'recent' | 'all' | 'today' | 'week' | 'month' | 'last_month' | 'custom';

interface MobileListContext {
  page: number;
  search: string;
  dateFrom: string;
  dateTo: string;
  quickDate: QuickDate;
  fulfillment: string;
  payment: string;
  reviewOnly: boolean;
  listKey: string;
  scrollY: number;
}

const isMobileList = () => window.matchMedia?.('(max-width: 1023px)').matches;

export default function SalesPage() {
  const location = useLocation();
  const [params] = useSearchParams();
  // A standalone order link has its own exact-order search. Leaving it opens a fresh list.
  return <SalesOrders key={location.state?.salesList ? 'list' : params.get('order') ?? 'list'} />;
}

function SalesOrders() {
  const { setMeta } = usePageMeta();
  const queryClient = useQueryClient();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const location = useLocation();
  const mobileList: MobileListContext | undefined = location.state?.salesList;
  const bench = useRef<HTMLDivElement>(null);
  const previousDetail = useRef(mobileList);
  const scrollToPage = useRef(false);
  const requestedId = Number(params.get('order'));
  const initialOrderId = Number.isSafeInteger(requestedId) && requestedId > 0 ? requestedId : null;
  const [page, setPage] = useState(mobileList?.page ?? 1);
  const [search, setSearch] = useState(() => mobileList?.search ?? (initialOrderId ? `SO-${String(initialOrderId).padStart(6, '0')}` : ''));
  const [dateFrom, setDateFrom] = useState(mobileList?.dateFrom ?? '');
  const [dateTo, setDateTo] = useState(mobileList?.dateTo ?? '');
  const [quickDate, setQuickDate] = useState<QuickDate>(mobileList?.quickDate ?? (initialOrderId ? 'all' : 'recent'));
  const [fulfillment, setFulfillment] = useState(mobileList?.fulfillment ?? (initialOrderId ? '' : 'non_cancelled'));
  const [payment, setPayment] = useState(mobileList?.payment ?? '');
  const [reviewOnly, setReviewOnly] = useState(mobileList?.reviewOnly ?? false);
  const [desktopSelection, setDesktopSelection] = useState<number | null>(mobileList ? null : initialOrderId);
  const selectedId = mobileList ? initialOrderId : desktopSelection;
  const setSelectedId = (id: number | null) => {
    setDesktopSelection(id);
    if (mobileList) {
      const next = new URLSearchParams(params);
      next.delete('order');
      void navigate({ search: next.toString() }, { replace: true, state: null });
    }
  };
  const returnToList = () => {
    if (mobileList) {
      void navigate(-1);
    } else {
      const next = new URLSearchParams(params);
      next.delete('order');
      void navigate({ search: next.toString() }, { replace: true });
    }
  };
  const selectOrder = (id: number | null, listPage = page) => {
    if (id === null || !isMobileList()) {
      setSelectedId(id);
      return;
    }
    const next = new URLSearchParams(params);
    next.set('order', String(id));
    const salesList: MobileListContext = {
      page: listPage, search, dateFrom, dateTo, quickDate, fulfillment, payment, reviewOnly,
      listKey: location.key, scrollY: window.scrollY,
    };
    void navigate({ search: next.toString() }, { state: { salesList } });
  };
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [statsOpen, setStatsOpen] = useState(false);
  const filterCount = [quickDate !== 'recent', fulfillment !== 'non_cancelled', payment, reviewOnly].filter(Boolean).length;
  const [formError, setFormError] = useState('');
  const [creating, setCreating] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [customerModal, setCustomerModal] = useState<{ mode: 'create' | 'detail'; id: number | null } | null>(null);

  useEffect(() => { setMeta({ title: '销售订单工作台', breadcrumbs: [{ label: '首页', to: '/' }, { label: '销售订单' }] }); }, [setMeta]);

  const ordersQuery = useQuery({
    queryKey: ['sales-orders', search, dateFrom, dateTo, fulfillment, payment, reviewOnly, page, quickDate === 'recent'],
    queryFn: () => fetchSalesOrderList({
      q: search || undefined,
      date_from: dateFrom || undefined,
      date_to: dateTo || undefined,
      fulfillment_status: fulfillment || undefined,
      payment_status: payment || undefined,
      limit: 20,
      page,
      review_only: reviewOnly ? 1 : 0,
      recent_only: quickDate === 'recent' ? 1 : 0,
    }),
    // 筛选变化时保留当前工作台，只在真正的首次加载显示整页骨架。
    placeholderData: previous => previous,
  });
  const accountsQuery = useQuery({ queryKey: ['accounting-accounts'], queryFn: fetchAccountingAccounts });
  const orders = useMemo(() => ordersQuery.data?.results || [], [ordersQuery.data]);
  const summary = ordersQuery.isPlaceholderData || ordersQuery.error ? undefined : ordersQuery.data;
  const stats = summary?.stats;
  const pendingCollection = summary?.pending_collection;
  const reviewCount = summary?.review_count;
  const visibleOrders = orders;
  const count = ordersQuery.data?.count ?? orders.length;
  const currentPage = ordersQuery.data?.page ?? page;
  const pages = ordersQuery.data?.pages ?? 1;
  const changePage = (next: number) => {
    scrollToPage.current = Boolean(isMobileList());
    setSelectedId(null);
    setPage(next);
  };

  useLayoutEffect(() => {
    if (ordersQuery.isLoading || ordersQuery.isPlaceholderData) return;
    const from = previousDetail.current;
    previousDetail.current = mobileList;
    if (mobileList && bench.current && isMobileList()) {
      if (from !== mobileList) bench.current.scrollIntoView({ block: 'start' });
    } else if (from?.listKey === location.key) {
      window.scrollTo(0, from.scrollY);
    } else if (scrollToPage.current) {
      bench.current?.scrollIntoView({ block: 'start' });
    }
    scrollToPage.current = false;
  }, [mobileList, location.key, page, ordersQuery.isLoading, ordersQuery.isPlaceholderData]);

  const visibleSelectedId = selectedId && visibleOrders.some(order => order.id === selectedId) ? selectedId : null;

  const invalidateSales = () => {
    queryClient.invalidateQueries({ queryKey: ['sales-orders'] });
    queryClient.invalidateQueries({ queryKey: ['preorder-source'] });
    queryClient.invalidateQueries({ queryKey: ['inventory'] });
    queryClient.invalidateQueries({ queryKey: ['accounting-dashboard'] });
    queryClient.invalidateQueries({ queryKey: ['accounting-accounts'] });
    queryClient.invalidateQueries({ queryKey: ['accounting-summary'] });
    queryClient.invalidateQueries({ queryKey: ['monthly-profit'] });
    queryClient.invalidateQueries({ queryKey: ['accounting-actions'] });
    queryClient.invalidateQueries({ queryKey: ['sales-customer'] });
    queryClient.invalidateQueries({ queryKey: ['sales-customers'] });
    queryClient.invalidateQueries({ queryKey: ['sales-receipts'] });
    queryClient.invalidateQueries({ queryKey: ['dividend-rounds'] });
  };
  const create = async (payload: Parameters<typeof createSalesOrder>[0]) => {
    setFormError('');
    setCreating(true);
    try {
      const order = await createSalesOrder(payload);
      invalidateSales();
      setPage(1);
      selectOrder(order.id, 1);
      setCreateOpen(false);
    } catch (error) {
      setFormError(apiErrorMessage(error));
      throw error;
    } finally {
      setCreating(false);
    }
  };
  const selectQuickDate = (value: QuickDate) => {
    setSelectedId(null);
    setPage(1);
    setQuickDate(value);
    const today = shanghaiBusinessDate();
    if (value === 'all' || value === 'recent') { setDateFrom(''); setDateTo(''); return; }
    if (value === 'today') { setDateFrom(today); setDateTo(today); return; }
    if (value === 'last_month') {
      const end = shiftIsoDate(`${today.slice(0, 8)}01`, -1);
      setDateFrom(`${end.slice(0, 8)}01`);
      setDateTo(end);
      return;
    }
    const start = value === 'week' ? shiftIsoDate(today, -6) : `${today.slice(0, 8)}01`;
    setDateFrom(start);
    setDateTo(today);
  };

  return <div className="w-full">
    <div className={visibleSelectedId ? 'hidden lg:block' : undefined}>
      <SalesSectionNav />
      <header className="mb-3 flex flex-wrap items-center justify-between gap-2 lg:mb-5">
        <h1 className="font-display text-2xl font-semibold lg:text-4xl">销售订单</h1>
        <div className="flex items-center gap-2">
          <button type="button" aria-label="新建客户" onClick={() => setCustomerModal({ mode: 'create', id: null })} className="inline-flex min-h-11 items-center gap-1 rounded border border-border bg-white px-3 text-sm"><UserPlus className="h-4 w-4" /><span className="hidden lg:inline">新建客户</span></button>
          <button type="button" onClick={() => { setCreateOpen(true); setFormError(''); }} className="inline-flex min-h-11 items-center gap-1 rounded bg-accent px-3 text-sm font-semibold text-white"><Plus className="h-4 w-4" />新建销售单</button>
          <button type="button" aria-label="刷新" onClick={invalidateSales} className="inline-flex min-h-11 items-center gap-1 rounded border border-border bg-white px-3 text-sm"><RefreshCw className="h-4 w-4" /><span className="hidden lg:inline">刷新</span></button>
        </div>
      </header>



      <div className="mb-3 flex items-center gap-2">
        <div className="relative min-w-0 flex-1"><Search className="absolute left-3 top-3.5 h-4 w-4 text-muted" /><input value={search} onChange={event => { setSelectedId(null); setPage(1); setSearch(event.target.value); }} aria-label="搜索订单号或客户" placeholder="搜索订单号或客户" className="min-h-11 w-full rounded border border-border py-2 pl-9 pr-3 text-sm outline-none focus:border-gold" /></div>
        <button type="button" aria-expanded={filtersOpen} aria-controls="sales-filters" onClick={() => setFiltersOpen(open => !open)} className="flex min-h-11 items-center gap-1 rounded border border-border bg-white px-3 text-sm lg:hidden"><SlidersHorizontal className="h-4 w-4" />筛选{filterCount > 0 && <span>（{filterCount}）</span>}</button>
        <button type="button" aria-expanded={statsOpen} aria-controls="sales-stats" onClick={() => setStatsOpen(open => !open)} className="flex min-h-11 items-center gap-1 rounded border border-border bg-white px-3 text-sm lg:hidden"><ChartColumn className="h-4 w-4" />统计</button>
      </div>
      <section id="sales-stats" className={`mb-3 grid-cols-2 overflow-hidden rounded-md border border-border bg-white shadow-sm lg:grid lg:grid-cols-4 ${statsOpen ? 'grid' : 'hidden'}`}><SummaryCell label="订单数" value={stats ? String(stats.order_count) : '—'} hint={quickDate === 'recent' ? '最近 60 条，按创建时间倒序' : '当前筛选范围'} /><SummaryCell label="应收合计" value={stats ? formatCny(stats.amount_due_cny) : '—'} hint="当前筛选范围" /><SummaryCell label="待收金额" value={pendingCollection ? formatCny(pendingCollection.amount_cny) : '—'} hint={`${pendingCollection?.order_count ?? '—'} 笔已确认未收款订单`} /><SummaryCell label="预计贡献利润" value={stats ? formatCny(stats.contribution_profit_cny) : '—'} hint="按商品成本估算" /></section>
      <section id="sales-filters" className={`mb-4 rounded-md border border-border bg-white p-3 shadow-sm lg:block ${filtersOpen ? '' : 'hidden'}`}>
        <div className="flex flex-wrap items-end gap-2">
          <label className="text-[11px] font-semibold text-muted">订单日期<DateField value={dateFrom} onChange={event => { setSelectedId(null); setPage(1); setDateFrom(event.target.value); setQuickDate('custom'); }} className="mt-1 block rounded border border-border px-2 py-1.5 text-xs text-fg" /></label>
          <span className="pb-2 text-xs text-muted">至</span>
          <label className="text-[11px] font-semibold text-muted"><span className="sr-only">结束日期</span><DateField value={dateTo} onChange={event => { setSelectedId(null); setPage(1); setDateTo(event.target.value); setQuickDate('custom'); }} className="mt-1 block rounded border border-border px-2 py-1.5 text-xs text-fg" /></label>
          <div className="flex flex-wrap gap-1">{([['recent', '最近 60 条'], ['all', '全部'], ['today', '今天'], ['week', '近 7 天'], ['month', '本月'], ['last_month', '上个月']] as [QuickDate, string][]).map(([value, label]) => <button key={value} type="button" onClick={() => selectQuickDate(value)} className={'rounded-full border px-3 py-1.5 text-xs font-semibold ' + (quickDate === value ? 'border-fg bg-fg text-white' : 'border-border hover:border-gold')}>{label}</button>)}</div>
          <label className="text-[11px] font-semibold text-muted">订单<select aria-label="订单" value={fulfillment} onChange={event => { setSelectedId(null); setPage(1); setFulfillment(event.target.value); }} className="mt-1 block rounded border border-border bg-white px-2 py-1.5 text-xs text-fg"><option value="non_cancelled">未取消订单</option><option value="">全部订单</option><option value="draft">草稿</option><option value="confirmed">已确认</option><option value="shipped">已出库</option><option value="cancelled">已取消</option><option value="returned">已退货</option></select></label>
          <label className="text-[11px] font-semibold text-muted">付款<select aria-label="付款" value={payment} onChange={event => { setSelectedId(null); setPage(1); setPayment(event.target.value); }} className="mt-1 block rounded border border-border bg-white px-2 py-1.5 text-xs text-fg"><option value="">全部付款</option><option value="unpaid">未收款</option><option value="partial">部分收款</option><option value="paid">已收款</option><option value="refund_pending">待退款</option><option value="refunded">已退款</option></select></label>
          <button type="button" onClick={() => { setSelectedId(null); setPage(1); setReviewOnly(value => !value); }} className={`rounded-full border px-3 py-1.5 text-xs font-semibold ${reviewOnly ? 'border-accent bg-accent text-white' : reviewCount ? 'border-orange-200 bg-orange-50 text-orange-800' : 'border-border text-muted'}`}>待核实 <span className="font-mono">{reviewCount ?? '—'}</span></button>

        </div>
      </section>
    </div>
    {ordersQuery.error && <p className="mb-4 rounded border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{apiErrorMessage(ordersQuery.error, '订单加载失败')}</p>}
    {accountsQuery.error && <p className="mb-4 rounded border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">资金账户加载失败，收款和人肉成本动作暂不可用。</p>}
    <div className="flex flex-col gap-3">
      <div ref={bench} className="order-1 scroll-mt-20">
        <SalesOrderWorkbench key={mobileList ? 'mobile-detail' : 'list'} loading={ordersQuery.isLoading || ordersQuery.isPlaceholderData} orders={ordersQuery.isPlaceholderData || ordersQuery.error ? [] : visibleOrders} selectedId={ordersQuery.isPlaceholderData || ordersQuery.error ? null : visibleSelectedId} accounts={accountsQuery.data || []} accountsError={accountsQuery.error ? apiErrorMessage(accountsQuery.error) : ''} onSelect={selectOrder} onHistoryBack={initialOrderId ? returnToList : undefined} onChanged={invalidateSales} onCustomer={id => setCustomerModal({ mode: 'detail', id })} />
      </div>
      <nav aria-label="订单分页" className={`${visibleSelectedId ? 'hidden lg:flex' : 'flex'} order-2 flex-col items-stretch lg:order-0 lg:flex-row lg:flex-wrap lg:items-center lg:justify-between gap-3 rounded border border-border bg-cream px-4 py-3 text-xs text-muted`}>
        <span aria-live="polite">{ordersQuery.error ? `第 ${currentPage} 页加载失败` : `共 ${count} 条 · 每页 20 条 · 第 ${currentPage} / ${pages} 页`}</span>
        <div className="flex gap-2 [&>button]:min-h-11 [&>button]:flex-1 lg:[&>button]:min-h-0 lg:[&>button]:flex-none">
          <button type="button" disabled={ordersQuery.isFetching || currentPage <= 1} onClick={() => changePage(currentPage - 1)} className="rounded border border-border bg-white px-3 py-2 text-xs font-semibold hover:border-gold disabled:opacity-40">上一页</button>
          <button type="button" disabled={ordersQuery.isFetching || Boolean(ordersQuery.error) || currentPage >= pages} onClick={() => changePage(currentPage + 1)} className="rounded border border-border bg-white px-3 py-2 text-xs font-semibold hover:border-gold disabled:opacity-40">下一页</button>
          {ordersQuery.error && <button type="button" onClick={() => void ordersQuery.refetch()} disabled={ordersQuery.isFetching} className="rounded border border-border bg-white px-3 py-2 text-xs font-semibold disabled:opacity-40">重试</button>}
        </div>
      </nav>
    </div>

    {createOpen && <div role="dialog" aria-modal="true" aria-label="新建销售单" className="fixed inset-0 z-50 grid place-items-center bg-fg/30 p-3" onMouseDown={event => { if (event.target === event.currentTarget) setCreateOpen(false); }}><div className="relative max-h-[calc(100vh-1.5rem)] w-full max-w-4xl overflow-y-auto"><button type="button" aria-label="关闭新建销售单" onClick={() => setCreateOpen(false)} className="absolute right-5 top-5 z-10 text-muted"><X className="h-4 w-4" /></button><SalesOrderForm onSubmit={create} busy={creating} error={formError} /></div></div>}
    {customerModal && <SalesCustomerModal customerId={customerModal.id} mode={customerModal.mode} onClose={() => setCustomerModal(null)} onCreated={() => setCustomerModal(null)} />}
  </div>;
}

function SummaryCell({ label, value, hint }: { label: string; value: string; hint: string }) { return <div className="border-b border-r border-border p-4 last:border-r-0 lg:border-b-0"><span className="text-[11px] text-muted">{label}</span><strong className="mt-2 block font-mono text-xl">{value}</strong><small className="mt-1 block text-[10px] text-muted">{hint}</small></div>; }
