import type { FundAccount } from '../../types';

// 只从 active 账户中选择候选值，外部刷新后自动回退到首个可用账户。
export function selectActiveAccountId(accounts: FundAccount[], candidate?: number | '' | null): number | '' {
  const selected = accounts.find(account => account.is_active && account.id === candidate);
  return selected?.id ?? accounts.find(account => account.is_active)?.id ?? '';
}
