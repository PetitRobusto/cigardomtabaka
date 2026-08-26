import { describe, expect, it, vi } from 'vitest';
import { salesFundAccountError, salesOrderActionBusinessDate, salesOrderFinancialView, salesOrderItemCostView, selectActiveCnyAccountId } from './SalesOrderCard.logic';
import { salesActionBlockedByAccount } from './salesState';
import type { SalesOrder, SalesOrderItem } from '../../types';

const itemWithReservation = (overrides: Partial<SalesOrderItem> = {}): SalesOrderItem => ({
  id: 1, cigar_id: 2, cigar_name: '测试雪茄', quantity: 2, sale_unit: 'stick', sale_quantity: 2,
  box_size: null, unit_price: 100, unit_cost: 0, revenue: 200, cost: 0, profit: 0,
  fulfillment_type: 'in_stock', allocations: [{ id: 1, batch_id: 10, quantity: 2, status: 'reserved', cost_cny: 60 }], ...overrides,
});

const financialOrder = (overrides: Partial<SalesOrder> = {}): SalesOrder => ({
  id: 1, order_number: 'SO-000001', status: 'pending_payment', display_status: '待出库', fulfillment_status: 'confirmed', payment_status: 'unpaid',
  customer_id: null, customer_name: '测试客户', goods_amount_cny: 200, customer_transport_fee_cny: 20, transport_payer: 'customer', amount_due_cny: 220,
  total_revenue: 200, total_cost: 0, total_profit: 0, fifo_cost: 0, contribution_profit: 0, actual_transport_cost_cny: 0, locked: true,
  created_at: null, confirmed_at: null, cancelled_at: null, note: '', items: [itemWithReservation()], payment_notes: [],
  sales_shipment: null, sales_receipt: null, sales_refund: null, sales_transport_cost: null, available_actions: ['ship', 'receive', 'cancel'], ...overrides,
});

describe('sales account error boundary', () => {
  it('blocks only fund-account actions while accounts are unavailable', () => {
    expect(salesActionBlockedByAccount('receive', '账户加载失败')).toBe(true);
    expect(salesActionBlockedByAccount('transport_cost', '账户加载失败')).toBe(true);
    expect(salesActionBlockedByAccount('ship', '账户加载失败')).toBe(false);
    expect(salesActionBlockedByAccount('receive', '')).toBe(false);
  });
});

describe('销售动作业务日期', () => {
  it('在 UTC 已跨日但 Moscow 尚未跨日时仍返回 Moscow 业务日', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-08-13T23:00:00.000Z'));
    expect(salesOrderActionBusinessDate()).toBe('2026-08-14');
    vi.useRealTimers();
  });
});

describe('销售动作账户刷新', () => {
  it('当前 CNY 账户停用后替换为 active CNY，且没有可用账户时清空', () => {
    const accounts = [
      { id: 10, name: '已停用', currency: 'CNY', is_active: false },
      { id: 20, name: '有效 CNY', currency: 'CNY', is_active: true },
      { id: 30, name: '有效 RUB', currency: 'RUB', is_active: true },
    ];
    expect(selectActiveCnyAccountId(accounts, 10)).toBe(20);
    expect(selectActiveCnyAccountId(accounts, 999)).toBe(20);
    expect(selectActiveCnyAccountId([], 10)).toBe(0);
  });

  it('接受界面已派生出的回退账户，只在完全没有账户时阻止资金动作', () => {
    expect(salesFundAccountError('receive', 20)).toBe('');
    expect(salesFundAccountError('transport_cost', 0)).toContain('有效的 CNY');
    expect(salesFundAccountError('ship', 0)).toBe('');
  });
});

describe('订单成本与贡献利润展示口径', () => {
  it('已确认未出库按预留批次显示预计成本和预计贡献利润', () => {
    const order = financialOrder();
    expect(salesOrderItemCostView(order, order.items[0])).toMatchObject({ basis: 'estimated', totalCost: 60, unitCost: 30, label: '预计成本' });
    expect(salesOrderFinancialView(order)).toMatchObject({ basis: 'estimated', totalCost: 60, contributionProfit: 160, profitLabel: '预计贡献利润' });
  });

  it('已收款但未出库仍然是预计利润，预售或未完整分配时不伪造零成本', () => {
    expect(salesOrderFinancialView(financialOrder({ payment_status: 'paid' })).profitLabel).toBe('预计贡献利润');
    const incomplete = financialOrder({ items: [itemWithReservation({ allocations: [] })] });
    expect(salesOrderFinancialView(incomplete)).toMatchObject({ basis: 'unavailable', totalCost: null, contributionProfit: null });
  });

  it('已出库即使未收款也显示实际贡献利润', () => {
    const order = financialOrder({ fulfillment_status: 'shipped', fifo_cost: 61, contribution_profit: 149, available_actions: ['return', 'receive'], items: [itemWithReservation({ cost: 61, unit_cost: 30.5, profit: 139, allocations: [{ id: 1, batch_id: 10, quantity: 2, status: 'fulfilled', cost_cny: 61 }] })] });
    expect(salesOrderFinancialView(order)).toMatchObject({ basis: 'actual', totalCost: 61, contributionProfit: 149, costLabel: '实际商品成本', profitLabel: '订单贡献利润' });
  });

  it('已退货不再显示有效贡献利润，仅保留原出库成本追溯', () => {
    const order = financialOrder({ fulfillment_status: 'returned', fifo_cost: 60, contribution_profit: 160, sales_return: { id: 2, amount_cny: 220, fifo_cost_cny: 60, business_date: '2026-08-20', reason: '退货' } });
    expect(salesOrderFinancialView(order)).toMatchObject({ basis: 'reversed', totalCost: 60, contributionProfit: null, profitLabel: '贡献利润已冲销' });
  });
});
