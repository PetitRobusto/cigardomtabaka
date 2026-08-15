import type { AccountingActionsResponse, AccountingApiError, DividendAction, ExpenseActionPayload, FundAccount, PurchaseAction } from '../../types';
import { apiErrorMessage, exchangeToRub, recordExpense } from '../../api';
import ExchangeAction from './ExchangeAction';
import PurchaseAction from './PurchaseAction';
import ExpenseAction from './ExpenseAction';
import DividendActionCard from './DividendAction';

export interface AccountingActionCenterProps {
  accounts: FundAccount[];
  summaryAccounts?: FundAccount[];
  actions?: AccountingActionsResponse;
  purchases?: PurchaseAction[];
  dividends?: DividendAction[];
  businessDate: string;
  /** 动作列表查询独立于 dashboard；失败只在中心显示。 */
  loading?: boolean;
  error?: string | AccountingApiError;
  actionsLoading?: boolean;
  actionsError?: string | AccountingApiError;
  onChanged?: () => void;
}

function hasValue(value: string | null | undefined): value is string {
  return value !== null && value !== undefined && value.trim() !== '';
}

function accountAmount(account: FundAccount): { value: string; currency: string } | null {
  if (hasValue(account.original_balance)) return { value: account.original_balance, currency: account.currency };
  if (hasValue(account.cny_book_cost)) return { value: account.cny_book_cost, currency: 'CNY book cost' };
  return null;
}

function actionErrorMessage(error: string | AccountingApiError | null | undefined): string | null {
  if (!error) return null;
  return typeof error === 'string' ? error : apiErrorMessage(error, '账务动作列表加载失败');
}

/** 账务动作中心采用全宽双列卡片，摘要只展示接口确实提供的字段。 */
export default function AccountingActionCenter({
  accounts,
  summaryAccounts,
  actions,
  purchases = [],
  dividends = [],
  businessDate,
  loading = false,
  error,
  actionsLoading,
  actionsError,
  onChanged,
}: AccountingActionCenterProps) {
  const isLoading = actionsLoading ?? loading;
  const actionPurchases = actions?.purchases ?? purchases;
  const actionDividends = actions?.dividends ?? dividends;
  const listError = actionErrorMessage(actionsError ?? error);
  const activeAccounts = (summaryAccounts ?? accounts).filter(account => account.is_active);
  const accountsWithAmount = activeAccounts.filter(account => accountAmount(account) !== null);

  const submitExchange = async (payload: Parameters<typeof exchangeToRub>[0]) => {
    const result = await exchangeToRub(payload);
    onChanged?.();
    return result;
  };
  const submitExpense = async (payload: ExpenseActionPayload) => {
    const result = await recordExpense(payload);
    onChanged?.();
    return result;
  };

  return (
    <section aria-labelledby="accounting-actions-title" className="mb-7 w-full">
      <div className="mb-4 flex flex-col gap-4 rounded-md border border-border bg-[#FFFDFA] p-5 shadow-sm lg:flex-row lg:items-start lg:justify-between">
        <div>
          <p className="text-[11px] font-bold uppercase tracking-[.12em] text-accent">Action center</p>
          <h2 id="accounting-actions-title" className="mt-1 font-display text-2xl font-semibold">经营动作</h2>
          <p className="mt-1 text-sm text-muted">先记录实际资金动作，再由下方报表刷新库存成本、利润和对账。</p>
        </div>
        <div className="grid min-w-0 gap-2 text-xs text-muted sm:grid-cols-2 lg:min-w-[28rem]">
          <div className="rounded border border-border bg-white px-3 py-2">
            <span className="block uppercase tracking-wider">资产构成</span>
            {accountsWithAmount.length > 0 ? (
              <div className="mt-1 space-y-0.5 text-fg">
                {accountsWithAmount.map(account => { const amount = accountAmount(account); return <p key={account.id}>{account.name} · {amount?.value} {amount?.currency}</p>; })}
              </div>
            ) : <p className="mt-1">当前接口未提供余额，不在此处推算。</p>}
          </div>
          <div className="rounded border border-border bg-white px-3 py-2">
            <span className="block uppercase tracking-wider">费用分类规则</span>
            <p className="mt-1 text-fg">工资从 CNY；房租、水电和其他经营费用从 RUB。分类金额以费用流水和月报为准。</p>
          </div>
        </div>
      </div>
      {isLoading && <p role="status" className="mb-4 rounded border border-border bg-white px-4 py-3 text-sm text-muted">正在加载待处理账务动作…</p>}
      {listError && <p role="alert" className="mb-4 rounded border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{listError}</p>}
      <div className="grid w-full gap-5 xl:grid-cols-2">
        <ExchangeAction accounts={accounts} businessDate={businessDate} submit={submitExchange} />
        <PurchaseAction purchases={actionPurchases} rubAccounts={accounts} businessDate={businessDate} onChanged={onChanged} />
        <ExpenseAction accounts={accounts} businessDate={businessDate} submit={submitExpense} />
        <DividendActionCard accounts={accounts} draft={actionDividends[0] || null} businessDate={businessDate} onChanged={onChanged} />
      </div>
    </section>
  );
}
