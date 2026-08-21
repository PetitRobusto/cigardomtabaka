import { useMemo, useState } from 'react';
import { CircleDollarSign, PackageCheck, RotateCcw, Truck, X } from 'lucide-react';
import type { FundAccount, SalesOrder } from '../../types';
import {
  apiErrorMessage,
  cancelSalesOrder,
  confirmSalesOrder,
  receiveSalesOrder,
  recordSalesTransportCost,
  refundSalesOrder,
  returnSalesOrder,
  shipSalesOrder,
} from '../../api';
import {
  actionLabel,
  actionNeedsFundAccount,
  formatCny,
  receiveAmountMatchesDue,
  statusLabel,
  validatePositiveMoneyInput,
} from './salesState';
import { salesFundAccountError, salesOrderActionBusinessDate, selectActiveCnyAccountId } from './SalesOrderCard.logic';
import { formatShanghaiDateTime } from '../../utils/businessDate';
import SalesOrderStatusTags from './SalesOrderStatusTags';

type DetailTab = 'overview' | 'items' | 'amounts' | 'facts' | 'timeline';

interface Props {
  orders: SalesOrder[];
  selectedId: number | null;
  accounts: FundAccount[];
  accountsError?: string;
  onSelect: (id: number | null) => void;
  onChanged: () => void;
  onCustomer: (customerId: number) => void;
}

export default function SalesOrderWorkbench({
  orders,
  selectedId,
  accounts: allAccounts,
  accountsError = '',
  onSelect,
  onChanged,
  onCustomer,
}: Props) {
  const selected = orders.find(order => order.id === selectedId) || null;
  const [tab, setTab] = useState<DetailTab>('overview');

  return <div className={`grid gap-4 lg:grid-cols-[300px_minmax(0,1fr)] ${selected ? 'sales-workbench-selected' : ''}`}>
    <section className={(selected ? 'hidden lg:block ' : '') + 'overflow-hidden rounded-md border border-border bg-white shadow-sm'}>
      <div className="border-b border-border px-4 py-3">
        <h2 className="font-display text-base font-semibold">订单轨道</h2>
        <p className="mt-0.5 text-[11px] text-muted">{orders.length} 笔筛选结果</p>
      </div>
      <div className="max-h-[calc(100vh-22rem)] min-h-60 overflow-y-auto lg:max-h-[calc(100vh-20rem)]">
        {orders.map(order => <button
          key={order.id}
          type="button"
          onClick={() => { onSelect(order.id); setTab('overview'); }}
          className={`block w-full border-b border-border px-4 py-3 text-left last:border-0 hover:bg-[#FFFCF9] ${selected?.id === order.id ? 'border-l-[3px] border-l-accent bg-[#FFFCF4]' : ''}`}
        >
          <span className="flex items-baseline justify-between gap-2">
            <span className="font-mono text-[11px] font-semibold">{order.order_number}</span>
            <strong className="font-mono text-xs">{formatCny(order.amount_due_cny)}</strong>
          </span>
          <strong className="mt-1 block truncate text-sm">{order.customer_name || '散客'}</strong>
          <span className="mt-2 flex items-center justify-between gap-2 text-[10px] text-muted">
            <span>{formatShanghaiDateTime(order.created_at).slice(0, 10)}</span>
            <SalesOrderStatusTags order={order} compact />
          </span>
        </button>)}
        {!orders.length && <div className="px-4 py-14 text-center text-sm text-muted">当前筛选条件下没有订单</div>}
      </div>
    </section>

    <section className={(!selected ? 'hidden lg:block ' : '') + 'min-w-0 overflow-hidden rounded-md border border-border bg-white shadow-sm'}>
      {!selected && <div className="grid min-h-[420px] place-items-center px-6 text-center text-sm text-muted">
        <div><p className="text-2xl">→</p><p className="mt-2 font-semibold text-fg">请选择一笔订单</p><p className="mt-1">查看订单、客户、FIFO、业务事实与当前可用动作。</p></div>
      </div>}
      {selected && <>
        <div className="border-b border-border bg-[#FFFDFA] px-4 py-4 sm:px-5">
          <button type="button" onClick={() => onSelect(null)} className="mb-3 rounded border border-border px-2 py-1 text-xs lg:hidden">← 返回订单轨道</button>
          <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-start">
            <div><h2 className="font-display text-xl font-semibold">{selected.order_number}</h2><p className="mt-1 text-xs text-muted">创建于 {formatShanghaiDateTime(selected.created_at)} · {selected.items.length} 项商品</p></div>
            <div className="flex flex-wrap gap-1.5 text-[11px]">
              <SalesOrderStatusTags order={selected} />
            </div>
          </div>
          <OrderActions order={selected} accounts={allAccounts} accountsError={accountsError} onChanged={onChanged} />
        </div>
        <div className="flex overflow-x-auto border-b border-border bg-[#FFFDFA] px-3">
          {([
            ['overview', '概览'],
            ['items', '商品'],
            ['amounts', '金额构成'],
            ['facts', '单据事实'],
            ['timeline', '时间线'],
          ] as [DetailTab, string][]).map(([value, label]) => <button key={value} type="button" onClick={() => setTab(value)} className={`whitespace-nowrap border-b-2 px-3 py-2.5 text-xs font-semibold ${tab === value ? 'border-accent text-accent' : 'border-transparent text-muted hover:text-fg'}`}>{label}</button>)}
        </div>
        <div className="max-h-[calc(100vh-24rem)] min-h-[360px] overflow-y-auto p-4 sm:p-5">
          {tab === 'overview' && <Overview order={selected} onCustomer={onCustomer} />}
          {tab === 'items' && <Items order={selected} />}
          {tab === 'amounts' && <Amounts order={selected} />}
          {tab === 'facts' && <Facts order={selected} />}
          {tab === 'timeline' && <Timeline order={selected} />}
        </div>
      </>}
    </section>
  </div>;
}

