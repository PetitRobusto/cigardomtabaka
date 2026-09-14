// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import ExpenseAction from './ExpenseAction';

afterEach(cleanup);
const accounts = [{ id: 1, name: '公司人民币', currency: 'CNY', custodian_id: null, is_active: true }];
const value = { amount: '120.50', business_date: '2026-09-14', note: '本月房租', fund_account_id: 1 as const };

describe('费用确认交互', () => {
  it('提交只展示快照，取消保留输入并恢复焦点，确认后才入账', async () => {
    const submit = vi.fn().mockResolvedValue({ id: 1 });
    render(<ExpenseAction accounts={accounts} category="rent" value={value} submit={submit} />);
    const trigger = screen.getByRole('button', { name: '记录费用' });
    trigger.focus();
    fireEvent.click(trigger);
    const dialog = screen.getByRole('dialog', { name: '确认记录费用' });
    expect(submit).not.toHaveBeenCalled();
    for (const text of ['房租与物业', '房租', '120.50 CNY', '公司人民币 · CNY', '2026-09-14', '本月房租']) expect(within(dialog).getByText(text)).toBeTruthy();
    expect(document.activeElement).toBe(dialog);
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(document.activeElement).toBe(trigger);
    expect(screen.getByDisplayValue('120.50')).toBeTruthy();
    fireEvent.click(trigger);
    fireEvent.click(screen.getByRole('button', { name: '确认费用并入账' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(submit).toHaveBeenCalledExactlyOnceWith({ category: 'rent', subcategory: 'rent', amount: '120.50', fund_account_id: 1, business_date: '2026-09-14', note: '本月房租' });
  });

  it('失败保留 modal 和输入可重试，同步重复点击只能发一次请求', async () => {
    let rejectRequest: (error: unknown) => void = () => undefined;
    const submit = vi.fn().mockImplementationOnce(() => new Promise((_, reject) => { rejectRequest = reject; })).mockResolvedValueOnce({ id: 1 });
    render(<ExpenseAction accounts={accounts} value={value} submit={submit} />);
    fireEvent.click(screen.getByRole('button', { name: '记录费用' }));
    const confirm = screen.getByRole('button', { name: '确认费用并入账' });
    fireEvent.click(confirm); fireEvent.click(confirm);
    expect(submit).toHaveBeenCalledTimes(1);
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.getByRole('dialog')).toBeTruthy();
    rejectRequest(new Error('余额不足'));
    await waitFor(() => expect(within(screen.getByRole('dialog')).getByRole('alert').textContent).toContain('余额不足'));
    fireEvent.click(screen.getByRole('button', { name: '确认费用并入账' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(submit).toHaveBeenCalledTimes(2);
    expect(submit.mock.calls[0][0]).toEqual(submit.mock.calls[1][0]);
  });

  it('受控状态仍有独立在途保护，外部字段变化不会改变确认快照', async () => {
    let resolve: (value: unknown) => void = () => undefined;
    const submit = vi.fn().mockImplementation(() => new Promise(done => { resolve = done; }));
    const controlled = { status: 'idle' as const, input: {} };
    const view = render(<ExpenseAction accounts={accounts} category="rent" value={value} state={controlled} submit={submit} />);
    fireEvent.click(screen.getByRole('button', { name: '记录费用' }));
    view.rerender(<ExpenseAction accounts={[{ ...accounts[0], name: '修改后的名称' }]} category="salary" value={{ ...value, amount: '999.00', note: '修改备注' }} state={controlled} submit={submit} />);
    const dialog = screen.getByRole('dialog');
    expect(within(dialog).getByText('120.50 CNY')).toBeTruthy();
    expect(within(dialog).getByText('公司人民币 · CNY')).toBeTruthy();
    const confirm = within(dialog).getByRole('button', { name: '确认费用并入账' });
    fireEvent.click(confirm); fireEvent.click(confirm);
    expect(submit).toHaveBeenCalledTimes(1);
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.getByRole('dialog')).toBeTruthy();
    resolve({ id: 1 });
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(submit.mock.calls[0][0]).toEqual({ category: 'rent', subcategory: 'rent', amount: '120.50', fund_account_id: 1, business_date: '2026-09-14', note: '本月房租' });
  });
});
