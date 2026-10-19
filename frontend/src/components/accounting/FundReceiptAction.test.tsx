// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import FundReceiptAction from './FundReceiptAction';
import { fetchFundReceipts, recordFundReceipt } from '../../api';

vi.mock('../../api', () => ({ fetchFundReceipts: vi.fn(), recordFundReceipt: vi.fn(), apiErrorMessage: (error: Error) => error.message }));
const accounts = [
  { id: 1, name: '公司人民币', currency: 'CNY', is_active: true, custodian_id: 1 },
  { id: 2, name: '卢布', currency: 'RUB', is_active: true, custodian_id: 1 },
  { id: 3, name: '停用', currency: 'CNY', is_active: false, custodian_id: 1 },
];
const response = { receipts: [], contributors: [{ id: 7, name: '投入人甲' }], page: 1, next_page: null };
beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(fetchFundReceipts).mockResolvedValue(response);
});
afterEach(cleanup);

async function open() {
  const button = screen.getByRole('button', { name: '人民币入账' }); button.focus(); fireEvent.click(button);
  const dialog = screen.getByRole('dialog');
  await within(dialog).findByRole('option', { name: '投入人甲' });
  return dialog;
}
function fill(dialog: HTMLElement, amount = '30000') {
  fireEvent.change(within(dialog).getByLabelText('投入人'), { target: { value: '7' } });
  fireEvent.change(within(dialog).getByLabelText('到账账户'), { target: { value: '1' } });
  fireEvent.change(within(dialog).getByLabelText('到账金额（CNY）'), { target: { value: amount } });
  fireEvent.change(within(dialog).getByLabelText('实际到账日期'), { target: { value: '2026-08-12' } });
}

