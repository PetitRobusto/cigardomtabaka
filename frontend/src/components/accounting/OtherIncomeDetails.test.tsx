// @vitest-environment jsdom
import { installIncomeTestLocks } from '../../features/accounting/incomeTestLocks';
installIncomeTestLocks();

import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import OtherIncomeDetails from './OtherIncomeDetails';
import type { OtherIncome, OtherIncomesResponse } from '../../types';
import { incomeReverseScope, writeIncomeRequest } from '../../features/accounting/incomeRequests';

const api = vi.hoisted(() => ({ fetchOtherIncome: vi.fn(), reverseOtherIncome: vi.fn() }));
vi.mock('../../api', async importOriginal => ({ ...await importOriginal<typeof import('../../api')>(), ...api }));
afterEach(() => { cleanup(); localStorage.clear(); });
beforeEach(() => vi.clearAllMocks());
const income: OtherIncome = { id: 12, category: 'interest', category_label: '存款利息', fund_account_id: 2, fund_account_name: '公司卢布', currency: 'RUB', amount: '11000.00', amount_cny: '1000.00', exchange_rate: '11.00000000', rate_source: '银行报价', reference: '回单123', business_date: '2026-08-12', note: '公司结息', operator_id: 1, agent_source: '', ledger_transaction_id: 22, status: 'posted', reversal: null };
const reversal = { id: 3, income_id: 12, business_date: '2026-09-02', note: '重复登记', operator_id: 1, agent_source: '', ledger_transaction_id: 23 };
const data: OtherIncomesResponse = { incomes: [income], reversals: [], summary: { received_cny: '1000.00', reversed_cny: '0.00', net_cny: '1000.00' }, count: 1, reversal_count: 0, page: 1, next_page: null };

