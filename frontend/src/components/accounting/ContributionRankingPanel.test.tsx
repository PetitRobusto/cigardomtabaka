// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import type { MonthlyBusinessReport } from '../../types';
import ContributionRankingPanel from './ContributionRankingPanel';

afterEach(cleanup);

const row = (key: string | number, name: string) => ({
  key, name, net_sales_revenue_cny: '190.00', quantity: 2,
  product_cost_cny: '70.00', human_cost_cny: '-0.00',
  sales_profit_cny: '120.00', sales_profit_rate: '0.6316',
});

const report = {
  rankings: {
    default_sort: 'sales_profit_cny', allocation_rule: '人肉成本按履约归属',
    unallocated_human_cost_cny: '-0.00',
    brands: [row('Cohiba', '高希霸')],
    products: [row(1, '高希霸 罗布图')],
    customers: [row(2, '王先生')],
  },
} as MonthlyBusinessReport;

describe('经营贡献排行', () => {
  it('使用中文品牌、正数成本，并可切换到独立商品排行', () => {
    render(<ContributionRankingPanel report={report} />);

    expect(screen.getAllByText('高希霸').length).toBeGreaterThan(0);
    expect(screen.queryByText('-¥0.00')).toBeNull();
    expect(screen.queryByText(/尚未分摊/)).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: '商品' }));
    expect(screen.getAllByText('高希霸 罗布图').length).toBeGreaterThan(0);
  });
});
