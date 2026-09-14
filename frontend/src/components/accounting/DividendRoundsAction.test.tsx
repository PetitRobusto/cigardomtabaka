// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import DividendRoundsAction from './DividendRoundsAction';
import { dividendCents } from './DividendRoundsAction.logic';
import type { DividendPreview, DividendRound, DividendRoundsResponse } from '../../types';

const api = vi.hoisted(() => ({
  fetchDividendRounds: vi.fn(), previewDividendRound: vi.fn(), confirmDividendRound: vi.fn(), recordDividendPayout: vi.fn(),
  parseAccountingApiError: (error: unknown) => ({ code: (error as { code?: string }).code ?? 'unknown', message: (error as Error).message }),
}));
vi.mock('../../api', () => api);
afterEach(cleanup);
const round: DividendRound = { id: 7, status: 'posted', total_cny: '100.02', business_date: '2026-09-14', note: '九月分红', operator_id: 9, agent_source: '', ledger_transaction_id: 101,
  partners: [{ id: 1, name: '张三', allocated_cny: '50.01', paid_cny: '10.00', pending_cny: '40.01' }, { id: 2, name: '李四', allocated_cny: '50.01', paid_cny: '0.00', pending_cny: '50.01' }],
  pending_cny: '90.02', payouts: [{ id: 1, recipient_id: 1, recipient_name: '张三', fund_account_id: 3, fund_account_name: '公司人民币', amount_cny: '10.00', business_date: '2026-09-14', operator_id: 9, ledger_transaction_id: 102 }] };
const listing: DividendRoundsResponse = { rounds: [round], recipients: [{ id: 1, name: '张三' }, { id: 2, name: '李四' }], count: 21, next_page: 2,
  legacy_dividends: [{ id: 99, status: 'draft', version: 1, total_cny: '20.00' }] };
const preview: DividendPreview = { requested_cny: '100.02', retained_earnings_cny: '0.00', warning: { code: 'retained_earnings_exceeded', requested_cny: '100.02', retained_earnings_cny: '0.00', fingerprint: 'warning' }, warning_fingerprint: 'preview-1' };
const accounts = [{ id: 3, name: '公司人民币', currency: 'CNY', is_active: true, custodian_id: null }, { id: 4, name: '停用账户', currency: 'CNY', is_active: false, custodian_id: null }, { id: 5, name: '卢布', currency: 'RUB', is_active: true, custodian_id: null }];

beforeEach(() => {
  vi.clearAllMocks();
  api.fetchDividendRounds.mockImplementation((page: number) => Promise.resolve(page === 1 ? listing : { ...listing, rounds: [], next_page: null }));
  api.previewDividendRound.mockResolvedValue(preview);
  api.confirmDividendRound.mockResolvedValue(round);
  api.recordDividendPayout.mockResolvedValue({ round, payout: round.payouts[0] });
});

function mount(onChanged: () => void = vi.fn()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 300000 } } });
  render(<QueryClientProvider client={client}><DividendRoundsAction accounts={accounts} businessDate="2026-09-14" onChanged={onChanged} /></QueryClientProvider>);
  return { client, onChanged };
}
async function allocation() {
  await screen.findByRole('button', { name: '记录领取 · 第 7 轮' });
  fireEvent.change(screen.getByLabelText('分红总额（CNY）'), { target: { value: '100.02' } });
  fireEvent.change(screen.getByLabelText('领取人 1'), { target: { value: '1' } });
  fireEvent.change(screen.getByLabelText('领取人 2'), { target: { value: '2' } });
  fireEvent.change(screen.getByLabelText('分配备注'), { target: { value: '分配快照' } });
  const trigger = screen.getByRole('button', { name: '预览分配' });
  trigger.focus(); fireEvent.click(trigger);
  return screen.findByRole('dialog', { name: '确认分红分配' });
}
async function payout(recipient = '1', amount = '20.00') {
  fireEvent.click(await screen.findByRole('button', { name: '记录领取 · 第 7 轮' }));
  const dialog = screen.getByRole('dialog');
  fireEvent.change(within(dialog).getByLabelText('领取人'), { target: { value: recipient } });
  fireEvent.change(within(dialog).getByLabelText('公司付款账户'), { target: { value: '3' } });
  fireEvent.change(within(dialog).getByLabelText('领取金额（CNY）'), { target: { value: amount } });
  fireEvent.change(within(dialog).getByLabelText('领取备注'), { target: { value: '实际支付' } });
  fireEvent.click(within(dialog).getByRole('button', { name: '核对领取' }));
  return dialog;
}

