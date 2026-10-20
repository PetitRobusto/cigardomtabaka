// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import DividendRoundsAction from './DividendRoundsAction';
import DividendDetails from './DividendDetails';
import AccountingActionCenter from './AccountingActionCenter';
import { dividendCents, personalDividendAmounts } from './DividendRoundsAction.logic';
import type { DividendRound, DividendRoundsResponse } from '../../types';

const api = vi.hoisted(() => ({
  fetchDividendRounds: vi.fn(), recordPaidDividend: vi.fn(), recordDividendPayout: vi.fn(),
  parseAccountingApiError: (error: unknown) => error,
}));
vi.mock('../../api', () => api);
vi.mock('./ExpenseAction', () => ({ default: () => <p>费用表单</p> }));
vi.mock('./ExchangeAction', () => ({ default: () => null }));
vi.mock('./PurchaseAction', () => ({ default: () => null }));
afterEach(cleanup);
const round: DividendRound = { id: 7, status: 'posted', total_cny: '100.02', business_date: '2026-09-14', note: '九月分红', operator_id: 9, agent_source: '', ledger_transaction_id: 101,
  partners: [{ id: 1, name: '张三', allocated_cny: '50.01', paid_cny: '10.00', pending_cny: '40.01' }, { id: 2, name: '李四', allocated_cny: '50.01', paid_cny: '0.00', pending_cny: '50.01' }],
  pending_cny: '90.02', payouts: [{ id: 1, recipient_id: 1, recipient_name: '张三', fund_account_id: 3, fund_account_name: '公司人民币', amount_cny: '10.00', business_date: '2026-10-01', operator_id: 9, ledger_transaction_id: 102 }] };
const listing: DividendRoundsResponse = { rounds: [round], recipients: [{ id: 1, name: '张三' }, { id: 2, name: '李四' }], count: 21, next_page: 2,
  defaults: { partner_a_id: 1, partner_b_id: 2, fund_account_id: 3 }, legacy_dividends: [] };
const warning = { requested_cny: '100.02', retained_earnings_cny: '0.00', warning: { code: 'retained_earnings_exceeded', requested_cny: '100.02', retained_earnings_cny: '0.00', fingerprint: 'warning' }, warning_fingerprint: 'preview-1' };
const accounts = [{ id: 3, name: '公司人民币', currency: 'CNY', is_active: true, custodian_id: null }, { id: 4, name: '停用账户', currency: 'CNY', is_active: false, custodian_id: null }, { id: 5, name: '卢布', currency: 'RUB', is_active: true, custodian_id: null }];
const payload = { total_cny: '100.02', partner_a_paid_cny: '50.01', partner_b_paid_cny: '0.00', partner_a_id: 1, partner_b_id: 2, fund_account_id: 3, business_date: '2026-10-19', note: '' };

beforeEach(() => {
  vi.resetAllMocks();
  api.fetchDividendRounds.mockResolvedValue(listing);
  api.recordPaidDividend.mockResolvedValue({ ...round, business_date: '2026-10-19', pending_cny: '0.00' });
  api.recordDividendPayout.mockResolvedValue({ round, payout: round.payouts[0] });
});
function mount(details = false, onChanged = vi.fn()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 300000 } } });
  const view = render(<QueryClientProvider client={client}>{details
    ? <DividendDetails month="2026-10" accounts={accounts} businessDate="2026-10-19" onChanged={onChanged} />
    : <DividendRoundsAction accounts={accounts} businessDate="2026-10-19" onChanged={onChanged} />}</QueryClientProvider>);
  return { ...view, client, onChanged };
}
async function fill() {
  await waitFor(() => expect((screen.getByLabelText('本次领取人') as HTMLSelectElement).value).toBe('1'));
  fireEvent.change(screen.getByLabelText('个人实领金额（CNY）'), { target: { value: '50.01' } });
}

