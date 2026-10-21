import { useEffect, useMemo, useRef, useState } from "react";
import {
  CircleDollarSign,
  PackageCheck,
  RotateCcw,
  Truck,
  X,
} from "lucide-react";
import type { FundAccount, PaymentMethod, PaymentSubmission, SalesOrder } from "../../types";
import {
  apiErrorMessage,
  acceptPaymentSubmission,
  cancelSalesOrder,
  createPrivnote,
  fetchPaymentSubmissions,
  fetchPaymentMethods,
  confirmSalesOrder,
  receiveSalesOrder,
  recordSalesTransportCost,
  paymentSubmissionAttachmentUrl,
  requestMorePaymentEvidence,
  refundSalesOrder,
  returnSalesOrder,
  shipSalesOrder,
  withdrawSalesOrderReceipt,
} from "../../api";
import {
  actionLabel,
  actionNeedsFundAccount,
  formatCny,
  receiveAmountWithinRemaining,
  statusLabel,
  validatePositiveMoneyInput,
} from "./salesState";
import {
  salesFundAccountError,
  salesOrderActionBusinessDate,
  salesOrderFinancialView,
  salesOrderItemCostView,
  selectActiveCnyAccountId,
} from "./SalesOrderCard.logic";
import { formatShanghaiDateTime } from "../../utils/businessDate";
import PaymentRequestModal from "./PaymentRequestModal";
import PaymentDialog from "../privnote/PaymentDialog";
import SalesOrderStatusTags from "./SalesOrderStatusTags";

function publicPrivnoteUrl(value: string): string {
  if (typeof window === "undefined") return value;
  const current = new URL(window.location.href);
  const parsed = new URL(value, current.origin);
  // 订单 API 可能返回相对路径，或开发代理的本机 Django 地址。
  // 对外链接统一使用当前浏览器可访问的 origin。
  if (
    parsed.origin === current.origin ||
    parsed.hostname === "localhost" ||
    parsed.hostname === "127.0.0.1" ||
    parsed.port === "8000"
  ) {
    return current.origin + parsed.pathname + parsed.search + parsed.hash;
  }
  return parsed.href;
}

async function copyText(value: string): Promise<boolean> {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(value);
      return true;
    }
  } catch {
    // 使用兼容旧浏览器和非 HTTPS 局域网访问的降级方案。
  }
  const textarea = document.createElement("textarea");
  textarea.value = value;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.opacity = "0";
  document.body.appendChild(textarea);
  textarea.select();
  const copied = document.execCommand("copy");
  textarea.remove();
  return copied;
}

interface Props {
  orders: SalesOrder[];
  selectedId: number | null;
  accounts: FundAccount[];
  accountsError?: string;
  onSelect: (id: number | null) => void;
  onChanged: () => void;
  onCustomer: (customerId: number) => void;
}

export default function SalesOrderWorkbench({
  orders,
  selectedId,
  accounts: allAccounts,
  accountsError = "",
  onSelect,
  onChanged,
  onCustomer,
}: Props) {
  const selected = orders.find((order) => order.id === selectedId) || null;

  return (
    <div
      className={`grid gap-4 lg:grid-cols-[300px_minmax(0,1fr)] ${selected ? "sales-workbench-selected" : ""}`}
    >
      <section
        className={
          (selected ? "hidden lg:block " : "") +
          "overflow-hidden rounded-md border border-border bg-white shadow-sm"
        }
      >
        <div className="border-b border-border px-4 py-3">
          <h2 className="font-display text-base font-semibold">订单轨道</h2>
          <p className="mt-0.5 text-[11px] text-muted">
            {orders.length} 笔筛选结果
          </p>
        </div>
        <div className="max-h-[calc(100vh-22rem)] min-h-60 overflow-y-auto lg:max-h-[calc(100vh-20rem)]">
          {orders.map((order) => (
            <button
              key={order.id}
              type="button"
              onClick={() => {
                onSelect(order.id);
              }}
              className={`block w-full border-b border-border px-4 py-3 text-left last:border-0 hover:bg-[#FFFCF9] ${selected?.id === order.id ? "border-l-[3px] border-l-accent bg-[#FFFCF4]" : ""}`}
            >
              <span className="flex items-baseline justify-between gap-2">
                <span className="font-mono text-[11px] font-semibold">
                  {order.order_number}
                </span>
                <strong className="font-mono text-xs">
                  {formatCny(order.amount_due_cny)}
                </strong>
              </span>
              <strong className="mt-1 block truncate text-sm">
                {order.customer_name || "散客"}
              </strong>
              <span className="mt-2 flex items-center justify-between gap-2 text-[10px] text-muted">
                <span>
                  {formatShanghaiDateTime(order.created_at).slice(0, 10)}
                </span>
                <span className="flex items-center gap-1"><SalesOrderStatusTags order={order} compact />{order.payment_review?.status === "pending" && <span className="rounded-full bg-orange-50 px-2 py-0.5 text-[10px] font-bold text-orange-800">待核实</span>}</span>
              </span>
            </button>
          ))}
          {!orders.length && (
            <div className="px-4 py-14 text-center text-sm text-muted">
              当前筛选条件下没有订单
            </div>
          )}
        </div>
      </section>

      <section
        className={
          (!selected ? "hidden lg:block " : "") +
          "min-w-0 overflow-hidden rounded-md border border-border bg-white shadow-sm"
        }
      >
        {!selected && (
          <div className="grid min-h-[420px] place-items-center px-6 text-center text-sm text-muted">
            <div>
              <p className="text-2xl">→</p>
              <p className="mt-2 font-semibold text-fg">请选择一笔订单</p>
              <p className="mt-1">
                查看订单、客户、商品成本、业务事实与当前可用动作。
              </p>
            </div>
          </div>
        )}
        {selected && (
          <>
            <div className="border-b border-border bg-[#FFFDFA] px-4 py-4 sm:px-5">
              <button
                type="button"
                onClick={() => onSelect(null)}
                className="mb-3 rounded border border-border px-2 py-1 text-xs lg:hidden"
              >
                ← 返回订单轨道
              </button>
              <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-start">
                <div>
                  <h2 className="font-display text-xl font-semibold">
                    {selected.order_number}
                  </h2>
                  <p className="mt-1 text-xs text-muted">
                    创建于 {formatShanghaiDateTime(selected.created_at)} ·{" "}
                    {selected.items.length} 项商品
                  </p>
                </div>
                <div className="flex flex-wrap gap-1.5 text-[11px]">
                  <SalesOrderStatusTags order={selected} />
                </div>
              </div>
              <OrderActions
                order={selected}
                accounts={allAccounts}
                accountsError={accountsError}
                onChanged={onChanged}
              />
              <div className="mt-4">
                <ReceiptPanel key={selected.id} order={selected} accounts={allAccounts} onChanged={onChanged} />
              </div>
            </div>
            <div className="max-h-[calc(100vh-24rem)] min-h-[360px] space-y-6 overflow-y-auto p-4 sm:p-5">
              <DetailSection title="概览">
                <Overview order={selected} onCustomer={onCustomer} />
              </DetailSection>
              <DetailSection title="商品明细">
                <Items order={selected} />
              </DetailSection>
              <DetailSection title="金额与利润">
                <Amounts order={selected} />
              </DetailSection>
              <DetailSection title="业务事实">
                <Facts order={selected} accounts={allAccounts} />
              </DetailSection>
              <DetailSection title="时间线">
                <Timeline order={selected} accounts={allAccounts} />
              </DetailSection>
            </div>
          </>
        )}
      </section>
    </div>
  );
}

