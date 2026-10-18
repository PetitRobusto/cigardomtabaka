// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import ExpenseDetails from './ExpenseDetails';
import type { AccountingExpense } from '../../types';

const expense: AccountingExpense = {
  id: 7, category: 'salary', category_label: '工资', subcategory: 'personnel_salary', subcategory_label: '人员费用 · 工资',
  fund_account_id: 1, fund_account_name: '公司银行', currency: 'CNY', original_amount: '15000.00000000', amount_cny: '15000.00',
  business_date: '2026-08-12', operator_id: 1, status: 'posted', note: '合伙人工资', reversed: false,
  reversal_transaction_id: null, reversal_business_date: null, refunded_amount: '0', remaining_refundable_amount: '15000', refunds: [],
};
const accounts = [
  { id: 1, name: '公司银行', currency: 'CNY', is_active: true, custodian_id: 1 },
  { id: 2, name: '公司微信', currency: 'CNY', is_active: true, custodian_id: 1 },
  { id: 3, name: '卢布账户', currency: 'RUB', is_active: true, custodian_id: 1 },
  { id: 4, name: '停用账户', currency: 'CNY', is_active: false, custodian_id: 1 },
];
afterEach(cleanup);
function openRefund() {
  const more = screen.getByLabelText('费用 7 更多操作');
  more.focus(); more.closest('details')!.open = true;
  fireEvent.click(screen.getByRole('button', { name: '登记退回' }));
  return screen.getByRole('dialog', { name: '登记费用退回' });
}
function fill(dialog: HTMLElement, amount = '3000') {
  fireEvent.change(within(dialog).getByLabelText('本次退回金额（CNY）'), { target: { value: amount } });
  fireEvent.change(within(dialog).getByLabelText('实际到账日期'), { target: { value: '2026-09-12' } });
  fireEvent.change(within(dialog).getByLabelText('收款账户'), { target: { value: '2' } });
  fireEvent.change(within(dialog).getByLabelText('退回原因'), { target: { value: '退还部分工资' } });
}

