import { useEffect, useState } from 'react';
import { ChevronRight, CircleDollarSign, PackageCheck, RotateCcw, Truck, X } from 'lucide-react';
import type { FundAccount, SalesOrder } from '../../types';
import { apiErrorMessage, cancelSalesOrder, confirmSalesOrder, receiveSalesOrder, recordSalesTransportCost, refundSalesOrder, shipSalesOrder } from '../../api';
import { actionLabel, actionNeedsFundAccount, availableActions, formatCny, initialActionAmount, orderDisplayStatus, statusLabel, validateMoneyInput } from './salesState';

interface Props { order: SalesOrder; accounts: FundAccount[]; onChanged: () => void; }
const today = () => { const date = new Date(); return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 10); };

export default function SalesOrderCard({ order, accounts: allAccounts, onChanged }: Props) {
  const accounts = allAccounts.filter(account => account.currency === 'CNY' && account.is_active);
  const [open, setOpen] = useState(false);
  const [action, setAction] = useState('');
  const [date, setDate] = useState(today());
  const [receiptAmount, setReceiptAmount] = useState(initialActionAmount('receive', order.amount_due_cny));
  const [transportCostAmount, setTransportCostAmount] = useState('');
  const [accountId, setAccountId] = useState(accounts[0]?.id ?? 0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => {
    if (!accountId && accounts[0]) setAccountId(accounts[0].id);
  }, [accountId, accounts]);
  const actions = Array.isArray(order.available_actions) ? order.available_actions : availableActions(order);

  const run = async () => {
    setBusy(true); setError('');
    try {
      if (action === 'confirm') await confirmSalesOrder(order.id);
      if (action === 'cancel') await cancelSalesOrder(order.id);
      if (action === 'ship') await shipSalesOrder(order.id, date);
      if (action === 'receive') await receiveSalesOrder(order.id, { amount_cny: receiptAmount, fund_account_id: accountId, business_date: date });
      if (action === 'refund') await refundSalesOrder(order.id, date);
      if (action === 'transport_cost') await recordSalesTransportCost(order.id, { actual_cost_cny: transportCostAmount, fund_account_id: accountId, business_date: date });
      setAction(''); onChanged();
    } catch (requestError) { setError(apiErrorMessage(requestError)); }
    finally { setBusy(false); }
  };

  const tone = order.fulfillment_status === 'cancelled' ? 'bg-gray-100 text-gray-600' : order.payment_status === 'paid' ? 'bg-green-50 text-success' : order.fulfillment_status === 'shipped' ? 'bg-blue-50 text-blue-700' : 'bg-orange-50 text-orange-700';
  return <article className="border-b border-border last:border-0">
    <button type="button" onClick={() => setOpen(value => !value)} className="grid w-full grid-cols-[minmax(0,1fr)_auto_auto] items-center gap-3 px-5 py-4 text-left hover:bg-[#FFFCF9] sm:grid-cols-[minmax(0,1.3fr)_0.8fr_0.8fr_auto]"><span><span className="font-mono text-[11px] font-semibold text-accent">{order.order_number || `SO-${order.id}`}</span><span className="mt-1 block font-semibold">{order.customer_name || '散客'}</span><span className="mt-0.5 block text-[11px] text-muted">{order.created_at?.slice(0, 10) || '—'} · {order.items.length} 项</span></span><span className="hidden text-xs text-muted sm:block">{orderDisplayStatus(order)}</span><span className="text-right font-mono text-sm font-semibold">{formatCny(order.amount_due_cny)}<span className={`mt-1 ml-auto block w-fit rounded-full px-2 py-0.5 text-[10px] font-bold ${tone}`}>{order.fulfillment_status === 'draft' ? '草稿' : statusLabel(order.payment_status)}</span></span><ChevronRight className={`h-5 w-5 text-muted transition-transform ${open ? 'rotate-90' : ''}`} /></button>
    {open && <div className="bg-[#FFFDFA] px-5 pb-5"><div className="border-t border-border pt-3"><div className="mb-3 grid gap-3 text-xs sm:grid-cols-3"><div><span className="text-muted">商品金额</span><strong className="ml-2 font-mono">{formatCny(order.goods_amount_cny)}</strong></div><div><span className="text-muted">FIFO 成本</span><strong className="ml-2 font-mono">{formatCny(order.fifo_cost)}</strong></div><div><span className="text-muted">订单贡献利润</span><strong className="ml-2 font-mono text-success">{formatCny(order.contribution_profit)}</strong></div></div><div className="divide-y divide-border rounded border border-border">{order.items.map(item => <div key={item.id} className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 text-xs"><span className="font-medium">{item.cigar_name}</span><span className="text-muted">{item.sale_unit === 'box' ? (item.sale_quantity ?? Math.ceil(item.quantity / (item.box_size || 1))) : item.quantity} {item.sale_unit === 'box' ? '盒' : '支'} × {formatCny(item.unit_price)}</span><span className="text-muted">FIFO {item.allocations.map(allocation => `批次#${allocation.batch_id} ×${allocation.quantity}${allocation.cost_cny != null ? ` · ¥${allocation.cost_cny}` : ''}`).join('，') || '待确认'}</span></div>)}</div><div className="mt-3 flex flex-wrap items-center gap-2">{actions.map(item => <button type="button" key={item} onClick={() => { setAction(item); setError(''); if (item === 'receive') setReceiptAmount(initialActionAmount(item, order.amount_due_cny)); if (item === 'transport_cost') setTransportCostAmount(''); }} className={`inline-flex items-center gap-1 rounded border px-3 py-1.5 text-xs font-semibold ${item === 'cancel' ? 'border-red-200 text-red-700 hover:bg-red-50' : 'border-border text-fg hover:border-gold hover:bg-white'}`}>{item === 'confirm' && <PackageCheck className="h-3.5 w-3.5" />}{item === 'ship' && <Truck className="h-3.5 w-3.5" />}{item === 'receive' && <CircleDollarSign className="h-3.5 w-3.5" />}{item === 'refund' && <RotateCcw className="h-3.5 w-3.5" />}{actionLabel(item)}</button>)}</div>{action && <div className="mt-3 rounded border border-gold/40 bg-gold/5 p-3"><div className="mb-2 flex items-center justify-between"><span className="text-xs font-semibold">{actionLabel(action)}</span><button type="button" onClick={() => setAction('')} className="text-muted"><X className="h-4 w-4" /></button></div>{(action === 'ship' || action === 'receive' || action === 'refund' || action === 'transport_cost') && <label className="mb-2 block text-xs text-muted">业务日期<input type="date" value={date} onChange={e => setDate(e.target.value)} className="mt-1 block rounded border border-border px-2 py-1.5 text-sm" /></label>}{(action === 'receive' || action === 'transport_cost') && <div className="grid gap-2 sm:grid-cols-2"><label className="text-xs text-muted">{action === 'receive' ? '收款金额 CNY' : '实际人肉成本 CNY'}<input type="number" min="0" step="0.01" value={action === 'receive' ? receiptAmount : transportCostAmount} onChange={e => action === 'receive' ? setReceiptAmount(e.target.value) : setTransportCostAmount(e.target.value)} className="mt-1 w-full rounded border border-border px-2 py-1.5 text-sm" /></label><label className="text-xs text-muted">资金账户<select value={accountId} onChange={e => setAccountId(Number(e.target.value))} className="mt-1 w-full rounded border border-border px-2 py-1.5 text-sm">{accounts.map(account => <option key={account.id} value={account.id}>{account.name} · CNY</option>)}</select></label></div>}{(!accounts.length && (action === 'receive' || action === 'transport_cost')) && <p className="mt-2 text-xs text-red-700">暂无可用 CNY 资金账户，无法执行该操作。</p>}<button type="button" onClick={run} disabled={busy || (actionNeedsFundAccount(action) && !accounts.length) || ((action === 'receive' && !validateMoneyInput(receiptAmount)) || (action === 'transport_cost' && !validateMoneyInput(transportCostAmount)))} className="mt-3 rounded bg-accent px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-50">{busy ? '处理中…' : '执行操作'}</button>{error && <p className="mt-2 text-xs text-red-700">{error}</p>}</div>}</div></div>}
  </article>;
}
