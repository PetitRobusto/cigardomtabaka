// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
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
    operating_expense_breakdown: { salary_cny: '10.00', rent_cny: '0.00', transport_cny: '0.00', professional_services_cny: '0.00', financial_cny: '0.00', other_cny: '0.00' },
    core_operating_profit_cny: '90.00', inventory_adjustment_cny: '0.00', reconciliation_adjustment_cny: '0.00', net_operating_profit_cny: '90.00',
  },
  cash: { sales_receipts_cny: '150.00', refunds_cny: '10.00', net_receipts_cny: '140.00', accounts_receivable_cny: '40.00', customer_prepayments_cny: '20.00' },
  inventory: {
    opening_cost_cny: '200.00', received_cost_cny: '50.00', product_cost_consumed_cny: '70.00', adjustment_net_cny: '0.00', closing_cost_cny: '180.00', average_cost_cny: '190.00', monthly_turnover_rate: '0.3684',
    warnings: { status: 'unavailable', reason: '历史商品级月末库存成本尚无独立业务日期快照', items: [] },
  },
  customers: { fulfilled_customer_count: 1, new_customer_count: 1, repeat_customer_count: 1, new_customer_rate: '1.0000', repeat_customer_rate: '1.0000', fulfilled_order_count: 2, average_order_revenue_cny: '95.00', identified_customer_revenue_cny: '190.00', guest_orders_excluded: true },
  rankings: {
    default_sort: 'sales_profit_cny', allocation_rule: '测试分摊规则', unallocated_human_cost_cny: '0.00',
    brands: [{ key: 'Cohiba', name: '高希霸', net_sales_revenue_cny: '190.00', quantity: 2, product_cost_cny: '70.00', human_cost_cny: '20.00', sales_profit_cny: '100.00', sales_profit_rate: '0.5263' }],
    products: [{ key: 1, name: '高希霸 罗布图', net_sales_revenue_cny: '190.00', quantity: 2, product_cost_cny: '70.00', human_cost_cny: '20.00', sales_profit_cny: '100.00', sales_profit_rate: '0.5263' }],
    customers: [{ key: 1, name: '王先生', net_sales_revenue_cny: '190.00', quantity: 2, product_cost_cny: '70.00', human_cost_cny: '20.00', sales_profit_cny: '100.00', sales_profit_rate: '0.5263' }],
  },
  metrics: { sales_revenue_cny: '190.00', sales_profit_cny: '100.00', core_operating_profit_cny: '90.00', net_operating_profit_cny: '90.00' },
  comparison: {
    mode: 'full_previous_month', previous_period_start: '2026-07-01', previous_period_end: '2026-07-31',
    metrics: { sales_revenue_cny: comparison, sales_profit_cny: comparison, core_operating_profit_cny: comparison, net_operating_profit_cny: comparison },
  },
  conclusions: [{ code: 'sales_margin', status: 'available', metric_keys: ['profit.sales_profit_cny'], text: '本月销售利润 ¥100.00，利润率 52.6%。' }],
};

function renderReport(value: MonthlyBusinessReport = report) {
  return render(<MemoryRouter><MonthlyBusinessReportPanel report={value} month="2026-08" /></MemoryRouter>);
}