function DetailSection({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section>
      <div className="mb-2 flex items-center justify-between border-b border-border pb-2">
        <h3 className="font-display text-base font-semibold">{title}</h3>
        <span className="font-mono text-[10px] uppercase tracking-wide text-muted">
          Order detail
        </span>
      </div>
      {children}
    </section>
  );
}

function Overview({
  order,
  onCustomer,
}: {
  order: SalesOrder;
  onCustomer: (id: number) => void;
}) {
  const financial = salesOrderFinancialView(order);
  return (
    <div className="space-y-5">
      <div>
        <div className="mb-2 flex items-center justify-between">
          <h3 className="text-xs font-bold uppercase tracking-wide">
            客户资料
          </h3>
          {order.customer_id && !order.customer?.deleted_at && (
            <button
              type="button"
              onClick={() => onCustomer(order.customer_id!)}
              className="text-xs font-semibold text-accent hover:underline"
            >
              查看 / 编辑 →
            </button>
          )}
        </div>
        <div className="rounded border border-border bg-[#FFFDFA] p-4">
          <strong>{order.customer_name || "散客"}</strong>
          {order.customer?.deleted_at && (
            <span className="ml-2 rounded-full bg-gray-100 px-2 py-0.5 text-[10px] text-muted">
              已归档客户
            </span>
          )}
          <p className="mt-1 text-xs text-muted">
            {order.customer?.phone || "未填写电话"}
          </p>
        </div>
      </div>
      <div>
        <h3 className="mb-2 text-xs font-bold uppercase tracking-wide">
          订单信息
        </h3>
        <dl className="grid gap-3 rounded border border-border p-4 text-xs sm:grid-cols-2">
          <Info
            label="订单状态"
            value={statusLabel(order.fulfillment_status)}
          />
          <Info label="付款状态" value={statusLabel(order.payment_status)} />
          <Info label="应收金额" value={formatCny(order.amount_due_cny)} /><Info label="累计已收" value={formatCny(order.received_amount_cny ?? 0)} /><Info label="剩余待收" value={formatCny(order.remaining_amount_cny ?? order.amount_due_cny)} />
          <Info
            label={financial.profitLabel}
            value={financial.contributionProfit === null ? "—" : formatCny(financial.contributionProfit)}
          />
          <Info label="备注" value={order.note || "—"} />
          <Info
            label="可用动作"
            value={order.available_actions.map(actionLabel).join("、") || "无"}
          />
        </dl>
      </div>
    </div>
  );
}

