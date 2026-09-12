import { useState } from "react";
import { X } from "lucide-react";
import type { FundAccount, PaymentMethod, PaymentData, SalesOrder } from "../../types";
import { formatCny } from "./salesState";
import PaymentDialog from "../privnote/PaymentDialog";
import PaymentView from "../privnote/PaymentView";
import { useFilePreview } from "../../hooks/useFilePreview";
import StoreHeader from "../privnote/StoreHeader";

export default function PaymentRequestModal({
  order, source, setSource, methods, methodId, setMethodId, accounts,
  temporaryType, setTemporaryType, temporaryAccountId, setTemporaryAccountId,
  temporaryBankName, setTemporaryBankName,
  temporaryCardNumber, setTemporaryCardNumber, temporaryCardHolder, setTemporaryCardHolder,
  temporaryQr, setTemporaryQr, duration, setDuration, password, setPassword,
  remark, setRemark, busy, error, url, copied, onCopy, onClose, onSubmit,
}: {
  order: SalesOrder;
  source: "temporary" | "saved";
  setSource: (value: "temporary" | "saved") => void;
  methods: PaymentMethod[]; methodId: string; setMethodId: (value: string) => void;
  accounts: FundAccount[]; temporaryType: "wechat" | "alipay" | "bank_card";
  setTemporaryType: (value: "wechat" | "alipay" | "bank_card") => void;
  temporaryAccountId: string; setTemporaryAccountId: (value: string) => void;
  temporaryBankName: string; setTemporaryBankName: (value: string) => void;
  temporaryCardNumber: string; setTemporaryCardNumber: (value: string) => void;
  temporaryCardHolder: string; setTemporaryCardHolder: (value: string) => void;
  temporaryQr: File | null; setTemporaryQr: (value: File | null) => void;
  duration: string; setDuration: (value: string) => void; password: string; setPassword: (value: string) => void;
  remark: string; setRemark: (value: string) => void; busy: boolean; error: string; url: string; copied: boolean;
  onCopy: () => void; onClose: () => void; onSubmit: () => void;
}) {
  const selectedMethod = methods.find(method => String(method.id) === methodId);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [zoomedQr, setZoomedQr] = useState<string | null>(null);
  const qrUrl = useFilePreview(temporaryQr);
  const method: PaymentMethod | undefined = source === "saved" ? selectedMethod : {
    id: 0, method_type: temporaryType, bank_name: temporaryBankName,
    card_number: temporaryCardNumber, card_holder: temporaryCardHolder, qr_url: qrUrl,
  };
  const data: PaymentData = {
    mode: "payment", customer_name: order.customer_name, total: Number(order.goods_amount_cny),
    grand_total: Number(order.amount_due_cny), extra_total: Number(order.customer_transport_fee_cny),
    extra_fees: Number(order.customer_transport_fee_cny) ? [{ name: "人肉费", amount: Number(order.customer_transport_fee_cny) }] : [],
    items: order.items.map(item => ({ name: item.cigar_name, english_name: "", vitola: "", thumb_url: "",
      quantity: item.quantity, sale_quantity: item.sale_quantity, sale_unit: item.sale_unit, box_size: item.box_size,
      unit_price: Number(item.unit_price), subtotal: Number(item.revenue) })),
    payment_methods: method ? [method] : [], remark,
  };
  const customerPage = <><StoreHeader compact /><PaymentView data={data} preview onZoom={setZoomedQr} /></>;
  return <PaymentDialog title="创建收款单" busy={busy} onClose={onClose}>
    <div className="max-h-[100dvh] w-full overflow-y-auto rounded-t-lg bg-white shadow-2xl sm:max-h-[calc(100dvh-2.5rem)] sm:max-w-5xl sm:rounded-lg">
      <header className="sticky top-0 z-10 flex items-start justify-between border-b border-border bg-[#FFFDFA] px-5 py-4">
        <div><h3 className="font-display text-xl font-semibold">创建收款单</h3><p className="mt-1 text-xs text-muted">{order.order_number} · {order.customer_name || "散客"} · 应收 <strong className="font-mono text-fg">{formatCny(order.amount_due_cny)}</strong></p></div>
        <button type="button" aria-label="关闭创建收款单" onClick={onClose} disabled={busy} className="rounded border border-border p-1.5 text-muted hover:border-gold"><X className="h-4 w-4" /></button>
      </header>
      {url ? <div className="m-5 rounded border border-green-200 bg-green-50 p-5"><strong className="text-green-900">收款链接已创建</strong><p className="mt-1 text-xs text-green-800">二维码与链接同一有效期；客户无需登录即可上传付款凭证。</p><div className="mt-3 break-all rounded border border-green-200 bg-white p-3 font-mono text-xs">{url}</div><div className="mt-3 flex gap-2"><button type="button" onClick={onCopy} className="rounded border border-green-300 px-3 py-2 text-xs font-semibold text-green-800">{copied ? "已复制" : "复制链接"}</button><button type="button" onClick={() => setPreviewOpen(true)} className="rounded border border-green-300 px-3 py-2 text-xs font-semibold text-green-800">预览客户页</button></div></div> : <div className="grid gap-6 p-5 lg:grid-cols-[minmax(0,1fr)_340px]">
        <section className="space-y-4"><fieldset disabled={busy} className="space-y-4">
          <div className="grid grid-cols-2 rounded-md border border-border bg-cream p-1"><button type="button" onClick={() => setSource("temporary")} className={`rounded px-3 py-2 text-sm font-semibold ${source === "temporary" ? "bg-white text-accent shadow-sm" : "text-muted"}`}>本次临时</button><button type="button" onClick={() => setSource("saved")} className={`rounded px-3 py-2 text-sm font-semibold ${source === "saved" ? "bg-white text-accent shadow-sm" : "text-muted"}`}>常用方式</button></div>
          {source === "temporary" ? <>
            <div className="rounded border border-gold/40 bg-gold/5 p-3 text-xs leading-relaxed text-muted"><strong className="text-fg">临时收款信息仅保留在本张收款单快照中。</strong>不会创建或改动常用收款方式。</div>
            <label className="block text-xs font-semibold text-muted">收款类型<select value={temporaryType} onChange={event => setTemporaryType(event.target.value as "wechat" | "alipay" | "bank_card")} className="mt-1.5 w-full rounded border border-border bg-white px-3 py-2 text-sm text-fg"><option value="wechat">微信</option><option value="alipay">支付宝</option><option value="bank_card">银行卡</option></select></label>
            <label className="block text-xs font-semibold text-muted">入账 CNY 账户（仅内部）<select value={temporaryAccountId} onChange={event => setTemporaryAccountId(event.target.value)} className="mt-1.5 w-full rounded border border-border bg-white px-3 py-2 text-sm text-fg"><option value="">请选择入账账户</option>{accounts.map(account => <option key={account.id} value={account.id}>{account.name} · CNY</option>)}</select></label>
            {temporaryType === "bank_card" ? <div className="grid gap-3 sm:grid-cols-2"><label className="text-xs font-semibold text-muted">银行名<input value={temporaryBankName} onChange={event => setTemporaryBankName(event.target.value)} className="mt-1.5 w-full rounded border border-border px-3 py-2 text-sm text-fg" /></label><label className="text-xs font-semibold text-muted">户名<input value={temporaryCardHolder} onChange={event => setTemporaryCardHolder(event.target.value)} className="mt-1.5 w-full rounded border border-border px-3 py-2 text-sm text-fg" /></label><label className="text-xs font-semibold text-muted sm:col-span-2">卡号<input value={temporaryCardNumber} onChange={event => setTemporaryCardNumber(event.target.value)} className="mt-1.5 w-full rounded border border-border px-3 py-2 text-sm text-fg" /></label></div> : null}
            {temporaryType !== "bank_card" && <label className="block rounded border border-dashed border-border bg-[#FFFDFA] p-3 text-xs text-muted hover:border-gold">上传收款二维码（PNG / JPG / WebP，≤ 5MB）<input type="file" accept="image/png,image/jpeg,image/webp" onChange={event => setTemporaryQr(event.target.files?.[0] || null)} className="mt-2 block w-full text-xs" />{temporaryQr && <span className="mt-2 block font-medium text-fg">已选择：{temporaryQr.name}</span>}</label>}
          </> : <div className="space-y-2">{methods.length === 0 && <p className="rounded border border-border bg-[#FFFDFA] p-3 text-xs text-muted">暂无启用中的常用收款方式。请使用临时方式，或先到收款方式管理中新增。</p>}{methods.map(method => <button key={method.id} type="button" onClick={() => setMethodId(String(method.id))} className={`block w-full rounded border p-3 text-left ${methodId === String(method.id) ? "border-accent bg-accent-light/40" : "border-border hover:border-gold"}`}><span className="font-semibold">{method.label || "未命名收款方式"}</span><span className="mt-1 block font-mono text-xs text-muted">{method.method_type === "bank_card" ? `${method.bank_name || "银行卡"} · ${method.card_number || ""}` : method.account || "二维码收款"}</span></button>)}</div>}
          <details className="rounded border border-border p-3"><summary className="cursor-pointer text-xs font-semibold text-fg">更多设置</summary><div className="mt-3 grid gap-3 sm:grid-cols-2"><label className="text-xs font-semibold text-muted">有效期<select value={duration} onChange={event => setDuration(event.target.value)} className="mt-1.5 w-full rounded border border-border bg-white px-3 py-2 text-sm text-fg">{[["1","1 小时"],["6","6 小时"],["24","24 小时"],["72","3 天"],["168","7 天"],["720","30 天"]].map(([value,label]) => <option key={value} value={value}>{label}</option>)}</select></label><label className="text-xs font-semibold text-muted">查看密码（可选）<input type="password" value={password} onChange={event => setPassword(event.target.value)} className="mt-1.5 w-full rounded border border-border px-3 py-2 text-sm text-fg" placeholder="客户查看时输入" /></label></div></details>
          <label className="block text-xs font-semibold text-muted">补充备注（客户可见，可选）<textarea value={remark} onChange={event => setRemark(event.target.value)} rows={3} className="mt-1.5 w-full rounded border border-border px-3 py-2 text-sm text-fg" placeholder="例如：转账请备注订单号；完成后上传截图。" /></label>
          {error && <p role="alert" className="rounded border border-red-200 bg-red-50 p-3 text-xs text-red-700">{error}</p>}
        </fieldset></section>
        <aside className="min-w-0 rounded-lg border border-border bg-cream p-3">
          <div className="mb-3 flex items-center justify-between gap-2"><span className="text-xs font-semibold text-muted">客户视角 · 实时预览</span><button type="button" onClick={() => setPreviewOpen(true)} className="rounded border border-border bg-white px-2 py-1.5 text-xs">预览客户页</button></div>
          <div className="max-h-[540px] overflow-y-auto rounded-lg border border-border bg-cream p-3">{customerPage}</div>
        </aside>
      </div>}
      {!url && <footer className="sticky bottom-0 flex justify-end gap-2 border-t border-border bg-[#FFFDFA] px-5 py-4"><button type="button" onClick={onClose} disabled={busy} className="rounded border border-border px-4 py-2 text-sm">取消</button><button type="button" onClick={onSubmit} disabled={busy} className="rounded bg-accent px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">{busy ? "创建中…" : "创建并生成链接"}</button></footer>}
    </div>
    {previewOpen && <PaymentDialog title="客户页面预览" narrow onClose={() => setPreviewOpen(false)}>
      <header className="sticky top-0 z-10 flex items-center justify-between border-b border-border bg-white p-4"><div><h2 className="font-semibold">客户页面预览</h2><p className="mt-1 text-xs text-muted">仅预览 · 不创建链接或提交凭证</p></div><button type="button" aria-label="关闭客户预览" onClick={() => setPreviewOpen(false)} className="rounded border border-border p-2"><X size={16} /></button></header>
      <div className="mx-auto max-w-[460px] bg-cream p-4">{customerPage}</div>
    </PaymentDialog>}
    {zoomedQr && <PaymentDialog title="收款二维码" narrow onClose={() => setZoomedQr(null)}><div className="p-4"><button type="button" aria-label="关闭二维码" onClick={() => setZoomedQr(null)} className="mb-3 ml-auto block rounded border border-border p-2"><X size={16} /></button><img src={zoomedQr} alt="收款二维码" className="mx-auto max-h-[70dvh] max-w-full object-contain" /></div></PaymentDialog>}
  </PaymentDialog>;
}
