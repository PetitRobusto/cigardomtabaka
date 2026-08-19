import { useState } from 'react';
import { ArrowLeftRight, ClipboardCheck, HandCoins, PackageCheck, ReceiptText } from 'lucide-react';
import type {
  AccountingActionsResponse,
  AccountingApiError,
  DividendAction,
  ExpenseActionPayload,
  FundAccount,
  PurchaseAction as PurchaseOrderAction,
} from '../../types';
import { apiErrorMessage, exchangeToRub, recordExpense } from '../../api';
import ExchangeAction from './ExchangeAction';
import PurchaseAction from './PurchaseAction';
import ExpenseAction from './ExpenseAction';
import DividendActionCard from './DividendAction';
import { formatOriginalAmount } from '../sales/salesState';
export type AccountingActionKind = 'exchange' | 'purchase' | 'expense' | 'dividend';

export interface AccountingActionCenterProps {
  accounts: FundAccount[];
  summaryAccounts?: FundAccount[];
  actions?: AccountingActionsResponse;
  purchases?: PurchaseOrderAction[];
  dividends?: DividendAction[];
  businessDate: string;
  /** 动作列表查询独立于 dashboard；失败只在中心显示。 */
  loading?: boolean;
  error?: string | AccountingApiError;
  actionsLoading?: boolean;
  actionsError?: string | AccountingApiError;
  onChanged?: () => void;
  initialAction?: AccountingActionKind;
  onOpenReconciliation?: () => void;
}

function hasValue(value: string | null | undefined): value is string {
  return value !== null && value !== undefined && value.trim() !== '';
}

function accountAmount(account: FundAccount): { value: string; currency: string } | null {
  if (hasValue(account.original_balance)) return { value: formatOriginalAmount(account.original_balance, account.currency), currency: account.currency };
  if (hasValue(account.cny_book_cost)) return { value: account.cny_book_cost, currency: '人民币账面成本' };
  return null;
}

function actionErrorMessage(error: string | AccountingApiError | null | undefined): string | null {
  if (!error) return null;
  return typeof error === 'string' ? error : apiErrorMessage(error, '账务动作列表加载失败');
}

/** 低频账务动作共用一个区域，避免多个表单长期占用页面。 */
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
  initialAction = 'exchange',
  onOpenReconciliation,
}: AccountingActionCenterProps) {
  const [activeAction, setActiveAction] = useState<AccountingActionKind>(initialAction);
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

  const actionButtons = [
    { id: 'exchange' as const, label: '换汇', Icon: ArrowLeftRight, count: 0 },
    { id: 'purchase' as const, label: '采购', Icon: PackageCheck, count: actionPurchases.length },
    { id: 'expense' as const, label: '记录费用', Icon: ReceiptText, count: 0 },
    { id: 'dividend' as const, label: '分红', Icon: HandCoins, count: actionDividends.length },
  ];

  const actionPanel = {
    exchange: <ExchangeAction accounts={accounts} businessDate={businessDate} submit={submitExchange} />,
    purchase: <PurchaseAction purchases={actionPurchases} rubAccounts={accounts} businessDate={businessDate} onChanged={onChanged} />,
    expense: <ExpenseAction accounts={accounts} businessDate={businessDate} submit={submitExpense} />,
    dividend: <DividendActionCard accounts={accounts} draft={actionDividends[0] || null} businessDate={businessDate} onChanged={onChanged} />,
  }[activeAction];

  return (
    <section aria-labelledby="accounting-actions-title" className="mb-7 w-full overflow-hidden rounded-md border border-border bg-white shadow-sm">
      <div className="grid gap-4 px-5 py-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,2fr)] lg:items-start">
        <div>
          <h2 id="accounting-actions-title" className="font-display text-lg font-semibold">记录经营动作</h2>
          <p className="mt-1 text-xs text-muted">选择一种动作，只展开当前需要填写的表单。</p>
        </div>
        <div className="min-w-0 text-xs text-muted lg:max-w-none lg:justify-self-end lg:text-right">
          <span className="font-semibold text-fg">当前账户</span>
          {accountsWithAmount.length > 0 ? (
            <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1">
              {accountsWithAmount.map(account => { const amount = accountAmount(account); return <span key={account.id}>{account.name} · <span className="font-mono text-fg">{amount?.value} {amount?.currency}</span></span>; })}
            </div>
          ) : <p className="mt-1">当前接口未提供余额，不在此处推算。</p>}
        </div>
      </div>
      <div aria-label="账务操作" className="flex overflow-x-auto border-y border-border px-2 sm:px-5">
        {actionButtons.map(({ id, label, Icon, count }) => <button key={id} type="button" aria-pressed={activeAction === id} onClick={() => setActiveAction(id)} className={`inline-flex min-w-fit items-center gap-2 border-b-2 px-4 py-3 text-sm ${activeAction === id ? 'border-accent font-semibold text-accent' : 'border-transparent text-muted hover:bg-[#FFFCF9] hover:text-fg'}`}><Icon className="h-4 w-4" />{label}{count > 0 && <span className="min-w-5 rounded-full bg-accent-light px-1.5 py-0.5 text-center text-[10px] font-bold text-accent">{count}</span>}</button>)}
        <button data-guide="accounting-reconciliation-open" type="button" onClick={onOpenReconciliation} className="inline-flex min-w-fit items-center gap-2 border-b-2 border-transparent px-4 py-3 text-sm text-muted hover:bg-[#FFFCF9] hover:text-fg"><ClipboardCheck className="h-4 w-4" />账户对账</button>
      </div>
      <div className="bg-[#FFFDFA] p-4 sm:p-5">
        {isLoading && <p role="status" className="mb-4 rounded border border-border bg-white px-4 py-3 text-sm text-muted">正在加载待处理账务动作…</p>}
        {listError && <p role="alert" className="mb-4 rounded border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{listError}</p>}
        <div role="region" aria-live="polite">{actionPanel}</div>
      </div>
    </section>
  );
}