function Items({ order }: { order: SalesOrder }) {
  return (
    <div className="overflow-x-auto rounded border border-border">
      <table className="w-full min-w-[680px] text-xs">
        <thead className="bg-[#F5EFE8] text-muted">
          <tr>
            <th className="px-3 py-2 text-left">品牌 / 商品</th>
            <th className="px-3 py-2 text-right">数量</th>
            <th className="px-3 py-2 text-right">单价</th>
            <th className="px-3 py-2 text-left">库存批次</th>
            <th className="px-3 py-2 text-right">成本</th>
          </tr>
        </thead>
        <tbody>
          {order.items.map((item) => (
            (() => {
              const cost = salesOrderItemCostView(order, item);
              return (
            <tr key={item.id} className="border-t border-border">
              <td className="px-3 py-3">
                <span className="block text-[10px] font-bold uppercase tracking-wide text-muted">
                  {item.cigar_brand_cn || item.cigar_brand || "未标注品牌"}
                </span>
                <strong className="mt-0.5 block">{item.cigar_name}</strong>
              </td>
              <td className="px-3 py-3 text-right">
                {item.sale_unit === "box" ? item.sale_quantity : item.quantity}{" "}
                {item.sale_unit === "box" ? "盒" : "支"}
              </td>
              <td className="px-3 py-3 text-right font-mono">
                {formatCny(item.unit_price)}
              </td>
              <td className="px-3 py-3 text-muted">
                {item.allocations
                  .map(
                    (allocation) => {
                      const status = allocation.status === "reserved" ? "预留" : allocation.status === "fulfilled" ? "已出库" : allocation.status === "returned" ? "已退回" : "已释放";
                      const amount = allocation.cost_cny != null && allocation.status !== "released" ? ` · ${formatCny(allocation.cost_cny)}` : "";
                      return `#${allocation.batch_id} × ${allocation.quantity}（${status}${amount}）`;
                    },
                  )
                  .join("，") || "确认订单后分配"}
              </td>
              <td className="px-3 py-3 text-right font-mono">
                <span className="block">{cost.totalCost === null ? "—" : formatCny(cost.totalCost)}</span>
                <span className="block text-[10px] text-muted">{cost.label}{cost.unitCost === null ? "" : ` · ${formatCny(cost.unitCost)}/支`}</span>
              </td>
            </tr>
              );
            })()
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ReceiptPanel({
  order,
  accounts: allAccounts,
  onChanged,
}: {
  order: SalesOrder;
  accounts: FundAccount[];
  onChanged: () => void;
}) {
  const receipt = order.sales_receipt;
  const activeNote = (order.payment_notes || []).find((note) => note.is_active);
  const activeNoteUrl = activeNote ? publicPrivnoteUrl(activeNote.url) : "";
  const review = order.payment_review;
  const canCreateLink =
    !activeNote &&
    ["unpaid", "partial"].includes(order.payment_status) &&
    ["confirmed", "shipped"].includes(order.fulfillment_status);
  const [open, setOpen] = useState(false);
  const [methods, setMethods] = useState<PaymentMethod[]>([]);
  const [source, setSource] = useState<"temporary" | "saved">("temporary");
  const [methodId, setMethodId] = useState("");
  const [temporaryType, setTemporaryType] = useState<"wechat" | "alipay" | "bank_card">("wechat");
  const [temporaryAccountId, setTemporaryAccountId] = useState("");
  const [temporaryBankName, setTemporaryBankName] = useState("");
  const [temporaryCardNumber, setTemporaryCardNumber] = useState("");
  const [temporaryCardHolder, setTemporaryCardHolder] = useState("");
  const [temporaryQr, setTemporaryQr] = useState<File | null>(null);
  const [remark, setRemark] = useState("");
  const [duration, setDuration] = useState("24");
  const [password, setPassword] = useState("");
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);
  const [reviewOpen, setReviewOpen] = useState(false);
  const cnyAccounts = allAccounts.filter((account) => account.currency === "CNY" && account.is_active);
  const selectedAccountId = selectActiveCnyAccountId(allAccounts, Number(temporaryAccountId)) || "";

  const startCreate = async () => {
    setError("");
    setUrl("");
    setCopied(false);
    setOpen(true);
    if (methods.length) return;
    try {
      const loaded = await fetchPaymentMethods();
      setMethods(loaded);
    } catch (requestError) {
      setError(apiErrorMessage(requestError, "收款方式加载失败"));
    }
  };
  const createLink = async () => {
    if (busy) return;
    if (source === "temporary" && temporaryType !== "bank_card" && !temporaryQr) { setError("请上传收款二维码"); return; }
    if (source === "saved" && !methodId) {
      setError("请选择一个常用收款方式");
      return;
    }
    if (source === "temporary" && !selectedAccountId) {
      setError("临时收款方式必须选择人民币入账账户");
      return;
    }
    if (source === "temporary" && temporaryQr && (temporaryQr.size > 5 * 1024 * 1024 || !["image/jpeg", "image/png", "image/webp"].includes(temporaryQr.type))) { setError("二维码需为 JPG、PNG 或 WebP，且不超过 5MB"); return; }
    setBusy(true);
    setError("");
    try {
      const form = new FormData();
      form.append("note_type", "payment");
      form.append("sales_order_id", String(order.id));
      form.append("payment_source", source);
      if (source === "saved") form.append("payment_method_id", methodId);
      if (source === "temporary") {
        form.append("fund_account_id", String(selectedAccountId));
        form.append("temporary_method_type", temporaryType);
        form.append("temporary_bank_name", temporaryBankName);
        form.append("temporary_card_number", temporaryCardNumber);
        form.append("temporary_card_holder", temporaryCardHolder);
        if (temporaryQr) form.append("temporary_qr_image", temporaryQr);
      }
      form.append("duration", duration);
      form.append("password", password);
      if (remark.trim()) form.append("remark", remark.trim());
      const result = await createPrivnote(form);
      setUrl(publicPrivnoteUrl(result.url));
      setCopied(false);
      onChanged();
    } catch (requestError) {
      setError(apiErrorMessage(requestError, "收款单创建失败"));
    } finally {
      setBusy(false);
    }
  };
  if (receipt && !["unpaid", "partial"].includes(order.payment_status))
    return (
      <div className="grid gap-3 rounded border border-green-200 bg-green-50/40 p-4 text-sm sm:grid-cols-4">
        <div>
          <span className="block text-xs text-muted">最近收款记录</span>
          <strong className="mt-1 block font-mono">
            RC-{String(receipt.id).padStart(6, "0")}
          </strong>
        </div>
        <div>
          <span className="block text-xs text-muted">累计已收</span>
          <strong className="mt-1 block font-mono text-green-800">
            {formatCny(order.received_amount_cny ?? receipt.amount_cny)}
          </strong>
        </div>
        <div>
          <span className="block text-xs text-muted">业务日期</span>
          <strong className="mt-1 block">{receipt.business_date}</strong>
        </div>
        <div>
          <span className="block text-xs text-muted">资金账户</span>
          <strong className="mt-1 block">#{receipt.fund_account_id}</strong>
        </div>
      </div>
    );
  return (
    <div className="rounded-md border-t-4 border border-gold/60 bg-[#FFFDFA] p-4 text-sm shadow-sm">
      {activeNote && (
        <div className="mb-4 rounded border border-blue-200 bg-blue-50/50 p-3">
          <strong className="block text-blue-900">付款链接已创建</strong>
          <span className="mt-1 block text-xs text-blue-800">
            客户可在链接有效期内反复查看并提交付款凭证。
          </span>
          <div className="mt-2 break-all font-mono text-xs text-fg">
            {activeNoteUrl}
          </div>
          <div className="mt-2 text-xs text-muted">
            创建于 {formatShanghaiDateTime(activeNote.created_at)} · 查看{" "}
            {activeNote.view_count} 次 · 到期{" "}
            {formatShanghaiDateTime(activeNote.expires_at)}
          </div>
          <button
            type="button"
            onClick={() => {
              void copyText(activeNoteUrl).then((ok) => setCopied(ok));
            }}
            className="mt-2 rounded border border-blue-300 px-2 py-1 text-xs text-blue-800"
          >
            {copied ? "已复制" : "复制收款单"}
          </button>
        </div>
      )}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-2"><strong className="block text-fg">{review?.status === "pending" ? "客户已提交凭证，等待人工核实" : review?.status === "needs_more" ? "等待客户补充凭证" : "收款进度"}</strong><span className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${review ? "bg-orange-50 text-orange-800" : "bg-blue-50 text-blue-800"}`}>{review?.status === "pending" ? "待核实" : review?.status === "needs_more" ? "需补充" : activeNote ? "链接有效" : "待创建"}</span></div>
          <span className="mt-1 block text-xs text-muted">
            应收 {formatCny(order.amount_due_cny)} · 已收 {formatCny(order.received_amount_cny ?? 0)} · 待收 {formatCny(order.remaining_amount_cny ?? order.amount_due_cny)} · 截图提交不代表已到账，确认后才生成正式收款记录。
          </span>
        </div>
        <div className="flex flex-wrap gap-2">
        {review?.status === "pending" && (
          <button type="button" onClick={() => setReviewOpen(true)} className="rounded bg-accent px-3 py-2 text-xs font-semibold text-white hover:bg-accent-hover">核实收款</button>
        )}
        {canCreateLink && review?.status !== "pending" && (
          <button
            type="button"
            onClick={startCreate}
            className="rounded bg-accent px-3 py-2 text-xs font-semibold text-white hover:bg-accent-hover"
          >
            创建收款单
          </button>
        )}
        </div>
      </div>
      {!canCreateLink && !activeNote && !review && (
        <p className="mt-3 text-xs text-muted">订单确认后才可以创建收款单。</p>
      )}
      {open && (canCreateLink || Boolean(url)) && <PaymentRequestModal
        order={order} source={source} setSource={setSource} methods={methods} methodId={methodId} setMethodId={setMethodId}
        accounts={cnyAccounts} temporaryType={temporaryType} setTemporaryType={setTemporaryType}
        temporaryAccountId={String(selectedAccountId)} setTemporaryAccountId={setTemporaryAccountId}
        temporaryBankName={temporaryBankName} setTemporaryBankName={setTemporaryBankName}
        temporaryCardNumber={temporaryCardNumber} setTemporaryCardNumber={setTemporaryCardNumber}
        temporaryCardHolder={temporaryCardHolder} setTemporaryCardHolder={setTemporaryCardHolder}
        temporaryQr={temporaryQr} setTemporaryQr={setTemporaryQr} duration={duration} setDuration={setDuration}
        password={password} setPassword={setPassword} remark={remark} setRemark={setRemark} busy={busy} error={error}
        url={url} copied={copied} onCopy={() => { void copyText(url).then(setCopied); }} onClose={() => setOpen(false)} onSubmit={createLink}
      />}
      {reviewOpen && <PaymentReviewModal order={order} accounts={cnyAccounts} onClose={() => setReviewOpen(false)} onChanged={onChanged} />}
    </div>
  );
}

function PaymentReviewModal({ order, accounts, onClose, onChanged }: { order: SalesOrder; accounts: FundAccount[]; onClose: () => void; onChanged: () => void }) {
  const [submissions, setSubmissions] = useState<PaymentSubmission[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [reviewNote, setReviewNote] = useState("");
  const [businessDate, setBusinessDate] = useState(salesOrderActionBusinessDate());
  const [amount, setAmount] = useState('');
  const [accountId, setAccountId] = useState<number | null>(null);
  const [confirmReceipt, setConfirmReceipt] = useState(false);
  const inFlight = useRef(false);
  const remaining = order.remaining_amount_cny ?? order.amount_due_cny;
  const current = submissions.find(item => item.status === "pending") || null;
  const selectedAccountId = accountId ?? current?.fund_account_id ?? 0;
  const validAmount = receiveAmountWithinRemaining(amount, remaining);
  const load = () => { setLoading(true); fetchPaymentSubmissions(order.id).then(setSubmissions).catch(requestError => setError(apiErrorMessage(requestError, "付款凭证加载失败"))).finally(() => setLoading(false)); };
  useEffect(() => {
    let cancelled = false;
    void fetchPaymentSubmissions(order.id)
      .then(values => { if (!cancelled) setSubmissions(values); })
      .catch(requestError => { if (!cancelled) setError(apiErrorMessage(requestError, "付款凭证加载失败")); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [order.id]);
  const accept = async () => { if (!current || !businessDate || !validAmount || inFlight.current) return; inFlight.current = true; setBusy(true); setError(""); try { await acceptPaymentSubmission(order.id, current.id, businessDate, amount, selectedAccountId); onChanged(); onClose(); } catch (requestError) { setError(apiErrorMessage(requestError, "确认到账失败")); } finally { inFlight.current = false; setBusy(false); } };
  const needsMore = async () => { if (!current) return; if (!reviewNote.trim()) { setError("请填写客户可见的补充说明"); return; } setBusy(true); setError(""); try { await requestMorePaymentEvidence(order.id, current.id, reviewNote.trim()); load(); onChanged(); } catch (requestError) { setError(apiErrorMessage(requestError, "发送补充要求失败")); } finally { setBusy(false); } };
  return <><PaymentDialog title="核实付款凭证" width="3xl" onClose={onClose} busy={busy}><div className="w-full bg-white"><header className="sticky top-0 z-10 flex justify-between border-b border-border bg-[#FFFDFA] px-5 py-4"><div><h3 className="font-display text-xl font-semibold">核实收款</h3><p className="mt-1 text-xs text-muted">{order.order_number} · 应收 {formatCny(order.amount_due_cny)} · 确认到账会生成正式收款，履约状态不变。</p></div><button type="button" onClick={onClose} className="rounded border border-border p-1.5 text-muted"><X className="h-4 w-4" /></button></header><div className="space-y-4 p-5">{loading ? <p className="text-sm text-muted">加载付款凭证…</p> : !current ? <p className="rounded border border-border bg-[#FFFDFA] p-4 text-sm text-muted">当前没有待核实的付款凭证。</p> : <><div className="grid gap-3 rounded border border-border bg-[#FFFDFA] p-4 text-xs sm:grid-cols-3"><div><span className="block text-muted">应收金额</span><strong className="mt-1 block font-mono text-base">{formatCny(order.amount_due_cny)}</strong><span className="mt-1 block">已收 {formatCny(order.received_amount_cny ?? 0)} · 待收 {formatCny(remaining)}</span></div><div><span className="block text-muted">入账账户 ID</span><strong className="mt-1 block">#{current.fund_account_id}</strong></div><div><span className="block text-muted">提交时间</span><strong className="mt-1 block">{current.submitted_at ? formatShanghaiDateTime(current.submitted_at) : "—"}</strong></div></div><div><h4 className="text-xs font-bold uppercase tracking-wide text-muted">付款凭证</h4><div className="mt-2 grid grid-cols-2 gap-3 sm:grid-cols-3">{current.attachments?.map(attachment => <a key={attachment.id} href={paymentSubmissionAttachmentUrl(order.id, current.id, attachment.id)} target="_blank" rel="noreferrer" className="overflow-hidden rounded border border-border bg-[#FFFDFA] hover:border-gold"><img src={paymentSubmissionAttachmentUrl(order.id, current.id, attachment.id)} alt={attachment.name} className="aspect-square w-full object-cover" /><span className="block truncate p-2 text-[11px] text-muted">{attachment.name}</span></a>)}</div></div><div className="grid gap-3 sm:grid-cols-2"><label className="text-xs font-semibold text-muted">本次实收金额<input type="number" min="0.01" max={remaining} step="0.01" value={amount} onChange={event => setAmount(event.target.value)} className="mt-1.5 w-full rounded border border-border px-3 py-2 text-sm text-fg" placeholder="核实实际到账金额" /></label><label className="text-xs font-semibold text-muted">到账账户<select value={selectedAccountId} onChange={event => setAccountId(Number(event.target.value))} className="mt-1.5 w-full rounded border border-border px-3 py-2 text-sm text-fg"><option value={0}>请选择到账账户</option>{accounts.map(account => <option key={account.id} value={account.id}>{account.name}</option>)}</select></label><label className="text-xs font-semibold text-muted">业务日期<input type="date" value={businessDate} onChange={event => setBusinessDate(event.target.value)} className="mt-1.5 w-full rounded border border-border px-3 py-2 text-sm text-fg" /></label><label className="text-xs font-semibold text-muted">需补充说明（客户可见）<textarea value={reviewNote} onChange={event => setReviewNote(event.target.value)} rows={2} className="mt-1.5 w-full rounded border border-border px-3 py-2 text-sm text-fg" placeholder="例如：请补充含付款账户尾号的完整回单" /></label></div></>}</div>{error && <p className="mx-5 mb-0 rounded border border-red-200 bg-red-50 p-3 text-xs text-red-700">{error}</p>}<footer className="sticky bottom-0 flex justify-end gap-2 border-t border-border bg-[#FFFDFA] px-5 py-4"><button type="button" onClick={onClose} className="rounded border border-border px-4 py-2 text-sm">关闭</button>{current && <><button type="button" onClick={needsMore} disabled={busy} className="rounded border border-red-200 px-4 py-2 text-sm font-semibold text-red-700 disabled:opacity-50">需补充凭证</button><button type="button" onClick={() => setConfirmReceipt(true)} disabled={busy || !businessDate || !validAmount || !accounts.some(account => account.id === selectedAccountId)} className="rounded bg-accent px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">{busy ? "处理中…" : "确认到账"}</button></>}</footer></div></PaymentDialog>{confirmReceipt && <ReceiptConfirmation order={order} amount={amount} date={businessDate} accountName={accounts.find(account => account.id === selectedAccountId)?.name || ''} busy={busy} onBack={() => setConfirmReceipt(false)} onConfirm={accept} error={error} />}</>;
}

function Amounts({ order }: { order: SalesOrder }) {
  const financial = salesOrderFinancialView(order);
  const transportRecorded = Boolean(order.sales_transport_cost);
  const transportLabel = transportRecorded
    ? "实际人肉成本"
    : order.fulfillment_status === "shipped"
      ? "实际人肉成本（待记录）"
      : "实际人肉成本（履约后记录）";
  return (
    <div className="space-y-3 rounded border border-border p-4 text-sm">
      <Money label="商品金额" value={order.goods_amount_cny} />
      <Money label="客户承担人肉费" value={order.customer_transport_fee_cny} />
      <Money label="应收合计" value={order.amount_due_cny} strong />
      <div className="border-t border-border pt-3">
        <Money label={financial.costLabel} value={financial.totalCost} />
      </div>
      <Money label={transportLabel} value={transportRecorded ? order.actual_transport_cost_cny : null} />
      <Money
        label={financial.profitLabel}
        value={financial.contributionProfit}
        strong
        tone={financial.contributionProfit === null ? undefined : financial.contributionProfit >= 0 ? "green" : "red"}
      />
      <p className="border-t border-border pt-3 text-xs leading-relaxed text-muted">{financial.note}</p>
    </div>
  );
}

function Facts({ order, accounts }: { order: SalesOrder; accounts: FundAccount[] }) {
  const accountName = (accountId: number) =>
    accounts.find((account) => account.id === accountId)?.name || `账户 #${accountId}`;
  const facts = [
    ...(order.sales_receipts || (order.sales_receipt ? [{
      ...order.sales_receipt,
      reversed_at: null,
      reversal_business_date: null,
      reversal_reason: "",
    }] : [])).map((receipt) => ({
      type: receipt.reversed_at ? "SalesReceipt · 已撤回收款" : "SalesReceipt · 有效收款",
      id: receipt.id,
      amount: receipt.amount_cny,
      date: receipt.business_date,
      detail: receipt.reversed_at
        ? `${accountName(receipt.fund_account_id)} · 撤回日期 ${receipt.reversal_business_date} · ${receipt.reversal_reason}`
        : `到账账户：${accountName(receipt.fund_account_id)}`,
    })),
    order.sales_shipment && {
      type: "SalesShipment · 出库",
      id: order.sales_shipment.id,
      amount: order.sales_shipment.fifo_cost_cny,
      date: order.sales_shipment.business_date,
    },
    order.sales_refund && {
      type: "SalesRefund · 退款",
      id: order.sales_refund.id,
      amount: order.sales_refund.amount_cny,
      date: order.sales_refund.business_date,
      detail: order.sales_refund.accounts?.map(item => `${accountName(item.fund_account_id)} · ${formatCny(item.amount_cny)}`).join("；"),
    },
    order.sales_return && {
      type: "SalesReturn · 退货",
      id: order.sales_return.id,
      amount: order.sales_return.amount_cny,
      date: order.sales_return.business_date,
    },
    order.sales_transport_cost && {
      type: "SalesTransportCost · 人肉成本",
      id: order.sales_transport_cost.id,
      amount: order.sales_transport_cost.actual_cost_cny,
      date: order.sales_transport_cost.business_date,
    },
  ].filter(Boolean) as {
    type: string;
    id: number;
    amount: number;
    date: string;
    detail?: string;
  }[];
  if (!facts.length)
    return (
      <div className="rounded border border-dashed border-border px-4 py-14 text-center text-sm text-muted">
        尚未生成业务事实
      </div>
    );
  return (
    <div className="grid gap-3 xl:grid-cols-2">
      {facts.map((fact) => (
        <div
          key={`${fact.type}-${fact.id}`}
          className="rounded border border-border border-l-4 border-l-gold bg-[#FFFDFA] p-4"
        >
          <span className="text-[10px] font-bold uppercase tracking-wide text-muted">
            {fact.type}
          </span>
          <strong className="mt-2 block font-mono text-lg">
            {formatCny(fact.amount)}
          </strong>
          <p className="mt-1 text-xs text-muted">
            事实 #{fact.id} · 业务日期 {fact.date}
          </p>
          {fact.detail && <p className="mt-1 text-xs text-muted">{fact.detail}</p>}
        </div>
      ))}
    </div>
  );
}

function Timeline({ order, accounts }: { order: SalesOrder; accounts: FundAccount[] }) {
  const accountName = (id: number) => accounts.find(account => account.id === id)?.name || `账户 #${id}`;
  const itemSummary = order.items.map(item => `${item.cigar_name} × ${item.quantity} 支`).join("；");
  const receipts = order.sales_receipts || (order.sales_receipt ? [{
    ...order.sales_receipt, reversed_at: null, reversal_business_date: null, reversal_reason: "",
  }] : []);
  const events = [
    order.created_at && {
      label: "销售单创建", date: order.created_at,
      detail: `客户：${order.customer_name || "未填写"} · 当前订单应收 ${formatCny(order.amount_due_cny)}`,
    },
    order.confirmed_at && {
      label: "订单确认", date: order.confirmed_at,
      detail: `${itemSummary || "无商品明细"} · ${order.items.some(item => item.fulfillment_type === 'in_stock') ? "现货已预留" : "预售待备货"}`,
    },
    ...receipts.flatMap(receipt => [
      {
        label: `登记收款记录 #${receipt.id}`, date: receipt.business_date,
        detail: `实收 ${formatCny(receipt.amount_cny)} · 到账账户：${accountName(receipt.fund_account_id)}`,
      },
      receipt.reversed_at && {
        label: `撤回收款记录 #${receipt.id}`, date: receipt.reversal_business_date || receipt.reversed_at,
        detail: `撤回 ${formatCny(receipt.amount_cny)} · 原账户：${accountName(receipt.fund_account_id)} · 原因：${receipt.reversal_reason || "未填写"}`,
      },
    ]),
    order.payment_review && {
      label: order.payment_review.status === 'pending' ? "付款凭证待核实" : "付款凭证待补充",
      date: order.payment_review.submitted_at,
      detail: `凭证 #${order.payment_review.id} · 尚未确认到账${order.payment_review.review_note ? ` · ${order.payment_review.review_note}` : ''}`,
    },
    order.sales_shipment && {
      label: "订单出库", date: order.sales_shipment.business_date,
      detail: `${itemSummary} · 出库成本 ${formatCny(order.sales_shipment.fifo_cost_cny)}`,
    },
    order.sales_transport_cost && {
      label: "登记人肉成本", date: order.sales_transport_cost.business_date,
      detail: `实际成本 ${formatCny(order.sales_transport_cost.actual_cost_cny)} · 付款账户：${accountName(order.sales_transport_cost.fund_account_id)}`,
    },
    order.sales_return && {
      label: "订单退货", date: order.sales_return.business_date,
      detail: `退货金额 ${formatCny(order.sales_return.amount_cny)} · 回库成本 ${formatCny(order.sales_return.fifo_cost_cny)} · 原因：${order.sales_return.reason || "未填写"}`,
    },
    order.sales_refund && {
      label: "订单退款", date: order.sales_refund.business_date,
      detail: `退款 ${formatCny(order.sales_refund.amount_cny)} · ${(order.sales_refund.accounts?.length
        ? order.sales_refund.accounts.map(item => `${accountName(item.fund_account_id)} ${formatCny(item.amount_cny)}`).join("；")
        : order.sales_refund.fund_account_id ? accountName(order.sales_refund.fund_account_id) : "账户明细未提供")}`,
    },
    order.cancelled_at && { label: "订单取消", date: order.cancelled_at, detail: "订单履约已取消；收款和退款以各自流水为准。" },
  ].filter(Boolean) as { label: string; date: string; detail: string }[];
  // Historical facts expose business dates, not a reliable within-day sequence.
  const days = new Map<string, typeof events>();
  for (const event of events) {
    const day = formatShanghaiDateTime(event.date).slice(0, 10);
    days.set(day, [...(days.get(day) || []), event]);
  }
  return (
    <ol aria-label="订单时间线" className="space-y-0">
      {[...days].sort(([a], [b]) => a.localeCompare(b)).map(([day, dayEvents]) => (
        <li key={day} className="relative border-l border-border pb-5 pl-5 last:pb-0">
          <span className="absolute -left-1 top-1 h-2 w-2 rounded-full bg-accent" />
          <strong className="block font-mono text-sm">{day}</strong>
          {dayEvents.length > 1 && <p className="mt-1 text-[11px] text-muted">同日记录，未按实际先后排序</p>}
          {dayEvents.map((event, index) => <div key={`${event.label}-${index}`} className="mt-3">
            <strong className="block text-sm">{event.label}</strong>
            <p className="mt-1 break-words text-xs leading-relaxed text-fg">{event.detail}</p>
            {event.date.includes('T') && <span className="mt-1 block font-mono text-[11px] text-muted">{formatShanghaiDateTime(event.date)}</span>}
          </div>)}
        </li>
      ))}
    </ol>
  );
}

function OrderActions({
  order,
  accounts: allAccounts,
  accountsError,
  onChanged,
}: {
  order: SalesOrder;
  accounts: FundAccount[];
  accountsError: string;
  onChanged: () => void;
}) {
  const accounts = useMemo(
    () =>
      allAccounts.filter(
        (account) => account.currency === "CNY" && account.is_active,
      ),
    [allAccounts],
  );
  const [action, setAction] = useState("");
  const [confirmReceipt, setConfirmReceipt] = useState(false);
  const [date, setDate] = useState(salesOrderActionBusinessDate());
  const [amount, setAmount] = useState("");
  const [reason, setReason] = useState("");
  const [accountId, setAccountId] = useState(accounts[0]?.id ?? 0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const selectedAccountId = selectActiveCnyAccountId(allAccounts, accountId);
  const actions = Array.isArray(order.available_actions)
    ? order.available_actions
    : [];
  const needsBusinessDate = [
    "ship",
    "receive",
    "refund",
    "return",
    "transport_cost",
    "withdraw_receipt",
  ].includes(action);
  const receiveMatchesDue =
    action !== "receive" ||
    receiveAmountWithinRemaining(amount, order.remaining_amount_cny ?? order.amount_due_cny);

  const open = (nextAction: string) => {
    setAction(nextAction);
    setError("");
    setReason("");
    setConfirmReceipt(false);
    setAmount(nextAction === "receive" ? String(order.remaining_amount_cny ?? order.amount_due_cny) : "");
    setDate(salesOrderActionBusinessDate());
  };
  const actionInFlight = useRef(false);
  const executeAction = async () => {
    if (actionInFlight.current) return;
    actionInFlight.current = true;
    setBusy(true);
    try {
      if (action === "confirm") await confirmSalesOrder(order.id);
      if (action === "cancel") await cancelSalesOrder(order.id);
      if (action === "ship") await shipSalesOrder(order.id, date);
      if (action === "receive")
        await receiveSalesOrder(order.id, {
          amount_cny: amount,
          fund_account_id: selectedAccountId,
          business_date: date,
        });
      if (action === "withdraw_receipt")
        await withdrawSalesOrderReceipt(order.id, {
          ...(order.sales_receipt ? { sales_receipt_id: order.sales_receipt.id } : {}),
          business_date: date,
          reason: reason.trim(),
        });
      if (action === "refund") await refundSalesOrder(order.id, date);
      if (action === "return")
        await returnSalesOrder(order.id, {
          business_date: date,
          reason: reason.trim(),
        });
      if (action === "transport_cost")
        await recordSalesTransportCost(order.id, {
          actual_cost_cny: amount,
          fund_account_id: selectedAccountId,
          business_date: date,
        });
      setConfirmReceipt(false);
      setAction("");
      onChanged();
    } catch (requestError) {
      setError(apiErrorMessage(requestError));
    } finally {
      actionInFlight.current = false;
      setBusy(false);
    }
  };
  const run = async () => {
    setError("");
    if (action === "receive" && !receiveMatchesDue) {
      setError(
        `本次实收须大于零且不超过剩余待收 ${formatCny(order.remaining_amount_cny ?? order.amount_due_cny)}，请修正差额后提交。`,
      );
      return;
    }
    if (["return", "withdraw_receipt"].includes(action) && !reason.trim()) {
      setError(action === "return" ? "退货原因不能为空" : "撤回原因不能为空");
      return;
    }
    const accountError = salesFundAccountError(action, selectedAccountId);
    if (accountError) {
      setError(accountError);
      return;
    }
    if (action === "receive") {
      setConfirmReceipt(true);
      return;
    }
    await executeAction();
  };

  return (
    <div className="mt-3">
      <div className="flex flex-wrap gap-2">
        {actions.map((item) => (
          <button
            key={item}
            type="button"
            onClick={() => open(item)}
            disabled={Boolean(accountsError && actionNeedsFundAccount(item))}
            className={`inline-flex items-center gap-1 rounded border px-3 py-1.5 text-xs font-semibold ${["cancel", "refund", "return", "withdraw_receipt"].includes(item) ? "border-red-200 text-red-700 hover:bg-red-50" : item === "receive" ? "border-accent bg-accent text-white" : "border-border hover:border-gold"}`}
          >
            {item === "confirm" && <PackageCheck className="h-3.5 w-3.5" />}
            {item === "ship" && <Truck className="h-3.5 w-3.5" />}
            {item === "receive" && <CircleDollarSign className="h-3.5 w-3.5" />}
            {["refund", "return", "withdraw_receipt"].includes(item) && (
              <RotateCcw className="h-3.5 w-3.5" />
            )}
            {actionLabel(item)}
          </button>
        ))}
      </div>
      {action && (
        <PaymentDialog title={actionLabel(action)} width="md" busy={busy} onClose={() => setAction("")}>
          <div className="w-full bg-white">
            <div className="flex items-center justify-between border-b border-border px-5 py-4">
              <div>
                <h3 className="font-display text-lg font-semibold">
                  {actionLabel(action)}
                </h3>
                <p className="mt-0.5 text-xs text-muted">
                  {order.order_number}
                </p>
              </div>
              <button
                type="button"
                aria-label="关闭订单动作"
                onClick={() => setAction("")}
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="space-y-3 p-5">
              {action === "confirm" && <ConfirmSummary order={order} />}
              {[
                "ship",
                "receive",
                "refund",
                "return",
                "transport_cost",
                "withdraw_receipt",
              ].includes(action) && (
                <label className="block text-xs font-medium text-muted">
                  业务日期
                  <input
                    type="date"
                    value={date}
                    onChange={(event) => setDate(event.target.value)}
                    className="mt-1.5 w-full rounded border border-border px-3 py-2 text-sm"
                  />
                </label>
              )}
              {["return", "withdraw_receipt"].includes(action) && (
                <label className="block text-xs font-medium text-muted">
                  {action === "return" ? "退货原因" : "撤回原因"}
                  <input
                    value={reason}
                    onChange={(event) => setReason(event.target.value)}
                    className="mt-1.5 w-full rounded border border-border px-3 py-2 text-sm"
                  />
                </label>
              )}
              {(action === "receive" || action === "transport_cost") && (
                <>
                  <label className="block text-xs font-medium text-muted">
                    {action === "receive"
                      ? `本次实收金额（最多 ${formatCny(order.remaining_amount_cny ?? order.amount_due_cny)}）`
                      : "实际人肉成本"}
                    <input
                      type="number"
                      min="0"
                      step="0.01"
                      value={amount}
                      onChange={(event) => setAmount(event.target.value)}
                      className="mt-1.5 w-full rounded border border-border px-3 py-2 text-sm"
                    />
                  </label>
                  {action === "receive" && amount && !receiveMatchesDue && (
                    <p className="rounded border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
                      本次实收须大于零且不超过剩余待收 {formatCny(order.remaining_amount_cny ?? order.amount_due_cny)}。
                    </p>
                  )}
                  <label className="block text-xs font-medium text-muted">
                    资金账户
                    <select
                      value={selectedAccountId}
                      onChange={(event) =>
                        setAccountId(Number(event.target.value))
                      }
                      className="mt-1.5 w-full rounded border border-border bg-white px-3 py-2 text-sm"
                    >
                      {accounts.map((account) => (
                        <option key={account.id} value={account.id}>
                          {account.name} · CNY
                        </option>
                      ))}
                    </select>
                  </label>
                </>
              )}
              {(action === "cancel" ||
                action === "refund" ||
                action === "return" ||
                action === "withdraw_receipt") && (
                <p className="rounded border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
                  {action === "withdraw_receipt"
                    ? "仅撤回最新一笔有效收款，且该笔收款之后没有其他正式流水、出库或已确认对账时可撤回；原收款及冲正记录会永久保留。"
                    : "这是会改变订单、库存或资金事实的操作，请确认后执行。"}
                </p>
              )}
              {error && <p className="text-xs text-red-700">{error}</p>}
            </div>
            <div className="flex justify-end gap-2 border-t border-border px-5 py-4">
              <button
                type="button"
                onClick={() => setAction("")}
                className="rounded border border-border px-4 py-2 text-sm"
              >
                取消
              </button>
              <button
                type="button"
                onClick={run}
                disabled={
                  busy ||
                  (needsBusinessDate && !date) ||
                  !receiveMatchesDue ||
                  (actionNeedsFundAccount(action) && !accounts.length) ||
                  (action === "transport_cost" &&
                    !validatePositiveMoneyInput(amount))
                }
                className="rounded bg-accent px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
              >
                {busy ? "处理中…" : "确认执行"}
              </button>
            </div>
          </div>
        </PaymentDialog>
      )}
      {confirmReceipt && <ReceiptConfirmation order={order} amount={amount} date={date} accountName={accounts.find(account => account.id === selectedAccountId)?.name || `账户 #${selectedAccountId}`} busy={busy} onBack={() => setConfirmReceipt(false)} onConfirm={executeAction} error={error} />}

    </div>
  );
}

function ConfirmSummary({ order }: { order: SalesOrder }) {
  return (
    <div className="space-y-3 rounded border border-blue-200 bg-blue-50/50 p-3 text-xs">
      <p className="font-semibold text-blue-900">
        确认后会预留现货库存，订单进入待履约状态。
      </p>
      <div className="grid gap-2 sm:grid-cols-2">
        <div>
          <span className="text-muted">客户</span>
          <strong className="ml-2">{order.customer_name || "散客"}</strong>
        </div>
        <div>
          <span className="text-muted">应收</span>
          <strong className="ml-2 font-mono">
            {formatCny(order.amount_due_cny)}
          </strong>
        </div>
      </div>
      <ul className="space-y-1 border-t border-blue-200 pt-2 text-muted">
        {order.items.map((item) => (
          <li key={item.id} className="flex justify-between gap-3">
            <span>{item.cigar_name}</span>
            <span className="font-mono">
              {item.sale_unit === "box"
                ? `${item.sale_quantity ?? 0} 盒`
                : `${item.quantity} 支`}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Info({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-muted">{label}</dt>
      <dd className="mt-1 font-semibold">{value}</dd>
    </div>
  );
}
function Money({
  label,
  value,
  strong = false,
  tone,
}: {
  label: string;
  value: number | null;
  strong?: boolean;
  tone?: "green" | "red";
}) {
  return (
    <div
      className={`flex items-center justify-between ${strong ? "font-semibold" : ""}`}
    >
      <span className="text-muted">{label}</span>
      <span
        className={`font-mono ${tone === "green" ? "text-success" : tone === "red" ? "text-red-700" : ""}`}
      >
        {value === null ? "—" : formatCny(value)}
      </span>
    </div>
  );
}

function ReceiptConfirmation({ order, amount, date, accountName, busy, onBack, onConfirm, error }: {
  order: SalesOrder; amount: string; date: string; accountName: string; busy: boolean;
  onBack: () => void; onConfirm: () => void; error: string;
}) {
  return <PaymentDialog title="确认收款信息" role="alertdialog" width="md" onClose={onBack} busy={busy}>
    <div className="w-full bg-white">
      <div className="border-b border-border px-5 py-4"><h3 className="font-display text-lg font-semibold">请再次确认收款</h3><p className="mt-1 text-xs text-muted">确认后会立即生成正式资金流水。</p></div>
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-3 p-5 text-sm">
        <dt className="text-muted">订单</dt><dd className="font-mono font-semibold">{order.order_number}</dd>
        <dt className="text-muted">订单应收</dt><dd>{formatCny(order.amount_due_cny)}</dd>
        <dt className="text-muted">此前已收</dt><dd>{formatCny(order.received_amount_cny ?? 0)}</dd>
        <dt className="text-muted">本次实收</dt><dd className="font-mono font-semibold">{formatCny(amount)}</dd>
        <dt className="text-muted">本次收款后待收</dt><dd>{formatCny((order.remaining_amount_cny ?? order.amount_due_cny) - Number(amount))}</dd>
        <dt className="text-muted">业务日期</dt><dd className="font-semibold">{date}</dd>
        <dt className="text-muted">到账账户</dt><dd className="font-semibold">{accountName}</dd>
      </dl>
      {error && <p role="alert" className="px-5 pb-3 text-sm text-red-700">{error}</p>}
      <div className="flex justify-end gap-2 border-t border-border px-5 py-4"><button type="button" onClick={onBack} disabled={busy} className="rounded border border-border px-4 py-2 text-sm">返回修改</button><button type="button" onClick={onConfirm} disabled={busy} className="rounded bg-accent px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">{busy ? '处理中…' : '确认收款'}</button></div>
    </div>
  </PaymentDialog>;
}
