// @vitest-environment jsdom
import { cleanup, fireEvent, render, waitFor, within } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import SalesOrderWorkbench from './SalesOrderWorkbench';
import type { FundAccount, SalesOrder } from '../../types';

vi.mock('../../api', async importOriginal => ({
  ...await importOriginal<typeof import('../../api')>(),
  fetchPaymentMethods: vi.fn().mockResolvedValue([]),
  createPrivnote: vi.fn().mockResolvedValue({ url: '/p/test/', token: 'test' }),
}));
afterEach(cleanup);

const order = {
  id: 1, order_number: 'SO-TEST', customer_name: '测试客户', customer_id: null,
  fulfillment_status: 'confirmed', payment_status: 'unpaid', status: 'confirmed',
  display_status: '已确认', amount_due_cny: 120, goods_amount_cny: 100,
  customer_transport_fee_cny: 20, transport_payer: 'customer', items: [],
  available_actions: [], created_at: '2026-09-12T00:00:00Z', note: '',
} as unknown as SalesOrder;
const accounts: FundAccount[] = [
  { id: 2, name: '卢布', currency: 'RUB', is_active: true, custodian_id: null },
  { id: 3, name: '停用人民币', currency: 'CNY', is_active: false, custodian_id: null },
  { id: 4, name: '人民币一', currency: 'CNY', is_active: true, custodian_id: null },
  { id: 5, name: '人民币二', currency: 'CNY', is_active: true, custodian_id: null },
];
const props = { orders: [order], selectedId: 1, onSelect: vi.fn(), onChanged: vi.fn(), onCustomer: vi.fn() };

it('账户异步到达后默认选择启用人民币账户，保留用户切换', async () => {
  const screen = render(<SalesOrderWorkbench {...props} accounts={[]} />);
  fireEvent.click(screen.getByRole('button', { name: '创建收款单' }));
  await waitFor(() => expect(screen.getByRole('dialog')).toBeTruthy());
  screen.rerender(<SalesOrderWorkbench {...props} accounts={accounts} />);
  const select = within(screen.getByRole('dialog')).getByLabelText(/入账.*账户/) as HTMLSelectElement;
  expect(select.value).toBe('4');
  fireEvent.change(select, { target: { value: '5' } });
  screen.rerender(<SalesOrderWorkbench {...props} accounts={[...accounts]} />);
  expect(select.value).toBe('5');
});

it('客户预览在独立窗口展示付款流程且不创建链接', async () => {
  const { createPrivnote } = await import('../../api');
  const screen = render(<SalesOrderWorkbench {...props} accounts={accounts} />);
  fireEvent.click(screen.getByRole('button', { name: '创建收款单' }));
  await waitFor(() => expect(screen.getByRole('dialog')).toBeTruthy());
  expect(screen.queryByLabelText(/微信号|支付宝账号/)).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: '预览客户页' }));
  const preview = screen.getByRole('dialog', { name: '客户页面预览' });
  expect(within(preview).getByText('保存付款截图')).toBeTruthy();
  expect(within(preview).getByRole('button', { name: /预览中不可提交/ }).hasAttribute('disabled')).toBe(true);
  expect(createPrivnote).not.toHaveBeenCalled();
  const stepLink = within(preview).getByRole('link', { name: /01.*付款/ });
  const targetId = stepLink.getAttribute('href')!.slice(1);
  expect(preview.contains(document.getElementById(targetId))).toBe(true);
  fireEvent(preview, new Event('cancel', { bubbles: true, cancelable: true }));
  expect(screen.queryByRole('dialog', { name: '客户页面预览' })).toBeNull();
  expect(screen.getByRole('dialog', { name: '创建收款单' })).toBeTruthy();
});

it('创建时提交默认人民币账户和客户备注，不提交微信或支付宝账号', async () => {
  const { createPrivnote } = await import('../../api');
  vi.mocked(createPrivnote).mockClear();
  const screen = render(<SalesOrderWorkbench {...props} accounts={accounts} />);
  fireEvent.click(screen.getByRole('button', { name: '创建收款单' }));
  const dialog = within(screen.getByRole('dialog', { name: '创建收款单' }));
  fireEvent.change(dialog.getByLabelText('收款类型'), { target: { value: 'bank_card' } });
  fireEvent.change(dialog.getByLabelText('银行名'), { target: { value: '测试银行' } });
  fireEvent.change(dialog.getByLabelText('户名'), { target: { value: '测试收款人' } });
  fireEvent.change(dialog.getByLabelText('卡号'), { target: { value: '6222000000000000' } });
  fireEvent.change(dialog.getByLabelText('补充备注（客户可见，可选）'), { target: { value: '请备注订单号' } });
  fireEvent.click(dialog.getByRole('button', { name: '创建并生成链接' }));
  await waitFor(() => expect(createPrivnote).toHaveBeenCalledTimes(1));
  const payload = vi.mocked(createPrivnote).mock.calls[0][0];
  expect(payload.get('fund_account_id')).toBe('4');
  expect(payload.get('remark')).toBe('请备注订单号');
  expect(payload.has('temporary_account')).toBe(false);
});
