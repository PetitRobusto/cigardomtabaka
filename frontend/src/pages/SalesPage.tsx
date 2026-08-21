import { useEffect, useMemo, useState } from 'react';
import { Plus, RefreshCw, Search, UserPlus, X } from 'lucide-react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { apiErrorMessage, createSalesOrder, fetchAccountingAccounts, fetchSalesOrders } from '../api';
import { usePageMeta } from '../hooks/usePageMeta';
import SalesOrderForm from '../components/sales/SalesOrderForm';
import SalesOrderWorkbench from '../components/sales/SalesOrderWorkbench';
import SalesCustomerModal from '../components/sales/SalesCustomerModal';
import SalesSectionNav from '../components/sales/SalesSectionNav';
import { activeSalesAmount, activeSalesProfit, formatCny, summarizeSalesOrders } from '../components/sales/salesState';
import { shanghaiBusinessDate, shiftIsoDate } from '../utils/businessDate';

type QuickDate = 'all' | 'today' | 'week' | 'month' | 'custom';

export default function SalesPage() {
  const { setMeta } = usePageMeta();
  const queryClient = useQueryClient();
  const [search, setSearch] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [quickDate, setQuickDate] = useState<QuickDate>('all');
  const [fulfillment, setFulfillment] = useState('');
  const [payment, setPayment] = useState('');
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [formError, setFormError] = useState('');
  const [creating, setCreating] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [customerModal, setCustomerModal] = useState<{ mode: 'create' | 'detail'; id: number | null } | null>(null);

  useEffect(() => { setMeta({ title: '销售订单工作台', breadcrumbs: [{ label: '首页', to: '/' }, { label: '销售订单' }] }); }, [setMeta]);

  const ordersQuery = useQuery({
    queryKey: ['sales-orders', search, dateFrom, dateTo, fulfillment, payment],
    queryFn: () => fetchSalesOrders({
      q: search || undefined,
      date_from: dateFrom || undefined,
      date_to: dateTo || undefined,
      fulfillment_status: fulfillment || undefined,
      payment_status: payment || undefined,
      limit: 100,
    }),
  });
  const accountsQuery = useQuery({ queryKey: ['accounting-accounts'], queryFn: fetchAccountingAccounts });
  const orders = useMemo(() => ordersQuery.data || [], [ordersQuery.data]);
  const summary = summarizeSalesOrders(orders);
  const totalDue = activeSalesAmount(orders);
  const totalProfit = activeSalesProfit(orders);

  const visibleSelectedId = selectedId && orders.some(order => order.id === selectedId) ? selectedId : null;

  const invalidateSales = () => {
    queryClient.invalidateQueries({ queryKey: ['sales-orders'] });
    queryClient.invalidateQueries({ queryKey: ['inventory'] });
    queryClient.invalidateQueries({ queryKey: ['accounting-dashboard'] });
    queryClient.invalidateQueries({ queryKey: ['accounting-accounts'] });
    queryClient.invalidateQueries({ queryKey: ['accounting-summary'] });
    queryClient.invalidateQueries({ queryKey: ['monthly-profit'] });
    queryClient.invalidateQueries({ queryKey: ['accounting-actions'] });
    queryClient.invalidateQueries({ queryKey: ['sales-customer'] });
  };
  const create = async (payload: Parameters<typeof createSalesOrder>[0]) => {
    setFormError('');
    setCreating(true);
    try {
      const order = await createSalesOrder(payload);
      invalidateSales();
      setSelectedId(order.id);
      setCreateOpen(false);
    } catch (error) {
      setFormError(apiErrorMessage(error));
      throw error;
    } finally {
      setCreating(false);
    }
  };
  const selectQuickDate = (value: QuickDate) => {
    setQuickDate(value);
    const today = shanghaiBusinessDate();
    if (value === 'all') { setDateFrom(''); setDateTo(''); return; }
    if (value === 'today') { setDateFrom(today); setDateTo(today); return; }
    const start = value === 'week' ? shiftIsoDate(today, -6) : `${today.slice(0, 8)}01`;
    setDateFrom(start);
    setDateTo(today);
  };

  return <div className="w-full animate-fade-in">
    <SalesSectionNav />
    <header className="mb-5 flex flex-col justify-between gap-4 sm:flex-row sm:items-end"><div><p className="text-[11px] font-bold uppercase tracking-[.12em] text-accent">Master-detail bench</p><h1 className="mt-1 font-display text-3xl font-semibold sm:text-4xl">销售订单工作台</h1><p className="mt-2 text-sm text-muted">订单、客户、FIFO 与收付款事实在同一主从工作台中推进。</p></div><div className="flex flex-wrap gap-2"><button type="button" onClick={() => setCustomerModal({ mode: 'create', id: null })} className="inline-flex items-center gap-1 rounded border border-border bg-white px-3 py-2 text-sm hover:border-gold"><UserPlus className="h-4 w-4" />新建客户</button><button type="button" onClick={() => { setCreateOpen(true); setFormError(''); }} className="inline-flex items-center gap-1 rounded bg-accent px-3 py-2 text-sm font-semibold text-white hover:bg-accent-hover"><Plus className="h-4 w-4" />新建销售单</button><button type="button" onClick={invalidateSales} className="inline-flex items-center gap-1 rounded border border-border bg-white px-3 py-2 text-sm hover:border-gold"><RefreshCw className="h-4 w-4" />刷新</button></div></header>

    <section className="mb-4 grid grid-cols-2 overflow-hidden rounded-md border border-border bg-white shadow-sm lg:grid-cols-4"><SummaryCell label="订单数" value={String(orders.length)} hint="当前筛选范围" /><SummaryCell label="应收合计" value={formatCny(totalDue)} hint="商品与客户承担费用" /><SummaryCell label="待收金额" value={formatCny(summary.unpaid.amount)} hint={String(summary.unpaid.count) + ' 笔未核销'} /><SummaryCell label="预计贡献利润" value={formatCny(totalProfit)} hint="FIFO 成本口径" /></section>

    <section className="mb-4 rounded-md border border-border bg-white p-3 shadow-sm">
      <div className="flex flex-wrap items-end gap-2">
        <label className="text-[11px] font-semibold text-muted">订单日期<input type="date" value={dateFrom} onChange={event => { setDateFrom(event.target.value); setQuickDate('custom'); }} className="mt-1 block rounded border border-border px-2 py-1.5 text-xs text-fg" /></label>
        <span className="pb-2 text-xs text-muted">至</span>
        <label className="text-[11px] font-semibold text-muted"><span className="sr-only">结束日期</span><input type="date" value={dateTo} onChange={event => { setDateTo(event.target.value); setQuickDate('custom'); }} className="mt-1 block rounded border border-border px-2 py-1.5 text-xs text-fg" /></label>
        <div className="flex flex-wrap gap-1">{([['all', '全部'], ['today', '今天'], ['week', '近 7 天'], ['month', '本月']] as [QuickDate, string][]).map(([value, label]) => <button key={value} type="button" onClick={() => selectQuickDate(value)} className={'rounded-full border px-3 py-1.5 text-xs font-semibold ' + (quickDate === value ? 'border-fg bg-fg text-white' : 'border-border hover:border-gold')}>{label}</button>)}</div>
        <label className="text-[11px] font-semibold text-muted">订单<select value={fulfillment} onChange={event => setFulfillment(event.target.value)} className="mt-1 block rounded border border-border bg-white px-2 py-1.5 text-xs text-fg"><option value="">全部订单</option><option value="draft">草稿</option><option value="confirmed">已确认</option><option value="shipped">已出库</option><option value="cancelled">已取消</option><option value="returned">已退货</option></select></label>
        <label className="text-[11px] font-semibold text-muted">付款<select value={payment} onChange={event => setPayment(event.target.value)} className="mt-1 block rounded border border-border bg-white px-2 py-1.5 text-xs text-fg"><option value="">全部付款</option><option value="unpaid">未收款</option><option value="paid">已收款</option><option value="refund_pending">待退款</option><option value="refunded">已退款</option></select></label>
        <div className="relative min-w-48 flex-1"><Search className="absolute left-3 top-2.5 h-4 w-4 text-muted" /><input value={search} onChange={event => setSearch(event.target.value)} placeholder="搜索订单号或客户" className="w-full rounded border border-border py-2 pl-9 pr-3 text-sm outline-none focus:border-gold" /></div>
      </div>
    </section>

    {ordersQuery.error && <p className="mb-4 rounded border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{apiErrorMessage(ordersQuery.error, '订单加载失败')}</p>}
    {accountsQuery.error && <p className="mb-4 rounded border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">资金账户加载失败，收款和人肉成本动作暂不可用。</p>}
    {ordersQuery.isLoading ? <p className="rounded border border-border bg-white px-5 py-16 text-center text-sm text-muted">加载订单工作台…</p> : <SalesOrderWorkbench orders={orders} selectedId={visibleSelectedId} accounts={accountsQuery.data || []} accountsError={accountsQuery.error ? apiErrorMessage(accountsQuery.error) : ''} onSelect={setSelectedId} onChanged={invalidateSales} onCustomer={id => setCustomerModal({ mode: 'detail', id })} />}

    {createOpen && <div role="dialog" aria-modal="true" aria-label="新建销售单" className="fixed inset-0 z-50 grid place-items-center bg-fg/30 p-3" onMouseDown={event => { if (event.target === event.currentTarget) setCreateOpen(false); }}><div className="relative max-h-[calc(100vh-1.5rem)] w-full max-w-4xl overflow-y-auto"><button type="button" aria-label="关闭新建销售单" onClick={() => setCreateOpen(false)} className="absolute right-5 top-5 z-10 text-muted"><X className="h-4 w-4" /></button><SalesOrderForm onSubmit={create} busy={creating} error={formError} /></div></div>}
    {customerModal && <SalesCustomerModal customerId={customerModal.id} mode={customerModal.mode} onClose={() => setCustomerModal(null)} onCreated={() => setCustomerModal(null)} />}
  </div>;
}

function SummaryCell({ label, value, hint }: { label: string; value: string; hint: string }) { return <div className="border-b border-r border-border p-4 last:border-r-0 lg:border-b-0"><span className="text-[11px] text-muted">{label}</span><strong className="mt-2 block font-mono text-xl">{value}</strong><small className="mt-1 block text-[10px] text-muted">{hint}</small></div>; }
