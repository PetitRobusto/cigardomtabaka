// @vitest-environment jsdom
import { cleanup, fireEvent, render, waitFor, within } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import SalesOrderWorkbench from './SalesOrderWorkbench';
import type { FundAccount, SalesOrder } from '../../types';

vi.mock('../../api', async importOriginal => ({
  ...await importOriginal<typeof import('../../api')>(),
  receiveSalesOrder: vi.fn().mockResolvedValue({}),
  withdrawSalesOrderReceipt: vi.fn().mockResolvedValue({}),
  fetchPaymentSubmissions: vi.fn().mockResolvedValue([]),
  acceptPaymentSubmission: vi.fn().mockResolvedValue({}),
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

it('部分收款继续登记实收，确认框展示余款且取消不入账', async () => {
  const { receiveSalesOrder } = await import('../../api');
  vi.mocked(receiveSalesOrder).mockClear();
  const order = { ...baseOrder, payment_status: 'partial', received_amount_cny: 30000, remaining_amount_cny: 56100 };
  const screen = render(<SalesOrderWorkbench {...props} orders={[order]} />);
  fireEvent.click(screen.getByRole('button', { name: '收款' }));
  const form = within(screen.getByRole('dialog', { name: '收款' }));
  fireEvent.change(form.getByRole('spinbutton'), { target: { value: '10000' } });
  fireEvent.click(form.getByRole('button', { name: '确认执行' }));
  const confirmation = within(screen.getByRole('alertdialog', { name: '确认收款信息' }));
  expect(confirmation.getByText(/46,100/)).toBeTruthy();
  expect(receiveSalesOrder).not.toHaveBeenCalled();
  fireEvent.click(confirmation.getByRole('button', { name: '返回修改' }));
  fireEvent.change(form.getByRole('spinbutton'), { target: { value: '56100.01' } });
  fireEvent.click(form.getByRole('button', { name: '确认执行' }));
  expect(screen.queryByRole('alertdialog')).toBeNull();
  expect(receiveSalesOrder).not.toHaveBeenCalled();
});

it('核实凭证必须填写实收并在独立modal再次确认，保留实际账户', async () => {
  const originalOverflow = document.body.style.overflow;
  const { fetchPaymentSubmissions, acceptPaymentSubmission } = await import('../../api');
  vi.mocked(acceptPaymentSubmission).mockClear();
  vi.mocked(fetchPaymentSubmissions).mockResolvedValueOnce([{
    id: 7, status: 'pending', amount_cny: 86100, fund_account_id: 1,
    submitted_at: '2026-10-21T00:00:00Z', reviewed_at: null, review_note: '',
    closed_reason: '', sales_receipt_id: null, attachments: [],
  }]);
  const order = { ...baseOrder, payment_review: { id: 7, status: 'pending' as const, submitted_at: '2026-10-21T00:00:00Z', review_note: '' } };
  const screen = render(<SalesOrderWorkbench {...props} orders={[order]} />);
  fireEvent.click(screen.getByRole('button', { name: /核实收款/ }));
  const modal = within(screen.getByRole('dialog', { name: '核实付款凭证' }));
  const input = await modal.findByLabelText('本次实收金额');
  expect((modal.getByRole('button', { name: '确认到账' }) as HTMLButtonElement).disabled).toBe(true);
  fireEvent.change(input, { target: { value: '10000' } });
  fireEvent.change(modal.getByLabelText('到账账户'), { target: { value: '2' } });
  fireEvent.change(modal.getByLabelText('业务日期'), { target: { value: '2026-10-21' } });
  fireEvent.click(modal.getByRole('button', { name: '确认到账' }));
  expect(acceptPaymentSubmission).not.toHaveBeenCalled();
  const confirmation = within(screen.getByRole('alertdialog', { name: '确认收款信息' }));
  expect(confirmation.getByText('马人民币账户')).toBeTruthy();
  expect(confirmation.getByText(/76,100/)).toBeTruthy();
  fireEvent.click(confirmation.getByRole('button', { name: '确认收款' }));
  await waitFor(() => expect(acceptPaymentSubmission).toHaveBeenCalledWith(31, 7, '2026-10-21', '10000', 2));
  await waitFor(() => expect(screen.queryByRole('alertdialog')).toBeNull());
  expect(document.body.style.overflow).toBe(originalOverflow);
});

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
  expect(confirmation.getAllByText(/86,100/)).toHaveLength(2);
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

it('时间线展示每笔金额、账户、撤回原因及多账户退款，按业务日期排列', () => {
  const order: SalesOrder = {
    ...baseOrder, available_actions: [],
    sales_receipts: [
      { id: 11, amount_cny: 800, business_date: '2026-09-25', fund_account_id: 1, reversed_at: '2026-09-27T00:00:00Z', reversal_business_date: '2026-09-27', reversal_reason: '账户填错' },
      { id: 12, amount_cny: 300, business_date: '2026-09-26', fund_account_id: 2, reversed_at: null, reversal_business_date: null, reversal_reason: '' },
    ],
    sales_shipment: { id: 1, business_date: '2026-09-26', fifo_cost_cny: 120 },
    sales_transport_cost: { id: 1, business_date: '2026-09-26', actual_cost_cny: 20, fund_account_id: 2 },
    sales_return: { id: 1, business_date: '2026-09-28', amount_cny: 500, fifo_cost_cny: 120, reason: '客户退货' },
    sales_refund: { id: 1, business_date: '2026-09-29', amount_cny: 300, fund_account_id: null, accounts: [
      { fund_account_id: 1, amount_cny: 100 }, { fund_account_id: 2, amount_cny: 200 },
    ] },
  };
  const screen = render(<SalesOrderWorkbench {...props} orders={[order]} />);
  const timeline = within(screen.getByRole('list', { name: '订单时间线' }));
  expect(timeline.getByText('实收 ¥800.00 · 到账账户：石人民币账户')).toBeTruthy();
  expect(timeline.getByText('实收 ¥300.00 · 到账账户：马人民币账户')).toBeTruthy();
  expect(timeline.getByText('撤回 ¥800.00 · 原账户：石人民币账户 · 原因：账户填错')).toBeTruthy();
  expect(timeline.getByText(/出库成本 ¥120.00/)).toBeTruthy();
  expect(timeline.getByText('实际成本 ¥20.00 · 付款账户：马人民币账户')).toBeTruthy();
  expect(timeline.getByText('退货金额 ¥500.00 · 回库成本 ¥120.00 · 原因：客户退货')).toBeTruthy();
  expect(timeline.getByText('退款 ¥300.00 · 石人民币账户 ¥100.00；马人民币账户 ¥200.00')).toBeTruthy();
  const rows = timeline.getAllByRole('listitem').map(item => item.textContent);
  expect(rows.findIndex(text => text?.includes('登记收款记录 #12'))).toBeLessThan(rows.findIndex(text => text?.includes('撤回收款记录 #11')));
});

it('时间线兼容历史单笔收款和未知账户，待核实凭证不当作到账', () => {
  const order: SalesOrder = {
    ...baseOrder, available_actions: [],
    sales_receipt: { id: 1, amount_cny: 200, business_date: '2026-09-25', fund_account_id: 99 },
    payment_review: { id: 7, status: 'pending', submitted_at: '2026-09-26T00:00:00Z', review_note: '' },
  };
  const screen = render(<SalesOrderWorkbench {...props} orders={[order]} />);
  const timeline = within(screen.getByRole('list', { name: '订单时间线' }));
  expect(timeline.getByText('实收 ¥200.00 · 到账账户：账户 #99')).toBeTruthy();
  expect(timeline.getByText('凭证 #7 · 尚未确认到账')).toBeTruthy();
  expect(timeline.queryByText(/实收 ¥86,100/)).toBeNull();
});

it('时间线按上海日期归组，同日出库、收款和退款不虚构实际先后', () => {
  const order: SalesOrder = {
    ...baseOrder, available_actions: [], created_at: '2026-09-25T23:00:00Z', cancelled_at: '2026-09-26T02:00:00Z',
    sales_receipt: { id: 1, amount_cny: 200, business_date: '2026-09-26', fund_account_id: 1 },
    sales_shipment: { id: 1, business_date: '2026-09-26', fifo_cost_cny: 100 },
    sales_refund: { id: 1, amount_cny: 200, business_date: '2026-09-26', fund_account_id: 1 },
  };
  const screen = render(<SalesOrderWorkbench {...props} orders={[order]} />);
  const timeline = within(screen.getByRole('list', { name: '订单时间线' }));
  expect(timeline.getAllByRole('listitem')).toHaveLength(1);
  expect(timeline.getByText('2026-09-26')).toBeTruthy();
  expect(timeline.getByText('同日记录，未按实际先后排序')).toBeTruthy();
  expect(timeline.getByText('2026-09-26 07:00')).toBeTruthy();
});
