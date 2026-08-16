import type { FundAccount } from '../../types';

// 对账表单仅在没有当前选择时回退到首个 active 账户，保持原 effect 语义。
export function selectReconciliationAccountId(
  accounts: Pick<FundAccount, 'id' | 'is_active'>[],
  candidate: number,
): number {
  return candidate || accounts.find(account => account.is_active)?.id || 0;
}
