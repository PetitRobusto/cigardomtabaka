import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import ExpenseDetails from './ExpenseDetails';

describe('费用明细列表', () => {
  it('显示分类、明细、金额、账户和备注', () => {
    const html = renderToStaticMarkup(<ExpenseDetails month="2026-08" expenses={[{
      id: 1, category: 'other', category_label: '其他', subcategory: 'transport_taxi',
      subcategory_label: '交通 / 物流 · 打车', fund_account_id: 2, fund_account_name: '人民币账户',
      currency: 'CNY', original_amount: '25.00', amount_cny: '25.00', business_date: '2026-08-25',
      operator_id: 1, status: 'posted', note: '去仓库取货', reversed: false, reversal_transaction_id: null, reversal_business_date: null,
    }]} />);
    expect(html).toContain('费用明细');
    expect(html).toContain('交通 / 物流 · 打车');
    expect(html).toContain('人民币账户');
    expect(html).toContain('去仓库取货');
    expect(html).toContain('¥25.00');
  });

  it('空列表显示月份提示', () => {
    const html = renderToStaticMarkup(<ExpenseDetails month="2026-08" expenses={[]} />);
    expect(html).toContain('本月还没有已入账费用');
  });
});