describe('一次登记已支付分红', () => {
  it('个人金额精确翻倍，只有勾选另一人也领取才增加实际扣款', () => {
    expect(personalDividendAmounts('5000', false)).toEqual({
      individual: '5000.00', total: '10000.00', paid: '5000.00', pending: '5000.00', otherPaid: '0.00',
    });
    expect(personalDividendAmounts('0.01', true)).toEqual({
      individual: '0.01', total: '0.02', paid: '0.02', pending: '0.00', otherPaid: '0.01',
    });
    for (const value of ['0', '-1', '1.001', '1e3', '500000000000', '99999999999999999999.99']) {
      expect(personalDividendAmounts(value, false)).toBeNull();
    }
    expect(personalDividendAmounts('499999999999.99', false)?.total).toBe('999999999999.98');
  });
  it('个人实领5000自动建立另一人待领5000，仅扣账户5000', async () => {
    mount(); await fill();
    fireEvent.change(screen.getByLabelText('个人实领金额（CNY）'), { target: { value: '5000' } });
    expect((screen.getByLabelText('另一位合伙人也已领取同额分红') as HTMLInputElement).checked).toBe(false);
    expect(screen.getByText(/待领资金不冻结/)).toBeTruthy();
    expect(screen.getByRole('link', { name: '查看分红明细' }).getAttribute('href')).toBe('#dividend-details');
    fireEvent.click(screen.getByRole('button', { name: '保存分红' }));
    await waitFor(() => expect(api.recordPaidDividend).toHaveBeenCalledExactlyOnceWith({
      ...payload, total_cny: '10000.00', partner_a_paid_cny: '5000.00',
    }));
    expect(screen.getByRole('status').textContent).toContain('账户扣款 5000.00 CNY，待领 5000.00 CNY');
  });
  it('另一人也已领时扣两人金额，下一次重新默认为仅一人领取', async () => {
    mount(); await fill();
    fireEvent.click(screen.getByLabelText('另一位合伙人也已领取同额分红'));
    fireEvent.click(screen.getByRole('button', { name: '保存分红' }));
    await waitFor(() => expect(api.recordPaidDividend).toHaveBeenCalledExactlyOnceWith({
      ...payload, partner_b_paid_cny: '50.01',
    }));
    expect((screen.getByLabelText('另一位合伙人也已领取同额分红') as HTMLInputElement).checked).toBe(false);
    expect(screen.getByRole('status').textContent).toContain('账户扣款 100.02 CNY，待领 0.00 CNY');
  });
  it('两位用户时切换领取人自动匹配另一人，实领随领取人变更', async () => {
    mount(); await fill();
    fireEvent.change(screen.getByLabelText('本次领取人'), { target: { value: '2' } });
    expect((screen.getByLabelText('另一位合伙人') as HTMLSelectElement).value).toBe('1');
    fireEvent.click(screen.getByRole('button', { name: '保存分红' }));
    await waitFor(() => expect(api.recordPaidDividend).toHaveBeenCalledExactlyOnceWith({
      ...payload, partner_a_id: 2, partner_b_id: 1,
    }));
  });
  it('多人场景不猜选另一人，不能为同一人建立两个份额', async () => {
    api.fetchDividendRounds.mockResolvedValue({ ...listing, recipients: [...listing.recipients, { id: 3, name: '王五' }] });
    mount(); await fill();
    fireEvent.change(screen.getByLabelText('本次领取人'), { target: { value: '2' } });
    expect((screen.getByLabelText('另一位合伙人') as HTMLSelectElement).value).toBe('');
    expect((screen.getByRole('button', { name: '保存分红' }) as HTMLButtonElement).disabled).toBe(true);
    expect(api.recordPaidDividend).not.toHaveBeenCalled();
  });
  it('人民币按分精确平分', () => {
    expect(dividendCents('100.02')).toBe(10002n);
    expect(dividendCents('100.01')! % 2n).toBe(1n);
    expect(dividendCents('9007199254740993.02')).toBe(900719925474099302n);
    for (const value of ['NaN', '1e2', '-1', '1.001', '']) expect(dividendCents(value)).toBeNull();
  });
  it('沿用有效人员和账户，正常一次保存，清空金额防止重复录入', async () => {
    const { onChanged } = mount(); await fill();
    expect(screen.queryByText('停用账户')).toBeNull();
    expect(screen.queryByText('卢布')).toBeNull();
    expect(screen.queryByRole('table')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: '保存分红' }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(1));
    expect(api.recordPaidDividend).toHaveBeenCalledExactlyOnceWith(payload);
    expect(screen.queryByRole('dialog')).toBeNull();
    expect((screen.getByLabelText('个人实领金额（CNY）') as HTMLInputElement).value).toBe('');
    expect((screen.getByLabelText('本次领取人') as HTMLSelectElement).value).toBe('1');
    expect(screen.getByRole('status').textContent).toContain('已记录');
  });
  it('超利润只显示警告，明确确认后重试；变化后的警告重新确认', async () => {
    api.recordPaidDividend.mockRejectedValueOnce({ code: 'warning_required', message: '利润不足', details: warning });
    mount(); await fill(); fireEvent.click(screen.getByRole('button', { name: '保存分红' }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText('本次账户扣款')).toBeTruthy();
    expect(within(dialog).getByText('待领合计')).toBeTruthy();
    const confirm = within(dialog).getByRole('button', { name: '确认保存分红' });
    expect((confirm as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(within(dialog).getByRole('checkbox'));
    api.recordPaidDividend.mockRejectedValueOnce({ code: 'warning_stale', message: '利润已变化', details: { ...warning, warning_fingerprint: 'preview-2' } });
    fireEvent.click(confirm);
    await waitFor(() => expect((within(screen.getByRole('dialog')).getByRole('checkbox') as HTMLInputElement).checked).toBe(false));
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('checkbox'));
    fireEvent.click(screen.getByRole('button', { name: '确认保存分红' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(api.recordPaidDividend.mock.calls[2][0]).toEqual({ ...payload, warning_ack: true, warning_fingerprint: 'preview-2' });
  });
  it('同步双击防护，网络失败冻结输入并用原请求重试', async () => {
    let fail: (value: unknown) => void = () => undefined;
    api.recordPaidDividend.mockImplementationOnce(() => new Promise((_, reject) => { fail = reject; }));
    mount(); await fill();
    const save = screen.getByRole('button', { name: '保存分红' });
    fireEvent.click(save); fireEvent.click(save);
    expect(api.recordPaidDividend).toHaveBeenCalledTimes(1);
    fail(new Error('网络中断'));
    await screen.findByRole('button', { name: '重试本次记录' });
    expect((screen.getByLabelText('另一位合伙人也已领取同额分红') as HTMLInputElement).closest('fieldset')?.disabled).toBe(true);
    fireEvent.click(await screen.findByRole('button', { name: '重试本次记录' }));
    await waitFor(() => expect(api.recordPaidDividend).toHaveBeenCalledTimes(2));
    expect(api.recordPaidDividend.mock.calls[0]).toEqual(api.recordPaidDividend.mock.calls[1]);
  });
  it('确定性余额不足允许修改，刷新失败不重复记账', async () => {
    api.recordPaidDividend.mockRejectedValueOnce({ isAxiosError: true, response: { status: 409 }, code: 'insufficient_balance', message: '余额不足' });
    mount(false, vi.fn(() => { throw new Error('refresh'); })); await fill();
    fireEvent.click(screen.getByRole('button', { name: '保存分红' }));
    await screen.findByText('余额不足');
    expect((screen.getByRole('button', { name: '保存分红' }) as HTMLButtonElement).disabled).toBe(false);
    fireEvent.click(screen.getByRole('button', { name: '保存分红' }));
    await screen.findByText(/记账成功.*刷新失败/);
    expect(api.recordPaidDividend).toHaveBeenCalledTimes(2);
  });
  it('不默认选择已停用或不存在的历史合伙人', async () => {
    api.fetchDividendRounds.mockResolvedValue({ ...listing, defaults: { partner_a_id: 999, partner_b_id: 2, fund_account_id: 4 } });
    mount();
    await waitFor(() => expect((screen.getByLabelText('另一位合伙人') as HTMLSelectElement).value).toBe('2'));
    expect((screen.getByLabelText('本次领取人') as HTMLSelectElement).value).toBe('');
    expect((screen.getByLabelText('公司付款账户') as HTMLSelectElement).value).toBe('');
  });
  it('切换操作页签保留在途请求和警告确认后的原请求重试', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={client}><AccountingActionCenter accounts={accounts} businessDate="2026-10-19" initialAction="dividend" /></QueryClientProvider>);
    api.recordPaidDividend.mockRejectedValueOnce({ code: 'warning_required', message: '利润不足', details: warning });
    await fill(); fireEvent.click(screen.getByRole('button', { name: '保存分红' }));
    await screen.findByRole('dialog'); fireEvent.click(within(screen.getByRole('dialog')).getByRole('checkbox'));
    let fail: (error: Error) => void = () => undefined;
    api.recordPaidDividend.mockImplementationOnce(() => new Promise((_, reject) => { fail = reject; }));
    fireEvent.click(screen.getByRole('button', { name: '确认保存分红' }));
    fireEvent.click(screen.getByRole('button', { name: '记录费用' }));
    fail(new Error('响应丢失'));
    await waitFor(() => expect(screen.getByText('响应丢失')).toBeTruthy());
    fireEvent.click(screen.getByRole('button', { name: '分红' }));
    expect((screen.getByLabelText('个人实领金额（CNY）') as HTMLInputElement).closest('fieldset')?.disabled).toBe(true);
    fireEvent.click(screen.getByRole('button', { name: '重试本次记录' }));
    await waitFor(() => expect(api.recordPaidDividend).toHaveBeenCalledTimes(3));
    expect(api.recordPaidDividend.mock.calls[2]).toEqual(api.recordPaidDividend.mock.calls[1]);
    expect(api.recordPaidDividend.mock.calls[2][0]).toEqual({ ...payload, warning_ack: true, warning_fingerprint: 'preview-1' });
  });
});

describe('分红明细表格和历史领取', () => {
  it('按月分页，一轮一行，展开实际付款，历史待领继续补记', async () => {
    const { onChanged } = mount(true);
    const table = await screen.findByRole('table', { name: '分红明细' });
    expect(api.fetchDividendRounds).toHaveBeenCalledWith(1, '2026-10');
    expect(within(table).getByText('部分领取')).toBeTruthy();
    fireEvent.click(within(table).getByRole('button', { name: '查看详情' }));
    expect(within(table).getByText('2026-10-01')).toBeTruthy();
    fireEvent.click(within(table).getByRole('button', { name: '继续登记领取' }));
    const dialog = screen.getByRole('dialog');
    fireEvent.change(within(dialog).getByLabelText('领取人'), { target: { value: '1' } });
    fireEvent.change(within(dialog).getByLabelText('公司付款账户'), { target: { value: '3' } });
    fireEvent.change(within(dialog).getByLabelText('领取金额（CNY）'), { target: { value: '40.02' } });
    fireEvent.click(within(dialog).getByRole('button', { name: '核对领取' }));
    expect(within(dialog).getByRole('alert').textContent).toContain('超过');
    expect(api.recordDividendPayout).not.toHaveBeenCalled();
    fireEvent.change(within(dialog).getByLabelText('领取金额（CNY）'), { target: { value: '40.01' } });
    fireEvent.click(within(dialog).getByRole('button', { name: '核对领取' }));
    fireEvent.click(within(dialog).getByRole('button', { name: '确认记录领取' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(onChanged).toHaveBeenCalledTimes(1);
    expect(api.recordDividendPayout.mock.calls[0][0]).toBe(7);
    fireEvent.click(screen.getByRole('button', { name: '下一页' }));
    await waitFor(() => expect(api.fetchDividendRounds).toHaveBeenCalledWith(2, '2026-10'));
  });
  it('已付清不提供重复领取入口，空月份有明确提示', async () => {
    api.fetchDividendRounds.mockResolvedValueOnce({ ...listing, rounds: [{ ...round, pending_cny: '0.00' }] });
    const view = mount(true);
    await screen.findByText('已付清');
    expect(screen.queryByRole('button', { name: '继续登记领取' })).toBeNull();
    view.unmount();
    api.fetchDividendRounds.mockResolvedValue({ ...listing, rounds: [], count: 0, next_page: null });
    mount(true); await screen.findByText('2026-10 暂无分红记录');
  });
});