describe('经营月报', () => {
  it('只展示三个主指标，成本使用正数，并隐藏内部字段名', () => {
    renderReport();

    expect(screen.getAllByText('净销售收入').length).toBeGreaterThan(0);
    expect(screen.getAllByText('销售利润').length).toBeGreaterThan(0);
    expect(screen.getAllByText('经营净利润').length).toBeGreaterThan(0);
    expect(screen.queryByText('核心经营利润')).toBeNull();
    expect(screen.queryByText('-¥20.00')).toBeNull();
    expect(screen.getAllByText('¥20.00').length).toBeGreaterThan(0);
    expect(screen.queryByText('profit.sales_profit_cny')).toBeNull();
  });

  it('费用构成默认收起，展开后展示明细及三类经营贡献入口', () => {
    renderReport();

    expect(within(screen.getByRole('heading', { name: '成本构成' }).parentElement as HTMLElement).getByText('运输（含打车）')).toBeTruthy();
    expect(screen.queryByText('水电')).toBeNull();
    expect(screen.getByRole('img', { name: /成本合计环形图/ })).toBeTruthy();
    const expenseSummary = screen.getByText('查看经营费用构成');
    expect(expenseSummary.closest('details')?.open).toBe(false);
    fireEvent.click(expenseSummary);
    expect(expenseSummary.closest('details')?.open).toBe(true);
    expect(screen.getByRole('img', { name: /费用合计环形图/ })).toBeTruthy();
    const overallSalaryColor = (within(screen.getByRole('heading', { name: '成本构成' }).parentElement as HTMLElement).getByText('工资').previousElementSibling as HTMLElement).style.backgroundColor;
    const expenseSalaryColor = (within(expenseSummary.closest('details') as HTMLElement).getByText('工资').previousElementSibling as HTMLElement).style.backgroundColor;
    expect(expenseSalaryColor).toBe(overallSalaryColor);
    expect(screen.getAllByText('运输（含打车）')).toHaveLength(2);
    expect(screen.getByText('高希霸')).toBeTruthy();
    expect(screen.getByText('品牌贡献')).toBeTruthy();
    expect(screen.getByText('商品贡献')).toBeTruthy();
    expect(screen.getByText('客户贡献')).toBeTruthy();
    expect(screen.getByRole('link', { name: /查看完整经营贡献排行/ }).getAttribute('href')).toBe('/accounting/reports/contributions?month=2026-08');
  });

  it('成本构成直接包含经营费用大项，不重复计入费用总额', () => {
    renderReport({
      ...report,
      profit: {
        ...report.profit,
        operating_expenses_cny: '60.00',
        operating_expense_breakdown: {
          salary_cny: '10.00', rent_cny: '10.00', transport_cny: '10.00',
          professional_services_cny: '10.00', financial_cny: '10.00', other_cny: '10.00',
        },
      },
    });

    const costCard = screen.getByRole('heading', { name: '成本构成' }).parentElement as HTMLElement;
    expect(within(costCard).getByRole('img', { name: '成本合计环形图，合计¥150.00' })).toBeTruthy();
    for (const label of ['商品成本', '人肉成本', '工资', '房租', '运输（含打车）', '专业服务', '财务费用', '其他']) {
      expect(within(costCard).getByText(label)).toBeTruthy();
    }
    expect(within(costCard).queryByText('经营费用')).toBeNull();
    const swatches = [...costCard.querySelectorAll('span[style*="background-color"]')];
    expect(new Set(swatches.map(swatch => swatch.getAttribute('style'))).size).toBe(8);
  });

  it('总览图先显示总成本和利润，再展开成本结构', () => {
    renderReport();

    const overviewHeading = screen.getByRole('heading', { name: '成本与利润占比' });
    const overview = overviewHeading.closest('section') as HTMLElement;
    expect(within(overview).getByRole('img', { name: '净销售收入环形图，合计¥190.00' })).toBeTruthy();
    const costRow = within(overview).getByText('总成本').parentElement as HTMLElement;
    expect(within(costRow).getByText('¥100.00')).toBeTruthy();
    expect(within(costRow).getByText('52.6%')).toBeTruthy();
    const profitRow = within(overview).getByText('经营净利润').parentElement as HTMLElement;
    expect(within(profitRow).getByText('¥90.00')).toBeTruthy();
    expect(within(profitRow).getByText('47.4%')).toBeTruthy();
    expect(overviewHeading.compareDocumentPosition(screen.getByRole('heading', { name: '成本结构' })) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('库存调整只影响实际净利润，不混进收入分配图', () => {
    renderReport({ ...report, profit: { ...report.profit, inventory_adjustment_cny: '-2.00', net_operating_profit_cny: '88.00' } });

    const overview = screen.getByRole('heading', { name: '成本与利润占比' }).closest('section') as HTMLElement;
    expect(within(overview).getByRole('img', { name: '净销售收入环形图，合计¥190.00' })).toBeTruthy();
    expect(within(overview).getByText('调整前经营利润')).toBeTruthy();
    expect(within(overview).getByText(/经营净利润为 ¥88\.00/)).toBeTruthy();
  });

  it('亏损和负成本时不把负数绘成正数扇区', () => {
    const lossProfit = { ...report.profit, sales_revenue_cny: '80.00', core_operating_profit_cny: '-20.00', net_operating_profit_cny: '-20.00' };
    const { rerender } = renderReport({ ...report, profit: lossProfit });

    expect(screen.queryByRole('img', { name: /净销售收入环形图/ })).toBeNull();
    expect(screen.getByText(/总成本 ¥100\.00 · 经营净利润 -¥20\.00/)).toBeTruthy();

    rerender(<MemoryRouter><MonthlyBusinessReportPanel report={{ ...report, profit: { ...lossProfit, inventory_adjustment_cny: '-5.00', net_operating_profit_cny: '-25.00' } }} month="2026-08" /></MemoryRouter>);
    expect(screen.getByText(/总成本 ¥100\.00 · 调整前经营利润 -¥20\.00/)).toBeTruthy();
    expect(screen.getByText(/经营净利润为 -¥25\.00/)).toBeTruthy();

    rerender(<MemoryRouter><MonthlyBusinessReportPanel report={{ ...report, profit: { ...report.profit, sales_revenue_cny: '10.00', product_cost_cny: '-20.00', human_cost_cny: '0.00', operating_expenses_cny: '0.00', core_operating_profit_cny: '30.00', net_operating_profit_cny: '30.00' } }} month="2026-08" /></MemoryRouter>);
    expect(screen.queryByRole('img', { name: /净销售收入环形图/ })).toBeNull();
    expect(screen.getByText(/总成本 -¥20\.00 · 经营净利润 ¥30\.00/)).toBeTruthy();

    rerender(<MemoryRouter><MonthlyBusinessReportPanel report={{ ...report, profit: { ...report.profit, sales_revenue_cny: '0.00', product_cost_cny: '0.00', human_cost_cny: '0.00', operating_expenses_cny: '0.00', core_operating_profit_cny: '0.00', net_operating_profit_cny: '0.00' } }} month="2026-08" /></MemoryRouter>);
    expect(screen.queryByRole('img', { name: /净销售收入环形图/ })).toBeNull();
    expect(screen.getByText(/净销售收入非正/)).toBeTruthy();

    rerender(<MemoryRouter><MonthlyBusinessReportPanel report={{ ...report, profit: { ...report.profit, sales_revenue_cny: '191.00' } }} month="2026-08" /></MemoryRouter>);
    expect(screen.queryByRole('img', { name: /净销售收入环形图/ })).toBeNull();
    expect(screen.getByText(/金额未对齐/)).toBeTruthy();
  });

  it('客户结构同时展示订单、客单价、复购覆盖与客户贡献', () => {
    renderReport();

    expect(screen.getByText('履约订单')).toBeTruthy();
    expect(screen.getByText('平均订单金额')).toBeTruthy();
    expect(screen.getByText('¥95.00')).toBeTruthy();
    expect(screen.getByText('覆盖履约客户 100.0%')).toBeTruthy();
    expect(screen.getByText('已识别客户销售额')).toBeTruthy();
    expect(screen.getByText('客户贡献前三名')).toBeTruthy();
    expect(screen.getAllByText('王先生').length).toBeGreaterThan(0);
  });

  it('零成本不会显示负零', () => {
    renderReport({ ...report, profit: { ...report.profit, human_cost_cny: '-0.00' } });
    expect(screen.queryByText('-¥0.00')).toBeNull();
  });

  it('有调整时在经营净利润卡中展开调整前金额', () => {
    renderReport({ ...report, profit: { ...report.profit, inventory_adjustment_cny: '-2.00', net_operating_profit_cny: '88.00' } });
    expect(screen.getAllByText('调整前经营利润').length).toBeGreaterThan(0);
    expect(screen.getAllByText('库存调整').length).toBeGreaterThan(0);
  });

  it('费用冲正不会被取绝对值后误画成新增成本', () => {
    renderReport({
      ...report,
      profit: {
        ...report.profit,
        operating_expenses_cny: '-30.00',
        operating_expense_breakdown: {
          ...report.profit.operating_expense_breakdown,
          salary_cny: '0.00',
          transport_cny: '-30.00',
        },
      },
    });

    fireEvent.click(screen.getByText('查看经营费用构成'));
    expect(screen.getByRole('img', { name: '费用合计环形图，合计¥0.00' })).toBeTruthy();
    expect(screen.getByText(/本月包含成本冲正/)).toBeTruthy();
  });
});
