import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import type { MonthlyProfitReport } from '../../types';
import MonthlyProfitSummary from './MonthlyProfitSummary';

const report: MonthlyProfitReport = {
  period_start: '2026-08-01', period_end: '2026-08-31',
  sales_revenue_cny: '-1000.00', customer_transport_revenue_cny: '-20.00',
  cost_of_goods_sold_cny: '400.00', transport_expense_cny: '80.00',
  transport_settlement_expense_cny: '20.00',
  salary_expense_cny: '100.00', rent_expense_cny: '60.00',
  utilities_expense_cny: '20.00', professional_expense_cny: '30.00',
  interest_expense_cny: '40.00', other_expense_cny: '10.00',
  inventory_adjustment_gain_cny: '0.00', inventory_adjustment_loss_cny: '0.00',
  reconciliation_gain_cny: '0.00', reconciliation_loss_cny: '0.00',
  net_profit_cny: '450.00', transaction_count: 8,
};

describe('月度经营总结', () => {
  it('客户人肉费并入销售收入，实际人肉成本以负数展示', () => {
    const html = renderToStaticMarkup(<MonthlyProfitSummary profit={report} month="2026-08" />);
    expect(html).toContain('2026年8月经营总结');
    expect(html).toContain('¥260.00');
    expect(html).not.toContain('客户人肉费收入');
    expect(html).toContain('¥1,020.00');
    expect(html).toContain('商品成本');
    expect(html).not.toContain('FIFO');
    expect(html).toContain('人肉成本');
    expect(html).toContain('-¥100.00');
    expect(html).toContain('¥450.00');
  });

  it('退款和费用冲正保留符号，不误计为新增收入或成本', () => {
    const reversed: MonthlyProfitReport = {
      ...report,
      sales_revenue_cny: '50.00', customer_transport_revenue_cny: '10.00',
      cost_of_goods_sold_cny: '-20.00',
      transport_expense_cny: '-30.00', transport_settlement_expense_cny: '10.00',
      salary_expense_cny: '-50.00', rent_expense_cny: '10.00',
      utilities_expense_cny: '0.00', professional_expense_cny: '0.00',
      interest_expense_cny: '0.00', other_expense_cny: '0.00',
    };
    const html = renderToStaticMarkup(<MonthlyProfitSummary profit={reversed} month="2026-08" />);

    expect(html).toMatch(/销售收入<\/p><p[^>]*>-¥60\.00<\/p>/);
    expect(html).toMatch(/商品成本<\/p><p[^>]*>-¥20\.00<\/p>/);
    expect(html).toMatch(/经营费用<\/p><p[^>]*>-¥40\.00<\/p>/);
    expect(html).toMatch(/人肉成本<\/p><p[^>]*>¥20\.00<\/p>/);
  });
});
