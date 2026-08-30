import { useMemo, useState } from 'react';
import type {
  FundAccount,
  PurchaseAction as PurchaseOrderAction,
  PurchaseCancelPayload,
  PurchasePayPayload,
  PurchaseReceivePayload,
} from '../../types';
import {
  cancelPurchaseOrder,
  parseAccountingApiError,
  payPurchaseOrder,
  receivePurchaseOrder,
  reverseReceivedPurchaseOrder,
} from '../../api';
import {
  initialActionState,
  reduceActionState,
  type ActionState,
} from '../../features/accounting/actionState';
import { selectActiveAccountId } from './PurchaseAction.logic';

export interface PurchaseActionProps {
  purchases: PurchaseOrderAction[];
  rubAccounts: FundAccount[];
  businessDate: string;
  onPay?: (purchaseId: number, payload: PurchasePayPayload) => Promise<unknown> | unknown;
  onReceive?: (purchaseId: number, payload: PurchaseReceivePayload) => Promise<unknown> | unknown;
  onCancel?: (purchaseId: number, payload: PurchaseCancelPayload) => Promise<unknown> | unknown;
  onReverseReceive?: (purchaseId: number, payload: { business_date: string; note: string }) => Promise<unknown> | unknown;
  onChanged?: () => void;
}

type PurchaseInputs = { accountId: string; businessDate: string; note: string };

const emptyInputs = (businessDate: string): PurchaseInputs => ({
  accountId: '', businessDate, note: '',
});

function errorFor(error: unknown): { code: string; message: string; conflict: boolean } {
  const parsed = parseAccountingApiError(error);
  const status = parsed.status ?? (error && typeof error === "object" && "status" in error ? Number(error.status) : undefined);
  return { code: parsed.code, message: parsed.message, conflict: status === 409 };
}

function money(value: string | number | null | undefined, currency = ''): string {
  if (value === null || value === undefined || value === '') return '—';
  return `${String(value)}${currency ? ` ${currency}` : ''}`;
}

function decimalCents(value: string | number | null | undefined): bigint | null {
  if (value === null || value === undefined || value === "") return null;
  const text = String(value).trim();
  if (!/^(?:0|[1-9]\d*)(?:\.\d{1,2})?$/.test(text)) return null;
  const [whole, fraction = ""] = text.split(".");
  return BigInt(whole) * 100n + BigInt((fraction + "00").slice(0, 2));
}

function formatCents(value: bigint): string {
  const whole = value / 100n;
  const fraction = String(value % 100n).padStart(2, "0");
  return `${whole}.${fraction}`;
}

function itemTotal(item: PurchaseOrderAction['items'][number]): string {
  const stickMode = item.purchase_unit === 'stick';
  const price = decimalCents(stickMode ? item.unit_price_rub_per_stick : item.unit_price_rub_per_box);
  const quantity = stickMode ? (item.quantity_sticks ?? item.quantity) : item.box_quantity;
  // 待复核的数量不能参与采购总额推算。
  if (price === null || quantity === null || quantity === undefined || !Number.isInteger(quantity) || quantity < 0) return "—";
  return formatCents(price * BigInt(quantity));
}

