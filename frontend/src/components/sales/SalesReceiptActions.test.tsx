// @vitest-environment jsdom
import { cleanup, fireEvent, render, waitFor, within } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import SalesOrderWorkbench from './SalesOrderWorkbench';
import type { FundAccount, SalesOrder } from '../../types';

vi.mock('../../api', async importOriginal => ({
  ...await importOriginal<typeof import('../../api')>(),
  receiveSalesOrder: vi.fn().mockResolvedValue({}),
  withdrawSalesOrderReceipt: vi.fn().mockResolvedValue({}),
}));
afterEach(cleanup);

const baseOrder = {
  id: 31, order_number: 'SO-000031', customer_name: '测试客户', customer_id: null,
  fulfillment_status: 'confirmed', payment_status: 'unpaid', status: 'confirmed',
  display_status: '已确认', amount_due_cny: 86100, goods_amount_cny: 83900,
  customer_transport_fee_cny: 2200, transport_payer: 'customer', items: [],
  available_actions: ['receive'], created_at: '2026-09-25T00:00:00Z', note: '',
} as unknown as SalesOrder;
const accounts: FundAccount[] = [
  { id: 1, name: '石人民币账户', currency: 'CNY', is_active: true, custodian_id: null },
  { id: 2, name: '马人民币账户', currency: 'CNY', is_active: true, custodian_id: null },
];
const props = {
  orders: [baseOrder], selectedId: 31, accounts,
  onSelect: vi.fn(), onChanged: vi.fn(), onCustomer: vi.fn(),
};

it('收款先核对订单金额日期与账户，二次确认后才写入', async () => {
  const { receiveSalesOrder } = await import('../../api');
  vi.mocked(receiveSalesOrder).mockClear();
  const screen = render(<SalesOrderWorkbench {...props} />);
  fireEvent.click(screen.getByRole('button', { name: '收款' }));
  const form = within(screen.getByRole('dialog', { name: '收款' }));
  fireEvent.change(form.getByLabelText('资金账户'), { target: { value: '2' } });
  fireEvent.change(form.getByLabelText('业务日期'), { target: { value: '2026-09-25' } });
  fireEvent.click(form.getByRole('button', { name: '确认执行' }));

  const confirmation = within(screen.getByRole('alertdialog', { name: '确认收款信息' }));
  expect(receiveSalesOrder).not.toHaveBeenCalled();
  expect(confirmation.getByText('SO-000031')).toBeTruthy();
  expect(confirmation.getByText('马人民币账户')).toBeTruthy();
  expect(confirmation.getByText('2026-09-25')).toBeTruthy();
  expect(confirmation.getByText(/86,100/)).toBeTruthy();
  fireEvent.click(confirmation.getByRole('button', { name: '返回修改' }));
  expect(receiveSalesOrder).not.toHaveBeenCalled();
  fireEvent.click(form.getByRole('button', { name: '确认执行' }));
  fireEvent.click(within(screen.getByRole('alertdialog', { name: '确认收款信息' })).getByRole('button', { name: '确认收款' }));
  await waitFor(() => expect(receiveSalesOrder).toHaveBeenCalledWith(31, {
    amount_cny: '86100', fund_account_id: 2, business_date: '2026-09-25',
  }));
});

it('撤回收款必须填写原因并调用专用撤回动作', async () => {
  const { withdrawSalesOrderReceipt } = await import('../../api');
  vi.mocked(withdrawSalesOrderReceipt).mockClear();
  const order = { ...baseOrder, payment_status: 'paid', available_actions: ['withdraw_receipt'] };
  const screen = render(<SalesOrderWorkbench {...props} orders={[order]} />);
  fireEvent.click(screen.getByRole('button', { name: '撤回收款' }));
  const form = within(screen.getByRole('dialog', { name: '撤回收款' }));
  fireEvent.change(form.getByLabelText('业务日期'), { target: { value: '2026-09-25' } });
  fireEvent.click(form.getByRole('button', { name: '确认执行' }));
  expect(withdrawSalesOrderReceipt).not.toHaveBeenCalled();
  expect(form.getByText('撤回原因不能为空')).toBeTruthy();
  fireEvent.change(form.getByLabelText('撤回原因'), { target: { value: '到账账户选错' } });
  fireEvent.click(form.getByRole('button', { name: '确认执行' }));
  await waitFor(() => expect(withdrawSalesOrderReceipt).toHaveBeenCalledWith(31, {
    business_date: '2026-09-25', reason: '到账账户选错',
  }));
});

it('订单事实保留原账户撤回记录并显示新到账账户', () => {
  const order = {
    ...baseOrder,
    payment_status: 'paid',
    available_actions: [],
    sales_receipt: { id: 12, amount_cny: 86100, business_date: '2026-09-25', fund_account_id: 2 },
    sales_receipts: [
      { id: 11, amount_cny: 86100, business_date: '2026-09-25', fund_account_id: 1, reversed_at: '2026-09-25T17:00:00Z', reversal_business_date: '2026-09-25', reversal_reason: '到账账户选错' },
      { id: 12, amount_cny: 86100, business_date: '2026-09-25', fund_account_id: 2, reversed_at: null, reversal_business_date: null, reversal_reason: '' },
    ],
  };
  const screen = render(<SalesOrderWorkbench {...props} orders={[order]} />);
  expect(screen.getByText('SalesReceipt · 已撤回收款')).toBeTruthy();
  expect(screen.getByText('石人民币账户 · 撤回日期 2026-09-25 · 到账账户选错')).toBeTruthy();
  expect(screen.getByText('SalesReceipt · 有效收款')).toBeTruthy();
  expect(screen.getByText('到账账户：马人民币账户')).toBeTruthy();
});
