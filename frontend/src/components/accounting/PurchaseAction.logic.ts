import type { FundAccount } from '../../types';

// 采购付款和到货只允许使用 active RUB 账户。
export function selectActiveAccountId(
  accounts: FundAccount[],
  candidate: number | string | null | undefined,
): number | '' {
  const active = accounts.filter(account => account.currency === 'RUB' && account.is_active);
  const id = Number(candidate);
  return active.some(account => account.id === id) ? id : (active[0]?.id ?? '');
}