/** 采购卡只允许一次付款、一次整单到货；表单输入与动作状态彼此隔离。 */
export default function PurchaseAction({
  purchases,
  rubAccounts,
  businessDate,
  onPay = (id, payload) => payPurchaseOrder(id, payload),
  onReceive = (id, payload) => receivePurchaseOrder(id, payload),
  onCancel = (id, payload) => cancelPurchaseOrder(id, payload),
  onReverseReceive = (id, payload) => reverseReceivedPurchaseOrder(id, payload),
  onChanged,
}: PurchaseActionProps) {
  const activeRubAccounts = useMemo(
    () => rubAccounts.filter(account => account.currency === 'RUB' && account.is_active),
    [rubAccounts],
  );
  const [inputs, setInputs] = useState<Record<number, PurchaseInputs>>({});
  const [states, setStates] = useState<Record<number, ActionState>>({});
  const [reverseVisible, setReverseVisible] = useState<Record<number, boolean>>({});

  const inputFor = (id: number): PurchaseInputs => inputs[id] || emptyInputs(businessDate);
  const stateFor = (id: number): ActionState => states[id] || initialActionState();

  const updateInput = (id: number, patch: Partial<PurchaseInputs>) => {
    setInputs(previous => ({ ...previous, [id]: { ...inputFor(id), ...patch } }));
  };

  const run = async (
    purchase: PurchaseOrderAction,
    operation: () => Promise<unknown> | unknown,
  ) => {
    const id = purchase.id;
    setStates(previous => ({
      ...previous,
      [id]: reduceActionState(stateFor(id), { type: 'loading' }),
    }));
    try {
      const result = await operation();
      setStates(previous => ({
        ...previous,
        [id]: reduceActionState(stateFor(id), { type: 'success', result }),
      }));
      onChanged?.();
    } catch (error) {
      const parsed = errorFor(error);
      setStates(previous => ({
        ...previous,
        [id]: reduceActionState(stateFor(id), {
          type: parsed.conflict ? 'conflict' : 'error',
          code: parsed.code,
          message: parsed.message,
        }),
      }));
    }
  };

  const pay = (purchase: PurchaseOrderAction) => {
    const input = inputFor(purchase.id);
    const accountId = selectActiveAccountId(rubAccounts, input.accountId);
    if (!accountId || !input.businessDate) return;
    const payload: PurchasePayPayload = {
      rub_account_id: accountId, business_date: input.businessDate,
    };
    void run(purchase, () => onPay(purchase.id, payload));
  };

  const receive = (purchase: PurchaseOrderAction) => {
    const input = inputFor(purchase.id);
    if (!input.businessDate) return;
    const payload: PurchaseReceivePayload = { business_date: input.businessDate, note: input.note };
    void run(purchase, () => onReceive(purchase.id, payload));
  };

  const cancel = (purchase: PurchaseOrderAction) => {
    const input = inputFor(purchase.id);
    const payload: PurchaseCancelPayload = {
      expected_version: purchase.version, note: input.note,
    };
    void run(purchase, () => onCancel(purchase.id, payload));
  };

  const reverseReceive = (purchase: PurchaseOrderAction) => {
    const input = inputFor(purchase.id);
    const note = input.note.trim();
    if (!input.businessDate || !note) {
      setStates(previous => ({
        ...previous,
        [purchase.id]: reduceActionState(stateFor(purchase.id), { type: 'error', code: 'input_error', message: '撤销原因不能为空' }),
      }));
      return;
    }
    void run(purchase, () => onReverseReceive(purchase.id, { business_date: input.businessDate, note }));
  };

  return (
    <section tabIndex={-1} data-guide="accounting-actions-purchase" className="rounded-2xl border border-[#E8E0D6] bg-[#FAF8F5] p-5 text-[#2C2416]">
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-[0.18em] text-[#8A7E6E]">Purchase</p>
          <h2 className="text-xl font-semibold">采购付款与到货</h2>
          <p className="mt-1 text-sm text-[#8A7E6E]">付款只从卢布账户扣除；到货按整单创建库存批次。</p>
        </div>
        <span className="rounded-full bg-[#F5EFE8] px-3 py-1 text-xs text-[#7A1F2E]">RUB</span>
      </div>
      {purchases.length === 0 ? (
        <p className="rounded-xl border border-dashed border-[#E8E0D6] p-4 text-sm text-[#8A7E6E]">暂无待处理采购单</p>
      ) : (
        <div className="space-y-4">
          {purchases.map(purchase => {
            const input = inputFor(purchase.id);
            const state = stateFor(purchase.id);
            const boxes = purchase.items.reduce<number | null>((sum, item) => {
              if (item.purchase_unit === 'stick') return sum;
              if (sum === null || item.box_quantity === null || item.box_quantity === undefined || item.packaging_status === 'review_required' || item.review_required) return null;
              return sum + item.box_quantity;
            }, 0);
            const boxesLabel = boxes === null ? '待复核' : `${boxes} 盒`;
            const packagingReviewRequired = purchase.items.some(item => item.packaging_status === 'review_required' || item.review_required || (item.purchase_unit === 'stick' ? item.quantity_sticks == null && item.quantity == null : item.box_quantity == null));
            const accountId = selectActiveAccountId(rubAccounts, input.accountId);
            const calculatedTotal = purchase.items.reduce<bigint | null>((sum, item) => {
              const row = decimalCents(itemTotal(item));
              return sum === null || row === null ? null : sum + row;
            }, 0n);
            const total = purchase.rub_total ?? (calculatedTotal === null ? null : formatCents(calculatedTotal));
            const busy = state.status === 'loading';
            const reverseOpen = Boolean(reverseVisible[purchase.id]);
            return (
              <article key={purchase.id} className="rounded-xl border border-[#E8E0D6] bg-white p-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <strong>{purchase.order_number || `采购单 #${purchase.id}`}</strong>
                    <span className="ml-2 text-sm text-[#8A7E6E]">{purchase.status === 'draft' ? '草稿' : purchase.status === 'in_transit' ? '在途' : purchase.status}</span>
                  </div>
                  <div className="text-right text-sm"><span className="text-[#8A7E6E]">RUB 合计 </span><strong>{money(total, 'RUB')}</strong></div>
                </div>
                <div className="mt-3 divide-y divide-[#E8E0D6]">
                  {purchase.items.map((item, index) => (
                    <div key={item.id || `${purchase.id}-${index}`} className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm">
                      <span>{item.cigar_name || `雪茄 #${item.cigar_id}`}</span>
                      <span className="text-[#8A7E6E]">{item.packaging_status === 'review_required' || item.review_required ? '待复核' : item.purchase_unit === 'stick' ? `${item.quantity_sticks ?? item.quantity ?? '待补'} 支 × ${money(item.unit_price_rub_per_stick, 'RUB')}（按支，到货入散支库存）` : item.box_quantity == null ? '待复核' : `${item.box_quantity} 盒 × ${money(item.unit_price_rub_per_box, 'RUB')}（每盒 ${item.box_size} 支）`}</span>
                    </div>
                  ))}
                </div>
                <div className="mt-2 flex flex-wrap gap-3 text-xs text-[#8A7E6E]">
                  <span>canonical 盒数：{boxesLabel}</span>
                  <span>付款金额：按采购单 RUB 合计</span>
                  {packagingReviewRequired && <span role="status" className="text-[#7A1F2E]">包装待复核：后端 packaging gate 会阻止付款/到货</span>}
                </div>
                {purchase.status === 'received' && !reverseOpen ? <div className="mt-4 flex justify-end border-t border-[#E8E0D6] pt-3"><button data-guide="accounting-purchase-reverse-reveal" type="button" onClick={() => setReverseVisible(previous => ({ ...previous, [purchase.id]: true }))} className="text-xs text-[#8A7E6E] underline decoration-dotted underline-offset-4 hover:text-[#7A1F2E]">显示撤销到货</button></div> : <div className="mt-4 grid gap-3 sm:grid-cols-[1fr_1fr_1fr_auto] sm:items-end">
                  <label className="text-sm">业务日期<input data-guide={purchase.status === 'received' ? 'accounting-purchase-reverse-date' : 'accounting-purchase-date'} type="date" value={input.businessDate} onChange={event => updateInput(purchase.id, { businessDate: event.target.value })} className="mt-1 block w-full rounded-lg border border-[#E8E0D6] p-2" /></label>
                  {purchase.status === 'draft' ? (
                    <label className="text-sm">卢布账户<select data-guide="accounting-purchase-account" value={accountId ? String(accountId) : ''} onChange={event => updateInput(purchase.id, { accountId: event.target.value })} className="mt-1 block w-full rounded-lg border border-[#E8E0D6] bg-white p-2"><option value="">选择账户</option>{activeRubAccounts.map(account => <option key={account.id} value={account.id}>{account.name}</option>)}</select></label>
                  ) : <label className="text-sm">{purchase.status === 'received' ? '撤销原因' : '备注'}<input data-guide={purchase.status === 'received' ? 'accounting-purchase-reverse-reason' : 'accounting-purchase-note'} value={input.note} onChange={event => updateInput(purchase.id, { note: event.target.value })} className="mt-1 block w-full rounded-lg border border-[#E8E0D6] p-2" /></label>}
                  {purchase.status === 'draft' && <label className="text-sm">备注<input data-guide="accounting-purchase-note" value={input.note} onChange={event => updateInput(purchase.id, { note: event.target.value })} className="mt-1 block w-full rounded-lg border border-[#E8E0D6] p-2" /></label>}
                  <div className="flex gap-2 sm:justify-end">
                    {purchase.status === 'draft' ? <><span data-guide="accounting-purchase-pay"><button type="button" disabled={busy || !accountId || !input.businessDate} onClick={() => pay(purchase)} className="rounded-lg bg-[#7A1F2E] px-3 py-2 text-sm text-white disabled:opacity-50">{busy ? '处理中…' : '付款'}</button></span><button type="button" disabled={busy} onClick={() => cancel(purchase)} className="rounded-lg border border-[#7A1F2E] px-3 py-2 text-sm text-[#7A1F2E] disabled:opacity-50">取消</button></> : purchase.status === 'in_transit' ? <span data-guide="accounting-purchase-receive"><button type="button" disabled={busy || !input.businessDate} onClick={() => receive(purchase)} className="rounded-lg bg-[#7A1F2E] px-3 py-2 text-sm text-white disabled:opacity-50">{busy ? '处理中…' : '整单到货'}</button></span> : purchase.status === 'received' ? <><button type="button" disabled={busy} onClick={() => setReverseVisible(previous => ({ ...previous, [purchase.id]: false }))} className="rounded-lg border border-[#E8E0D6] px-3 py-2 text-sm text-[#8A7E6E] disabled:opacity-50">收起</button><span data-guide="accounting-purchase-reverse-submit"><button type="button" disabled={busy || !input.businessDate || !input.note.trim()} onClick={() => reverseReceive(purchase)} className="rounded-lg border border-[#7A1F2E] px-3 py-2 text-sm text-[#7A1F2E] disabled:opacity-50">{busy ? '处理中…' : '确认撤销到货'}</button></span></> : null}
                  </div>
                </div>}
                {state.status === 'success' && <p role="status" className="mt-3 text-sm text-green-700">已提交</p>}
                {(state.status === 'error' || state.status === 'conflict') && <p role="alert" className="mt-3 text-sm text-[#7A1F2E]">{state.status === 'conflict' ? '数据已被另一位经营者更新，请刷新后重试。' : state.error?.message}</p>}
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}
