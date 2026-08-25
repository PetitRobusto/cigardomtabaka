import { useMemo, useState } from 'react';
import { CircleDollarSign, PackageCheck, RotateCcw, Truck, X } from 'lucide-react';
import type { FundAccount, PaymentMethod, SalesOrder } from '../../types';
import {
  apiErrorMessage,
  cancelSalesOrder,
  createPrivnote,
  fetchPaymentMethods,
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
          onClick={() => { onSelect(order.id); }}
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
        <div className="max-h-[calc(100vh-24rem)] min-h-[360px] space-y-6 overflow-y-auto p-4 sm:p-5">
          <DetailSection title="概览"><Overview order={selected} onCustomer={onCustomer} /></DetailSection>
          <DetailSection title="商品明细"><Items order={selected} /></DetailSection>
          <DetailSection title="金额与利润"><Amounts order={selected} /></DetailSection>
          <DetailSection title="收款单（付款链接）"><ReceiptPanel order={selected} onChanged={onChanged} /></DetailSection>
          <DetailSection title="业务事实"><Facts order={selected} /></DetailSection>
          <DetailSection title="时间线"><Timeline order={selected} /></DetailSection>
        </div>
      </>}
    </section>
  </div>;
}

function DetailSection({ title, children }: { title: string; children: React.ReactNode }) {
  return <section><div className="mb-2 flex items-center justify-between border-b border-border pb-2"><h3 className="font-display text-base font-semibold">{title}</h3><span className="font-mono text-[10px] uppercase tracking-wide text-muted">Order detail</span></div>{children}</section>;
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
  return <div className="overflow-x-auto rounded border border-border"><table className="w-full min-w-[680px] text-xs"><thead className="bg-[#F5EFE8] text-muted"><tr><th className="px-3 py-2 text-left">品牌 / 商品</th><th className="px-3 py-2 text-right">数量</th><th className="px-3 py-2 text-right">单价</th><th className="px-3 py-2 text-left">FIFO 批次</th><th className="px-3 py-2 text-right">成本</th></tr></thead><tbody>{order.items.map(item => <tr key={item.id} className="border-t border-border"><td className="px-3 py-3"><span className="block text-[10px] font-bold uppercase tracking-wide text-muted">{item.cigar_brand_cn || item.cigar_brand || '未标注品牌'}</span><strong className="mt-0.5 block">{item.cigar_name}</strong></td><td className="px-3 py-3 text-right">{item.sale_unit === 'box' ? item.sale_quantity : item.quantity} {item.sale_unit === 'box' ? '盒' : '支'}</td><td className="px-3 py-3 text-right font-mono">{formatCny(item.unit_price)}</td><td className="px-3 py-3 text-muted">{item.allocations.map(allocation => `#${allocation.batch_id} × ${allocation.quantity}`).join('，') || '确认订单后分配'}</td><td className="px-3 py-3 text-right font-mono">{formatCny(item.cost)}</td></tr>)}</tbody></table></div>;
}

