import { ChevronRight, X } from 'lucide-react';
import type { SalesOrder } from '../../types';
import { formatShanghaiDateTime } from '../../utils/businessDate';
import { salesPreorderLabel, salesPreorderStage } from './preorderState';
import { formatCny, statusLabel } from './salesState';

const tones: Record<string, { row: string; status: string }> = {
  draft: { row: 'border-l-[#9A8E77] bg-[#F6F3ED]', status: 'bg-[#F1EDE6] text-[#6E6353]' },
  confirmed: { row: 'border-l-[#466681] bg-[#F1F5F8]', status: 'bg-[#EAF0F4] text-[#466681]' },
  shipped: { row: 'border-l-[#36526B] bg-[#EAEFF4]', status: 'bg-[#E3EAF0] text-[#36526B]' },
  completed: { row: 'border-l-[#3D6B4F] bg-[#EFF4F0]', status: 'bg-[#E9F1EB] text-[#3D6B4F]' },
  cancelled: { row: 'border-l-[#9A8E77] bg-[#F6F3ED]', status: 'bg-[#F1EDE6] text-[#6E6353]' },
  returned: { row: 'border-l-[#8E4451] bg-[#F7EEEE]', status: 'bg-[#FAF1F0] text-accent' },
};

function paymentText(order: SalesOrder): string | null {
  if (order.fulfillment_status === 'draft') return null;
  if (['cancelled', 'returned'].includes(order.fulfillment_status) && order.payment_status === 'unpaid') return null;
  if (order.payment_status === 'paid') return '已收清';
  if (['unpaid', 'partial'].includes(order.payment_status) && order.remaining_amount_cny != null) {
    return `${order.payment_status === 'partial' ? '部分收款 · ' : ''}待收 ${formatCny(order.remaining_amount_cny)}`;
  }
  return statusLabel(order.payment_status);
}

export default function SalesOrderListItem({ order, selected, onSelect }: {
  order: SalesOrder;
  selected: boolean;
  onSelect: (id: number) => void;
}) {
  // 完成由订单接口判定；仅已收清的待履约订单仍使用蓝色。
  const status = order.status === 'completed' ? 'completed' : order.fulfillment_status;
  const tone = tones[status] ?? tones.draft;
  const preorder = salesPreorderLabel(order);
  const stage = salesPreorderStage(order);
  const payment = paymentText(order);

  return <button
    type="button"
    onClick={() => onSelect(order.id)}
    aria-current={selected ? 'true' : undefined}
    className={`relative block w-full min-w-0 border-b border-l-[3px] border-b-border px-3 py-3 text-left last:border-b-0 hover:outline hover:outline-1 hover:-outline-offset-1 hover:outline-fg/20 focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-gold ${tone.row} ${selected ? 'shadow-[inset_0_0_0_1.5px_#2C2416]' : ''}`}
  >
    <span className="flex items-baseline justify-between gap-2">
      <span className="min-w-0 truncate font-mono text-[11px] font-semibold" title={order.order_number}>{order.order_number}</span>
      <span className="flex shrink-0 items-center gap-1">
        <strong className="whitespace-nowrap font-mono text-xs">{formatCny(order.amount_due_cny)}</strong>
        <ChevronRight aria-hidden="true" className={`h-3 w-3 ${selected ? 'opacity-100' : 'opacity-0'}`} />
      </span>
    </span>
    <span className="mt-1 flex min-w-0 items-center gap-2">
      <strong className="min-w-0 truncate text-sm" title={order.customer_name || '散客'}>{order.customer_name || '散客'}</strong>
      {preorder && <span className="shrink-0 whitespace-nowrap rounded-full border border-gold bg-white px-1.5 py-0.5 text-[9px] font-semibold text-[#8A5A24]">{preorder}</span>}
    </span>
    <span className="mt-1 block text-[10px] text-[#6E6353]">{formatShanghaiDateTime(order.created_at).slice(0, 10)}</span>
    <span className="mt-2 flex flex-wrap items-center justify-between gap-x-2 gap-y-1 text-[10px]">
      <span className="flex flex-wrap items-center gap-1">
        <span className={`inline-flex items-center gap-1 whitespace-nowrap rounded-full px-1.5 py-0.5 font-bold ${tone.status}`}>
          {status === 'cancelled' ? <X aria-hidden="true" className="h-2.5 w-2.5" /> : <span aria-hidden="true" className="h-1 w-1 rounded-full bg-current" />}
          {status === 'confirmed' ? '待发货' : statusLabel(status)}
        </span>
        {stage && <><span aria-hidden="true" className="text-[#6E6353]">·</span><span className="text-[#6E6353]">{stage}</span></>}
      </span>
      {payment && <span className={`ml-auto ${order.payment_status === 'refund_pending' ? 'font-semibold text-[#8A4A1F]' : 'text-[#6E6353]'}`}>{payment}</span>}
      {order.payment_review?.status === 'pending' && <span className="w-full text-right font-semibold text-[#8A4A1F]">付款凭证待核实</span>}
    </span>
  </button>;
}