describe('按轮分配与领取', () => {
  it('按分验证，不使用浮点取整', () => {
    expect(dividendCents('100.02')).toBe(10002n);
    expect(dividendCents('100.01')! % 2n).toBe(1n);
    expect(dividendCents('9007199254740993.02')).toBe(900719925474099302n);
    for (const value of ['NaN', '1e2', '-1', '1.001', '']) expect(dividendCents(value)).toBeNull();
  });

  it('预览后核对冻结快照，警告须确认；取消保留字段焦点', async () => {
    mount();
    const dialog = await allocation();
    expect(api.confirmDividendRound).not.toHaveBeenCalled();
    expect(within(dialog).getAllByText('50.01 CNY · 50%')).toHaveLength(2);
    expect(within(dialog).getByText('分配快照')).toBeTruthy();
    expect((within(dialog).getByRole('button', { name: '确认分配（不付款）' }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(screen.getByDisplayValue('100.02')).toBeTruthy();
    expect(document.activeElement).toBe(screen.getByRole('button', { name: '预览分配' }));
    fireEvent.click(screen.getByRole('button', { name: '预览分配' }));
    await screen.findByRole('dialog');
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(screen.getByRole('button', { name: '确认分配（不付款）' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(api.confirmDividendRound).toHaveBeenCalledExactlyOnceWith({ total_cny: '100.02', partner_a_id: 1, partner_b_id: 2, business_date: '2026-09-14', note: '分配快照', warning_fingerprint: 'preview-1', warning_ack: true });
  });

  it('旧预览失败只能重新预览并再次确认警告', async () => {
    const { onChanged } = mount();
    api.confirmDividendRound.mockRejectedValueOnce(Object.assign(new Error('利润已变化'), { code: 'warning_stale' }));
    await allocation(); fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(screen.getByRole('button', { name: '确认分配（不付款）' }));
    await screen.findByRole('button', { name: '重新预览' });
    expect(screen.queryByRole('button', { name: '确认分配（不付款）' })).toBeNull();
    expect(onChanged).not.toHaveBeenCalled();
    api.previewDividendRound.mockResolvedValueOnce({ ...preview, warning_fingerprint: 'preview-2' });
    fireEvent.click(screen.getByRole('button', { name: '重新预览' }));
    const confirm = await screen.findByRole('button', { name: '确认分配（不付款）' });
    expect((confirm as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole('checkbox')); fireEvent.click(confirm);
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(api.confirmDividendRound.mock.calls[1][0].warning_fingerprint).toBe('preview-2');
  });

  it('领取确认前不写入，同步双击防护，失败重试相同快照', async () => {
    const { onChanged } = mount();
    let reject: (error: unknown) => void = () => undefined;
    api.recordDividendPayout.mockImplementationOnce(() => new Promise((_, fail) => { reject = fail; }));
    const dialog = await payout();
    expect(api.recordDividendPayout).not.toHaveBeenCalled();
    expect(within(dialog).getByText('公司人民币')).toBeTruthy();
    expect(within(dialog).getByText('实际支付')).toBeTruthy();
    const confirm = within(dialog).getByRole('button', { name: '确认领取并付款' });
    fireEvent.click(confirm); fireEvent.click(confirm);
    expect(api.recordDividendPayout).toHaveBeenCalledTimes(1);
    fireEvent.keyDown(document, { key: 'Escape' }); expect(screen.getByRole('dialog')).toBeTruthy();
    reject(new Error('余额不足'));
    await waitFor(() => expect(within(dialog).getByRole('alert').textContent).toContain('余额不足'));
    expect(onChanged).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: '确认领取并付款' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(api.recordDividendPayout.mock.calls[0]).toEqual(api.recordDividendPayout.mock.calls[1]);
    expect(api.recordDividendPayout.mock.calls[0]).toEqual([7, { recipient_id: 1, fund_account_id: 3, amount_cny: '20.00', business_date: '2026-09-14', note: '实际支付' }]);
    expect(onChanged).toHaveBeenCalledTimes(1);
  });

  it('两人可选择同一个公司账户，限制本人待领，返回修改保留字段', async () => {
    mount();
    const dialog = await payout('1', '40.02');
    expect(within(dialog).getByRole('alert').textContent).toContain('超过');
    expect(api.recordDividendPayout).not.toHaveBeenCalled();
    fireEvent.change(within(dialog).getByLabelText('领取金额（CNY）'), { target: { value: '20.00' } });
    fireEvent.click(within(dialog).getByRole('button', { name: '核对领取' }));
    fireEvent.click(within(dialog).getByRole('button', { name: '返回修改' }));
    expect(within(dialog).getByDisplayValue('20.00')).toBeTruthy();
    expect(within(dialog).queryByText('停用账户')).toBeNull();
    expect(within(dialog).queryByText('卢布')).toBeNull();
    fireEvent.change(within(dialog).getByLabelText('领取人'), { target: { value: '2' } });
    expect((within(dialog).getByLabelText('公司付款账户') as HTMLSelectElement).value).toBe('3');
    fireEvent.click(within(dialog).getByRole('button', { name: '核对领取' }));
    fireEvent.click(within(dialog).getByRole('button', { name: '确认领取并付款' }));
    await waitFor(() => expect(api.recordDividendPayout).toHaveBeenCalled());
    expect(api.recordDividendPayout.mock.calls[0][1].recipient_id).toBe(2);
  });

  it('分页成功刷新不跳页；历史草稿只读', async () => {
    api.fetchDividendRounds.mockImplementation((page: number) => Promise.resolve({ ...listing, next_page: page === 1 ? 2 : null }));
    mount();
    await screen.findByText('历史 A/B 分红（只读，最近 50 条）');
    fireEvent.click(screen.getByRole('button', { name: '下一页' }));
    await waitFor(() => expect(screen.getByText('第 2 页 · 共 21 轮')).toBeTruthy());
    expect(api.fetchDividendRounds).toHaveBeenCalledWith(2);
    await allocation();
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(screen.getByRole('button', { name: '确认分配（不付款）' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(screen.getByText('第 2 页 · 共 21 轮')).toBeTruthy();
    expect(screen.getByDisplayValue('100.02')).toBeTruthy();
    expect(api.fetchDividendRounds.mock.calls.slice(-1)[0]).toEqual([2]);
  });

  it('刷新回调失败不把记账成功变成写入失败', async () => {
    mount(() => { throw new Error('refresh failure'); });
    await payout(); fireEvent.click(screen.getByRole('button', { name: '确认领取并付款' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(screen.getByRole('status').textContent).toContain('记账成功');
    expect(api.recordDividendPayout).toHaveBeenCalledTimes(1);
  });
});
