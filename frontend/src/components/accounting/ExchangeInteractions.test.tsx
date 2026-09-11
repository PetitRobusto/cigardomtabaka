// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { AccountingTransaction, FundAccount } from '../../types';
import ExchangeAction from './ExchangeAction';
import ExchangeDetails from './ExchangeDetails';

afterEach(cleanup);

const accounts: FundAccount[] = [
  { id: 1, name: '人民币账户', currency: 'CNY', custodian_id: null, is_active: true },
  { id: 2, name: '卢布账户', currency: 'RUB', custodian_id: null, is_active: true },
];

const exchange: AccountingTransaction = {
  id: 9, transaction_type: 'exchange', status: 'posted', business_date: '2026-09-10',
  effective_sequence: 3, description: '', operator_id: 7, source_type: '', source_id: '',
  reversed_by_id: null, reversal_business_date: null,
  postings: [
    { account_id: 1, category: '', currency: 'CNY', amount: '-100.00', cny_amount: '-100.00' },
    { account_id: 2, category: '', currency: 'RUB', amount: '1200.00', cny_amount: '100.00' },
  ],
};

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

describe('换汇高风险交互', () => {
  it('第一次点击只打开确认框，确认按钮的快速重复点击只提交一次', async () => {
    const pending = deferred<unknown>();
    const submit = vi.fn(() => pending.promise);
    const screen = render(<ExchangeAction
      accounts={accounts}
      businessDate="2026-09-11"
      value={{ source_account_id: 1, rub_account_id: 2, source_amount: '100.00', rub_amount: '1200.00' }}
      submit={submit}
    />);

    fireEvent.click(screen.getByRole('button', { name: '记录换汇' }));
    const dialog = screen.getByRole('dialog', { name: '确认换汇' });
    expect(submit).not.toHaveBeenCalled();
    expect(document.activeElement).toBe(dialog);

    const confirm = within(dialog).getByRole('button', { name: '确认换汇并入账' });
    fireEvent.click(confirm);
    fireEvent.click(confirm);
    expect(submit).toHaveBeenCalledTimes(1);

    await act(async () => pending.resolve({ id: 9 }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  });

  it('请求失败时保留确认快照，并支持 Esc 关闭后恢复焦点', async () => {
    const submit = vi.fn().mockRejectedValue(new Error('账务系统繁忙'));
    const screen = render(<ExchangeAction
      accounts={accounts}
      businessDate="2026-09-11"
      value={{ source_account_id: 1, rub_account_id: 2, source_amount: '100.00', rub_amount: '1200.00' }}
      submit={submit}
    />);
    const trigger = screen.getByRole('button', { name: '记录换汇' });
    trigger.focus();
    fireEvent.click(trigger);
    const dialog = screen.getByRole('dialog', { name: '确认换汇' });

    fireEvent.click(within(dialog).getByRole('button', { name: '确认换汇并入账' }));
    await waitFor(() => expect(within(dialog).getByRole('alert').textContent).toContain('账务系统繁忙'));
    expect(within(dialog).getByText('100.00 CNY')).toBeTruthy();

    fireEvent.keyDown(document, { key: 'Escape' });
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(document.activeElement).toBe(trigger);
  });

  it('回撤 Modal 保留日期和原因，忙碌期间只发送一个请求', async () => {
    const pending = deferred<void>();
    const onReverse = vi.fn(() => pending.promise);
    const screen = render(<ExchangeDetails
      month="2026-09"
      accounts={accounts}
      transactions={[exchange]}
      onReverse={onReverse}
    />);

    fireEvent.click(screen.getByRole('button', { name: '撤回' }));
    const dialog = screen.getByRole('dialog', { name: '确认回撤换汇' });
    const reason = within(dialog).getByLabelText('回撤原因 *');
    fireEvent.change(reason, { target: { value: '实际到账金额录错' } });
    const confirm = within(dialog).getByRole('button', { name: '确认回撤并写入反向流水' });
    fireEvent.click(confirm);
    fireEvent.click(confirm);

    expect(onReverse).toHaveBeenCalledTimes(1);
    expect(onReverse).toHaveBeenCalledWith(exchange, expect.any(String), '实际到账金额录错');
    expect((reason as HTMLTextAreaElement).value).toBe('实际到账金额录错');

    await act(async () => pending.resolve());
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  });
});
