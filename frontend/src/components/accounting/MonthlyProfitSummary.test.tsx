import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import type { MonthlyProfitReport } from '../../types';
import MonthlyProfitSummary from './MonthlyProfitSummary';

const report: MonthlyProfitReport = {
  period_start: '2026-08-01', period_end: '2026-08-31',
  sales_revenue_cny: '-1000.00', customer_transport_revenue_cny: '-120.00',
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
  it('展示经营费用合计和人肉净额', () => {
    const html = renderToStaticMarkup(<MonthlyProfitSummary profit={report} month="2026-08" />);
    expect(html).toContain('2026年8月经营总结');
    expect(html).toContain('¥260.00');
    expect(html).toContain('¥20.00');
    expect(html).toContain('¥450.00');
  });
});
