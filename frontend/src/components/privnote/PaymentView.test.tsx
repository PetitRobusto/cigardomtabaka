// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { submitPaymentEvidence } from '../../api';
import { trackAccessAction } from '../../api/privnoteAccess';
import type { PaymentData } from '../../types';
import PaymentView from './PaymentView';

vi.mock('../../api', () => ({ submitPaymentEvidence: vi.fn() }));
beforeEach(() => {
  vi.clearAllMocks();
  vi.stubGlobal('crypto', { getRandomValues: (array: Uint32Array) => array.fill(42) });
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
const data: PaymentData = {
  mode: 'payment', items: [], total: 100, extra_fees: [{ name: '人肉费', amount: 20 }],
  extra_total: 20, grand_total: 120, customer_name: '测试客户', remark: '转账请备注订单号',
  payment_methods: [{ id: 1, method_type: 'wechat', qr_url: '/qr.png', label: '内部标签', fund_account_name: '内部账户' }],
  payment_flow: { status: 'active', review_note: '', submitted_at: null },
};
const submission: Awaited<ReturnType<typeof submitPaymentEvidence>> = {
  id: 3, status: 'pending', submitted_at: '2026-09-12', reviewed_at: null,
  review_note: '', closed_reason: '', amount_cny: 120, fund_account_id: 4, sales_receipt_id: null,
};
const file = new File(['image'], '付款截图.png', { type: 'image/png' });

it('局域网 HTTP 缺少 randomUUID 时仍能上传，失败重试沿用幂等键', async () => {
  vi.mocked(submitPaymentEvidence).mockRejectedValueOnce(new Error('网络中断')).mockResolvedValueOnce(submission);
  const onSubmitted = vi.fn();
  const screen = render(<PaymentView data={data} token="test" onZoom={vi.fn()} onSubmitted={onSubmitted} />);
  fireEvent.change(screen.getByLabelText('付款凭证图片'), { target: { files: [file] } });
  fireEvent.click(screen.getByRole('button', { name: '提交凭证，等待核实' }));
  await waitFor(() => expect(screen.getByRole('alert').textContent).toBe('网络中断'));
  fireEvent.click(screen.getByRole('button', { name: '提交凭证，等待核实' }));
  await waitFor(() => expect(onSubmitted).toHaveBeenCalledTimes(1));
  const calls = vi.mocked(submitPaymentEvidence).mock.calls;
  expect(calls[0][2]).toBe(calls[1][2]);
  expect(screen.getByText('付款凭证已提交，等待核实')).toBeTruthy();
  expect(screen.queryByLabelText('付款凭证图片')).toBeNull();
});

it('上传期间锁定文件列表并防止重复提交', async () => {
  let finish!: (value: Awaited<ReturnType<typeof submitPaymentEvidence>>) => void;
  vi.mocked(submitPaymentEvidence).mockImplementation(() => new Promise(resolve => { finish = resolve; }));
  const screen = render(<PaymentView data={data} token="test" onZoom={vi.fn()} />);
  fireEvent.change(screen.getByLabelText('付款凭证图片'), { target: { files: [file] } });
  const submit = screen.getByRole('button', { name: '提交凭证，等待核实' });
  fireEvent.click(submit); fireEvent.click(submit);
  expect(submitPaymentEvidence).toHaveBeenCalledTimes(1);
  expect(screen.getByLabelText('付款凭证图片').hasAttribute('disabled')).toBe(true);
  expect(screen.getByRole('button', { name: '移除 付款截图.png' }).hasAttribute('disabled')).toBe(true);
  await act(async () => finish(submission));
});

it('明确拒绝过多或过大文件，不静默截断；支持缩略图与移除', () => {
  const screen = render(<PaymentView data={data} token="test" onZoom={vi.fn()} />);
  const input = screen.getByLabelText('付款凭证图片');
  fireEvent.change(input, { target: { files: Array(6).fill(file) } });
  expect(screen.getByRole('alert').textContent).toContain('最多上传 5 张');
  expect(screen.queryByRole('img', { name: file.name })).toBeNull();
  const big = new File([new Uint8Array(5 * 1024 * 1024 + 1)], 'large.png', { type: 'image/png' });
  fireEvent.change(input, { target: { files: [big] } });
  expect(screen.getByRole('alert').textContent).toContain('不能超过 5MB');
  fireEvent.change(input, { target: { files: [file] } });
  expect(screen.getByRole('img', { name: file.name })).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: '移除 付款截图.png' }));
  expect(screen.queryByRole('img', { name: file.name })).toBeNull();
});

