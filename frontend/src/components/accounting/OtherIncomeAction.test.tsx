// @vitest-environment jsdom
import { installIncomeTestLocks } from '../../features/accounting/incomeTestLocks';
installIncomeTestLocks();

import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import OtherIncomeAction from './OtherIncomeAction';
import { incomeCreateScope, writeIncomeRequest } from '../../features/accounting/incomeRequests';

afterEach(() => { cleanup(); localStorage.clear(); });
const accounts = [
  { id: 1, name: '公司人民币', currency: 'CNY', custodian_id: null, is_active: true },
  { id: 2, name: '公司卢布', currency: 'RUB', custodian_id: null, is_active: true },
  { id: 3, name: '停用卢布', currency: 'RUB', custodian_id: null, is_active: false },
];
const fill = (rub = false) => {
  if (rub) fireEvent.change(screen.getByLabelText('收款币种'), { target: { value: 'RUB' } });
  fireEvent.change(screen.getByLabelText(`到账金额（${rub ? 'RUB' : 'CNY'}）`), { target: { value: rub ? '11000.00' : '100.01' } });
  fireEvent.change(screen.getByLabelText('来源说明'), { target: { value: '公司本月结息' } });
  if (rub) {
    fireEvent.change(screen.getByLabelText('业务日汇率（1 CNY = X RUB）'), { target: { value: '11.00000000' } });
    fireEvent.change(screen.getByLabelText('汇率来源'), { target: { value: '业务日银行报价' } });
  }
};

