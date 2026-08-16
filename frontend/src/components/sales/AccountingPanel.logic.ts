import type { FundAccount } from '../../types';

// 异步刷新后只保留仍然 active 的选择，否则回退到首个可用账户。
export function selectReconciliationAccountId(
  accounts: Pick<FundAccount, 'id' | 'is_active'>[],
  candidate: number,
): number {
  const selected = accounts.find(account => account.id === candidate && account.is_active);
  if (selected) return selected.id;
  return accounts.find(account => account.is_active)?.id || 0;
}
