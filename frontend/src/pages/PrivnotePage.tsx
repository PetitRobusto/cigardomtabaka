import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Copy, Check,
  Search, Plus,
  X, Upload, ImageIcon, ClipboardList, Wallet, Send, Package
} from 'lucide-react';
import {
  fetchPaymentMethods, createPrivnote, fetchQuoteProducts, fetchEligiblePaymentOrders,
  uploadPrivnoteImage
} from '../api';
import { useAuthStore } from '../store/authStore';
import { usePageMeta } from '../hooks/usePageMeta';
import type { PaymentMethod, QuoteProduct, PaymentOrder } from '../types';
import { canSubmitPayment, eligiblePaymentOrders, paymentOrderSummary } from './privnotePayment';
import { selectedIdsOnCustomEntry, type QuoteMode } from './privnoteQuote';

const DURATIONS = [
  { value: '1', label: '1 小时' },
  { value: '6', label: '6 小时' },
  { value: '24', label: '24 小时' },
  { value: '72', label: '3 天' },
  { value: '168', label: '7 天' },
  { value: '720', label: '30 天' },
];

const TABS = [
  { key: 'inventory' as const, label: '库存展示', icon: Package },
  { key: 'quote' as const, label: '报价单', icon: ClipboardList },
  { key: 'payment' as const, label: '收款单', icon: Wallet },
  { key: 'message' as const, label: '消息', icon: Send },
];

type TabKey = typeof TABS[number]['key'];
/* ─── Image Upload Hook ─── */
function useImageUpload() {
  const [images, setImages] = useState<{ url: string; name: string }[]>([]);
  const [uploading, setUploading] = useState(false);

  const onFileSelect = useCallback(async (files: FileList | null) => {
    if (!files) return;
    setUploading(true);
    const newImages: { url: string; name: string }[] = [];
    for (const file of Array.from(files)) {
      try {
        const res = await uploadPrivnoteImage(file);
        if (res.url) newImages.push({ url: res.url, name: res.name || file.name });
      } catch {
        // ignore upload errors
      }
    }
    setImages(prev => [...prev, ...newImages]);
    setUploading(false);
  }, []);

  const onRemove = useCallback((idx: number) => {
    setImages(prev => prev.filter((_, i) => i !== idx));
  }, []);

  return { images, setImages, uploading, onFileSelect, onRemove };
}