function Overview({ order, onCustomer }: { order: SalesOrder; onCustomer: (id: number) => void }) {
  return <div className="space-y-5">
    <div>
      <div className="mb-2 flex items-center justify-between"><h3 className="text-xs font-bold uppercase tracking-wide">客户资料</h3>{order.customer_id && !order.customer?.deleted_at && <button type="button" onClick={() => onCustomer(order.customer_id!)} className="text-xs font-semibold text-accent hover:underline">查看 / 编辑 →</button>}</div>
      <div className="rounded border border-border bg-[#FFFDFA] p-4"><strong>{order.customer_name || '散客'}</strong>{order.customer?.deleted_at && <span className="ml-2 rounded-full bg-gray-100 px-2 py-0.5 text-[10px] text-muted">已归档客户</span>}<p className="mt-1 text-xs text-muted">{order.customer?.phone || '未填写电话'}</p></div>
    </div>
    <div><h3 className="mb-2 text-xs font-bold uppercase tracking-wide">订单信息</h3><dl className="grid gap-3 rounded border border-border p-4 text-xs sm:grid-cols-2">
      <Info label="订单状态" value={statusLabel(order.fulfillment_status)} />
      <Info label="付款状态" value={statusLabel(order.payment_status)} />
      <Info label="应收金额" value={formatCny(order.amount_due_cny)} />
      <Info label="订单贡献利润" value={formatCny(order.contribution_profit)} />
      <Info label="备注" value={order.note || '—'} />
      <Info label="可用动作" value={order.available_actions.map(actionLabel).join('、') || '无'} />
    </dl></div>
  </div>;
}

