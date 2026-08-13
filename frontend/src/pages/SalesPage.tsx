import { useMemo, useState, useEffect } from 'react';
import { RefreshCw, Search } from 'lucide-react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { apiErrorMessage, createSalesOrder, fetchAccountingAccounts, fetchSalesOrders } from '../api';
import { usePageMeta } from '../hooks/usePageMeta';
import type { SalesOrder } from '../types';
import SalesOrderForm from '../components/sales/SalesOrderForm';
import SalesOrderCard from '../components/sales/SalesOrderCard';
import { formatCny, summarizeSalesOrders } from '../components/sales/salesState';

export default function SalesPage() {
  const { setMeta } = usePageMeta();
  const queryClient = useQueryClient();
  const [filter, setFilter] = useState('all');
  const [search, setSearch] = useState('');
  const [formError, setFormError] = useState('');
  const [creating, setCreating] = useState(false);
  useEffect(() => { setMeta({ title: '订单中心', breadcrumbs: [{ label: '首页', to: '/' }, { label: '订单中心' }] }); }, [setMeta]);
  const ordersQuery = useQuery({ queryKey: ['sales-orders', search], queryFn: () => fetchSalesOrders({ q: search || undefined, limit: 100 }) });
  const accountsQuery = useQuery({ queryKey: ['accounting-accounts'], queryFn: fetchAccountingAccounts });
  const orders = ordersQuery.data || [];
  const summary = summarizeSalesOrders(orders);
  const filteredOrders = useMemo(() => orders.filter(order => {
    if (filter === 'unpaid') return order.payment_status === 'unpaid' && order.fulfillment_status !== 'draft' && order.fulfillment_status !== 'cancelled';
    if (filter === 'shipped') return order.fulfillment_status === 'shipped';
    if (filter === 'paid') return order.payment_status === 'paid' && order.fulfillment_status !== 'cancelled';
    if (filter === 'cancelled') return order.fulfillment_status === 'cancelled';
    return true;
  }), [filter, orders]);
  const refresh = () => { queryClient.invalidateQueries({ queryKey: ['sales-orders'] }); queryClient.invalidateQueries({ queryKey: ['accounting'] }); };
  const create = async (payload: Parameters<typeof createSalesOrder>[0]) => { setFormError(''); setCreating(true); try { await createSalesOrder(payload); refresh(); } catch (error) { setFormError(apiErrorMessage(error)); throw error; } finally { setCreating(false); } };
  return <div className="w-full animate-fade-in">
    <header className="mb-6 flex flex-col justify-between gap-4 sm:flex-row sm:items-end"><div><p className="text-[11px] font-bold uppercase tracking-[.12em] text-accent">Sales desk</p><h1 className="mt-1 font-display text-3xl font-semibold tracking-tight sm:text-4xl">订单中心</h1><p className="mt-2 text-sm text-muted">创建、查询和推进销售订单。</p></div><button type="button" onClick={refresh} className="inline-flex w-fit items-center gap-1 rounded border border-border bg-white px-3 py-2 text-sm hover:border-gold"><RefreshCw className="h-4 w-4" />刷新</button></header>
    <div className="mb-7 grid grid-cols-2 overflow-hidden rounded-md border border-border bg-white shadow-sm lg:grid-cols-5"><SummaryCell label="全部订单" value={summary.total} amount={orders.reduce((sum, order) => sum + Number(order.amount_due_cny || 0), 0)} active={filter === 'all'} onClick={() => setFilter('all')} /><SummaryCell label="待收款" value={summary.unpaid.count} amount={summary.unpaid.amount} active={filter === 'unpaid'} onClick={() => setFilter('unpaid')} /><SummaryCell label="已出库" value={summary.shipped.count} amount={summary.shipped.amount} active={filter === 'shipped'} onClick={() => setFilter('shipped')} /><SummaryCell label="已收款" value={summary.paid.count} amount={summary.paid.amount} active={filter === 'paid'} onClick={() => setFilter('paid')} /><SummaryCell label="已取消" value={summary.cancelled.count} amount={summary.cancelled.amount} active={filter === 'cancelled'} onClick={() => setFilter('cancelled')} /></div>
    <div className="mb-4 flex items-center gap-2"><div className="relative max-w-sm flex-1"><Search className="absolute left-3 top-2.5 h-4 w-4 text-muted" /><input value={search} onChange={event => setSearch(event.target.value)} placeholder="搜索订单号或客户" className="w-full rounded border border-border bg-white py-2 pl-9 pr-3 text-sm outline-none focus:border-gold" /></div><span className="text-xs text-muted">显示 {filteredOrders.length} 笔</span></div>
    {ordersQuery.error && <div className="mb-5 rounded border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{apiErrorMessage(ordersQuery.error, '订单加载失败')}</div>}
    <div data-guide="sales-fulfillment" className="grid items-start gap-6 xl:grid-cols-[minmax(440px,.9fr)_minmax(560px,1.1fr)]"><SalesOrderForm onSubmit={create} busy={creating} error={formError} /><section className="rounded-md border border-border bg-white shadow-sm"><div className="flex items-center justify-between border-b border-border px-5 py-4"><div><h2 className="font-display text-lg font-semibold">销售订单</h2><p className="text-xs text-muted">点击订单查看商品、FIFO 批次与动作。</p></div><span className="text-xs text-muted">{ordersQuery.isLoading ? '加载中…' : `${filteredOrders.length} 笔`}</span></div>{ordersQuery.isLoading ? <p className="px-5 py-12 text-center text-sm text-muted">加载订单…</p> : filteredOrders.length === 0 ? <p className="px-5 py-12 text-center text-sm text-muted">暂无符合条件的销售单</p> : filteredOrders.map((order: SalesOrder) => <SalesOrderCard key={order.id} order={order} accounts={accountsQuery.data || []} onChanged={refresh} />)}</section></div>
  </div>;
}

function SummaryCell({ label, value, amount, active, onClick }: { label: string; value: number; amount: number; active: boolean; onClick: () => void }) { return <button type="button" onClick={onClick} className={`border-b border-border p-4 text-left transition last:border-0 lg:border-b-0 lg:border-r ${active ? 'bg-[#FFF8F1]' : 'hover:bg-[#FFFCF9]'}`}><span className="text-xs text-muted">{label}</span><strong className="mt-2 block font-mono text-2xl">{String(value).padStart(2, '0')}</strong><span className="mt-1 block font-mono text-xs text-muted">{formatCny(amount)}</span></button>; }