/* ─── File Upload Component ─── */
function FileUploadArea({
  images, uploading, onFileSelect, onRemove
}: {
  images: { url: string; name: string }[];
  uploading: boolean;
  onFileSelect: (files: FileList | null) => void;
  onRemove: (idx: number) => void;
}) {
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleClick = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  const handleChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    onFileSelect(e.target.files);
    if (fileInputRef.current) fileInputRef.current.value = '';
  }, [onFileSelect]);

  return (
    <div>
      <div
        onClick={handleClick}
        onDragOver={e => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={e => { e.preventDefault(); setDragOver(false); onFileSelect(e.dataTransfer.files); }}
        className={`border-2 border-dashed rounded-sm p-8 text-center cursor-pointer transition-colors ${
          dragOver ? 'border-accent bg-accent-light/50' : 'border-border hover:border-accent'
        }`}
      >
        <div className="text-sm text-muted mb-2 flex items-center justify-center gap-2">
          <Upload className="w-4 h-4" />
          {uploading ? '上传中…' : '点击或拖拽上传图片'}
        </div>
        <div className="text-xs text-border">支持 jpg / png / gif / webp</div>
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          multiple
          className="hidden"
          onChange={handleChange}
        />
      </div>
      {images.length > 0 && (
        <div className="flex gap-2 flex-wrap mt-3">
          {images.map((img, idx) => (
            <div key={idx} className="relative group inline-flex items-center gap-1.5 px-3 py-1.5 bg-accent-light rounded-full text-xs">
              <ImageIcon className="w-3 h-3 text-muted" />
              <span className="max-w-[120px] truncate">{img.name}</span>
              <button
                type="button"
                onClick={() => onRemove(idx)}
                className="w-4 h-4 rounded-full bg-border/50 hover:bg-accent hover:text-white flex items-center justify-center transition-colors"
              >
                <X className="w-3 h-3" />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function PrivnotePage() {
  const { user } = useAuthStore();
  const { setMeta } = usePageMeta();
  const [activeTab, setActiveTab] = useState<TabKey>('quote');

  useEffect(() => {
    setMeta({
      title: '创建链接',
      breadcrumbs: [
        { label: '首页', to: '/' },
        { label: '创建链接' },
      ],
    });
  }, [setMeta]);

  // Common config
  const [duration, setDuration] = useState('24');
  const [password, setPassword] = useState('');
  const [burn, setBurn] = useState(true);
  const [maxViews, setMaxViews] = useState('0');

  // Result
  const [result, setResult] = useState<{ url: string; token: string } | null>(null);
  const [copied, setCopied] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  // Payment tab state
  const [selectedPaymentOrderId, setSelectedPaymentOrderId] = useState('');
  const [paymentMethodId, setPaymentMethodId] = useState('');
  const [remark, setRemark] = useState('');
  const paymentImages = useImageUpload();

  const { data: paymentMethods } = useQuery({
    queryKey: ['payment-methods'],
    queryFn: fetchPaymentMethods,
    enabled: activeTab === 'payment',
  });
  const { data: salesOrders = [], isLoading: ordersLoading } = useQuery({
    queryKey: ['privnote-payment-orders'],
    queryFn: fetchEligiblePaymentOrders,
    enabled: activeTab === 'payment',
  });
  const eligibleOrders = eligiblePaymentOrders(salesOrders);
  const selectedPaymentOrder: PaymentOrder | null = eligibleOrders.find(order => String(order.id) === selectedPaymentOrderId) || null;

  // Message tab state
  const [messageText, setMessageText] = useState('');
  const [attachments, setAttachments] = useState<{ name: string; url: string }[]>([]);
  const [attachName, setAttachName] = useState('');
  const [attachUrl, setAttachUrl] = useState('');
  const [showAttachments, setShowAttachments] = useState(false);
  const messageImages = useImageUpload();

  // Quote mode
  const [quoteMode, setQuoteMode] = useState<QuoteMode>('full');
  const [shippingIncluded, setShippingIncluded] = useState(false);
  const [quoteSearchQ, setQuoteSearchQ] = useState('');
  const [selectedIds, setSelectedIds] = useState<number[] | null>([]);
  const [customPrices, setCustomPrices] = useState<Record<string, number>>({});
  const [quoteCustomerName, setQuoteCustomerName] = useState('');

  const { data: quoteProducts } = useQuery({
    queryKey: ['quote-products'],
    queryFn: fetchQuoteProducts,
    enabled: activeTab === 'quote',
  });

  // 定制模式默认选择全部可预售商品。
  const defaultSelectedIds = useMemo(() => quoteProducts ? [...new Set(quoteProducts.filter(p => p.can_preorder).map(p => p.cigar_id))] : [], [quoteProducts]);
  const visibleSelectedIds = selectedIds ?? defaultSelectedIds;


  if (!user?.is_staff) {
    return (
      <div className="text-center py-20">
        <p className="text-muted">您没有权限访问此页面</p>
      </div>
    );
  }

  const copyUrl = async () => {
    if (!result?.url) return;
    let success: boolean;
    try {
      await navigator.clipboard.writeText(result.url);
      success = true;
    } catch {
      const textarea = document.createElement('textarea');
      textarea.value = result.url;
      textarea.style.position = 'fixed';
      textarea.style.opacity = '0';
      document.body.appendChild(textarea);
      textarea.select();
      success = document.execCommand('copy');
      document.body.removeChild(textarea);
    }
    if (success) {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const addAttachment = () => {
    if (!attachName.trim() || !attachUrl.trim()) return;
    setAttachments(prev => [...prev, { name: attachName.trim(), url: attachUrl.trim() }]);
    setAttachName('');
    setAttachUrl('');
  };

  const removeAttachment = (idx: number) => {
    setAttachments(prev => prev.filter((_, i) => i !== idx));
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit()) return;
    setError('');
    setLoading(true);
    const form = new FormData();

    form.append('note_type', activeTab);
    form.append('duration', duration);
    form.append('password', password);
    form.append('burn', burn ? 'on' : 'off');
    form.append('max_views', burn ? '1' : maxViews);

    if (activeTab === 'payment') {
      form.append('sales_order_id', selectedPaymentOrderId);
      form.append('payment_method_id', paymentMethodId);
      form.append('remark', remark);
      form.append('images', JSON.stringify(paymentImages.images));
    } else if (activeTab === 'message') {
      form.append('text', messageText);
      form.append('attachments', JSON.stringify(attachments));
      form.append('images', JSON.stringify(messageImages.images));
    } else if (activeTab === 'quote') {
      form.append('quote_mode', quoteMode);
      form.append('selected_ids', JSON.stringify(visibleSelectedIds));
      form.append('shipping_included', shippingIncluded ? 'true' : 'false');
      if (quoteCustomerName.trim()) {
        form.append('customer_name', quoteCustomerName.trim());
      }
      if (quoteMode === 'custom' && Object.keys(customPrices).length > 0) {
        form.append('custom_prices', JSON.stringify(customPrices));
      }
    }

    try {
      const res = await createPrivnote(form);
      setResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : '私密链接创建失败，请稍后重试');
    } finally {
      setLoading(false);
    }
  };

  const resetAll = () => {
    setResult(null);
    setError('');
    setPassword('');
    setMaxViews('0');
    setSelectedPaymentOrderId('');
    setPaymentMethodId('');
    setMessageText('');
    setAttachments([]);
    setShowAttachments(false);
    setQuoteMode('full');
    setShippingIncluded(false);
    setQuoteSearchQ('');
    setSelectedIds([]);
    setCustomPrices({});
    setQuoteCustomerName('');
    paymentImages.setImages([]);
    messageImages.setImages([]);
    setRemark('');
    setActiveTab('quote');
  };

  const canSubmit = () => {
    if (activeTab === 'inventory') return true;
    if (activeTab === 'payment') return canSubmitPayment(selectedPaymentOrder, paymentMethodId);
    if (activeTab === 'message') return !!messageText.trim() || attachments.length > 0 || messageImages.images.length > 0;
    if (activeTab === 'quote') {
      if (quoteMode === 'full') return true;
      return visibleSelectedIds.length > 0;
    }
    return false;
  };

  const actionHint = () => {
    if (activeTab === 'inventory') return '将生成当前可售库存展示链接';
    if (activeTab === 'quote') {
      if (quoteMode === 'full') return '将生成包含全部 72 款雪茄的完整报价单';
      return visibleSelectedIds.length > 0 ? `已选 ${visibleSelectedIds.length} 项商品` : '请勾选要包含在报价单中的雪茄';
    }
    if (activeTab === 'payment') return selectedPaymentOrder ? '已选择销售单，可创建收款单' : '选择待收款销售单和收款方式，创建付款链接';
    return '输入消息内容并上传附件';
  };

  return (
    <div data-guide="privnote-create" className="animate-fade-in max-w-4xl mx-auto pb-32">
      {/* Page Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-display font-semibold text-fg">创建私密链接</h1>
        <p className="text-sm text-muted mt-1">Create a private link</p>
      </div>

      {result ? (
        <div className="bg-white border border-border rounded-sm p-6 text-center">
          <div className="w-12 h-12 rounded-full bg-emerald-50 flex items-center justify-center mx-auto mb-4">
            <Check className="w-6 h-6 text-emerald-600" />
          </div>
          <h3 className="text-lg font-semibold text-fg mb-2">链接已生成</h3>
          <div className="flex items-center gap-2 bg-accent-light rounded-sm p-3 mb-4">
            <code className="text-sm text-fg flex-1 break-all">{result.url}</code>
            <button
              onClick={copyUrl}
              className="p-2 rounded-sm text-accent hover:bg-accent/10 transition-colors shrink-0"
            >
              {copied ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
            </button>
          </div>
          <button onClick={resetAll} className="text-sm text-accent hover:underline">
            创建新的链接
          </button>
        </div>
      ) : (
        <form onSubmit={handleCreate} className="space-y-5">
          {/* Note Config */}
          <div className="bg-white border border-border rounded-sm p-5 flex items-center gap-8 flex-wrap">
            <div className="w-full text-xs font-bold uppercase tracking-wider text-muted">链接设置</div>
            <div className="flex items-center gap-3">
              <span className="text-xs text-muted uppercase tracking-wider">有效期</span>
              <select
                data-guide="privnote-duration"
                value={duration}
                onChange={e => setDuration(e.target.value)}
                className="px-3 py-2 border border-border rounded-sm text-sm text-fg bg-white focus:outline-none focus:border-accent min-w-[120px]"
              >
                {DURATIONS.map(d => (
                  <option key={d.value} value={d.value}>{d.label}</option>
                ))}
              </select>
            </div>
            <div className="flex items-center gap-3">
              <span className="text-xs text-muted uppercase tracking-wider">密码</span>
              <input
                data-guide="privnote-password"
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder="可选，客户查看时输入"
                className="px-3 py-2 border border-border rounded-sm text-sm text-fg bg-white focus:outline-none focus:border-accent min-w-[160px]"
              />
            </div>
            <div className="flex items-center gap-3">
              <span className="text-xs text-muted uppercase tracking-wider">最大查看次数</span>
              <select value={maxViews} onChange={e => setMaxViews(e.target.value)} disabled={burn} className="px-3 py-2 border border-border rounded-sm text-sm text-fg bg-white disabled:bg-accent-light disabled:text-muted">
                <option value="0">不限次数</option>
                <option value="1">1 次</option>
                <option value="3">3 次</option>
                <option value="5">5 次</option>
                <option value="10">10 次</option>
              </select>
            </div>
            <div className="flex items-center gap-3 ml-auto">
              <label className="flex items-center gap-3 cursor-pointer">
                <div className="relative">
                  <input data-guide="privnote-burn" type="checkbox" className="sr-only" checked={burn} onChange={e => setBurn(e.target.checked)} />
                  <span className={`block w-10 h-[22px] rounded-full transition-colors ${burn ? 'bg-accent' : 'bg-border'}`}>
                    <span className={`absolute top-[2px] left-[2px] w-[18px] h-[18px] bg-white rounded-full shadow transition-transform ${burn ? 'translate-x-[18px]' : 'translate-x-0'}`} />
                  </span>
                </div>
                <div>
                  <div className="text-sm font-medium text-fg">阅后即焚</div>
                  <div className="text-xs text-muted">首次查看后自动销毁</div>
                </div>
              </label>
            </div>
          </div>

          {/* Tabs */}
          <div className="flex border-b border-border overflow-x-auto">
            {TABS.map(tab => {
              const Icon = tab.icon;
              return (
                <button
                  data-guide={tab.key === 'quote' ? 'privnote-type' : undefined}
                  key={tab.key}
                  type="button"
                  onClick={() => setActiveTab(tab.key)}
                  className={`px-6 py-3 text-sm font-medium whitespace-nowrap border-b-2 -mb-px transition-colors flex items-center gap-2 ${
                    activeTab === tab.key
                      ? 'text-accent border-accent'
                      : 'text-muted border-transparent hover:text-fg'
                  }`}
                >
                  <Icon className="w-4 h-4" />
                  {tab.label}
                </button>
              );
            })}
          </div>

          {/* Tab Content */}
          <div>
            {/* ── INVENTORY TAB ── */}
            {activeTab === 'inventory' && (
              <div className="bg-white border border-border rounded-sm p-6">
                <h2 className="text-base font-semibold text-fg">库存展示</h2>
                <p className="mt-2 text-sm leading-relaxed text-muted">生成当前库存快照，客户只能查看展示内容，不会创建订单、预留库存或改变库存数量。</p>
              </div>
            )}

            {/* ── QUOTE TAB ── */}
            {activeTab === 'quote' && (
              <div className="space-y-4">
                <div className="bg-white border border-border rounded-sm overflow-hidden">
                  <div className="px-5 py-4 border-b border-border flex items-center justify-between gap-3 flex-wrap">
                    <span className="text-xs text-muted uppercase tracking-wider font-medium">报价单模式</span>
                    <div className="inline-flex bg-accent-light rounded-sm p-1 gap-1">
                      <button
                        data-guide="privnote-quote-mode-full"
                        type="button"
                        onClick={() => setQuoteMode('full')}
                        className={`px-4 py-2 text-xs font-medium rounded-sm transition-all ${
                          quoteMode === 'full'
                            ? 'bg-white text-fg shadow-sm'
                            : 'text-muted hover:text-fg'
                        }`}
                      >
                        完整目录
                      </button>
                      <button
                        data-guide="privnote-quote-mode-custom"
                        type="button"
                        onClick={() => {
                          setSelectedIds(current => selectedIdsOnCustomEntry(quoteMode, current));
                          setQuoteMode('custom');
                        }}
                        className={`px-4 py-2 text-xs font-medium rounded-sm transition-all ${
                          quoteMode === 'custom'
                            ? 'bg-white text-fg shadow-sm'
                            : 'text-muted hover:text-fg'
                        }`}
                      >
                        定制选择
                      </button>
                    </div>
                  </div>
                  <div className="p-5 space-y-4">
                    {/* Shipping toggle */}
                    <div className="flex items-center gap-3 pb-4 border-b border-border">
                      <label className="flex items-center gap-3 cursor-pointer">
                        <div className="relative">
                          <input data-guide="privnote-shipping" type="checkbox" className="sr-only" checked={shippingIncluded} onChange={e => setShippingIncluded(e.target.checked)} />
                          <span className={`block w-10 h-[22px] rounded-full transition-colors ${shippingIncluded ? 'bg-accent' : 'bg-border'}`}>
                            <span className={`absolute top-[2px] left-[2px] w-[18px] h-[18px] bg-white rounded-full shadow transition-transform ${shippingIncluded ? 'translate-x-[18px]' : 'translate-x-0'}`} />
                          </span>
                        </div>
                        <div>
                          <div className="text-sm font-medium text-fg">报价含运费</div>
                          <div className="text-xs text-muted">{shippingIncluded ? '开启 — 报价已包含运费' : '关闭 — 运费另行计算'}</div>
                        </div>
                      </label>
                    </div>

                    {/* Customer (optional) */}
                    <div className="pb-4 border-b border-border">
                      <label className="block text-xs text-muted uppercase tracking-wider mb-2">客户名称（可选）</label>
                      <input
                        data-guide="privnote-customer"
                        type="text"
                        value={quoteCustomerName}
                        onChange={e => setQuoteCustomerName(e.target.value)}
                        placeholder="输入客户名称，将显示在报价单头部"
                        className="w-full px-3 py-2 border border-border rounded-sm text-sm text-fg bg-white focus:outline-none focus:border-accent"
                      />
                    </div>

                    {quoteMode === 'full' && (
                      <p className="text-sm text-fg leading-relaxed">
                        将生成包含全部 <strong className="text-accent">{quoteProducts?.length ?? 0}</strong> 款雪茄批发报价的完整目录链接。<br />
                        <span className="text-muted">客户打开后可查看所有品牌、款式、支数、批发价及折算单价。</span>
                      </p>
                    )}

                    {quoteMode === 'custom' && (
                      <div className="space-y-3">
                        <div className="relative">
                          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted" />
                          <input
                            data-guide="privnote-quote-search"
                            type="text"
                            value={quoteSearchQ}
                            onChange={e => setQuoteSearchQ(e.target.value)}
                            placeholder="搜索雪茄（品牌/品名/英文名）"
                            className="w-full pl-9 pr-4 py-2 border border-border rounded-sm text-sm text-fg bg-white focus:outline-none focus:border-accent"
                          />
                        </div>

                        {quoteProducts && quoteProducts.length > 0 && (
                          <div className="border border-border rounded-sm bg-white max-h-[480px] overflow-y-auto">
                            {(() => {
                              const filtered = (quoteSearchQ.trim()
                                ? quoteProducts.filter(p =>
                                    p.brand.toLowerCase().includes(quoteSearchQ.toLowerCase()) ||
                                    p.name.toLowerCase().includes(quoteSearchQ.toLowerCase()) ||
                                    p.english_name.toLowerCase().includes(quoteSearchQ.toLowerCase())
                                  )
                                : quoteProducts).filter(p => p.can_preorder || p.in_stock);
                              const byBrand: Record<string, QuoteProduct[]> = {};
                              filtered.forEach(p => {
                                if (!byBrand[p.brand]) byBrand[p.brand] = [];
                                byBrand[p.brand].push(p);
                              });
                              return Object.entries(byBrand).map(([brand, items]) => (
                                <div key={brand} className="border-b border-border last:border-0">
                                  <div className="px-3 py-2 bg-accent-light text-xs font-semibold text-fg sticky top-0 uppercase tracking-wider">
                                    {items[0]?.brand_cn || brand}
                                  </div>
                                  {items.map(p => (
                                    <label
                                      key={`${p.cigar_id}-${p.box_size}`}
                                      className="flex items-center gap-3 px-3 py-2.5 hover:bg-accent-light cursor-pointer border-b border-border last:border-0"
                                    >
                                      <input
                                        data-guide="privnote-quote-product"
                                        type="checkbox"
                                        className="w-4 h-4 accent-accent shrink-0 cursor-pointer"
                                        checked={visibleSelectedIds.includes(p.cigar_id)}
                                        onChange={e => {
                                          if (e.target.checked) {
                                            setSelectedIds(prev => [...(prev ?? defaultSelectedIds), p.cigar_id]);
                                          } else {
                                            setSelectedIds(prev => (prev ?? defaultSelectedIds).filter(id => id !== p.cigar_id));
                                          }
                                        }}
                                      />
                                      <div className="flex-1 min-w-0">
                                        <div className="text-sm font-medium truncate">{p.name}</div>
                                        <div className="text-xs text-muted font-display italic">{p.english_name}</div>
                                      </div>
                                      <div className="flex items-center gap-3 shrink-0">
                                        <input
                                          type="number"
                                          min={1}
                                          value={customPrices[`${p.cigar_id}:${p.box_size}`] ?? p.wholesale_price}
                                          onChange={e => {
                                            const val = parseInt(e.target.value) || p.wholesale_price;
                                            setCustomPrices(prev => ({ ...prev, [`${p.cigar_id}:${p.box_size}`]: val }));
                                          }}
                                          onClick={e => e.stopPropagation()}
                                          className="w-20 px-2 py-1 border border-border rounded-sm text-sm text-right focus:outline-none focus:border-accent"
                                          title="自定义批发价"
                                        />
                                        <div className="text-right shrink-0 w-24">
                                          <div className="text-sm font-mono font-semibold text-accent">¥{(customPrices[`${p.cigar_id}:${p.box_size}`] ?? p.wholesale_price).toLocaleString()}</div>
                                          <div className="text-xs text-muted">{p.box_size}支/盒</div>
                                        </div>
                                      </div>
                                    </label>
                                  ))}
                                </div>
                              ));
                            })()}
                          </div>
                        )}

                        <div className="flex items-center justify-between pt-3 border-t border-border">
                          <span className="text-sm text-muted">已选 {visibleSelectedIds.length} 项</span>
                          <div className="flex gap-3">
                            <button
                              type="button"
                              onClick={() => {
                                const preorderIds = [...new Set((quoteProducts || []).filter(p => p.can_preorder).map(p => p.cigar_id))];
                                setSelectedIds(preorderIds);
                              }}
                              className="text-xs text-accent hover:underline"
                            >
                              全选
                            </button>
                            <button
                              type="button"
                              onClick={() => setSelectedIds([])}
                              className="text-xs text-accent hover:underline"
                            >
                              取消全选
                            </button>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )}

            {/* ── PAYMENT TAB ── */}
            {activeTab === 'payment' && (
              <div className="space-y-4">
                <div className="bg-white border border-border rounded-sm overflow-hidden">
                  <div className="px-5 py-4 border-b border-border">
                    <span className="text-xs text-muted uppercase tracking-wider font-medium">选择既有销售单</span>
                  </div>
                  <div className="p-5 space-y-3">
                    <select
                      data-guide="privnote-payment-order"
                      value={selectedPaymentOrderId}
                      onChange={e => setSelectedPaymentOrderId(e.target.value)}
                      disabled={ordersLoading}
                      className="w-full px-3 py-2.5 border border-border rounded-sm text-sm text-fg bg-white focus:outline-none focus:border-accent"
                    >
                      <option value="">{ordersLoading ? '销售单加载中…' : '请选择待收款销售单'}</option>
                      {eligibleOrders.map(order => (
                        <option key={order.id} value={order.id}>
                          {order.order_number || `SO-${order.id}`} · {order.customer_name || '散客'} · ¥{Number(order.amount_due_cny).toLocaleString()} · {order.display_status || order.status}
                        </option>
                      ))}
                    </select>
                    {!ordersLoading && eligibleOrders.length === 0 && <p className="text-xs text-muted">暂无已确认/已出库且未收款的销售单。</p>}
                  </div>
                </div>

                {selectedPaymentOrder && (
                  <div className="bg-white border border-border rounded-sm overflow-hidden">
                    <div className="px-5 py-4 border-b border-border"><span className="text-xs text-muted uppercase tracking-wider font-medium">订单摘要（只读）</span></div>
                    <div className="p-5 space-y-3 text-sm">
                      {(() => { const summary = paymentOrderSummary(selectedPaymentOrder); return <>
                        <div className="grid gap-2 sm:grid-cols-3"><div><span className="text-xs text-muted">订单号</span><p className="font-mono font-semibold">{summary.order_number}</p></div><div><span className="text-xs text-muted">客户</span><p>{summary.customer_name}</p></div><div><span className="text-xs text-muted">应收金额</span><p className="font-mono font-semibold text-accent">¥{Number(summary.amount_due_cny).toLocaleString()}</p></div></div>
                        <div className="rounded border border-border divide-y divide-border">{summary.items.map((item, index) => <div key={index} className="flex items-center justify-between px-3 py-2 text-xs"><span>{item.name}</span><span className="text-muted">{item.quantity} {item.sale_unit === 'box' ? '盒' : '支'} · ¥{Number(item.unit_price).toLocaleString()}</span></div>)}{summary.items.length === 0 && <p className="px-3 py-3 text-xs text-muted">暂无商品明细</p>}</div>
                      </>; })()}
                    </div>
                  </div>
                )}

                <div className="bg-white border border-border rounded-sm overflow-hidden">
                  <div className="px-5 py-4 border-b border-border"><span className="text-xs text-muted uppercase tracking-wider font-medium">收款方式</span></div>
                  <div className="p-5 space-y-4">
                    <select data-guide="privnote-payment-method" required value={paymentMethodId} onChange={e => setPaymentMethodId(e.target.value)} className="w-full px-3 py-2.5 border border-border rounded-sm text-sm text-fg bg-white focus:outline-none focus:border-accent">
                      <option value="">请选择已绑定的 CNY 收款账户</option>
                      {paymentMethods?.map((pm: PaymentMethod) => <option key={pm.id} value={pm.id}>{pm.label}{pm.remark ? ` · ${pm.remark}` : ''}</option>)}
                    </select>
                    <label className="block text-xs text-muted uppercase tracking-wider">备注<textarea data-guide="privnote-payment-remark" value={remark} onChange={e => setRemark(e.target.value)} rows={3} placeholder="备注信息…" className="mt-2 w-full px-3 py-2 border border-border rounded-sm text-sm text-fg bg-white focus:outline-none focus:border-accent resize-none" /></label>
                    <div><label className="block text-xs text-muted uppercase tracking-wider mb-2">备注图片</label><FileUploadArea {...paymentImages} /></div>
                  </div>
                </div>
              </div>
            )}
            {/* ── MESSAGE TAB ── */}
            {activeTab === 'message' && (
              <div className="space-y-4">
                <div className="bg-white border border-border rounded-sm overflow-hidden">
                  <div className="px-5 py-4 border-b border-border">
                    <span className="text-xs text-muted uppercase tracking-wider font-medium">消息内容</span>
                  </div>
                  <div className="p-5">
                    <textarea
                      data-guide="privnote-message"
                      value={messageText}
                      onChange={e => setMessageText(e.target.value)}
                      rows={6}
                      placeholder="在此输入要发送的消息内容..."
                      className="w-full px-3 py-2 border border-border rounded-sm text-sm text-fg bg-white focus:outline-none focus:border-accent resize-none leading-relaxed min-h-[120px]"
                    />
                  </div>
                </div>

                {/* Image upload — always visible */}
                <div className="bg-white border border-border rounded-sm overflow-hidden">
                  <div className="px-5 py-4 border-b border-border">
                    <span className="text-xs text-muted uppercase tracking-wider font-medium">图片附件</span>
                  </div>
                  <div className="p-5">
                    <FileUploadArea {...messageImages} />
                  </div>
                </div>

                {/* External link attachments — collapsible */}
                <div className="bg-white border border-border rounded-sm overflow-hidden">
                  <button
                    type="button"
                    onClick={() => setShowAttachments(v => !v)}
                    className="w-full px-5 py-4 flex items-center justify-between text-left hover:bg-accent-light/30 transition-colors"
                  >
                    <span className="text-xs text-muted uppercase tracking-wider font-medium">外部链接附件</span>
                    <span className="text-xs text-accent">{showAttachments ? '收起' : '展开添加'}</span>
                  </button>
                  {showAttachments && (
                    <div className="px-5 pb-5 space-y-4">
                      <p className="text-xs text-muted">可添加外部资源链接（如网盘、文档、视频链接等），客户可在查看页直接打开</p>
                      <div className="flex gap-2">
                        <input
                          type="text"
                          value={attachName}
                          onChange={e => setAttachName(e.target.value)}
                          placeholder="附件名称"
                          className="flex-1 px-3 py-2 border border-border rounded-sm text-sm text-fg bg-white focus:outline-none focus:border-accent"
                        />
                        <input
                          type="text"
                          value={attachUrl}
                          onChange={e => setAttachUrl(e.target.value)}
                          placeholder="URL"
                          className="flex-[2] px-3 py-2 border border-border rounded-sm text-sm text-fg bg-white focus:outline-none focus:border-accent"
                        />
                        <button
                          type="button"
                          onClick={addAttachment}
                          className="px-3 py-2 bg-accent text-white rounded-sm text-sm hover:bg-accent-hover transition-colors"
                        >
                          <Plus className="w-4 h-4" />
                        </button>
                      </div>
                      {attachments.length > 0 && (
                        <div className="space-y-1">
                          {attachments.map((att, idx) => (
                            <div
                              key={idx}
                              className="flex items-center justify-between bg-accent-light rounded-sm px-3 py-2"
                            >
                              <a
                                href={att.url}
                                target="_blank"
                                rel="noreferrer"
                                className="text-sm text-accent hover:underline truncate"
                              >
                                {att.name}
                              </a>
                              <button
                                type="button"
                                onClick={() => removeAttachment(idx)}
                                className="p-1 text-muted hover:text-accent transition-colors"
                              >
                                <X className="w-3.5 h-3.5" />
                              </button>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>

          {/* Action Bar */}
          <div className="sticky bottom-0 bg-white border-t border-border px-6 py-4 flex items-center justify-between gap-4 z-50">
            <div className="min-w-0 text-sm text-muted">{error ? <span className="text-red-700">{error}</span> : actionHint()}</div>
            <div className="flex gap-3">
              <button
                type="button"
                onClick={resetAll}
                className="px-5 py-2.5 border border-border rounded-sm text-sm font-medium text-fg hover:bg-accent-light transition-colors"
              >
                取消
              </button>
              <button
                data-guide="privnote-submit"
                type="submit"
                disabled={loading || !canSubmit()}
                className="px-5 py-2.5 bg-accent text-white rounded-sm text-sm font-medium hover:bg-accent-hover active:scale-[0.98] transition-all disabled:opacity-50"
              >
                {loading ? '生成中…' : '创建私密链接'}
              </button>
            </div>
          </div>
        </form>
      )}
    </div>
  );
}