function ReceiptPanel({ order, onChanged }: { order: SalesOrder; onChanged: () => void }) {
  const receipt = order.sales_receipt;
  const activeNote = (order.payment_notes || []).find(note => note.is_active);
  const canCreateLink = !receipt && !activeNote && order.payment_status === 'unpaid'
    && ['confirmed', 'shipped'].includes(order.fulfillment_status);
  const [open, setOpen] = useState(false);
  const [methods, setMethods] = useState<PaymentMethod[]>([]);
  const [methodId, setMethodId] = useState('');
  const [remark, setRemark] = useState('');
  const [url, setUrl] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const startCreate = async () => {
    setError('');
    setUrl('');
    setOpen(true);
    if (methods.length) return;
    try {
      const loaded = await fetchPaymentMethods();
      setMethods(loaded);
      setMethodId(String(loaded[0]?.id || ''));
    } catch (requestError) {
      setError(apiErrorMessage(requestError, '收款方式加载失败'));
    }
  };
  const createLink = async () => {
    if (!methodId) { setError('请选择收款方式'); return; }
    setBusy(true);
    setError('');
    try {
      const form = new FormData();
      form.append('note_type', 'payment');
      form.append('sales_order_id', String(order.id));
      form.append('payment_method_id', methodId);
      if (remark.trim()) form.append('remark', remark.trim());
      const result = await createPrivnote(form);
      setUrl(result.url);
      onChanged();
    } catch (requestError) {
      setError(apiErrorMessage(requestError, '收款单创建失败'));
    } finally {
      setBusy(false);
    }
  };
  if (receipt) return <div className="grid gap-3 rounded border border-green-200 bg-green-50/40 p-4 text-sm sm:grid-cols-4"><div><span className="block text-xs text-muted">收款记录编号</span><strong className="mt-1 block font-mono">RC-{String(receipt.id).padStart(6, '0')}</strong></div><div><span className="block text-xs text-muted">已收金额</span><strong className="mt-1 block font-mono text-green-800">{formatCny(receipt.amount_cny)}</strong></div><div><span className="block text-xs text-muted">业务日期</span><strong className="mt-1 block">{receipt.business_date}</strong></div><div><span className="block text-xs text-muted">资金账户</span><strong className="mt-1 block">#{receipt.fund_account_id}</strong></div></div>;
  return <div className="rounded border border-border bg-[#FFFDFA] p-4 text-sm">
    {activeNote && <div className="mb-4 rounded border border-blue-200 bg-blue-50/50 p-3"><strong className="block text-blue-900">已有有效收款单</strong><span className="mt-1 block text-xs text-blue-800">该订单同时只允许一个有效收款单，请先使用或等待当前链接过期。</span><div className="mt-2 break-all font-mono text-xs text-fg">{activeNote.url}</div><div className="mt-2 text-xs text-muted">创建于 {formatShanghaiDateTime(activeNote.created_at)} · 查看 {activeNote.view_count} 次 · 到期 {formatShanghaiDateTime(activeNote.expires_at)}</div><button type="button" onClick={() => navigator.clipboard?.writeText(activeNote.url)} className="mt-2 rounded border border-blue-300 px-2 py-1 text-xs text-blue-800">复制收款单</button></div>}
    <div className="flex flex-wrap items-center justify-between gap-3"><div><strong className="block text-fg">客户尚未付款</strong><span className="mt-1 block text-xs text-muted">创建收款单发给客户；客户点击查看并付款后，再在订单顶部登记收款记录。</span></div>{canCreateLink && <button type="button" onClick={startCreate} className="rounded bg-accent px-3 py-2 text-xs font-semibold text-white hover:bg-accent-hover">创建收款单</button>}</div>
    {!canCreateLink && !activeNote && <p className="mt-3 text-xs text-muted">订单确认后才可以创建收款单。</p>}
    {open && canCreateLink && <div className="mt-4 space-y-3 border-t border-border pt-4"><label className="block text-xs font-medium text-muted">收款方式<select value={methodId} onChange={event => setMethodId(event.target.value)} className="mt-1.5 w-full rounded border border-border bg-white px-3 py-2 text-sm"><option value="">请选择 CNY 收款方式</option>{methods.map(method => <option key={method.id} value={method.id}>{method.label}{method.remark ? ` · ${method.remark}` : ''}</option>)}</select></label><label className="block text-xs font-medium text-muted">给客户的备注<textarea value={remark} onChange={event => setRemark(event.target.value)} rows={2} placeholder="例如：转账请备注订单号" className="mt-1.5 w-full rounded border border-border px-3 py-2 text-sm" /></label><div className="flex flex-wrap gap-2"><button type="button" onClick={createLink} disabled={busy || !methodId} className="rounded bg-accent px-3 py-2 text-xs font-semibold text-white disabled:opacity-50">{busy ? '创建中…' : '确认创建收款单'}</button><button type="button" onClick={() => setOpen(false)} className="rounded border border-border px-3 py-2 text-xs">取消</button></div>{error && <p className="text-xs text-red-700">{error}</p>}{url && <div className="rounded border border-green-200 bg-green-50 p-3"><span className="text-xs font-semibold text-green-800">收款单已生成，可发送给客户</span><div className="mt-2 break-all font-mono text-xs text-fg">{url}</div><button type="button" onClick={() => navigator.clipboard?.writeText(url)} className="mt-2 rounded border border-green-300 px-2 py-1 text-xs text-green-800">复制收款单</button></div>}</div>}
  </div>;
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
    order.sales_receipt && { label: '登记收款记录（SalesReceipt）', date: order.sales_receipt.business_date },
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
          {action === 'confirm' && <ConfirmSummary order={order} />}
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

function ConfirmSummary({ order }: { order: SalesOrder }) {
  return <div className="space-y-3 rounded border border-blue-200 bg-blue-50/50 p-3 text-xs">
    <p className="font-semibold text-blue-900">确认后会预留现货库存，订单进入待履约状态。</p>
    <div className="grid gap-2 sm:grid-cols-2"><div><span className="text-muted">客户</span><strong className="ml-2">{order.customer_name || '散客'}</strong></div><div><span className="text-muted">应收</span><strong className="ml-2 font-mono">{formatCny(order.amount_due_cny)}</strong></div></div>
    <ul className="space-y-1 border-t border-blue-200 pt-2 text-muted">{order.items.map(item => <li key={item.id} className="flex justify-between gap-3"><span>{item.cigar_name}</span><span className="font-mono">{item.sale_unit === 'box' ? `${item.sale_quantity ?? 0} 盒` : `${item.quantity} 支`}</span></li>)}</ul>
  </div>;
}

function Info({ label, value }: { label: string; value: string }) { return <div><dt className="text-muted">{label}</dt><dd className="mt-1 font-semibold">{value}</dd></div>; }
function Money({ label, value, strong = false, tone }: { label: string; value: number; strong?: boolean; tone?: 'green' | 'red' }) { return <div className={`flex items-center justify-between ${strong ? 'font-semibold' : ''}`}><span className="text-muted">{label}</span><span className={`font-mono ${tone === 'green' ? 'text-success' : tone === 'red' ? 'text-red-700' : ''}`}>{formatCny(value)}</span></div>; }