describe('人民币入账', () => {
  it('按需加载，筛选人民币账户，取消恢复焦点与滚动', async () => {
    render(<FundReceiptAction accounts={accounts} onChanged={vi.fn()} />);
    expect(fetchFundReceipts).not.toHaveBeenCalled();
    const dialog = await open();
    expect(within(dialog).queryByRole('option', { name: '卢布' })).toBeNull();
    expect(within(dialog).queryByRole('option', { name: '停用' })).toBeNull();
    expect(document.body.style.overflow).toBe('hidden');
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(document.activeElement).toBe(screen.getByRole('button', { name: '人民币入账' }));
    expect(document.body.style.overflow).not.toBe('hidden');
  });

  it('金额和日期校验，核对确认后才提交，重复点击只提交一次', async () => {
    let resolve!: (value: Awaited<ReturnType<typeof recordFundReceipt>>) => void;
    vi.mocked(recordFundReceipt).mockImplementation(() => new Promise(done => { resolve = done; }));
    const changed = vi.fn();
    render(<FundReceiptAction accounts={accounts} onChanged={changed} />);
    const dialog = await open();
    for (const amount of ['0', '-1', '0.001', '1000000000000', 'NaN']) {
      fill(dialog, amount);
      expect((within(dialog).getByRole('button', { name: '核对入账信息' }) as HTMLButtonElement).disabled).toBe(true);
    }
    fill(dialog);
    fireEvent.change(within(dialog).getByLabelText('实际到账日期'), { target: { value: '2026-08-09' } });
    expect((within(dialog).getByRole('button', { name: '核对入账信息' }) as HTMLButtonElement).disabled).toBe(true);
    fill(dialog);
    fireEvent.click(within(dialog).getByRole('button', { name: '核对入账信息' }));
    expect(recordFundReceipt).not.toHaveBeenCalled();
    expect(dialog.textContent).toContain('¥30,000.00');
    fireEvent.click(within(dialog).getByRole('button', { name: '确认入账' }));
    fireEvent.click(within(dialog).getByRole('button', { name: '入账中…' }));
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.getByRole('dialog')).toBeTruthy();
    expect(recordFundReceipt).toHaveBeenCalledTimes(1);
    expect(recordFundReceipt).toHaveBeenCalledWith({ contributor_id: 7, fund_account_id: 1, amount_cny: '30000.00', business_date: '2026-08-12', note: '' });
    resolve({ id: 9 } as Awaited<ReturnType<typeof recordFundReceipt>>);
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(changed).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('status').textContent).toContain('可继续换汇');
    expect(screen.queryByText('第 1 页')).toBeNull();
    expect(screen.getByRole('button', { name: '查看入账记录' }).getAttribute('aria-expanded')).toBe('false');
  });

  it('加载失败可重试，提交失败保留确认内容，返回修改保留输入', async () => {
    vi.mocked(fetchFundReceipts).mockRejectedValueOnce(new Error('加载失败'));
    vi.mocked(recordFundReceipt).mockRejectedValueOnce(new Error('请求超时')).mockResolvedValue({ id: 9 } as Awaited<ReturnType<typeof recordFundReceipt>>);
    render(<FundReceiptAction accounts={accounts} onChanged={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: '人民币入账' }));
    await screen.findByRole('alert');
    fireEvent.click(screen.getByRole('button', { name: '重试' }));
    const dialog = screen.getByRole('dialog');
    await within(dialog).findByRole('option', { name: '投入人甲' }); fill(dialog);
    fireEvent.click(within(dialog).getByRole('button', { name: '核对入账信息' }));
    fireEvent.click(within(dialog).getByRole('button', { name: '返回修改' }));
    expect(within(dialog).getByDisplayValue('30000')).toBeTruthy();
    fireEvent.click(within(dialog).getByRole('button', { name: '核对入账信息' }));
    fireEvent.click(within(dialog).getByRole('button', { name: '确认入账' }));
    await within(dialog).findByText('请求超时');
    fireEvent.click(within(dialog).getByRole('button', { name: '确认入账' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(vi.mocked(recordFundReceipt).mock.calls[0]).toEqual(vi.mocked(recordFundReceipt).mock.calls[1]);
  });

  it('历史弹窗默认隐藏，支持分页、关闭及焦点恢复', async () => {
    vi.mocked(fetchFundReceipts).mockResolvedValueOnce({ ...response, next_page: 2 });
    render(<FundReceiptAction accounts={accounts} onChanged={vi.fn()} />);
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(fetchFundReceipts).not.toHaveBeenCalled();
    const trigger = screen.getByRole('button', { name: '查看入账记录' });
    trigger.focus(); fireEvent.click(trigger);
    const dialog = screen.getByRole('dialog', { name: '入账记录' });
    expect(document.body.style.overflow).toBe('hidden');
    await screen.findByText('第 1 页');
    vi.mocked(fetchFundReceipts).mockResolvedValueOnce({ ...response, page: 2, receipts: [{ id: 1, contributor_id: 7, contributor_name: '投入人甲', fund_account_id: 1, fund_account_name: '公司人民币', amount_cny: '30000.00', business_date: '2026-08-12', note: '买货', operator_id: 1, agent_source: '', ledger_transaction_id: 22 }] });
    fireEvent.click(screen.getByRole('button', { name: '下一页' }));
    await within(dialog).findByText(/流水 #22/);
    expect(fetchFundReceipts).toHaveBeenLastCalledWith(2);
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(screen.queryByText(/流水 #22/)).toBeNull();
    expect(document.activeElement).toBe(trigger);
    expect(document.body.style.overflow).not.toBe('hidden');
    fireEvent.click(trigger);
    await screen.findByText('第 1 页');
    expect(fetchFundReceipts).toHaveBeenLastCalledWith(1);
    fireEvent.click(screen.getByRole('button', { name: '关闭入账记录' }));
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('历史弹窗加载失败可重试，点击遮罩关闭', async () => {
    vi.mocked(fetchFundReceipts).mockRejectedValueOnce(new Error('记录加载失败'));
    render(<FundReceiptAction accounts={accounts} onChanged={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: '查看入账记录' }));
    const dialog = screen.getByRole('dialog', { name: '入账记录' });
    await within(dialog).findByRole('alert');
    fireEvent.click(within(dialog).getByRole('button', { name: '重试' }));
    await within(dialog).findByText('暂无人民币入账记录');
    fireEvent.mouseDown(dialog.parentElement!);
    expect(screen.queryByRole('dialog')).toBeNull();
  });
});
