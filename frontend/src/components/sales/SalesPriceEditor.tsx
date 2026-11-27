import { useRef, useState } from 'react';
import { apiErrorMessage, changeSalesPrices } from '../../api';
import type { SalesOrder } from '../../types';
import PaymentDialog from '../privnote/PaymentDialog';
import { formatCny, validateMoneyInput } from './salesState';

export default function SalesPriceEditor({ order, onChanged }: { order: SalesOrder; onChanged: () => void }) {
  const [snapshot, setSnapshot] = useState<SalesOrder | null>(null);
  return <>
    <button type="button" className="rounded border border-border px-3 py-2 text-xs" onClick={() => setSnapshot(order)}>修改单价</button>
    {snapshot && <PriceDialog order={snapshot} onClose={() => setSnapshot(null)} onChanged={onChanged} />}
  </>;
}

function PriceDialog({ order, onClose, onChanged }: { order: SalesOrder; onClose: () => void; onChanged: () => void }) {
  const [prices, setPrices] = useState<Record<number, string>>(() =>
    Object.fromEntries(order.items.map(item => [item.id, item.unit_price.toFixed(2)])));
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const submitting = useRef(false);
  const changes = order.items.filter(item => Number(prices[item.id]) !== item.unit_price);
  const valid = Object.values(prices).every(price => validateMoneyInput(price) && Number(price) < 1e10);
  // 金额预览使用整数分。未编辑的历史行沿用订单保存的小计。
  const dueCents = changes.reduce((sum, item) => {
    const quantity = item.sale_unit === 'box' ? item.sale_quantity! : item.quantity;
    return sum + Math.round(Number(prices[item.id]) * 100) * quantity - Math.round(item.revenue * 100);
  }, Math.round(order.amount_due_cny * 100));
  const received = order.received_amount_cny ?? 0;
  const remaining = (dueCents - Math.round(received * 100)) / 100;
  const pending = order.payment_review?.status === 'pending' && dueCents !== Math.round(order.amount_due_cny * 100);
  const issue = !valid ? '请输入非负单价，最多两位小数，整数最多十位。'
    : dueCents >= 1e12 ? '订单金额超出可记录范围。'
    : remaining < 0 ? '改价后订单金额不能低于累计有效实收。'
    : pending ? '有待核实的付款凭证，请先核实或要求补充，再调整订单总额。' : '';
  const save = async () => {
    if (submitting.current || issue || !changes.length || !order.price_revision) return;
    submitting.current = true;
    setBusy(true); setError('');
    try {
      await changeSalesPrices(order.id, order.price_revision, changes.map(item => ({ id: item.id, unit_price: prices[item.id] })));
      onChanged(); onClose();
    } catch (failure) {
      setError(apiErrorMessage(failure));
      onChanged();
    } finally {
      submitting.current = false;
      setBusy(false);
    }
  };
  return <PaymentDialog title="修改商品单价" busy={busy} onClose={onClose} width="md">
    <form className="space-y-4 p-5" onSubmit={event => { event.preventDefault(); void save(); }}>
      <h3 className="font-display text-lg font-semibold">修改商品单价</h3>
      <p className="text-xs text-muted">{order.order_number} · 原订单金额 {formatCny(order.amount_due_cny)}</p>
      <fieldset disabled={busy} className="space-y-3">
        {order.items.map(item => {
          const box = item.sale_unit === 'box';
          const unit = box ? '盒' : '支';
          return <label key={item.id} className="block text-sm">
            {item.cigar_name} · {box ? item.sale_quantity : item.quantity} {unit}{box && `（${item.box_size} 支/盒）`} · 元/{unit}
            <input type="number" min="0" step="0.01" required value={prices[item.id]} className="mt-1 w-full rounded border border-border px-3 py-2"
              onChange={event => { setPrices({ ...prices, [item.id]: event.target.value }); setError(''); }} />
          </label>;
        })}
      </fieldset>
      <div className="rounded border border-border p-3 text-sm">
        <p>改后订单金额（含人肉费） <strong>{valid ? formatCny(dueCents / 100) : '—'}</strong></p>
        <p>累计已收 {formatCny(received)} · 剩余待收 {valid && remaining >= 0 ? formatCny(remaining) : '—'}</p>
      </div>
      {(issue || error) && <p role="alert" className="text-sm text-red-700">{issue || error}</p>}
      <div className="flex justify-end gap-2">
        <button type="button" disabled={busy} onClick={onClose} className="rounded border border-border px-3 py-2 text-sm">取消</button>
        <button type="submit" disabled={busy || !!issue || !changes.length} className="rounded bg-accent px-3 py-2 text-sm text-white disabled:opacity-50">{busy ? '保存中…' : '保存改价'}</button>
      </div>
    </form>
  </PaymentDialog>;
}