describe('其他收入明细与冲正', () => {
  it('列表和详情显示两级分类，旧记录显示历史未细分', async () => {
    const classified = { ...income, subcategory: 'term_interest', income_group_label: '利息与汇兑', subcategory_label: '定期存款利息' };
    api.fetchOtherIncome.mockResolvedValue(classified);
    const view = render(<OtherIncomeDetails month="2026-08" data={{ ...data, incomes: [classified] }} loading={false} page={1} onPageChange={vi.fn()} onChanged={vi.fn()} />);
    expect(screen.getByText('利息与汇兑')).toBeTruthy();
    expect(screen.getByText('定期存款利息')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: '收入 12 详情' }));
    expect(await within(screen.getByRole('dialog')).findByText('定期存款利息')).toBeTruthy();
    expect(within(screen.getByRole('dialog')).getByText('利息与汇兑')).toBeTruthy();
    view.unmount();
    render(<OtherIncomeDetails month="2026-08" data={data} loading={false} page={1} onPageChange={vi.fn()} onChanged={vi.fn()} />);
    expect(screen.getByText('存款利息（历史未细分）')).toBeTruthy();
  });
  it('刷新后即使详情已显示冲正，也可按原请求重试并确认结果', async () => {
    const payload = { business_date: '2026-09-02', note: '重复登记' };
    await expect(writeIncomeRequest(incomeReverseScope(12), payload, async () => { throw new Error('timeout'); })).rejects.toThrow();
    api.fetchOtherIncome.mockResolvedValue({ ...income, status: 'reversed', reversal });
    api.reverseOtherIncome.mockResolvedValue({ ...income, status: 'reversed', reversal });
    render(<OtherIncomeDetails month="2026-08" data={data} loading={false} page={1} onPageChange={vi.fn()} onChanged={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: '收入 12 详情' }));
    await screen.findByLabelText('冲正原因');
    expect((screen.getByLabelText('冲正原因') as HTMLTextAreaElement).value).toBe('重复登记');
    fireEvent.click(screen.getByRole('button', { name: '重试本次冲正' }));
    await screen.findByText('冲正已入账，原收入记录保留。');
    expect(api.reverseOtherIncome).toHaveBeenCalledExactlyOnceWith(12, payload);
  });
  it('冲正月份单列负向流水，点击可追溯原月份收入及汇率', async () => {
    api.fetchOtherIncome.mockResolvedValue({ ...income, status: 'reversed', reversal });
    render(<OtherIncomeDetails month="2026-09" data={{ ...data, incomes: [], reversals: [{ ...reversal, ...{ category_label: income.category_label, fund_account_name: income.fund_account_name, currency: income.currency, amount: income.amount, amount_cny: income.amount_cny, income_business_date: income.business_date } }], summary: { received_cny: '0.00', reversed_cny: '1000.00', net_cny: '-1000.00' } }} loading={false} page={1} onPageChange={vi.fn()} onChanged={vi.fn()} />);
    expect(screen.getByText('原收入日期 2026-08-12')).toBeTruthy();
    expect(screen.getByText('−11,000.00 RUB')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: '冲正 3 详情' }));
    await screen.findByText('1 CNY = 11.00000000 RUB');
    expect(api.fetchOtherIncome).toHaveBeenCalledWith(12);
    expect(screen.getByText('回单123')).toBeTruthy();
    expect(screen.queryByRole('button', { name: '冲正收入' })).toBeNull();
  });

  it('冲正先确认原金额与原因；超时锁定内容并复用请求，成功更新明细', async () => {
    api.fetchOtherIncome.mockResolvedValue(income);
    api.reverseOtherIncome.mockRejectedValueOnce(new Error('网络超时')).mockResolvedValueOnce({ ...income, status: 'reversed', reversal });
    const onChanged = vi.fn();
    render(<OtherIncomeDetails month="2026-08" data={data} loading={false} page={1} onPageChange={vi.fn()} onChanged={onChanged} />);
    fireEvent.click(screen.getByRole('button', { name: '收入 12 详情' }));
    fireEvent.click(await screen.findByRole('button', { name: '冲正收入' }));
    expect(api.reverseOtherIncome).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText('冲正日期'), { target: { value: '2026-09-02' } });
    fireEvent.change(screen.getByLabelText('冲正原因'), { target: { value: '重复登记' } });
    fireEvent.click(screen.getByRole('button', { name: '确认冲正并入账' }));
    await screen.findByRole('button', { name: '重试本次冲正' });
    expect((screen.getByLabelText('冲正原因') as HTMLTextAreaElement).disabled).toBe(true);
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.getByRole('dialog')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: '重试本次冲正' }));
    await within(screen.getByRole('dialog')).findByText('冲正已入账，原收入记录保留。');
    expect(api.reverseOtherIncome.mock.calls[0]).toEqual(api.reverseOtherIncome.mock.calls[1]);
    expect(onChanged).toHaveBeenCalledTimes(1);
  });

  it('后续流水拒绝直接冲正，错误保留且不刷新成功状态', async () => {
    api.fetchOtherIncome.mockResolvedValue(income);
    api.reverseOtherIncome.mockRejectedValue({ isAxiosError: true, response: { status: 409, data: { error: '收款账户已有后续资金流水，不能直接冲正收入' } } });
    const onChanged = vi.fn();
    render(<OtherIncomeDetails month="2026-08" data={data} loading={false} page={1} onPageChange={vi.fn()} onChanged={onChanged} />);
    fireEvent.click(screen.getByRole('button', { name: '收入 12 详情' }));
    fireEvent.click(await screen.findByRole('button', { name: '冲正收入' }));
    fireEvent.change(screen.getByLabelText('冲正原因'), { target: { value: '复核' } });
    fireEvent.click(screen.getByRole('button', { name: '确认冲正并入账' }));
    await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('后续资金流水'));
    expect(onChanged).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: '返回详情' }));
    expect(screen.getByRole('dialog', { name: '收入详情' })).toBeTruthy();
  });
});
