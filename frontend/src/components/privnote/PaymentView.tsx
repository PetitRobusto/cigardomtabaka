import { useId, useRef, useState, type ReactNode } from 'react';
import { Check, Copy, ImagePlus, X } from 'lucide-react';
import { submitPaymentEvidence } from '../../api';
import type { PaymentData } from '../../types';
import { formatCny } from '../sales/salesState';
import { useFilePreview } from '../../hooks/useFilePreview';

function EvidenceThumbnail({ file }: { file: File }) {
  const url = useFilePreview(file);
  return <img src={url} alt={file.name} className="aspect-[4/3] w-full rounded object-contain bg-cream" />;
}

function CopyValue({ label, value }: { label: string; value: string }) {
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState('');
  const copy = async () => {
    try {
      if (navigator.clipboard && window.isSecureContext) await navigator.clipboard.writeText(value);
      else {
        const field = document.createElement('textarea');
        field.value = value;
        field.style.cssText = 'position:fixed;opacity:0';
        document.body.appendChild(field);
        try { field.select(); if (!document.execCommand('copy')) throw new Error(); }
        finally { field.remove(); }
      }
      setCopied(true); setError('');
    } catch { setError('请长按或选中号码复制'); }
  };
  return <div className="border-b border-border py-3 last:border-0">
    <div className="flex items-center justify-between gap-3 text-sm"><span className="shrink-0 text-muted">{label}</span><span className="select-text break-all text-right font-mono font-semibold">{value}</span><button type="button" aria-label={`复制${label}`} onClick={copy} className="shrink-0 rounded border border-border p-2 hover:border-gold">{copied ? <Check size={14} /> : <Copy size={14} />}</button></div>
    {error && <p role="status" className="mt-1 text-xs text-muted">{error}</p>}
  </div>;
}

function Step({ number, title, children }: { number: string; title: string; children: ReactNode }) {
  return <section className="overflow-hidden rounded-lg border border-border bg-white">
    <header className="flex items-center gap-3 border-b border-border px-4 py-3"><span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-accent-light font-mono text-xs font-bold text-accent">{number}</span><h2 className="font-display text-base font-semibold">{title}</h2></header>
    <div className="p-4">{children}</div>
  </section>;
}

