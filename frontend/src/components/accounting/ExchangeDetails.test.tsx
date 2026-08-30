import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import ExchangeDetails from './ExchangeDetails';

describe('换汇明细列表', () => {
  it('显示日期、账户、原币金额、卢布金额和实际汇率', () => {
    const html = renderToStaticMarkup(<ExchangeDetails
      month="2026-08"
      accounts={[
        { id: 1, name: '人民币账户', currency: 'CNY', custodian_id: null, is_active: true },
        { id: 2, name: '卢布账户', currency: 'RUB', custodian_id: null, is_active: true },
      ]}
      transactions={[{
        id: 9, transaction_type: 'exchange', status: 'posted', business_date: '2026-08-20',
        effective_sequence: 3, description: '', operator_id: 7,
        postings: [
          { account_id: 1, category: '', currency: 'CNY', amount: '-100.00', cny_amount: '-100.00' },
          { account_id: 2, category: '', currency: 'RUB', amount: '1200.00', cny_amount: '100.00' },
        ],
      }]}
    />);
    expect(html).toContain('换汇明细');
    expect(html).toContain('人民币账户 · CNY');
    expect(html).toContain('100.00 CNY');
    expect(html).toContain('1,200.00 RUB');
    expect(html).toContain('12.0000 RUB / 原币');
  });

  it('空列表显示月份提示', () => {
    const html = renderToStaticMarkup(<ExchangeDetails month="2026-08" transactions={[]} />);
    expect(html).toContain('2026-08 暂无换汇记录');
  });
});