it('预览显示真实应付额与步骤，隐藏内部信息并禁止提交', () => {
  const screen = render(<PaymentView data={data} preview onZoom={vi.fn()} />);
  expect(screen.getByText('¥120.00')).toBeTruthy();
  expect(screen.getByRole('heading', { name: '完成付款' })).toBeTruthy();
  expect(screen.getByRole('heading', { name: '保存付款截图' })).toBeTruthy();
  expect(screen.getByRole('heading', { name: '上传付款凭证' })).toBeTruthy();
  expect(screen.queryByText('内部标签')).toBeNull();
  expect(screen.queryByText('内部账户')).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: '预览中不可提交' }));
  expect(submitPaymentEvidence).not.toHaveBeenCalled();
});

it('刷新后展示最新核实状态，已核实和已关闭均不再展示收款码', () => {
  const screen = render(<PaymentView data={data} onZoom={vi.fn()} />);
  for (const status of ['accepted', 'closed'] as const) {
    screen.rerender(<PaymentView data={{ ...data, payment_flow: { status, review_note: '', submitted_at: null } }} onZoom={vi.fn()} />);
    expect(screen.queryByRole('img', { name: '收款二维码' })).toBeNull();
    expect(screen.queryByLabelText('付款凭证图片')).toBeNull();
  }
});

it('历史链接保留收款信息，明确提示通过商家提交凭证', () => {
  const screen = render(<PaymentView data={{ ...data, payment_flow: undefined }} onZoom={vi.fn()} />);
  expect(screen.getByRole('img', { name: '收款二维码' })).toBeTruthy();
  expect(screen.queryByLabelText('付款凭证图片')).toBeNull();
  expect(screen.getByText(/此历史收款链接不支持上传凭证/)).toBeTruthy();
});


it('仅成功复制才记录卡号操作，失败和预览都不记录', async () => {
  const onAccess = vi.fn();
  const execCommand = vi.fn().mockReturnValue(true);
  const previous = Object.getOwnPropertyDescriptor(document, 'execCommand');
  Object.defineProperty(document, 'execCommand', { configurable: true, value: execCommand });
  const bankData: PaymentData = {
    ...data,
    payment_methods: [{ id: 2, method_type: 'bank_card', bank_name: '银行', card_number: '62220001', card_holder: '持卡人' }],
  };
  try {
    const screen = render(<PaymentView data={bankData} onZoom={vi.fn()} onAccess={onAccess} />);
    fireEvent.click(screen.getByRole('button', { name: '复制卡号' }));
    await waitFor(() => expect(onAccess).toHaveBeenCalledWith('copy_card'));

    execCommand.mockReturnValue(false);
    fireEvent.click(screen.getByRole('button', { name: '复制卡号' }));
    await waitFor(() => expect(screen.getByRole('status').textContent).toContain('长按'));
    expect(onAccess).toHaveBeenCalledTimes(1);

    execCommand.mockReturnValue(true);
    const preview = render(<PaymentView data={bankData} preview onZoom={vi.fn()} onAccess={onAccess} />);
    fireEvent.click(within(preview.container).getByRole('button', { name: '复制卡号' }));
    await waitFor(() => expect(onAccess).toHaveBeenCalledTimes(1));
  } finally {
    if (previous) Object.defineProperty(document, 'execCommand', previous);
    else Reflect.deleteProperty(document, 'execCommand');
  }
});

it('二维码放大先完成界面动作，埋点网络失败不影响客户操作', async () => {
  const fetchMock = vi.fn().mockRejectedValue(new Error('offline'));
  vi.stubGlobal('fetch', fetchMock);
  const onZoom = vi.fn();
  const qrData: PaymentData = {
    ...data,
    payment_methods: [{ id: 1, method_type: 'wechat', qr_url: '/qr.png', account: '' }],
  };
  const screen = render(
    <PaymentView
      data={qrData}
      token="pay/token"
      onZoom={onZoom}
      onAccess={event => trackAccessAction('pay/token', 'visit-token', event)}
    />,
  );

  fireEvent.click(screen.getByRole('button', { name: '放大收款二维码' }));

  expect(onZoom).toHaveBeenCalledWith('/qr.png');
  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
});
