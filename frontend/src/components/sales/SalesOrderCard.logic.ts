import type { FundAccount } from '../../types';
import { moscowBusinessDate } from '../../utils/businessDate';
import { actionNeedsFundAccount } from './salesState';

// 销售动作统一使用 Moscow 业务日，避免 UTC 日界造成错期。
export const salesOrderActionBusinessDate = () => moscowBusinessDate();

// 账户刷新后立即回退到 active CNY，避免动作沿用停用账户。
export const selectActiveCnyAccountId = (
  accounts: Pick<FundAccount, 'id' | 'currency' | 'is_active'>[],
  candidate?: number | null,
): number => {
  const activeCny = accounts.filter(account => account.currency === 'CNY' && account.is_active);
  const selected = activeCny.find(account => account.id === candidate);
  return selected?.id ?? activeCny[0]?.id ?? 0;
};

// 资金动作接受界面已派生的回退账户，仅在没有任何有效账户时阻止提交。
export const salesFundAccountError = (action: string, selectedAccountId: number): string => (
  actionNeedsFundAccount(action) && !selectedAccountId
    ? '请选择有效的 CNY 资金账户'
    : ''
);
