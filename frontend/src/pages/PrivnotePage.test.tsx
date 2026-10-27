// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import PrivnotePage from "./PrivnotePage";

const mocks = vi.hoisted(() => ({
  createPrivnote: vi.fn(),
  fetchPaymentMethods: vi.fn(),
  fetchQuoteProducts: vi.fn(),
  fetchEligiblePaymentOrders: vi.fn(),
  uploadPrivnoteImage: vi.fn(),
  createPrivnoteQrImage: vi.fn(),
  setMeta: vi.fn(),
}));

vi.mock("../api", () => ({
  createPrivnote: mocks.createPrivnote,
  fetchPaymentMethods: mocks.fetchPaymentMethods,
  fetchQuoteProducts: mocks.fetchQuoteProducts,
  fetchEligiblePaymentOrders: mocks.fetchEligiblePaymentOrders,
  uploadPrivnoteImage: mocks.uploadPrivnoteImage,
}));
vi.mock("../store/authStore", () => ({
  useAuthStore: () => ({ user: { is_staff: true } }),
}));
vi.mock("../hooks/usePageMeta", () => ({
  usePageMeta: () => ({ setMeta: mocks.setMeta }),
}));
vi.mock("../components/privnote/AccessRecords", () => ({ default: () => null }));
vi.mock("../components/privnote/PaymentMethodManager", () => ({ default: () => null }));
vi.mock("../lib/privnoteQr", () => ({
  createPrivnoteQrImage: mocks.createPrivnoteQrImage,
}));

const created = {
  url: "https://example.test/p/test-token",
  token: "test-token",
};

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <PrivnotePage />
    </QueryClientProvider>,
  );
}

function getByGuide(name: string): HTMLElement {
  const element = document.querySelector<HTMLElement>(`[data-guide="${name}"]`);
  if (!element) throw new Error(`Missing element with data-guide="${name}"`);
  return element;
}

async function createAndExpectLink() {
  fireEvent.click(screen.getByRole("button", { name: "创建私密链接" }));
  expect(await screen.findByText(created.url)).toBeTruthy();
  await waitFor(() => expect(mocks.createPrivnote).toHaveBeenCalledTimes(1));
  const form = mocks.createPrivnote.mock.calls[0][0] as FormData;
  return form.get("note_type");
}

beforeEach(() => {
  mocks.createPrivnote.mockReset().mockResolvedValue(created);
  mocks.fetchPaymentMethods.mockReset().mockResolvedValue([
    { id: 4, method_type: "bank_card", label: "人民币账户" },
  ]);
  mocks.fetchEligiblePaymentOrders.mockReset().mockResolvedValue([
    {
      id: 12,
      order_number: "SO-12",
      status: "confirmed",
      display_status: "已确认",
      fulfillment_status: "confirmed",
      payment_status: "unpaid",
      customer_name: "测试客户",
      amount_due_cny: 500,
      remaining_amount_cny: 500,
      items: [],
    },
  ]);
  mocks.fetchQuoteProducts.mockReset().mockResolvedValue([]);
  mocks.uploadPrivnoteImage.mockReset();
  mocks.createPrivnoteQrImage.mockReset().mockResolvedValue("data:image/png;base64,qr");
});

afterEach(cleanup);

describe("Privnote link creation result", () => {
  it.each([
    ["库存展示", "inventory"],
    ["报价单", "quote"],
    ["消息", "message"],
  ])("creates a %s link once and shows its URL", async (label, noteType) => {
    renderPage();
    if (label !== "报价单") {
      fireEvent.click(screen.getByRole("button", { name: label }));
    }
    if (noteType === "message") {
      fireEvent.change(getByGuide("privnote-message"), {
        target: { value: "客户消息" },
      });
    }

    expect(await createAndExpectLink()).toBe(noteType);
    expect(await screen.findByAltText("链接二维码")).toBeTruthy();
    expect(mocks.createPrivnote).toHaveBeenCalledTimes(1);
  });

  it("creates a payment link from a valid existing order and payment method", async () => {
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: "收款单" }));

    await waitFor(() => expect(getByGuide("privnote-payment-order")).toBeTruthy());
    const orderSelect = getByGuide("privnote-payment-order");
    await screen.findByRole("option", { name: /SO-12/ });
    await screen.findByRole("option", { name: /人民币账户/ });
    fireEvent.change(orderSelect, { target: { value: "12" } });
    fireEvent.change(getByGuide("privnote-payment-method"), {
      target: { value: "4" },
    });

    expect(await createAndExpectLink()).toBe("payment");
    expect(mocks.createPrivnote).toHaveBeenCalledTimes(1);
  });

  it("does not render a QR code when link creation fails", async () => {
    mocks.createPrivnote.mockRejectedValueOnce(new Error("创建失败"));
    renderPage();

    fireEvent.click(screen.getByRole("button", { name: "创建私密链接" }));

    expect(await screen.findByText("创建失败")).toBeTruthy();
    expect(screen.queryByAltText("链接二维码")).toBeNull();
    expect(mocks.createPrivnoteQrImage).not.toHaveBeenCalled();
    expect(mocks.createPrivnote).toHaveBeenCalledTimes(1);
  });

  it("retries QR generation without creating a second link", async () => {
    mocks.createPrivnoteQrImage
      .mockRejectedValueOnce(new Error("二维码生成失败"))
      .mockResolvedValueOnce("data:image/png;base64,retried");
    renderPage();
    expect(await createAndExpectLink()).toBe("quote");

    expect(await screen.findByText("二维码生成失败，链接仍可使用。")).toBeTruthy();
    expect(screen.getByText(created.url)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "重试二维码" }));

    expect(await screen.findByAltText("链接二维码")).toBeTruthy();
    expect(mocks.createPrivnoteQrImage).toHaveBeenCalledTimes(2);
    expect(mocks.createPrivnote).toHaveBeenCalledTimes(1);
  });
});
