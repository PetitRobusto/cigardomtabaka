import { describe, expect, it } from 'vitest';
import {
  actionLabel,
  activeSalesAmount,
  activeSalesProfit,
  availableActions,
  actionNeedsFundAccount,
  formatCny,
  formatOriginalAmount,
  formatSignedCny,
  initialActionAmount,
  orderDisplayStatus,
  receiveAmountMatchesDue,
  validateMoneyInput,
  validatePositiveMoneyInput,
  statusLabel,
  statusTagTone,
  summarizeSalesOrders,
  type SalesOrderSummaryInput,
} from './salesState';

describe('summarizeSalesOrders', () => {
  it('按履约和付款状态生成工作台进度摘要，并保留金额合计', () => {
    const orders: SalesOrderSummaryInput[] = [
      { fulfillment_status: 'draft', payment_status: 'unpaid', amount_due_cny: 100 },
      { fulfillment_status: 'confirmed', payment_status: 'unpaid', amount_due_cny: 200 },
      { fulfillment_status: 'shipped', payment_status: 'paid', amount_due_cny: 300 },
      { fulfillment_status: 'cancelled', payment_status: 'refunded', amount_due_cny: 50 },
      { fulfillment_status: 'cancelled', payment_status: 'unpaid', amount_due_cny: 80 },
      { fulfillment_status: 'returned', payment_status: 'unpaid', amount_due_cny: 90 },
    ];

    expect(summarizeSalesOrders(orders)).toEqual({
      total: 6,
      draft: { count: 1, amount: 100 },
      confirmed: { count: 1, amount: 200 },
      shipped: { count: 1, amount: 300 },
      paid: { count: 1, amount: 300 },
      unpaid: { count: 1, amount: 200 },
      cancelled: { count: 2, amount: 130 },
    });
  });

  it('只把已确认或已出库订单计入有效金额与预计利润', () => {
    const orders = [
      { fulfillment_status: 'draft', payment_status: 'unpaid', amount_due_cny: 100, contribution_profit: 30 },
      { fulfillment_status: 'confirmed', payment_status: 'unpaid', amount_due_cny: 200, contribution_profit: 60 },
      { fulfillment_status: 'shipped', payment_status: 'paid', amount_due_cny: 300, contribution_profit: 90 },
      { fulfillment_status: 'returned', payment_status: 'refunded', amount_due_cny: 400, contribution_profit: 120 },
    ];
    expect(activeSalesAmount(orders)).toBe(500);
    expect(activeSalesProfit(orders)).toBe(150);
  });

  it('为订单状态和动作提供中文工作台标签，并稳健格式化金额', () => {
    expect(statusLabel('refund_pending')).toBe('待退款');
    expect(statusLabel('returned')).toBe('已退货');
    expect(statusTagTone('unpaid')).toContain('amber');
    expect(statusTagTone('cancelled')).toContain('red');
    expect(statusTagTone('paid')).toContain('green');
    expect(actionLabel('transport_cost')).toBe('记录人肉成本');
    expect(actionLabel('return')).toBe('整单退货');
    expect(formatCny('1234.5')).toBe('¥1,234.50');
    expect(formatCny('bad')).toBe('¥0.00');
    expect(formatOriginalAmount('1200.00000000', 'RUB')).toBe('1,200.00');
    expect(formatOriginalAmount('12.34000000', 'USDT')).toBe('12.34');
    expect(formatSignedCny('-123.4')).toBe('-¥123.40');
    expect(formatSignedCny('123.4')).toBe('¥123.40');
  });

  it('根据履约与付款双状态决定展示状态和可用动作', () => {
    expect(orderDisplayStatus({ fulfillment_status: 'confirmed', payment_status: 'unpaid' })).toBe('待收款');
    expect(orderDisplayStatus({ fulfillment_status: 'shipped', payment_status: 'paid' })).toBe('已出库 · 已收款');
    expect(orderDisplayStatus({ fulfillment_status: 'cancelled', payment_status: 'refund_pending' })).toBe('已取消 · 待退款');
    expect(orderDisplayStatus({ fulfillment_status: 'returned', payment_status: 'refund_pending' })).toBe('已退货 · 待退款');
    expect(availableActions({ fulfillment_status: 'draft', payment_status: 'unpaid' })).toEqual(['confirm', 'cancel']);
    expect(availableActions({ fulfillment_status: 'confirmed', payment_status: 'unpaid' })).toEqual(['ship', 'cancel', 'receive']);
    expect(availableActions({ fulfillment_status: 'cancelled', payment_status: 'refund_pending' })).toEqual(['refund']);
    expect(availableActions({ fulfillment_status: 'cancelled', payment_status: 'refunded' })).toEqual([]);
    expect(availableActions({ fulfillment_status: 'shipped', payment_status: 'paid' })).toEqual(['return', 'transport_cost']);
  });

  it('草稿不进入待收款，并校验金额输入与动作默认金额', () => {
    expect(validateMoneyInput('12.34')).toBe(true);
    expect(validateMoneyInput('12.345')).toBe(false);
    expect(validateMoneyInput('-1')).toBe(false);
    expect(validateMoneyInput('Infinity')).toBe(false);
    expect(validatePositiveMoneyInput('0')).toBe(false);
    expect(validatePositiveMoneyInput('0.01')).toBe(true);
    expect(initialActionAmount('receive', 180)).toBe('180');
    expect(initialActionAmount('transport_cost', 180)).toBe('');
    expect(actionNeedsFundAccount('receive')).toBe(true);
    expect(actionNeedsFundAccount('transport_cost')).toBe(true);
    expect(actionNeedsFundAccount('confirm')).toBe(false);
    expect(actionNeedsFundAccount('ship')).toBe(false);
    expect(receiveAmountMatchesDue('180.00', 180)).toBe(true);
    expect(receiveAmountMatchesDue('179.99', 180)).toBe(false);
    expect(actionNeedsFundAccount('refund')).toBe(false);
  });

});


describe('sales business state', () => {
  it('计算人肉费承担方对应的客户费用和应收', async () => {
    const { transportSummary } = await import('./salesState');
    expect(transportSummary('customer', 1000, 80)).toEqual({ goodsAmount: 1000, customerTransport: 80, amountDue: 1080 });
    expect(transportSummary('company', 1000, 80)).toEqual({ goodsAmount: 1000, customerTransport: 0, amountDue: 1000 });
  });
  it('focus 搜索使用空 query 且只搜现货', async () => {
    const { cigarSearchParams } = await import('./salesState');
    expect(cigarSearchParams('focus')).toEqual({ q: '', stock_only: true });
    expect(cigarSearchParams('input', 'Partagas')).toEqual({ q: 'Partagas', stock_only: true });
  });
});
