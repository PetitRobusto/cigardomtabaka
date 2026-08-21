import type { FundAccount, PurchaseActionItem, PurchaseActionCreatePayload } from '../types';

export type PurchaseStatus = 'draft' | 'in_transit' | 'received' | 'cancelled' | string;

export const PURCHASE_STATUS_LABELS: Record<string, string> = {
  draft: '草稿',
  in_transit: '待到货',
  received: '已到货',
  cancelled: '已取消',
};

export const PURCHASE_STATUS_FILTERS = [
  { value: '', label: '全部订单' },
  { value: 'draft', label: PURCHASE_STATUS_LABELS.draft },
  { value: 'in_transit', label: PURCHASE_STATUS_LABELS.in_transit },
  { value: 'received', label: PURCHASE_STATUS_LABELS.received },
  { value: 'cancelled', label: PURCHASE_STATUS_LABELS.cancelled },
] as const;

export function purchaseStatusLabel(status: PurchaseStatus): string {
  return PURCHASE_STATUS_LABELS[status] || status;
}

export function canEditPurchase(status: PurchaseStatus): boolean {
  return status === 'draft';
}

export function canCancelPurchase(status: PurchaseStatus): boolean {
  return status === 'draft';
}

export function canReceivePurchase(status: PurchaseStatus): boolean {
  return status === 'in_transit';
}

export function canReverseReceivePurchase(status: PurchaseStatus): boolean {
  return status === 'received';
}

export type PurchaseActionName = 'pay' | 'edit' | 'cancel' | 'receive' | 'reverse_receive';

export function purchaseActionMenu(status: PurchaseStatus): {
  primary: PurchaseActionName[];
  more: PurchaseActionName[];
} {
  if (status === 'draft') return { primary: ['pay', 'edit', 'cancel'], more: [] };
  if (status === 'in_transit') return { primary: ['receive'], more: [] };
  // Receipt reversal is a low-frequency, destructive action and must not be primary.
  if (status === 'received') return { primary: [], more: ['reverse_receive'] };
  return { primary: [], more: [] };
}

export interface PurchaseDraftFormValue {
  supplier_id?: number | null;
  business_date?: string | null;
  items?: PurchaseActionItem[];
  note?: string | null;
}

/** Drafts deliberately carry nullable/incomplete fields; strict checks belong to payment. */
export function buildPurchaseDraftPayload(value: PurchaseDraftFormValue): PurchaseActionCreatePayload {
  return {
    supplier_id: value.supplier_id ?? null,
    business_date: value.business_date || null,
    items: value.items || [],
    note: value.note || '',
  };
}

export function selectPurchaseRubAccountId(
  accounts: FundAccount[],
  candidate: number | string | null | undefined,
): number | '' {
  const active = accounts.filter(account => account.currency === 'RUB' && account.is_active);
  const id = Number(candidate);
  return active.some(account => account.id === id) ? id : (active[0]?.id ?? '');
}