function Items({ order }: { order: SalesOrder }) {
  return <div className="overflow-x-auto rounded border border-border"><table className="w-full min-w-[620px] text-xs"><thead className="bg-[#F5EFE8] text-muted"><tr><th className="px-3 py-2 text-left">商品</th><th className="px-3 py-2 text-right">数量</th><th className="px-3 py-2 text-right">单价</th><th className="px-3 py-2 text-left">FIFO 批次</th><th className="px-3 py-2 text-right">成本</th></tr></thead><tbody>{order.items.map(item => <tr key={item.id} className="border-t border-border"><td className="px-3 py-3 font-semibold">{item.cigar_name}</td><td className="px-3 py-3 text-right">{item.sale_unit === 'box' ? item.sale_quantity : item.quantity} {item.sale_unit === 'box' ? '盒' : '支'}</td><td className="px-3 py-3 text-right font-mono">{formatCny(item.unit_price)}</td><td className="px-3 py-3 text-muted">{item.allocations.map(allocation => `#${allocation.batch_id} × ${allocation.quantity}`).join('，') || '确认订单后分配'}</td><td className="px-3 py-3 text-right font-mono">{formatCny(item.cost)}</td></tr>)}</tbody></table></div>;
}

function Amounts({ order }: { order: SalesOrder }) {
  return <div className="space-y-3 rounded border border-border p-4 text-sm">
    <Money label="商品金额" value={order.goods_amount_cny} />
    <Money label="客户承担人肉费" value={order.customer_transport_fee_cny} />
    <Money label="应收合计" value={order.amount_due_cny} strong />
    <div className="border-t border-border pt-3"><Money label="FIFO 成本" value={order.fifo_cost} /></div>
    <Money label="实际人肉成本" value={order.actual_transport_cost_cny} />
    <Money label="订单贡献利润" value={order.contribution_profit} strong tone={Number(order.contribution_profit) >= 0 ? 'green' : 'red'} />
  </div>;
}

