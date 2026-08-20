import { useState, type FormEvent } from 'react';
import { Trash2, X } from 'lucide-react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { apiErrorMessage, createSalesCustomer, deleteSalesCustomer, fetchSalesCustomer, updateSalesCustomer } from '../../api';
import { formatCny, orderDisplayStatus } from './salesState';
import { formatShanghaiDateTime } from '../../utils/businessDate';

interface Props {
  customerId: number | null;
  mode: 'create' | 'detail';
  onClose: () => void;
  onCreated?: (customer: { id: number; name: string }) => void;
}

export default function SalesCustomerModal({ customerId, mode, onClose, onCreated }: Props) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(mode === 'create');
  const [name, setName] = useState('');
  const [phone, setPhone] = useState('');
  const [busy, setBusy] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [error, setError] = useState('');
  const customerQuery = useQuery({
    queryKey: ['sales-customer', customerId],
    queryFn: () => fetchSalesCustomer(customerId!),
    enabled: mode === 'detail' && Boolean(customerId),
  });
  const customer = customerQuery.data;

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError('');
    if (!name.trim()) { setError('客户姓名不能为空'); return; }
    setBusy(true);
    try {
      const saved = mode === 'create'
        ? await createSalesCustomer({ name: name.trim(), phone: phone.trim() })
        : await updateSalesCustomer(customerId!, { name: name.trim(), phone: phone.trim() });
      await queryClient.invalidateQueries({ queryKey: ['sales-customers'] });
      await queryClient.invalidateQueries({ queryKey: ['sales-orders'] });
      if (mode === 'create') onCreated?.({ id: saved.id, name: saved.name });
      else {
        queryClient.setQueryData(['sales-customer', customerId], saved);
        setEditing(false);
      }
    } catch (requestError) {
      setError(apiErrorMessage(requestError, '客户保存失败'));
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (!customerId) return;
    setBusy(true);
    setError('');
    try {
      await deleteSalesCustomer(customerId);
      await queryClient.invalidateQueries({ queryKey: ['sales-orders'] });
      await queryClient.invalidateQueries({ queryKey: ['sales-customers'] });
      queryClient.removeQueries({ queryKey: ['sales-customer', customerId] });
      onClose();
    } catch (requestError) {
      setError(apiErrorMessage(requestError, '客户删除失败'));
    } finally {
      setBusy(false);
    }
  };

  return <div role="dialog" aria-modal="true" aria-label={mode === 'create' ? '新建客户' : '客户资料'} className="fixed inset-0 z-50 grid place-items-center bg-fg/30 p-4" onMouseDown={event => { if (event.target === event.currentTarget) onClose(); }}>
    <div className="max-h-[calc(100vh-2rem)] w-full max-w-xl overflow-y-auto rounded-md border border-border bg-white shadow-xl">
      <div className="flex items-start justify-between border-b border-border px-5 py-4"><div><h2 className="font-display text-xl font-semibold">{mode === 'create' ? '新建客户' : customer?.name || '客户资料'}</h2><p className="mt-1 text-xs text-muted">{mode === 'create' ? '保存后可立即用于新建销售单。' : customer?.phone || '未填写电话'}</p></div><button type="button" aria-label="关闭客户资料" onClick={onClose}><X className="h-4 w-4" /></button></div>
      {(mode === 'create' || editing) && <form onSubmit={submit} className="space-y-4 p-5">
        <label className="block text-xs font-medium text-muted">客户姓名 *<input autoFocus value={name} onChange={event => setName(event.target.value)} maxLength={200} className="mt-1.5 w-full rounded border border-border px-3 py-2 text-sm text-fg outline-none focus:border-gold" /></label>
        <label className="block text-xs font-medium text-muted">电话<input value={phone} onChange={event => setPhone(event.target.value)} maxLength={50} className="mt-1.5 w-full rounded border border-border px-3 py-2 text-sm text-fg outline-none focus:border-gold" /></label>
        {error && <p className="text-xs text-red-700">{error}</p>}
        <div className="flex justify-end gap-2"><button type="button" onClick={mode === 'create' ? onClose : () => setEditing(false)} className="rounded border border-border px-4 py-2 text-sm">取消</button><button disabled={busy} className="rounded bg-accent px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">{busy ? '保存中…' : '保存客户'}</button></div>
      </form>}
      {mode === 'detail' && !editing && <>
        {customerQuery.isLoading && <p className="px-5 py-12 text-center text-sm text-muted">加载客户资料…</p>}
        {customerQuery.error && <p className="px-5 py-4 text-sm text-red-700">{apiErrorMessage(customerQuery.error)}</p>}
        {customer && <div className="space-y-5 p-5">
          <div className="grid grid-cols-3 overflow-hidden rounded border border-border text-center"><Metric label="历史订单" value={String(customer.order_count)} /><Metric label="有效订单" value={String(customer.active_order_count)} /><Metric label="累计应收" value={formatCny(customer.total_amount_cny)} /></div>
          <div><div className="mb-2 flex items-center justify-between"><h3 className="text-xs font-bold uppercase tracking-wide">最近订单</h3><button type="button" onClick={() => { setName(customer.name); setPhone(customer.phone); setEditing(true); }} className="text-xs font-semibold text-accent">编辑资料</button></div>
            <div className="overflow-hidden rounded border border-border">{customer.recent_orders.length ? customer.recent_orders.map(order => <div key={order.id} className="grid grid-cols-[1fr_auto] gap-2 border-b border-border px-3 py-2 text-xs last:border-0"><span><strong className="font-mono">{order.order_number}</strong><small className="mt-0.5 block text-muted">{formatShanghaiDateTime(order.created_at).slice(0, 10)} · {orderDisplayStatus(order)}</small></span><strong className="font-mono">{formatCny(order.amount_due_cny)}</strong></div>) : <p className="px-3 py-8 text-center text-sm text-muted">暂无历史订单</p>}</div>
          </div>
          <div className="border-t border-border pt-4">{confirmingDelete ? <div className="rounded border border-red-200 bg-red-50 p-3 text-xs text-red-800"><p>删除后客户不再出现在搜索中，历史订单仍会保留。</p><div className="mt-3 flex justify-end gap-2"><button type="button" disabled={busy} onClick={() => setConfirmingDelete(false)} className="rounded border border-border bg-white px-3 py-1.5">返回</button><button type="button" disabled={busy} onClick={remove} className="rounded bg-red-700 px-3 py-1.5 font-semibold text-white disabled:opacity-50">{busy ? '删除中…' : '确认删除'}</button></div></div> : <button type="button" onClick={() => setConfirmingDelete(true)} className="inline-flex items-center gap-1 text-xs font-semibold text-red-700"><Trash2 className="h-3.5 w-3.5" />删除客户</button>}{error && <p className="mt-2 text-xs text-red-700">{error}</p>}</div>
        </div>}
      </>}
    </div>
  </div>;
}

function Metric({ label, value }: { label: string; value: string }) { return <div className="border-r border-border p-3 last:border-0"><span className="block text-[10px] text-muted">{label}</span><strong className="mt-1 block font-mono text-sm">{value}</strong></div>; }
