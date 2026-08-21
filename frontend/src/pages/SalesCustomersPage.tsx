import { useEffect, useMemo, useState } from 'react';
import { Plus, RefreshCw, Search, UserRound, UsersRound } from 'lucide-react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { apiErrorMessage, fetchSalesCustomer, fetchSalesCustomerDirectory } from '../api';
import SalesCustomerModal from '../components/sales/SalesCustomerModal';
import SalesOrderStatusTags from '../components/sales/SalesOrderStatusTags';
import SalesSectionNav from '../components/sales/SalesSectionNav';
import { formatCny } from '../components/sales/salesState';
import { usePageMeta } from '../hooks/usePageMeta';
import type { CustomerResult } from '../types';
import { formatShanghaiDateTime } from '../utils/businessDate';

type ActivityFilter = 'all' | 'with_orders' | 'without_orders' | 'recent';

const activityFilters: { value: ActivityFilter; label: string }[] = [
  { value: 'all', label: '全部客户' },
  { value: 'with_orders', label: '有订单' },
  { value: 'without_orders', label: '暂无订单' },
  { value: 'recent', label: '近 30 天' },
];

function customerActivity(customer: CustomerResult): { label: string; tone: string } {
  if (!customer.order_count) return { label: '暂无订单', tone: 'border-slate-200 bg-slate-50 text-slate-600' };
  if (customer.last_order_at && Date.now() - new Date(customer.last_order_at).getTime() <= 30 * 24 * 60 * 60 * 1000) {
    return { label: '近期活跃', tone: 'border-emerald-200 bg-emerald-50 text-emerald-700' };
  }
  return { label: '有历史订单', tone: 'border-amber-200 bg-amber-50 text-amber-800' };
}