describe('其他收入登记', () => {
  it('重新打开后恢复原请求确认，不能误填新收入', async () => {
    const payload = { category: 'interest' as const, fund_account_id: 2, amount: '11000.00', exchange_rate: '11', rate_source: '银行报价', business_date: '2026-10-30', note: '尚未确认的结息' };
    await expect(writeIncomeRequest(incomeCreateScope, payload, async () => { throw new Error('timeout'); })).rejects.toThrow();
    const submit = vi.fn().mockResolvedValue({ id: 1 });
    render(<OtherIncomeAction accounts={accounts} businessDate="2026-11-02" submit={submit} />);
    const dialog = screen.getByRole('dialog');
    expect(within(dialog).getByText('2026-10-30')).toBeTruthy();
    expect(within(dialog).getByText('尚未确认的结息')).toBeTruthy();
    fireEvent.click(within(dialog).getByRole('button', { name: '重试本次入账' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(submit).toHaveBeenCalledExactlyOnceWith(payload);
  });
  it('卢布预览、账户过滤、确认快照、成功清空金额', async () => {
    const submit = vi.fn().mockResolvedValue({ id: 1 });
    const onChanged = vi.fn();
    render(<OtherIncomeAction accounts={accounts} businessDate="2026-11-02" submit={submit} onChanged={onChanged} />);
    fill(true);
    expect(screen.queryByRole('option', { name: /停用卢布/ })).toBeNull();
    expect((screen.getByLabelText('公司收款账户') as HTMLSelectElement).value).toBe('2');
    expect(screen.getByText('11,000.00 RUB ÷ 11.00000000 = ¥1,000.00')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: '核对收入' }));
    expect(submit).not.toHaveBeenCalled();
    const dialog = screen.getByRole('dialog', { name: '确认其他收入' });
    expect(within(dialog).getByText('1 CNY = 11.00000000 RUB')).toBeTruthy();
    fireEvent.click(within(dialog).getByRole('button', { name: '返回修改' }));
    expect(screen.getByDisplayValue('11000.00')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: '核对收入' }));
    fireEvent.click(screen.getByRole('button', { name: '确认收入并入账' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(submit).toHaveBeenCalledExactlyOnceWith({ category: 'interest', subcategory: 'bank_interest', recognition_confirmed: false, fund_account_id: 2, amount: '11000.00', business_date: '2026-11-02', exchange_rate: '11.00000000', rate_source: '业务日银行报价', note: '公司本月结息', reference: '', zero_book_value_confirmed: false });
    expect((screen.getByLabelText('到账金额（RUB）') as HTMLInputElement).value).toBe('');
    expect(onChanged).toHaveBeenCalledTimes(1);
  });

  it('超时后锁定原内容，重复点击只发一次，原内容重试成功', async () => {
    let reject: (error: Error) => void = () => {};
    const submit = vi.fn().mockImplementationOnce(() => new Promise((_, fail) => { reject = fail; })).mockResolvedValueOnce({ id: 1 });
    render(<OtherIncomeAction accounts={accounts} businessDate="2026-11-02" submit={submit} />);
    fill();
    fireEvent.click(screen.getByRole('button', { name: '核对收入' }));
    const confirm = screen.getByRole('button', { name: '确认收入并入账' });
    fireEvent.click(confirm); fireEvent.click(confirm);
    expect(submit).toHaveBeenCalledTimes(1);
    reject(new Error('网络超时'));
    await screen.findByRole('button', { name: '重试本次入账' });
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.getByRole('dialog')).toBeTruthy();
    expect((screen.getByRole('button', { name: '返回修改' }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole('button', { name: '重试本次入账' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(submit.mock.calls[0][0]).toEqual(submit.mock.calls[1][0]);
  });

  it('旧物需账面价值确认；人民币不提交卢布汇率，业务拒绝允许修改', async () => {
    const submit = vi.fn().mockRejectedValue({ isAxiosError: true, response: { status: 409, data: { error: '该收入日期已被确认对账覆盖' } } });
    render(<OtherIncomeAction accounts={accounts} businessDate="2026-11-02" submit={submit} />);
    fill(true);
    fireEvent.change(screen.getByLabelText('收款币种'), { target: { value: 'CNY' } });
    fireEvent.change(screen.getByLabelText('一级分类'), { target: { value: 'disposal' } });
    expect((screen.getByRole('button', { name: '核对收入' }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(screen.getByRole('button', { name: '核对收入' }));
    fireEvent.click(screen.getByRole('button', { name: '确认收入并入账' }));
    await within(screen.getByRole('dialog')).findByRole('alert');
    expect(submit.mock.calls[0][0]).toMatchObject({ category: 'used_item', fund_account_id: 1, zero_book_value_confirmed: true });
    expect(submit.mock.calls[0][0]).not.toHaveProperty('exchange_rate');
    fireEvent.click(screen.getByRole('button', { name: '返回修改' }));
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('两级联动重置确认，投资利息归其他收益，确认快照保留细分', async () => {
    const submit = vi.fn().mockResolvedValue({ id: 1 });
    render(<OtherIncomeAction accounts={accounts} businessDate="2026-11-02" submit={submit} />);
    fill();
    fireEvent.change(screen.getByLabelText('一级分类'), { target: { value: 'services' } });
    expect((screen.getByLabelText('二级明细') as HTMLSelectElement).value).toBe('storage_service');
    const verify = screen.getByRole('button', { name: '核对收入' }) as HTMLButtonElement;
    expect(verify.disabled).toBe(true);
    fireEvent.click(screen.getByRole('checkbox'));
    expect(verify.disabled).toBe(false);
    fireEvent.change(screen.getByLabelText('二级明细'), { target: { value: 'commission' } });
    expect(verify.disabled).toBe(true);
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.change(screen.getByLabelText('一级分类'), { target: { value: 'investment' } });
    expect(verify.disabled).toBe(true);
    fireEvent.change(screen.getByLabelText('二级明细'), { target: { value: 'investment_interest' } });
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(verify);
    expect(within(screen.getByRole('dialog')).getByText('投资收益')).toBeTruthy();
    expect(within(screen.getByRole('dialog')).getByText('投资利息')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: '确认收入并入账' }));
    await waitFor(() => expect(submit).toHaveBeenCalledTimes(1));
    expect(submit.mock.calls[0][0]).toMatchObject({ category: 'other', subcategory: 'investment_interest', recognition_confirmed: true });
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect((screen.getByRole('checkbox') as HTMLInputElement).checked).toBe(false);
  });

  it.each([['financial', 'fx_gain'], ['disposal', 'asset_disposal'], ['subsidies', 'asset_subsidy'], ['investment', 'investment_disposal']])('复杂类别 %s/%s 不能提交', (group, item) => {
    const submit = vi.fn();
    render(<OtherIncomeAction accounts={accounts} businessDate="2026-11-02" submit={submit} />);
    fill();
    fireEvent.change(screen.getByLabelText('一级分类'), { target: { value: group } });
    fireEvent.change(screen.getByLabelText('二级明细'), { target: { value: item } });
    expect((screen.getByRole('button', { name: '核对收入' }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.queryByRole('checkbox')).toBeNull();
    fireEvent.submit(screen.getByLabelText('一级分类').closest('form')!);
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(submit).not.toHaveBeenCalled();
  });

  it.each(['interest', 'used_item', 'other'] as const)('旧版 %s 被拒绝后保留原字段并要求主动选择细分', async category => {
    const payload = { category, fund_account_id: 2, amount: '11000.00', business_date: '2026-10-30', note: '旧版请求', exchange_rate: '11', rate_source: '银行报价', reference: '原凭证', zero_book_value_confirmed: category === 'used_item' };
    await expect(writeIncomeRequest(incomeCreateScope, payload, async () => { throw new Error('timeout'); })).rejects.toThrow();
    const submit = vi.fn().mockRejectedValue({ isAxiosError: true, response: { status: 400, data: { error: '请选择有效的收入一级分类和二级明细' } } });
    render(<OtherIncomeAction accounts={accounts} businessDate="2026-11-02" submit={submit} />);
    expect(within(screen.getByRole('dialog')).getByText(`${{ interest: '存款利息', used_item: '旧物出售', other: '其他收益' }[category]}（历史未细分）`)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: '重试本次入账' }));
    await within(screen.getByRole('dialog')).findByRole('alert');
    expect(submit).toHaveBeenCalledExactlyOnceWith(payload);
    fireEvent.click(screen.getByRole('button', { name: '返回修改' }));
    expect(screen.queryByRole('dialog')).toBeNull();
    expect((screen.getByLabelText('二级明细') as HTMLSelectElement).value).toBe('');
    expect((screen.getByLabelText('一级分类') as HTMLSelectElement).value).toBe({ interest: 'financial', used_item: 'disposal', other: 'other' }[category]);
    expect((screen.getByLabelText('公司收款账户') as HTMLSelectElement).value).toBe('2');
    expect(screen.getByDisplayValue('11000.00')).toBeTruthy();
    expect(screen.getByDisplayValue('2026-10-30')).toBeTruthy();
    expect(screen.getByDisplayValue('旧版请求')).toBeTruthy();
    expect(screen.getByDisplayValue('银行报价')).toBeTruthy();
    expect(screen.getByDisplayValue('原凭证')).toBeTruthy();
    expect((screen.getByRole('button', { name: '核对收入' }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(screen.getByLabelText('二级明细'), { target: { value: { interest: 'bank_interest', used_item: 'used_item_sale', other: 'other_gain' }[category] } });
    if (category !== 'interest') {
      expect((screen.getByRole('checkbox') as HTMLInputElement).checked).toBe(false);
      fireEvent.click(screen.getByRole('checkbox'));
    }
    fireEvent.click(screen.getByRole('button', { name: '核对收入' }));
    expect(within(screen.getByRole('dialog')).getByText('2026-10-30')).toBeTruthy();
  });
});