describe('费用更多与退回', () => {
  it('分类与明细分开展示，操作入口只有可见图标，详情沿用分类并能关闭', () => {
    render(<ExpenseDetails month="2026-08" expenses={[expense]} accounts={accounts} onRefund={vi.fn()} />);
    expect(screen.getByText('人员费用')).toBeTruthy();
    expect(screen.getByText('工资')).toBeTruthy();
    const trigger = screen.getByLabelText('费用 7 更多操作');
    expect(trigger.textContent).toBe('');
    expect(trigger.querySelector('svg')).toBeTruthy();
    trigger.focus(); trigger.closest('details')!.open = true;
    fireEvent.click(screen.getByRole('button', { name: '查看明细' }));
    const dialog = screen.getByRole('dialog', { name: '费用详情' });
    expect(within(dialog).getByText('人员费用').querySelector('svg')).toBeTruthy();
    fireEvent.click(within(dialog).getAllByRole('button', { name: '关闭' })[0]);
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });

  it('撤回弹窗保留原因与二次确认，取消不发请求', async () => {
    const reverse = vi.fn().mockResolvedValue(undefined);
    render(<ExpenseDetails month="2026-08" expenses={[expense]} onReverse={reverse} />);
    const open = () => {
      screen.getByLabelText('费用 7 更多操作').closest('details')!.open = true;
      fireEvent.click(screen.getByRole('button', { name: '撤回记录' }));
      return screen.getByRole('dialog', { name: '撤回费用记录' });
    };
    let dialog = open();
    expect((within(dialog).getByRole('button', { name: '确认整笔撤回' }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(within(dialog).getByRole('button', { name: '取消' }));
    expect(reverse).not.toHaveBeenCalled();
    dialog = open();
    fireEvent.change(within(dialog).getByLabelText('撤回原因'), { target: { value: '原费用重复登记' } });
    fireEvent.click(within(dialog).getByRole('button', { name: '确认整笔撤回' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(reverse).toHaveBeenCalledExactlyOnceWith(expense, '原费用重复登记');
  });

  it('低频动作收进更多，取消恢复焦点和页面滚动', () => {
    render(<ExpenseDetails month="2026-08" expenses={[expense]} accounts={accounts} onRefund={vi.fn()} onReverse={vi.fn()} />);
    expect(screen.getByLabelText('费用 7 更多操作').closest('details')!.open).toBe(false);
    const more = screen.getByLabelText('费用 7 更多操作');
    const dialog = openRefund();
    expect(document.activeElement).toBe(dialog);
    expect(document.body.style.overflow).toBe('hidden');
    expect(within(dialog).queryByRole('option', { name: /卢布账户|停用账户/ })).toBeNull();
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(document.activeElement).toBe(more);
    expect(document.body.style.overflow).not.toBe('hidden');
  });
  it('超额和早于原费用的日期不能提交，重复点击只入账一次', async () => {
    let resolve: (value: AccountingExpense) => void = () => undefined;
    const submit = vi.fn().mockImplementation(() => new Promise(done => { resolve = done; }));
    render(<ExpenseDetails month="2026-08" expenses={[expense]} accounts={accounts} onRefund={submit} />);
    const dialog = openRefund(); fill(dialog, '15000.01');
    const confirm = within(dialog).getByRole('button', { name: '确认退回并入账' }) as HTMLButtonElement;
    expect(confirm.disabled).toBe(true);
    expect(within(dialog).getByRole('alert').textContent).toContain('不能超过剩余可退');
    fill(dialog);
    fireEvent.change(within(dialog).getByLabelText('实际到账日期'), { target: { value: '2026-08-11' } });
    expect(confirm.disabled).toBe(true); fill(dialog);
    expect(dialog.textContent).toContain('公司微信 增加 ¥3,000.00');
    expect(dialog.textContent).toContain('本次冲减费用 ¥3,000.00');
    fireEvent.click(confirm); fireEvent.click(confirm);
    expect(submit).toHaveBeenCalledTimes(1);
    expect(submit.mock.calls[0][1]).toEqual({ amount: '3000', fund_account_id: 2, business_date: '2026-09-12', note: '退还部分工资' });
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.getByRole('dialog')).toBeTruthy(); resolve(expense);
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(screen.getByRole('status').textContent).toContain('费用退回已入账');
  });
  it('失败保留输入，重试使用相同参数', async () => {
    const submit = vi.fn().mockRejectedValueOnce(new Error('请求超时')).mockResolvedValue(expense);
    render(<ExpenseDetails month="2026-08" expenses={[expense]} accounts={accounts} onRefund={submit} />);
    const dialog = openRefund(); fill(dialog);
    fireEvent.click(within(dialog).getByRole('button', { name: '确认退回并入账' }));
    await waitFor(() => expect(within(dialog).getByRole('alert').textContent).toContain('请求超时'));
    expect(within(dialog).getByDisplayValue('3000')).toBeTruthy();
    fireEvent.click(within(dialog).getByRole('button', { name: '确认退回并入账' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(submit.mock.calls[0]).toEqual(submit.mock.calls[1]);
  });
  it('已有退回禁用撤回，全部退回禁用登记并说明原因', () => {
    render(<ExpenseDetails month="2026-08" expenses={[{ ...expense, refunded_amount: '15000', remaining_refundable_amount: '0' }]} accounts={accounts} onRefund={vi.fn()} onReverse={vi.fn()} />);
    screen.getByLabelText('费用 7 更多操作').closest('details')!.open = true;
    expect((screen.getByRole('button', { name: '登记退回' }) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByRole('button', { name: '撤回记录' }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText('已有退回，不能整笔撤回')).toBeTruthy();
    expect(screen.getByText('原费用已全部退回')).toBeTruthy();
  });
  it('只有退回的月份也显示记录，可跨月查看原费用', async () => {
    const onLoad = vi.fn().mockResolvedValue({ ...expense, refunded_amount: '3000', remaining_refundable_amount: '12000' });
    render(<ExpenseDetails month="2026-09" expenses={[]} refunds={[{ id: 1, expense_id: 7, fund_account_id: 2, fund_account_name: '公司微信', currency: 'CNY', original_amount: '3000', amount_cny: '3000', business_date: '2026-09-12', note: '退还工资', expense_business_date: '2026-08-12' }]} summary={{ spent_cny: '0', refunded_cny: '3000', reversed_cny: '0', net_cny: '-3000' }} onLoadExpense={onLoad} />);
    expect(screen.queryByText(/本月还没有/)).toBeNull(); expect(screen.getByText('¥-3,000.00')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: '查看原费用' }));
    await waitFor(() => expect(within(screen.getByRole('dialog')).getByText('合伙人工资')).toBeTruthy());
    expect(onLoad).toHaveBeenCalledWith(7);
  });
  it('无法刷新原费用时禁止提交', async () => {
    const submit = vi.fn();
    render(<ExpenseDetails month="2026-08" expenses={[expense]} accounts={accounts} onLoadExpense={vi.fn().mockRejectedValue(new Error('无法核对费用'))} onRefund={submit} />);
    const dialog = openRefund();
    await waitFor(() => expect(within(dialog).getByRole('alert').textContent).toContain('无法核对费用'));
    expect((within(dialog).getByRole('button', { name: '确认退回并入账' }) as HTMLButtonElement).disabled).toBe(true);
    expect(submit).not.toHaveBeenCalled();
  });
});