/** Both the customer route and the staff preview render this same component. */
export default function PaymentView({ data, token = '', onZoom, onSubmitted, preview = false }: {
  data: PaymentData; token?: string; onZoom: (url: string) => void;
  onSubmitted?: () => void; preview?: boolean;
}) {
  const stepId = useId();
  const [files, setFiles] = useState<File[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState('');
  const [submittedData, setSubmittedData] = useState<PaymentData | null>(null);
  const inFlight = useRef(false);
  const submissionKey = useRef('');
  const flow = submittedData === data ? 'pending' : data.payment_flow?.status || 'active';
  const supportsEvidence = preview || Boolean(data.payment_flow);
  const canSubmit = flow === 'active' || flow === 'needs_more';
  const status = { active: '待付款', pending: '等待核实', needs_more: '需补充', accepted: '已收款', closed: '已关闭' }[flow];
  const chooseFiles = (incoming: File[]) => {
    if (inFlight.current) return;
    if (files.length + incoming.length > 5) { setSubmitError('最多上传 5 张付款凭证，请先移除多余图片'); return; }
    if (incoming.some(file => !['image/jpeg', 'image/png', 'image/webp'].includes(file.type))) { setSubmitError('仅支持 JPG、PNG、WebP 图片'); return; }
    if (incoming.some(file => file.size > 5 * 1024 * 1024)) { setSubmitError('每张图片不能超过 5MB'); return; }
    setFiles(current => [...current, ...incoming]); submissionKey.current = ''; setSubmitError('');
  };
  const submit = async () => {
    if (preview || !supportsEvidence || inFlight.current || !canSubmit) return;
    if (!files.length) { setSubmitError('请先选择至少一张付款凭证'); return; }
    inFlight.current = true; setSubmitting(true); setSubmitError('');
    try {
      // getRandomValues also works on the LAN HTTP test server; randomUUID does not.
      if (!submissionKey.current) {
        const random = crypto.getRandomValues(new Uint32Array(4));
        submissionKey.current = `payment-evidence-${Array.from(random, value => value.toString(16).padStart(8, '0')).join('')}`;
      }
      await submitPaymentEvidence(token, files, submissionKey.current);
      setFiles([]); submissionKey.current = ''; setSubmittedData(data); onSubmitted?.();
    } catch (error) { setSubmitError(error instanceof Error ? error.message : '付款凭证提交失败'); }
    finally { inFlight.current = false; setSubmitting(false); }
  };

  return <div className="mx-auto max-w-2xl space-y-4 text-fg">
    <section className="rounded-lg border border-border bg-white p-5">
      <div className="flex items-center justify-between gap-3"><h1 className="font-display text-lg font-semibold">订单付款</h1><span className={`rounded-full px-3 py-1 text-xs font-semibold ${flow === 'accepted' ? 'bg-green-50 text-green-800' : flow === 'pending' || flow === 'needs_more' ? 'bg-orange-50 text-orange-800' : 'bg-accent-light text-muted'}`}>{status}</span></div>
      {data.customer_name && <p className="mt-2 text-sm text-muted">{data.customer_name}</p>}
      <div className="mt-5 flex items-baseline justify-between gap-3"><span className="text-sm text-muted">{flow === 'accepted' ? '已收金额' : '应付总额'}</span><strong className="font-mono text-3xl font-semibold text-accent">{formatCny(data.grand_total)}</strong></div>
      <details className="mt-4 border-t border-border pt-3"><summary className="cursor-pointer text-xs font-semibold text-muted">查看订单明细 · {data.items.length} 项商品</summary><div className="mt-2 divide-y divide-border">
        {data.items.map((item, index) => <div key={index} className="flex justify-between gap-3 py-3 text-sm"><div className="min-w-0"><strong>{item.name}</strong><p className="mt-1 text-xs text-muted">{item.sale_unit === 'box' ? `${item.sale_quantity ?? item.quantity} 盒 · ${item.box_size ?? '—'} 支/盒` : `${item.sale_quantity ?? item.quantity} 支`}</p></div><span className="shrink-0 font-mono">{formatCny(item.subtotal)}</span></div>)}
        {data.extra_fees?.map((fee, index) => <div key={index} className="flex justify-between gap-3 py-2 text-xs text-muted"><span>{fee.name}</span><span className="font-mono">{formatCny(fee.amount)}</span></div>)}
      </div></details>
    </section>

    {flow === 'pending' && <div role="status" className="rounded-lg border border-orange-200 bg-orange-50 p-5 text-sm text-orange-900"><strong className="block text-base">付款凭证已提交，等待核实</strong><p className="mt-2 leading-relaxed">请勿重复转账。商家核实到账后，可刷新查看收款状态。</p>{!preview && onSubmitted && <button type="button" onClick={onSubmitted} className="mt-3 rounded border border-orange-300 px-3 py-2 text-xs font-semibold">刷新收款状态</button>}</div>}
    {flow === 'accepted' && <div role="status" className="rounded-lg border border-green-200 bg-green-50 p-5 text-sm text-green-900"><strong className="block text-base">付款已确认，感谢</strong><p className="mt-2">商家已核实到账，订单将按原定方式履约。</p></div>}
    {flow === 'closed' && <div role="status" className="rounded-lg border border-border bg-white p-5 text-sm"><strong>收款已关闭</strong><p className="mt-2 text-muted">请联系商家确认订单状态，请勿继续转账。</p></div>}
    {flow === 'needs_more' && <div role="status" className="rounded-lg border border-orange-200 bg-orange-50 p-5 text-sm text-orange-900"><strong>需要补充付款凭证</strong><p className="mt-2 whitespace-pre-wrap">{data.payment_flow?.review_note || '请补充清晰的付款凭证。'}</p><p className="mt-2">已付款请勿再次转账，直接补充并上传截图。</p></div>}

    {canSubmit && <>
      <nav aria-label="付款步骤" className="grid grid-cols-3 gap-2 rounded-lg border border-border bg-white p-3 text-center text-xs">
        {[['01', '付款'], ['02', '截图'], ['03', '上传']].map(([number, title]) => <a key={number} href={`#${stepId}-payment-step-${number}`} className="rounded bg-cream px-2 py-3 hover:bg-accent-light"><span className="mr-1 font-mono font-semibold text-accent">{number}</span>{title}</a>)}
      </nav>
      <div id={`${stepId}-payment-step-01`} className="scroll-mt-4"><Step number="01" title="完成付款">
        <p className="mb-4 text-sm text-muted">核对收款信息，按应付总额足额转账。</p>
        {data.payment_methods.length === 0 && <p className="rounded border border-dashed border-border p-4 text-center text-sm text-muted">填写收款信息后显示在这里</p>}
        {data.payment_methods.map((method, index) => <div key={index}>
          <p className="text-sm font-semibold">{method.method_type === 'bank_card' ? '银行卡转账' : method.method_type === 'wechat' ? '微信扫码付款' : '支付宝扫码付款'}</p>
          {method.method_type === 'bank_card' ? <div className="mt-2"><CopyValue label="银行" value={method.bank_name || '—'} /><CopyValue label="户名" value={method.card_holder || '—'} /><CopyValue label="卡号" value={method.card_number || '—'} /></div> : <div className="mt-4 text-center">
            {method.qr_url ? <button type="button" onClick={() => onZoom(method.qr_url!)} aria-label="放大收款二维码" className="mx-auto block rounded-lg border border-border bg-white p-3 hover:border-gold"><img src={method.qr_url} alt="收款二维码" className="h-48 w-48 object-contain" /></button> : <div className="mx-auto grid h-40 w-40 place-items-center rounded border border-dashed border-border text-xs text-muted">{preview ? '上传二维码后显示' : '请核对下方收款账号'}</div>}
            {method.qr_url && <p className="mt-3 text-xs text-muted">点击二维码放大 · 保存后在微信 / 支付宝中识别</p>}
            {method.account && <CopyValue label="收款账号" value={method.account} />}
          </div>}
          {method.remark && <p className="mt-4 whitespace-pre-wrap rounded bg-cream p-3 text-sm leading-relaxed">{method.remark}</p>}
        </div>)}
        {data.remark && <div className="mt-4 rounded border border-gold/30 bg-[#FFFDFA] p-3"><p className="text-xs font-semibold text-muted">补充备注</p><p className="mt-1 whitespace-pre-wrap text-sm leading-relaxed">{data.remark}</p></div>}
        {!!data.images?.length && <div className="mt-3 grid grid-cols-3 gap-2">{data.images.map((image, index) => <button type="button" key={index} onClick={() => onZoom(image.url)}><img src={image.url} alt={image.name} className="aspect-square w-full rounded border border-border object-cover" /></button>)}</div>}
      </Step></div>
      <div id={`${stepId}-payment-step-02`} className="scroll-mt-4"><Step number="02" title="保存付款截图"><p className="text-sm leading-relaxed">付款成功后，请保存转账截图或银行回单，再回到本页上传。</p><p className="mt-2 text-xs leading-relaxed text-muted">截图请包含付款成功状态、金额、收款方和付款时间，方便我们核实。</p></Step></div>
      <div id={`${stepId}-payment-step-03`} className="scroll-mt-4"><Step number="03" title="上传付款凭证">
        {!supportsEvidence ? <p className="text-sm leading-relaxed text-muted">此历史收款链接不支持上传凭证，请联系商家提交付款截图。</p> : <>
        <label className={`block rounded-lg border border-dashed border-gold/60 bg-[#FFFDFA] p-5 text-center text-sm ${preview || submitting ? 'opacity-60' : 'cursor-pointer hover:border-accent'}`}><ImagePlus className="mx-auto mb-2 h-6 w-6 text-gold" /><span className="font-semibold">{flow === 'needs_more' ? '补充转账截图或回单' : '选择转账截图或回单'}</span><span className="mt-2 block text-xs text-muted">JPG / PNG / WebP · 最多 5 张 · 每张不超过 5MB</span><input aria-label="付款凭证图片" type="file" accept="image/jpeg,image/png,image/webp" multiple disabled={preview || submitting} className="mt-3 block w-full text-xs" onChange={event => { chooseFiles(Array.from(event.target.files || [])); event.target.value = ''; }} /></label>
        {files.length > 0 && <div className="mt-3 grid grid-cols-2 gap-3">{files.map((file, index) => <div key={`${file.name}-${index}`} className="min-w-0 rounded border border-border p-2"><EvidenceThumbnail file={file} /><div className="mt-2 flex items-center gap-1"><span className="min-w-0 flex-1 truncate text-xs text-muted">{file.name}</span><button type="button" disabled={submitting} aria-label={`移除 ${file.name}`} onClick={() => { setFiles(current => current.filter((_, i) => i !== index)); submissionKey.current = ''; setSubmitError(''); }} className="rounded p-1 text-muted"><X size={14} /></button></div></div>)}</div>}
        {submitError && <p role="alert" className="mt-3 text-sm text-red-700">{submitError}</p>}
        <button type="button" onClick={submit} disabled={preview || submitting || !files.length} className="mt-4 w-full rounded bg-accent px-4 py-3 text-sm font-semibold text-white disabled:opacity-50">{preview ? '预览中不可提交' : submitting ? '提交中…' : flow === 'needs_more' ? '重新提交凭证' : '提交凭证，等待核实'}</button>
        <p className="mt-3 text-center text-xs leading-relaxed text-muted">上传后请等待商家核实，无需再次付款。</p>
        </>}
      </Step></div>
    </>}
    <p className="py-3 text-center text-xs leading-relaxed text-muted">付款凭证提交不代表已到账；收款信息仅在链接有效期内展示。</p>
  </div>;
}