export default function SalesCustomersPage() {
  const { setMeta } = usePageMeta();
  const queryClient = useQueryClient();
  const [search, setSearch] = useState('');
  const [activity, setActivity] = useState<ActivityFilter>('all');
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [modal, setModal] = useState<{ mode: 'create' | 'detail'; id: number | null } | null>(null);

  useEffect(() => {
    setMeta({ title: '客户管理', breadcrumbs: [{ label: '首页', to: '/' }, { label: '订单', to: '/sales' }, { label: '客户管理' }] });
  }, [setMeta]);

  const directoryQuery = useQuery({
    queryKey: ['sales-customers', search, activity],
    queryFn: () => fetchSalesCustomerDirectory({ q: search || undefined, activity, limit: 100 }),
  });
  const customers = useMemo(() => directoryQuery.data?.results || [], [directoryQuery.data]);
  const visibleSelectedId = selectedId && customers.some(customer => customer.id === selectedId)
    ? selectedId
    : customers[0]?.id ?? null;
  const detailQuery = useQuery({
    queryKey: ['sales-customer', visibleSelectedId],
    queryFn: () => fetchSalesCustomer(visibleSelectedId!),
    enabled: Boolean(visibleSelectedId),
  });

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ['sales-customers'] });
    queryClient.invalidateQueries({ queryKey: ['sales-customer'] });
  };

  return <div className="w-full animate-fade-in">
    <SalesSectionNav />
    <header className="mb-5 flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
      <div><p className="text-[11px] font-bold uppercase tracking-[.12em] text-accent">Customer directory</p><h1 className="mt-1 font-display text-3xl font-semibold sm:text-4xl">客户管理</h1><p className="mt-2 text-sm text-muted">统一查看客户资料、订单活跃度和累计有效订单金额。</p></div>
      <div className="flex gap-2"><button type="button" onClick={refresh} className="inline-flex items-center gap-1 rounded border border-border bg-white px-3 py-2 text-sm hover:border-gold"><RefreshCw className="h-4 w-4" />刷新</button><button type="button" onClick={() => setModal({ mode: 'create', id: null })} className="inline-flex items-center gap-1 rounded bg-accent px-3 py-2 text-sm font-semibold text-white hover:bg-accent-hover"><Plus className="h-4 w-4" />新建客户</button></div>
    </header>

    <CustomerStats stats={directoryQuery.data?.stats} />

    <section className="mb-4 rounded-md border border-border bg-white p-3 shadow-sm">
      <div className="flex flex-wrap items-center gap-2" role="toolbar" aria-label="客户筛选">
        <div className="relative min-w-56 flex-1"><Search className="absolute left-3 top-2.5 h-4 w-4 text-muted" /><input type="search" value={search} onChange={event => setSearch(event.target.value)} placeholder="搜索客户姓名或电话" className="w-full rounded border border-border py-2 pl-9 pr-3 text-sm outline-none focus:border-gold" /></div>
        <div className="flex flex-wrap gap-1" role="group" aria-label="客户活跃度">{activityFilters.map(filter => <button key={filter.value} type="button" aria-pressed={activity === filter.value} onClick={() => setActivity(filter.value)} className={`rounded-full border px-3 py-1.5 text-xs font-semibold ${activity === filter.value ? 'border-fg bg-fg text-white' : 'border-border text-muted hover:border-gold hover:text-fg'}`}>{filter.label}</button>)}</div>
      </div>
    </section>

    {directoryQuery.error && <p className="mb-4 rounded border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{apiErrorMessage(directoryQuery.error, '客户目录加载失败')}</p>}
    <section className="grid min-h-[480px] gap-4 lg:grid-cols-[minmax(0,1.35fr)_minmax(340px,.65fr)]">
      <div className="overflow-hidden rounded-md border border-border bg-white shadow-sm">
        <div className="grid grid-cols-[minmax(0,1fr)_auto] border-b border-border bg-[#FCFBF9] px-4 py-2 text-[10px] font-bold uppercase tracking-wide text-muted"><span>客户 / 最近订单</span><span>累计有效订单</span></div>
        {directoryQuery.isLoading && <p className="px-5 py-20 text-center text-sm text-muted">加载客户目录…</p>}
        {!directoryQuery.isLoading && !customers.length && <div className="px-5 py-20 text-center"><UsersRound className="mx-auto h-8 w-8 text-border" /><p className="mt-3 text-sm font-semibold">没有符合条件的客户</p><p className="mt-1 text-xs text-muted">调整搜索或筛选条件后重试。</p></div>}
        {customers.map(customer => <CustomerRow key={customer.id} customer={customer} selected={visibleSelectedId === customer.id} onSelect={() => setSelectedId(customer.id)} />)}
      </div>

      <div className="min-w-0">
        {!visibleSelectedId && <div className="grid h-full min-h-72 place-items-center rounded-md border border-dashed border-border bg-white/60 p-8 text-center"><div><UserRound className="mx-auto h-9 w-9 text-border" /><p className="mt-3 text-sm font-semibold">选择一位客户</p><p className="mt-1 text-xs text-muted">查看资料、订单统计和最近订单。</p></div></div>}
        {visibleSelectedId && detailQuery.isLoading && <p className="rounded-md border border-border bg-white px-5 py-20 text-center text-sm text-muted">加载客户资料…</p>}
        {visibleSelectedId && detailQuery.error && <p className="rounded border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{apiErrorMessage(detailQuery.error, '客户资料加载失败')}</p>}
        {detailQuery.data && <CustomerDetail customer={detailQuery.data} onEdit={() => setModal({ mode: 'detail', id: detailQuery.data.id })} />}
      </div>
    </section>

    {modal && <SalesCustomerModal customerId={modal.id} mode={modal.mode} onClose={() => setModal(null)} onCreated={customer => { setSelectedId(customer.id); setModal(null); }} />}
  </div>;
}

function CustomerStats({ stats }: { stats?: { customer_count: number; with_orders_count: number; recent_customer_count: number; total_amount_cny: number } }) {
  const items = [
    ['客户总数', stats ? String(stats.customer_count) : '—', '当前有效客户'],
    ['有订单客户', stats ? String(stats.with_orders_count) : '—', '至少一笔历史订单'],
    ['近 30 天活跃', stats ? String(stats.recent_customer_count) : '—', '最近创建过订单'],
    ['累计有效订单', stats ? formatCny(stats.total_amount_cny) : '—', '已确认及已出库'],
  ];
  return <section className="mb-4 grid grid-cols-2 overflow-hidden rounded-md border border-border bg-white shadow-sm lg:grid-cols-4">{items.map(([label, value, hint]) => <div key={label} className="border-b border-r border-border p-4 last:border-r-0 lg:border-b-0"><span className="text-[11px] text-muted">{label}</span><strong className="mt-2 block font-mono text-xl">{value}</strong><small className="mt-1 block text-[10px] text-muted">{hint}</small></div>)}</section>;
}

function CustomerRow({ customer, selected, onSelect }: { customer: CustomerResult; selected: boolean; onSelect: () => void }) {
  const activity = customerActivity(customer);
  return <button type="button" onClick={onSelect} className={`grid w-full grid-cols-[minmax(0,1fr)_auto] gap-4 border-b border-border px-4 py-3 text-left last:border-0 ${selected ? 'bg-[#F5EFE8] shadow-[inset_3px_0_0_#7A1F2E]' : 'hover:bg-[#FCFBF9]'}`}>
    <span className="min-w-0"><span className="flex flex-wrap items-center gap-2"><strong className="truncate text-sm">{customer.name}</strong><small className={`rounded-full border px-2 py-0.5 text-[9px] font-bold ${activity.tone}`}>{activity.label}</small></span><small className="mt-1 block truncate text-xs text-muted">{customer.phone || '未填写电话'} · {customer.last_order_at ? `最近订单 ${formatShanghaiDateTime(customer.last_order_at).slice(0, 10)}` : '暂无订单'}</small><small className="mt-1 block text-[10px] text-muted">{customer.order_count || 0} 笔历史订单</small></span>
    <span className="text-right"><strong className="block font-mono text-sm">{formatCny(customer.total_amount_cny || 0)}</strong><small className="mt-1 block text-[10px] text-muted">累计有效订单</small></span>
  </button>;
}

function CustomerDetail({ customer, onEdit }: { customer: Awaited<ReturnType<typeof fetchSalesCustomer>>; onEdit: () => void }) {
  return <aside className="overflow-hidden rounded-md border border-border bg-white shadow-sm">
    <div className="border-b border-border p-5"><div className="flex items-start justify-between gap-3"><div><p className="font-mono text-[10px] uppercase tracking-wide text-muted">#{customer.id} · 客户资料</p><h2 className="mt-1 font-display text-2xl font-semibold">{customer.name}</h2><p className="mt-1 text-sm text-muted">{customer.phone || '未填写电话'}</p></div><button type="button" onClick={onEdit} className="rounded border border-border px-3 py-1.5 text-xs font-semibold hover:border-gold">编辑资料</button></div></div>
    <div className="p-5"><div className="grid grid-cols-3 overflow-hidden rounded border border-border text-center"><DetailMetric label="历史订单" value={String(customer.order_count)} /><DetailMetric label="有效订单" value={String(customer.active_order_count)} /><DetailMetric label="累计应收" value={formatCny(customer.total_amount_cny)} /></div>
      <div className="mt-5"><h3 className="text-xs font-bold uppercase tracking-wide">最近订单</h3><div className="mt-2 overflow-hidden rounded border border-border">{customer.recent_orders.length ? customer.recent_orders.map(order => <div key={order.id} className="grid grid-cols-[minmax(0,1fr)_auto] gap-3 border-b border-border px-3 py-3 last:border-0"><span className="min-w-0"><strong className="font-mono text-xs">{order.order_number}</strong><small className="mt-1 block text-[10px] text-muted">{order.created_at ? formatShanghaiDateTime(order.created_at).slice(0, 10) : '—'}</small><span className="mt-1.5 flex"><SalesOrderStatusTags order={order} compact /></span></span><strong className="font-mono text-xs">{formatCny(order.amount_due_cny)}</strong></div>) : <p className="px-3 py-10 text-center text-sm text-muted">暂无历史订单</p>}</div></div>
    </div>
  </aside>;
}

function DetailMetric({ label, value }: { label: string; value: string }) {
  return <div className="border-r border-border p-3 last:border-0"><span className="block text-[10px] text-muted">{label}</span><strong className="mt-1 block font-mono text-sm">{value}</strong></div>;
}
