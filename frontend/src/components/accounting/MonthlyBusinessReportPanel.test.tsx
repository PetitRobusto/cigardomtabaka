// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import type { MonthlyBusinessReport } from '../../types';
import MonthlyBusinessReportPanel from './MonthlyBusinessReportPanel';

afterEach(cleanup);

const comparison = {
  current_cny: '100.00', previous_cny: '0.00', delta_cny: '100.00',
  change_rate: null, status: 'new' as const,
};

const report: MonthlyBusinessReport = {
  period: { month: '2026-08', period_start: '2026-08-01', period_end: '2026-08-31', is_current_month: false, business_date_cutoff: '2026-08-31' },
  sales: { fulfilled_sales_revenue_cny: '190.00', return_reduction_cny: '0.00', net_sales_revenue_cny: '190.00', fulfillment_order_count: 2, return_order_count: 0 },
  profit: {
    sales_revenue_cny: '190.00', product_cost_cny: '70.00', human_cost_cny: '20.00',
    sales_profit_cny: '100.00', sales_profit_rate: '0.5263', operating_expenses_cny: '10.00',
    operating_expense_breakdown: { salary_cny: '10.00', rent_cny: '0.00', utilities_cny: '0.00', professional_services_cny: '0.00', financial_cny: '0.00', other_cny: '0.00' },
    core_operating_profit_cny: '90.00', inventory_adjustment_cny: '0.00', reconciliation_adjustment_cny: '0.00', net_operating_profit_cny: '90.00',
  },
  cash: { sales_receipts_cny: '150.00', refunds_cny: '10.00', net_receipts_cny: '140.00', accounts_receivable_cny: '40.00', customer_prepayments_cny: '20.00' },
  inventory: {
    opening_cost_cny: '200.00', received_cost_cny: '50.00', product_cost_consumed_cny: '70.00', adjustment_net_cny: '0.00', closing_cost_cny: '180.00', average_cost_cny: '190.00', monthly_turnover_rate: '0.3684',
    warnings: { status: 'unavailable', reason: '历史商品级月末库存成本尚无独立业务日期快照', items: [] },
  },
  customers: { fulfilled_customer_count: 1, new_customer_count: 1, repeat_customer_count: 1, guest_orders_excluded: true },
  rankings: {
    default_sort: 'sales_profit_cny', allocation_rule: '测试分摊规则', unallocated_human_cost_cny: '0.00',
    brands: [{ key: 'Cohiba', name: 'Cohiba', net_sales_revenue_cny: '190.00', quantity: 2, product_cost_cny: '70.00', human_cost_cny: '20.00', sales_profit_cny: '100.00', sales_profit_rate: '0.5263' }],
    products: [{ key: 1, name: 'Cohiba Robustos', net_sales_revenue_cny: '190.00', quantity: 2, product_cost_cny: '70.00', human_cost_cny: '20.00', sales_profit_cny: '100.00', sales_profit_rate: '0.5263' }],
    customers: [{ key: 1, name: '王先生', net_sales_revenue_cny: '190.00', quantity: 2, product_cost_cny: '70.00', human_cost_cny: '20.00', sales_profit_cny: '100.00', sales_profit_rate: '0.5263' }],
  },
  metrics: { sales_revenue_cny: '190.00', sales_profit_cny: '100.00', core_operating_profit_cny: '90.00', net_operating_profit_cny: '90.00' },
  comparison: {
    mode: 'full_previous_month', previous_period_start: '2026-07-01', previous_period_end: '2026-07-31',
    metrics: { sales_revenue_cny: comparison, sales_profit_cny: comparison, core_operating_profit_cny: comparison, net_operating_profit_cny: comparison },
  },
  conclusions: [{ code: 'sales_margin', status: 'available', metric_keys: ['profit.sales_profit_cny'], text: '销售利润可核验。' }],
};

describe('经营月报', () => {
  it('展示完整利润层级、负数人肉成本和独立回款区', () => {
    render(<MonthlyBusinessReportPanel report={report} month="2026-08" />);

    expect(screen.getByRole('heading', { name: '2026年8月经营月报' })).toBeTruthy();
    expect(screen.getAllByText('净销售收入').length).toBeGreaterThan(0);
    expect(screen.getAllByText('销售利润').length).toBeGreaterThan(0);
    expect(screen.getByText('核心经营利润')).toBeTruthy();
    expect(screen.getByText('经营净利润')).toBeTruthy();
    expect(screen.getAllByText('较上月新增')).toHaveLength(4);
    expect(screen.getAllByText('-¥20.00').length).toBeGreaterThan(0);
    expect(screen.getByText('回款与占款')).toBeTruthy();
    expect(screen.getByText('客户收款')).toBeTruthy();
    expect(screen.getByText('客户收款净额')).toBeTruthy();
    expect(screen.getByText('客户预收款')).toBeTruthy();
    expect(screen.queryByText(/FIFO/)).toBeNull();
    expect(screen.queryByText('客户人肉费收入')).toBeNull();
  });

  it('可切换品牌、商品和客户排行', () => {
    render(<MonthlyBusinessReportPanel report={report} month="2026-08" />);

    expect(screen.getByText('Cohiba')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: '商品' }));
    expect(screen.getByText('Cohiba Robustos')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: '客户' }));
    expect(screen.getByText('王先生')).toBeTruthy();
  });

  it('解释本期入账高于履约归属的人肉成本差额', () => {
    render(<MonthlyBusinessReportPanel
      report={{ ...report, rankings: { ...report.rankings, unallocated_human_cost_cny: '15.00' } }}
      month="2026-08"
    />);

    expect(screen.getByText(/本期入账与履约归属的人肉成本差额：¥15.00/)).toBeTruthy();
    expect(screen.getByText(/正数表示本期入账较多/)).toBeTruthy();
  });
});
