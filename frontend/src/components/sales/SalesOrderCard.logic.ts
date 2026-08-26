import type { FundAccount, SalesOrder, SalesOrderItem } from '../../types';
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

export type OrderCostBasis = 'actual' | 'estimated' | 'unavailable' | 'reversed';

export interface OrderItemCostView {
  basis: OrderCostBasis;
  totalCost: number | null;
  unitCost: number | null;
  label: string;
}

export interface OrderFinancialView {
  basis: OrderCostBasis;
  totalCost: number | null;
  contributionProfit: number | null;
  costLabel: string;
  profitLabel: string;
  note: string;
}

const finiteNumber = (value: unknown): number | null => {
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
};

const reservedItemCost = (item: SalesOrderItem): number | null => {
  const allocations = item.allocations.filter(allocation => allocation.status === 'reserved');
  if (allocations.reduce((sum, allocation) => sum + allocation.quantity, 0) !== item.quantity) return null;
  const costs = allocations.map(allocation => finiteNumber(allocation.cost_cny));
  if (costs.some(cost => cost === null)) return null;
  return costs.reduce<number>((sum, cost) => sum + (cost ?? 0), 0);
};

/** 已出库使用实际成本，已确认未出库使用预留批次的预计成本。 */
export const salesOrderItemCostView = (
  order: Pick<SalesOrder, 'fulfillment_status'>,
  item: SalesOrderItem,
): OrderItemCostView => {
  if (order.fulfillment_status === 'shipped') {
    const totalCost = finiteNumber(item.cost);
    return { basis: 'actual', totalCost, unitCost: totalCost === null ? null : totalCost / item.quantity, label: '实际成本' };
  }
  if (order.fulfillment_status === 'returned') {
    const totalCost = finiteNumber(item.cost);
    return { basis: 'reversed', totalCost, unitCost: totalCost === null ? null : totalCost / item.quantity, label: '原出库成本' };
  }
  if (order.fulfillment_status === 'confirmed') {
    const totalCost = reservedItemCost(item);
    return { basis: totalCost === null ? 'unavailable' : 'estimated', totalCost, unitCost: totalCost === null ? null : totalCost / item.quantity, label: totalCost === null ? '成本待分配' : '预计成本' };
  }
  return {
    basis: order.fulfillment_status === 'cancelled' ? 'reversed' : 'unavailable',
    totalCost: null,
    unitCost: null,
    label: order.fulfillment_status === 'cancelled' ? '已取消' : '成本待确认',
  };
};

/** 贡献利润按履约确认，而不是按收款确认；预收款不提前确认为利润。 */
export const salesOrderFinancialView = (order: SalesOrder): OrderFinancialView => {
  if (order.fulfillment_status === 'shipped') {
    const transportPending = order.available_actions.includes('transport_cost');
    return {
      basis: 'actual',
      totalCost: finiteNumber(order.fifo_cost),
      contributionProfit: finiteNumber(order.contribution_profit),
      costLabel: '实际商品成本',
      profitLabel: transportPending ? '当前贡献利润' : '订单贡献利润',
      note: transportPending
        ? '已出库，利润已确认；实际人肉成本尚未录入，录入后将扣减。'
        : order.payment_status === 'unpaid'
          ? '已出库，未收款形成应收款，不影响利润确认。'
          : '已出库，收入和商品成本已确认。',
    };
  }
  if (order.fulfillment_status === 'confirmed') {
    const itemCosts = order.items.map(item => salesOrderItemCostView(order, item).totalCost);
    const complete = itemCosts.every(cost => cost !== null);
    const totalCost = complete ? itemCosts.reduce<number>((sum, cost) => sum + (cost ?? 0), 0) : null;
    const contributionProfit = totalCost === null
      ? null
      : Number(order.amount_due_cny) - totalCost - Number(order.actual_transport_cost_cny || 0);
    return {
      basis: complete ? 'estimated' : 'unavailable',
      totalCost,
      contributionProfit,
      costLabel: '预计商品成本',
      profitLabel: '预计贡献利润',
      note: complete
        ? '基于已预留批次估算；出库时冻结实际成本，尚未发生或录入的人肉成本未计入。'
        : '部分商品尚无完整库存分配，暂时无法完整估算成本和贡献利润。',
    };
  }
  if (order.fulfillment_status === 'returned') {
    return {
      basis: 'reversed',
      totalCost: finiteNumber(order.sales_return?.fifo_cost_cny ?? order.fifo_cost),
      contributionProfit: null,
      costLabel: '原出库商品成本',
      profitLabel: '贡献利润已冲销',
      note: '订单已退货，原销售收入与成本已冲销，原成本仅供追溯。',
    };
  }
  if (order.fulfillment_status === 'cancelled') {
    return {
      basis: 'reversed', totalCost: null, contributionProfit: null,
      costLabel: '订单成本', profitLabel: '订单贡献利润',
      note: '订单已取消，不确认销售成本或贡献利润。',
    };
  }
  return {
    basis: 'unavailable', totalCost: null, contributionProfit: null,
    costLabel: '预计商品成本', profitLabel: '预计贡献利润',
    note: '草稿尚未预留库存；确认订单后才能按库存批次估算成本。',
  };
};
