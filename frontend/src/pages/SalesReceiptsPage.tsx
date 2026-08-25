import { useEffect, useMemo } from 'react';
import { RefreshCw, ReceiptText } from 'lucide-react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { apiErrorMessage, fetchSalesOrders } from '../api';
import SalesSectionNav from '../components/sales/SalesSectionNav';
import { formatCny } from '../components/sales/salesState';
import { usePageMeta } from '../hooks/usePageMeta';
import { formatShanghaiDateTime } from '../utils/businessDate';

export default function SalesReceiptsPage() {
  const { setMeta } = usePageMeta();
  const queryClient = useQueryClient();
  useEffect(() => { setMeta({ title: '收款记录', breadcrumbs: [{ label: '首页', to: '/' }, { label: '订单', to: '/sales' }, { label: '收款记录' }] }); }, [setMeta]);
  const query = useQuery({
    queryKey: ['sales-receipts'],
    queryFn: () => fetchSalesOrders({ payment_status: 'paid', limit: 100 }),
  });
  const receipts = useMemo(() => (query.data || []).filter(order => order.sales_receipt), [query.data]);
  const total = receipts.reduce((sum, order) => sum + Number(order.sales_receipt?.amount_cny || 0), 0);
  const refresh = () => { queryClient.invalidateQueries({ queryKey: ['sales-receipts'] }); queryClient.invalidateQueries({ queryKey: ['sales-orders'] }); };

  return <div className="w-full animate-fade-in">
    <SalesSectionNav />
    <header className="mb-5 flex flex-col justify-between gap-4 sm:flex-row sm:items-end"><div><p className="text-[11px] font-bold uppercase tracking-[.12em] text-accent">Sales receipts</p><h1 className="mt-1 font-display text-3xl font-semibold sm:text-4xl">收款记录</h1><p className="mt-2 text-sm text-muted">每条记录对应一笔客户已经付款后的正式 SalesReceipt 收款事实。</p></div><button type="button" onClick={refresh} className="inline-flex items-center gap-1 self-start rounded border border-border bg-white px-3 py-2 text-sm hover:border-gold sm:self-auto"><RefreshCw className="h-4 w-4" />刷新</button></header>
    <section className="mb-4 grid grid-cols-2 overflow-hidden rounded-md border border-border bg-white shadow-sm lg:grid-cols-3"><Metric label="记录数" value={query.isLoading ? '—' : String(receipts.length)} /><Metric label="累计收款" value={query.isLoading ? '—' : formatCny(total)} /><Metric label="来源" value="销售订单" /></section>
    {query.error && <p className="mb-4 rounded border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{apiErrorMessage(query.error, '收款记录加载失败')}</p>}
    <section className="overflow-hidden rounded-md border border-border bg-white shadow-sm">
      <div className="grid grid-cols-[minmax(0,1fr)_auto_auto] gap-4 border-b border-border bg-[#FCFBF9] px-4 py-2 text-[10px] font-bold uppercase tracking-wide text-muted"><span>收款记录 / 订单</span><span>业务日期</span><span>金额</span></div>
      {query.isLoading && <p className="px-5 py-20 text-center text-sm text-muted">加载收款记录…</p>}
      {!query.isLoading && !receipts.length && <div className="px-5 py-20 text-center"><ReceiptText className="mx-auto h-8 w-8 text-border" /><p className="mt-3 text-sm font-semibold">暂无收款记录</p><p className="mt-1 text-xs text-muted">客户付款后，在订单详情中登记收款记录，这里会显示已入账事实。</p></div>}
      {receipts.map(order => <ReceiptRow key={order.sales_receipt!.id} order={order} />)}
    </section>
  </div>;
}

function ReceiptRow({ order }: { order: Awaited<ReturnType<typeof fetchSalesOrders>>[number] }) {
  const receipt = order.sales_receipt!;
  return <div className="grid grid-cols-[minmax(0,1fr)_auto_auto] items-center gap-4 border-b border-border px-4 py-3 last:border-0 hover:bg-[#FFFCF9]"><div className="min-w-0"><strong className="font-mono text-xs">RC-{String(receipt.id).padStart(6, '0')}</strong><span className="ml-2 rounded-full border border-green-200 bg-green-50 px-2 py-0.5 text-[10px] font-semibold text-green-700">已收款</span><p className="mt-1 truncate text-sm font-semibold">{order.order_number} · {order.customer_name || '散客'}</p><p className="mt-1 text-[10px] text-muted">资金账户 #{receipt.fund_account_id} · 应收 {formatCny(order.amount_due_cny)}</p></div><span className="font-mono text-xs text-muted">{receipt.business_date || (order.created_at ? formatShanghaiDateTime(order.created_at).slice(0, 10) : '—')}</span><strong className="font-mono text-sm">{formatCny(receipt.amount_cny)}</strong></div>;
}

function Metric({ label, value }: { label: string; value: string }) { return <div className="border-b border-r border-border p-4 last:border-r-0 lg:border-b-0"><span className="text-[11px] text-muted">{label}</span><strong className="mt-2 block font-mono text-xl">{value}</strong></div>; }
