import type { SalesOrder } from '../../types';
import { statusLabel, statusTagTone } from './salesState';

export default function SalesOrderStatusTags({ order, compact = false }: { order: SalesOrder; compact?: boolean }) {
  const showPayment = order.fulfillment_status !== 'draft'
    && !(order.fulfillment_status === 'cancelled' && order.payment_status === 'unpaid')
    && !(order.fulfillment_status === 'returned' && order.payment_status === 'unpaid');
  const className = `rounded-full border font-bold ${compact ? 'px-1.5 py-0.5 text-[9px]' : 'px-2.5 py-1 text-[11px]'}`;
  return <span className="flex flex-wrap justify-end gap-1">
    <span className={`${className} ${statusTagTone(order.fulfillment_status)}`}>{statusLabel(order.fulfillment_status)}</span>
    {showPayment && <span className={`${className} ${statusTagTone(order.payment_status)}`}>{statusLabel(order.payment_status)}</span>}
  </span>;
}
