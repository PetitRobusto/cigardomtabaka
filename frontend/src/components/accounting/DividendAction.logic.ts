import type { DividendAction as DividendDraft, FundAccount } from '../../types';

export type DraftInput = {
  total: string;
  partnerA: string;
  partnerB: string;
  accountA: string;
  accountB: string;
  businessDate: string;
  note: string;
};

export function validateDividendDraft({
  draftDirty,
  accountA,
  accountB,
}: { draftDirty: boolean; accountA: number | string | null | undefined; accountB: number | string | null | undefined }) {
  if (draftDirty) return { ok: false, code: 'draft_dirty', message: '编辑已变更，请先保存分红草稿' };
  const idA = Number(accountA);
  const idB = Number(accountB);
  if (!Number.isInteger(idA) || idA <= 0 || !Number.isInteger(idB) || idB <= 0) {
    return { ok: false, code: 'account_required', message: '请选择两个人民币账户' };
  }
  if (idA === idB) return { ok: false, code: 'account_same', message: '两个合伙人必须选择不同的人民币账户' };
  return { ok: true as const };
}

export function dividendAccountOptions(accounts: FundAccount[], otherSelectedId: number | string | null | undefined) {
  const otherId = otherSelectedId == null || otherSelectedId === '' ? null : Number(otherSelectedId);
  return accounts
    .filter(account => account.currency === 'CNY' && account.is_active)
    .map(account => ({ account, disabled: account.id === otherId }));
}

// 仅在外部草稿语义变化时重置内部编辑状态，避免父组件普通重渲染丢失输入。
export function dividendActionResetKey(
  draft: DividendDraft | null,
  previewWarningFingerprint: string | undefined,
  businessDate: string,
  acknowledged: boolean,
): string {
  return JSON.stringify([draft?.id, draft?.version, previewWarningFingerprint, businessDate, acknowledged]);
}