function Facts({ order }: { order: SalesOrder }) {
  const facts = [
    order.sales_receipt && { type: 'SalesReceipt · 收款', id: order.sales_receipt.id, amount: order.sales_receipt.amount_cny, date: order.sales_receipt.business_date },
    order.sales_shipment && { type: 'SalesShipment · 出库', id: order.sales_shipment.id, amount: order.sales_shipment.fifo_cost_cny, date: order.sales_shipment.business_date },
    order.sales_refund && { type: 'SalesRefund · 退款', id: order.sales_refund.id, amount: order.sales_refund.amount_cny, date: order.sales_refund.business_date },
    order.sales_return && { type: 'SalesReturn · 退货', id: order.sales_return.id, amount: order.sales_return.amount_cny, date: order.sales_return.business_date },
    order.sales_transport_cost && { type: 'SalesTransportCost · 人肉成本', id: order.sales_transport_cost.id, amount: order.sales_transport_cost.actual_cost_cny, date: order.sales_transport_cost.business_date },
  ].filter(Boolean) as { type: string; id: number; amount: number; date: string }[];
  if (!facts.length) return <div className="rounded border border-dashed border-border px-4 py-14 text-center text-sm text-muted">尚未生成业务事实</div>;
  return <div className="grid gap-3 xl:grid-cols-2">{facts.map(fact => <div key={fact.type} className="rounded border border-border border-l-4 border-l-gold bg-[#FFFDFA] p-4"><span className="text-[10px] font-bold uppercase tracking-wide text-muted">{fact.type}</span><strong className="mt-2 block font-mono text-lg">{formatCny(fact.amount)}</strong><p className="mt-1 text-xs text-muted">事实 #{fact.id} · 业务日期 {fact.date}</p></div>)}</div>;
}

function Timeline({ order }: { order: SalesOrder }) {
  const events = [
    order.created_at && { label: '销售单创建', date: order.created_at },
    order.confirmed_at && { label: '订单确认并预留库存', date: order.confirmed_at },
    order.sales_receipt && { label: '生成 SalesReceipt 收款事实', date: order.sales_receipt.business_date },
    order.sales_shipment && { label: '生成 SalesShipment 出库事实', date: order.sales_shipment.business_date },
    order.sales_transport_cost && { label: '登记 SalesTransportCost', date: order.sales_transport_cost.business_date },
    order.sales_return && { label: '生成 SalesReturn 退货事实', date: order.sales_return.business_date },
    order.sales_refund && { label: '生成 SalesRefund 退款事实', date: order.sales_refund.business_date },
    order.cancelled_at && { label: '订单取消', date: order.cancelled_at },
  ].filter(Boolean) as { label: string; date: string }[];
  return <ol className="space-y-0">{events.map((event, index) => <li key={`${event.label}-${index}`} className="relative border-l border-border pb-5 pl-5 last:pb-0"><span className="absolute -left-1 top-1 h-2 w-2 rounded-full bg-accent" /><strong className="block text-sm">{event.label}</strong><span className="mt-1 block font-mono text-[11px] text-muted">{formatShanghaiDateTime(event.date)}</span></li>)}</ol>;
}

function OrderActions({ order, accounts: allAccounts, accountsError, onChanged }: { order: SalesOrder; accounts: FundAccount[]; accountsError: string; onChanged: () => void }) {
  const accounts = useMemo(() => allAccounts.filter(account => account.currency === 'CNY' && account.is_active), [allAccounts]);
  const [action, setAction] = useState('');
  const [date, setDate] = useState(salesOrderActionBusinessDate());
  const [amount, setAmount] = useState('');
  const [reason, setReason] = useState('');
  const [accountId, setAccountId] = useState(accounts[0]?.id ?? 0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const selectedAccountId = selectActiveCnyAccountId(allAccounts, accountId);
  const actions = Array.isArray(order.available_actions) ? order.available_actions : [];
  const needsBusinessDate = ['ship', 'receive', 'refund', 'return', 'transport_cost'].includes(action);
  const receiveMatchesDue = action !== 'receive' || receiveAmountMatchesDue(amount, order.amount_due_cny);

  const open = (nextAction: string) => {
    setAction(nextAction);
    setError('');
    setReason('');
    setAmount(nextAction === 'receive' ? String(order.amount_due_cny) : '');
    setDate(salesOrderActionBusinessDate());
  };
  const run = async () => {
    setError('');
    if (action === 'receive' && !receiveMatchesDue) {
      setError(`收款金额必须等于应收 ${formatCny(order.amount_due_cny)}，请修正差额后提交。`);
      return;
    }
    if (action === 'return' && !reason.trim()) {
      setError('退货原因不能为空');
      return;
    }
    const accountError = salesFundAccountError(action, selectedAccountId);
    if (accountError) { setError(accountError); return; }
    setBusy(true);
    try {
      if (action === 'confirm') await confirmSalesOrder(order.id);
      if (action === 'cancel') await cancelSalesOrder(order.id);
      if (action === 'ship') await shipSalesOrder(order.id, date);
      if (action === 'receive') await receiveSalesOrder(order.id, { amount_cny: amount, fund_account_id: selectedAccountId, business_date: date });
      if (action === 'refund') await refundSalesOrder(order.id, date);
      if (action === 'return') await returnSalesOrder(order.id, { business_date: date, reason: reason.trim() });
      if (action === 'transport_cost') await recordSalesTransportCost(order.id, { actual_cost_cny: amount, fund_account_id: selectedAccountId, business_date: date });
      setAction('');
      onChanged();
    } catch (requestError) {
      setError(apiErrorMessage(requestError));
    } finally {
      setBusy(false);
    }
  };

  return <div className="mt-3">
    <div className="flex flex-wrap gap-2">{actions.map(item => <button key={item} type="button" onClick={() => open(item)} disabled={Boolean(accountsError && actionNeedsFundAccount(item))} className={`inline-flex items-center gap-1 rounded border px-3 py-1.5 text-xs font-semibold ${item === 'cancel' || item === 'refund' || item === 'return' ? 'border-red-200 text-red-700 hover:bg-red-50' : item === 'receive' ? 'border-accent bg-accent text-white' : 'border-border hover:border-gold'}`}>
      {item === 'confirm' && <PackageCheck className="h-3.5 w-3.5" />}{item === 'ship' && <Truck className="h-3.5 w-3.5" />}{item === 'receive' && <CircleDollarSign className="h-3.5 w-3.5" />}{['refund', 'return'].includes(item) && <RotateCcw className="h-3.5 w-3.5" />}{actionLabel(item)}
    </button>)}</div>
    {action && <div role="dialog" aria-modal="true" aria-label={actionLabel(action)} className="fixed inset-0 z-50 grid place-items-center bg-fg/30 p-4" onMouseDown={event => { if (event.target === event.currentTarget) setAction(''); }}>
      <div className="w-full max-w-md rounded-md border border-border bg-white shadow-xl">
        <div className="flex items-center justify-between border-b border-border px-5 py-4"><div><h3 className="font-display text-lg font-semibold">{actionLabel(action)}</h3><p className="mt-0.5 text-xs text-muted">{order.order_number}</p></div><button type="button" aria-label="关闭订单动作" onClick={() => setAction('')}><X className="h-4 w-4" /></button></div>
        <div className="space-y-3 p-5">
          {['ship', 'receive', 'refund', 'return', 'transport_cost'].includes(action) && <label className="block text-xs font-medium text-muted">业务日期<input type="date" value={date} onChange={event => setDate(event.target.value)} className="mt-1.5 w-full rounded border border-border px-3 py-2 text-sm" /></label>}
          {action === 'return' && <label className="block text-xs font-medium text-muted">退货原因<input value={reason} onChange={event => setReason(event.target.value)} className="mt-1.5 w-full rounded border border-border px-3 py-2 text-sm" /></label>}
          {(action === 'receive' || action === 'transport_cost') && <>
            <label className="block text-xs font-medium text-muted">{action === 'receive' ? `收款金额（必须等于应收 ${formatCny(order.amount_due_cny)}）` : '实际人肉成本'}<input type="number" min="0" step="0.01" value={amount} onChange={event => setAmount(event.target.value)} className="mt-1.5 w-full rounded border border-border px-3 py-2 text-sm" /></label>
            {action === 'receive' && amount && !receiveMatchesDue && <p className="rounded border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">当前金额与应收相差 {formatCny(Math.abs(Number(amount) - Number(order.amount_due_cny)))}，暂不能提交。</p>}
            <label className="block text-xs font-medium text-muted">资金账户<select value={selectedAccountId} onChange={event => setAccountId(Number(event.target.value))} className="mt-1.5 w-full rounded border border-border bg-white px-3 py-2 text-sm">{accounts.map(account => <option key={account.id} value={account.id}>{account.name} · CNY</option>)}</select></label>
          </>}
          {(action === 'cancel' || action === 'refund' || action === 'return') && <p className="rounded border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">这是会改变订单、库存或资金事实的操作，请确认后执行。</p>}
          {error && <p className="text-xs text-red-700">{error}</p>}
        </div>
        <div className="flex justify-end gap-2 border-t border-border px-5 py-4"><button type="button" onClick={() => setAction('')} className="rounded border border-border px-4 py-2 text-sm">取消</button><button type="button" onClick={run} disabled={busy || (needsBusinessDate && !date) || !receiveMatchesDue || (actionNeedsFundAccount(action) && !accounts.length) || (action === 'transport_cost' && !validatePositiveMoneyInput(amount))} className="rounded bg-accent px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">{busy ? '处理中…' : '确认执行'}</button></div>
      </div>
    </div>}
  </div>;
}

function Info({ label, value }: { label: string; value: string }) { return <div><dt className="text-muted">{label}</dt><dd className="mt-1 font-semibold">{value}</dd></div>; }
function Money({ label, value, strong = false, tone }: { label: string; value: number; strong?: boolean; tone?: 'green' | 'red' }) { return <div className={`flex items-center justify-between ${strong ? 'font-semibold' : ''}`}><span className="text-muted">{label}</span><span className={`font-mono ${tone === 'green' ? 'text-success' : tone === 'red' ? 'text-red-700' : ''}`}>{formatCny(value)}</span></div>; }
