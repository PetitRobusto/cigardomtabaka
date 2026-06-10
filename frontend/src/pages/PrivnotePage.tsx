import { useState, useEffect, useRef, useCallback } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Copy, Check,
  Package, Search, Plus,
  X, Upload, ImageIcon, ClipboardList, Wallet, Send
} from 'lucide-react';
import {
  fetchPaymentMethods, searchCigars, createPrivnote, searchCustomers,
  fetchQuoteProducts, uploadPrivnoteImage
} from '../api';
import { useAuthStore } from '../store/authStore';
import { usePageMeta } from '../hooks/usePageMeta';
import type { SearchCigarResult, PaymentItem, CustomerResult, ExtraFee, QuoteProduct } from '../types';

const DURATIONS = [
  { value: '1', label: '1 小时' },
  { value: '6', label: '6 小时' },
  { value: '24', label: '24 小时' },
  { value: '72', label: '3 天' },
  { value: '168', label: '7 天' },
  { value: '720', label: '30 天' },
];

const TABS = [
  { key: 'quote' as const, label: '报价单', icon: ClipboardList },
  { key: 'payment' as const, label: '收款', icon: Wallet },
  { key: 'message' as const, label: '消息', icon: Send },
];

type TabKey = typeof TABS[number]['key'];
type QuoteMode = 'full' | 'custom';
type PaymentAddMode = 'stock' | 'manual';

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

  // Result
  const [result, setResult] = useState<{ url: string; token: string } | null>(null);
  const [copied, setCopied] = useState(false);
  const [loading, setLoading] = useState(false);

  // Payment tab state
  const [searchQ, setSearchQ] = useState('');
  const [searchResults, setSearchResults] = useState<SearchCigarResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [paymentItems, setPaymentItems] = useState<PaymentItem[]>([]);
  const [customerName, setCustomerName] = useState('');
  const [customerQuery, setCustomerQuery] = useState('');
  const [customerResults, setCustomerResults] = useState<CustomerResult[]>([]);
  const [customerSearching, setCustomerSearching] = useState(false);
  const [paymentMethodId, setPaymentMethodId] = useState('');
  const [useShipping, setUseShipping] = useState(false);
  const [shippingAmount, setShippingAmount] = useState(0);
  const [useCourier, setUseCourier] = useState(false);
  const [courierAmount, setCourierAmount] = useState(0);
  const [customFees, setCustomFees] = useState<ExtraFee[]>([]);
  const [remark, setRemark] = useState('');
  const [paymentAddMode, setPaymentAddMode] = useState<PaymentAddMode>('stock');
  const [manualName, setManualName] = useState('');
  const [manualQty, setManualQty] = useState(1);
  const [manualPrice, setManualPrice] = useState(0);
  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const customerTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const paymentImages = useImageUpload();

  const { data: paymentMethods } = useQuery({
    queryKey: ['payment-methods'],
    queryFn: fetchPaymentMethods,
    enabled: activeTab === 'payment',
  });

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
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [customPrices, setCustomPrices] = useState<Record<string, number>>({});
  const [quoteCustomerName, setQuoteCustomerName] = useState('');

  const { data: quoteProducts } = useQuery({
    queryKey: ['quote-products'],
    queryFn: fetchQuoteProducts,
    enabled: activeTab === 'quote',
  });

  // Default select all when switching to custom mode
  useEffect(() => {
    if (quoteMode === 'custom' && quoteProducts && quoteProducts.length > 0) {
      const preorderIds = [...new Set(quoteProducts.filter(p => p.can_preorder).map(p => p.cigar_id))];
      setSelectedIds(preorderIds);
    }
  }, [quoteMode, quoteProducts]);



  // Debounced cigar search
  useEffect(() => {
    if (searchTimer.current) clearTimeout(searchTimer.current);
    if (!searchQ.trim()) {
      setSearchResults([]);
      return;
    }
    setSearching(true);
    searchTimer.current = setTimeout(async () => {
      try {
        const res = await searchCigars(searchQ, false);
        setSearchResults(res);
      } catch {
        setSearchResults([]);
      } finally {
        setSearching(false);
      }
    }, 300);
    return () => { if (searchTimer.current) clearTimeout(searchTimer.current); };
  }, [searchQ]);

  // Debounced customer search
  useEffect(() => {
    if (customerTimer.current) clearTimeout(customerTimer.current);
    if (!customerQuery.trim()) {
      setCustomerResults([]);
      return;
    }
    setCustomerSearching(true);
    customerTimer.current = setTimeout(async () => {
      try {
        const res = await searchCustomers(customerQuery);
        setCustomerResults(res);
      } catch {
        setCustomerResults([]);
      } finally {
        setCustomerSearching(false);
      }
    }, 300);
    return () => { if (customerTimer.current) clearTimeout(customerTimer.current); };
  }, [customerQuery]);

  if (!user?.is_staff) {
    return (
      <div className="text-center py-20">
        <p className="text-muted">您没有权限访问此页面</p>
      </div>
    );
  }

  const copyUrl = async () => {
    if (!result?.url) return;
    let success = false;
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

  const addPaymentItem = (cigar: SearchCigarResult, batchId?: number) => {
    const batch = batchId ? cigar.batches.find(b => b.batch_id === batchId) : cigar.batches[0];
    const boxSize = batch?.box_size || 25;
    const unitCost = batch?.unit_cost_cny || 0;
    const unitPrice = batch ? Math.round(unitCost * 1.5) : 0;
    const exists = paymentItems.find(i => i.cigar_id === cigar.id && i.batch_id === batchId);
    if (exists) return;
    setPaymentItems(prev => [...prev, {
      cigar_id: cigar.id,
      batch_id: batchId || batch?.batch_id,
      name: cigar.name,
      english_name: cigar.english_name,
      brand: cigar.brand,
      brand_cn: cigar.brand_cn,
      vitola: cigar.vitola,
      length: cigar.length,
      ring_gauge: cigar.ring_gauge,
      thumb_url: cigar.thumb_url,
      quantity: 1,
      unit_price: unitPrice,
      box_size: boxSize,
    }]);
    setSearchQ('');
    setSearchResults([]);
  };

  const addManualPaymentItem = () => {
    if (!manualName.trim() || manualPrice <= 0) return;
    setPaymentItems(prev => [...prev, {
      cigar_id: 0,
      name: manualName.trim(),
      english_name: '',
      brand: '',
      brand_cn: '',
      vitola: '',
      length: null,
      ring_gauge: null,
      thumb_url: null,
      quantity: manualQty,
      unit_price: manualPrice,
      box_size: 1,
    }]);
    setManualName('');
    setManualQty(1);
    setManualPrice(0);
  };

  const removePaymentItem = (idx: number) => {
    setPaymentItems(prev => prev.filter((_, i) => i !== idx));
  };

  const updatePaymentItem = (idx: number, field: keyof PaymentItem, value: string | number) => {
    setPaymentItems(prev => prev.map((item, i) => i === idx ? { ...item, [field]: value } : item));
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

  const addCustomFee = () => {
    setCustomFees(prev => [...prev, { name: '', amount: 0 }]);
  };

  const updateCustomFee = (idx: number, field: keyof ExtraFee, value: string | number) => {
    setCustomFees(prev => prev.map((f, i) => i === idx ? { ...f, [field]: value } : f));
  };

  const removeCustomFee = (idx: number) => {
    setCustomFees(prev => prev.filter((_, i) => i !== idx));
  };

  const getExtraFees = (): ExtraFee[] => {
    const fees: ExtraFee[] = [];
    if (useShipping && shippingAmount > 0) fees.push({ name: '运费', amount: shippingAmount });
    if (useCourier && courierAmount > 0) fees.push({ name: '人肉费', amount: courierAmount });
    for (const f of customFees) {
      if (f.name.trim() && f.amount > 0) fees.push({ name: f.name.trim(), amount: f.amount });
    }
    return fees;
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    const form = new FormData();

    form.append('note_type', activeTab);
    form.append('duration', duration);
    form.append('password', password);
    form.append('burn', burn ? 'on' : 'off');

    if (activeTab === 'payment') {
      form.append('items', JSON.stringify(paymentItems.map(i => ({
        cigar_id: i.cigar_id,
        batch_id: i.batch_id,
        quantity: i.quantity,
        unit_price: i.unit_price,
      }))));
      form.append('customer_name', customerName);
      form.append('payment_method_id', paymentMethodId);
      form.append('extra_fees', JSON.stringify(getExtraFees()));
      form.append('remark', remark);
      form.append('images', JSON.stringify(paymentImages.images));
    } else if (activeTab === 'message') {
      form.append('text', messageText);
      form.append('attachments', JSON.stringify(attachments));
      form.append('images', JSON.stringify(messageImages.images));
    } else if (activeTab === 'quote') {
      form.append('quote_mode', quoteMode);
      form.append('selected_ids', JSON.stringify(selectedIds));
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
      if (res.url) setResult({ url: res.url, token: res.token });
    } finally {
      setLoading(false);
    }
  };

  const resetAll = () => {
    setResult(null);
    setPassword('');
    setPaymentItems([]);
    setCustomerName('');
    setPaymentMethodId('');
    setMessageText('');
    setAttachments([]);
    setShowAttachments(false);
    setSearchQ('');
    setSearchResults([]);
    setQuoteMode('full');
    setShippingIncluded(false);
    setQuoteSearchQ('');
    setSelectedIds([]);
    setCustomPrices({});
    setQuoteCustomerName('');
    paymentImages.setImages([]);
    messageImages.setImages([]);
    setRemark('');
    setUseShipping(false);
    setUseCourier(false);
    setCustomFees([]);
    setShippingAmount(0);
    setCourierAmount(0);
    setActiveTab('quote');
  };

  const canSubmit = () => {
    if (activeTab === 'payment') return paymentItems.length > 0;
    if (activeTab === 'message') return !!messageText.trim() || attachments.length > 0 || messageImages.images.length > 0;
    if (activeTab === 'quote') {
      if (quoteMode === 'full') return true;
      return selectedIds.length > 0;
    }
    return false;
  };

  const actionHint = () => {
    if (activeTab === 'quote') {
      if (quoteMode === 'full') return '将生成包含全部 72 款雪茄的完整报价单';
      return selectedIds.length > 0 ? `已选 ${selectedIds.length} 项商品` : '请勾选要包含在报价单中的雪茄';
    }
    if (activeTab === 'payment') return paymentItems.length > 0 ? `已选 ${paymentItems.length} 项商品` : '添加商品并选择收款方式';
    return '输入消息内容并上传附件';
  };

  const totalPayment = paymentItems.reduce((sum, i) => sum + i.quantity * i.unit_price, 0);

  return (
    <div className="animate-fade-in max-w-4xl mx-auto pb-32">
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
            <div className="flex items-center gap-3">
              <span className="text-xs text-muted uppercase tracking-wider">有效期</span>
              <select
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
                type="text"
                value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder="可选"
                className="px-3 py-2 border border-border rounded-sm text-sm text-fg bg-white focus:outline-none focus:border-accent min-w-[160px]"
              />
            </div>
            <div className="flex items-center gap-3 ml-auto">
              <label className="flex items-center gap-3 cursor-pointer">
                <div className="relative">
                  <input type="checkbox" className="sr-only" checked={burn} onChange={e => setBurn(e.target.checked)} />
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
            {/* ── QUOTE TAB ── */}
            {activeTab === 'quote' && (
              <div className="space-y-4">
                <div className="bg-white border border-border rounded-sm overflow-hidden">
                  <div className="px-5 py-4 border-b border-border flex items-center justify-between gap-3 flex-wrap">
                    <span className="text-xs text-muted uppercase tracking-wider font-medium">报价单模式</span>
                    <div className="inline-flex bg-accent-light rounded-sm p-1 gap-1">
                      <button
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
                        type="button"
                        onClick={() => setQuoteMode('custom')}
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
                          <input type="checkbox" className="sr-only" checked={shippingIncluded} onChange={e => setShippingIncluded(e.target.checked)} />
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
                                        type="checkbox"
                                        className="w-4 h-4 accent-accent shrink-0 cursor-pointer"
                                        checked={selectedIds.includes(p.cigar_id)}
                                        onChange={e => {
                                          if (e.target.checked) {
                                            setSelectedIds(prev => [...prev, p.cigar_id]);
                                          } else {
                                            setSelectedIds(prev => prev.filter(id => id !== p.cigar_id));
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
                          <span className="text-sm text-muted">已选 {selectedIds.length} 项</span>
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
                {/* Add Product */}
                <div className="bg-white border border-border rounded-sm overflow-hidden">
                  <div className="px-5 py-4 border-b border-border flex items-center justify-between gap-3 flex-wrap">
                    <span className="text-xs text-muted uppercase tracking-wider font-medium">添加商品</span>
                    <div className="inline-flex bg-accent-light rounded-sm p-1 gap-1">
                      <button
                        type="button"
                        onClick={() => setPaymentAddMode('stock')}
                        className={`px-4 py-2 text-xs font-medium rounded-sm transition-all ${
                          paymentAddMode === 'stock'
                            ? 'bg-white text-fg shadow-sm'
                            : 'text-muted hover:text-fg'
                        }`}
                      >
                        从库存选
                      </button>
                      <button
                        type="button"
                        onClick={() => setPaymentAddMode('manual')}
                        className={`px-4 py-2 text-xs font-medium rounded-sm transition-all ${
                          paymentAddMode === 'manual'
                            ? 'bg-white text-fg shadow-sm'
                            : 'text-muted hover:text-fg'
                        }`}
                      >
                        手动输入
                      </button>
                    </div>
                  </div>
                  <div className="p-5">
                    {paymentAddMode === 'stock' ? (
                      <div>
                        <div className="relative mb-3">
                          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted" />
                          <input
                            type="text"
                            value={searchQ}
                            onChange={e => setSearchQ(e.target.value)}
                            placeholder="搜索品牌 + 款式，如：高希霸 罗布图 / Cohiba D4"
                            className="w-full pl-9 pr-4 py-2 border border-border rounded-sm text-sm text-fg bg-white focus:outline-none focus:border-accent"
                          />
                        </div>
                        {searching && <p className="text-xs text-muted mb-2">搜索中…</p>}
                        {Array.isArray(searchResults) && searchResults.length > 0 && (
                          <div className="border border-border rounded-sm bg-white max-h-72 overflow-y-auto">
                            {searchResults.map(c => (
                              <div
                                key={c.id}
                                className="px-4 py-3 hover:bg-accent-light cursor-pointer border-b border-border last:border-0"
                                onClick={() => addPaymentItem(c)}
                              >
                                {/* 品牌 · 名称 */}
                                <div className="text-sm font-medium">
                                  {c.brand_cn ? `${c.brand_cn} · ${c.name}` : `${c.brand} · ${c.name}`}
                                </div>
                                {/* 品型 · 尺寸 */}
                                <div className="text-xs text-muted mt-0.5">
                                  {c.vitola}
                                  {c.length && c.ring_gauge ? ` · ${c.length}mm × ${c.ring_gauge}环径` : ''}
                                  {' · '}库存 {c.stock_qty} 支
                                </div>
                                {/* 图片 + 批次按钮 */}
                                <div className="flex items-start gap-3 mt-2">
                                  <div className="w-12 h-12 rounded-sm bg-accent-light flex items-center justify-center shrink-0 overflow-hidden">
                                    {c.thumb_url ? (
                                      <img src={c.thumb_url} alt={c.name} className="w-full h-full object-contain p-0.5" />
                                    ) : (
                                      <Package className="w-5 h-5 text-muted" />
                                    )}
                                  </div>
                                  {c.batches.length > 1 && (
                                    <div className="flex gap-1 flex-wrap flex-1">
                                      {c.batches.map(b => (
                                        <button
                                          key={b.batch_id}
                                          type="button"
                                          onClick={ev => { ev.stopPropagation(); addPaymentItem(c, b.batch_id); }}
                                          className="text-[10px] px-2 py-1 rounded-sm bg-accent/10 text-accent hover:bg-accent/20"
                                        >
                                          {b.box_size}支/盒 · 余{b.remaining}
                                        </button>
                                      ))}
                                    </div>
                                  )}
                                </div>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    ) : (
                      <div className="grid grid-cols-3 gap-4">
                        <div>
                          <label className="block text-xs text-muted uppercase tracking-wider mb-2">雪茄名称</label>
                          <input
                            type="text"
                            value={manualName}
                            onChange={e => setManualName(e.target.value)}
                            placeholder="输入雪茄名称"
                            className="w-full px-3 py-2 border border-border rounded-sm text-sm text-fg bg-white focus:outline-none focus:border-accent"
                          />
                        </div>
                        <div>
                          <label className="block text-xs text-muted uppercase tracking-wider mb-2">数量</label>
                          <input
                            type="number"
                            min={1}
                            value={manualQty}
                            onChange={e => setManualQty(parseInt(e.target.value) || 1)}
                            placeholder="1"
                            className="w-full px-3 py-2 border border-border rounded-sm text-sm text-fg bg-white focus:outline-none focus:border-accent"
                          />
                        </div>
                        <div>
                          <label className="block text-xs text-muted uppercase tracking-wider mb-2">单价 (CNY)</label>
                          <input
                            type="number"
                            min={0}
                            value={manualPrice}
                            onChange={e => setManualPrice(parseInt(e.target.value) || 0)}
                            placeholder="0"
                            className="w-full px-3 py-2 border border-border rounded-sm text-sm text-fg bg-white focus:outline-none focus:border-accent"
                          />
                        </div>
                        <div className="col-span-3 text-right">
                          <button
                            type="button"
                            onClick={addManualPaymentItem}
                            className="px-4 py-2 bg-accent text-white rounded-sm text-sm font-medium hover:bg-accent-hover transition-colors"
                          >
                            加入订单
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                </div>

                {/* Order List */}
                {paymentItems.length > 0 && (
                  <div className="bg-white border border-border rounded-sm overflow-hidden">
                    <div className="px-5 py-4 border-b border-border flex items-center justify-between">
                      <span className="text-xs text-muted uppercase tracking-wider font-medium">已选商品</span>
                      <span className="text-sm text-muted">{paymentItems.length} 项</span>
                    </div>
                    <div className="overflow-x-auto">
                      <table className="w-full border-collapse text-sm">
                        <thead>
                          <tr className="bg-accent-light">
                            <th className="px-4 py-3 text-left text-xs text-muted uppercase tracking-wider font-medium">雪茄</th>
                            <th className="px-4 py-3 text-right text-xs text-muted uppercase tracking-wider font-medium">数量</th>
                            <th className="px-4 py-3 text-right text-xs text-muted uppercase tracking-wider font-medium">单价</th>
                            <th className="px-4 py-3 text-right text-xs text-muted uppercase tracking-wider font-medium">小计</th>
                            <th className="px-4 py-3 text-center text-xs text-muted uppercase tracking-wider font-medium w-10"></th>
                          </tr>
                        </thead>
                        <tbody>
                          {paymentItems.map((item, idx) => (
                            <tr key={`${item.cigar_id}-${item.batch_id}-${idx}`} className="border-b border-border hover:bg-accent-light/30">
                              <td className="px-4 py-3">
                                <div className="flex flex-col gap-1">
                                  <div className="text-sm font-medium">
                                    {item.brand_cn ? `${item.brand_cn} · ${item.name}` : (item.brand ? `${item.brand} · ${item.name}` : item.name)}
                                  </div>
                                  <div className="text-xs text-muted">
                                    {item.vitola}
                                    {item.length && item.ring_gauge ? ` · ${item.length}mm × ${item.ring_gauge}环径` : ''}
                                  </div>
                                  {item.thumb_url ? (
                                    <img src={item.thumb_url} alt={item.name} className="w-12 h-12 object-contain rounded-sm bg-accent-light p-0.5 mt-0.5" />
                                  ) : (
                                    <div className="w-12 h-12 rounded-sm bg-accent-light flex items-center justify-center mt-0.5">
                                      <Package className="w-4 h-4 text-muted" />
                                    </div>
                                  )}
                                </div>
                              </td>
                              <td className="px-4 py-3 text-right">
                                <input
                                  type="number"
                                  min={1}
                                  value={item.quantity}
                                  onChange={e => updatePaymentItem(idx, 'quantity', parseInt(e.target.value) || 1)}
                                  className="w-16 px-2 py-1 border border-border rounded-sm text-sm text-center focus:outline-none focus:border-accent"
                                />
                              </td>
                              <td className="px-4 py-3 text-right">
                                <div className="flex items-center justify-end gap-1">
                                  <span className="text-xs text-muted">¥</span>
                                  <input
                                    type="number"
                                    min={0}
                                    value={item.unit_price}
                                    onChange={e => updatePaymentItem(idx, 'unit_price', parseInt(e.target.value) || 0)}
                                    className="w-20 px-2 py-1 border border-border rounded-sm text-sm text-right focus:outline-none focus:border-accent"
                                  />
                                </div>
                              </td>
                              <td className="px-4 py-3 text-right font-mono font-semibold">
                                ¥{(item.quantity * item.unit_price).toLocaleString()}
                              </td>
                              <td className="px-4 py-3 text-center">
                                <button
                                  type="button"
                                  onClick={() => removePaymentItem(idx)}
                                  className="text-muted hover:text-accent transition-colors"
                                >
                                  <X className="w-4 h-4" />
                                </button>
                              </td>
                            </tr>
                          ))}
                          <tr className="bg-accent-light font-semibold">
                            <td colSpan={3} className="px-4 py-3 text-right text-sm text-muted">合计</td>
                            <td className="px-4 py-3 text-right font-display text-lg text-accent">¥{totalPayment.toLocaleString()}</td>
                            <td></td>
                          </tr>
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}

                {/* Extra Fees */}
                <div className="bg-white border border-border rounded-sm overflow-hidden">
                  <div className="px-5 py-4 border-b border-border">
                    <span className="text-xs text-muted uppercase tracking-wider font-medium">额外费用</span>
                  </div>
                  <div className="p-5 space-y-3">
                    <label className="flex items-center gap-3 cursor-pointer">
                      <div className="relative">
                        <input type="checkbox" className="sr-only" checked={useShipping} onChange={e => setUseShipping(e.target.checked)} />
                        <span className={`block w-10 h-[22px] rounded-full transition-colors ${useShipping ? 'bg-accent' : 'bg-border'}`}>
                          <span className={`absolute top-[2px] left-[2px] w-[18px] h-[18px] bg-white rounded-full shadow transition-transform ${useShipping ? 'translate-x-[18px]' : 'translate-x-0'}`} />
                        </span>
                      </div>
                      <span className="text-sm">运费</span>
                      {useShipping && (
                        <input
                          type="number"
                          min={0}
                          value={shippingAmount}
                          onChange={e => setShippingAmount(parseInt(e.target.value) || 0)}
                          className="w-20 px-2 py-1 border border-border rounded-sm text-sm text-right focus:outline-none focus:border-accent"
                        />
                      )}
                    </label>
                    <label className="flex items-center gap-3 cursor-pointer">
                      <div className="relative">
                        <input type="checkbox" className="sr-only" checked={useCourier} onChange={e => setUseCourier(e.target.checked)} />
                        <span className={`block w-10 h-[22px] rounded-full transition-colors ${useCourier ? 'bg-accent' : 'bg-border'}`}>
                          <span className={`absolute top-[2px] left-[2px] w-[18px] h-[18px] bg-white rounded-full shadow transition-transform ${useCourier ? 'translate-x-[18px]' : 'translate-x-0'}`} />
                        </span>
                      </div>
                      <span className="text-sm">人肉费</span>
                      {useCourier && (
                        <input
                          type="number"
                          min={0}
                          value={courierAmount}
                          onChange={e => setCourierAmount(parseInt(e.target.value) || 0)}
                          className="w-20 px-2 py-1 border border-border rounded-sm text-sm text-right focus:outline-none focus:border-accent"
                        />
                      )}
                    </label>
                    {customFees.map((f, idx) => (
                      <div key={idx} className="flex items-center gap-2">
                        <input
                          type="text"
                          value={f.name}
                          onChange={e => updateCustomFee(idx, 'name', e.target.value)}
                          placeholder="费用名"
                          className="flex-1 px-3 py-1.5 border border-border rounded-sm text-sm focus:outline-none focus:border-accent"
                        />
                        <input
                          type="number"
                          min={0}
                          value={f.amount}
                          onChange={e => updateCustomFee(idx, 'amount', parseInt(e.target.value) || 0)}
                          placeholder="金额"
                          className="w-24 px-3 py-1.5 border border-border rounded-sm text-sm text-right focus:outline-none focus:border-accent"
                        />
                        <button type="button" onClick={() => removeCustomFee(idx)} className="p-1 text-muted hover:text-accent transition-colors">
                          <X className="w-4 h-4" />
                        </button>
                      </div>
                    ))}
                    <button type="button" onClick={addCustomFee} className="text-xs text-accent hover:underline flex items-center gap-1">
                      <Plus className="w-3 h-3" /> 添加费用
                    </button>
                  </div>
                </div>

                {/* Customer */}
                <div className="bg-white border border-border rounded-sm overflow-hidden">
                  <div className="px-5 py-4 border-b border-border">
                    <span className="text-xs text-muted uppercase tracking-wider font-medium">客户信息</span>
                  </div>
                  <div className="p-5">
                    <div className="relative">
                      <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted" />
                      <input
                        type="text"
                        value={customerQuery}
                        onChange={e => { setCustomerQuery(e.target.value); setCustomerName(e.target.value); }}
                        placeholder="搜索客户（输入名字，选已有或输入新名）"
                        className="w-full pl-9 pr-4 py-2 border border-border rounded-sm text-sm text-fg bg-white focus:outline-none focus:border-accent"
                      />
                    </div>
                    {customerSearching && <p className="text-xs text-muted mt-2">搜索中…</p>}
                    {Array.isArray(customerResults) && customerResults.length > 0 && (
                      <div className="mt-2 border border-border rounded-sm bg-white max-h-36 overflow-y-auto">
                        {customerResults.map(c => (
                          <div
                            key={c.id}
                            className="px-4 py-2.5 hover:bg-accent-light cursor-pointer border-b border-border last:border-0"
                            onClick={() => { setCustomerName(c.name); setCustomerQuery(c.name); setCustomerResults([]); }}
                          >
                            <div className="text-sm font-medium">{c.name}</div>
                            {c.phone && <div className="text-xs text-muted">{c.phone}</div>}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>

                {/* Payment Method */}
                <div className="bg-white border border-border rounded-sm overflow-hidden">
                  <div className="px-5 py-4 border-b border-border">
                    <span className="text-xs text-muted uppercase tracking-wider font-medium">收款方式</span>
                  </div>
                  <div className="p-5 space-y-4">
                    <div>
                      <label className="block text-xs text-muted uppercase tracking-wider mb-2">选择预设收款方式</label>
                      <select
                        value={paymentMethodId}
                        onChange={e => setPaymentMethodId(e.target.value)}
                        className="w-full px-3 py-2.5 border border-border rounded-sm text-sm text-fg bg-white focus:outline-none focus:border-accent appearance-none"
                        style={{ backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%238A7E6E' stroke-width='2.5' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='6 9 12 15 18 9'/%3E%3C/svg%3E")`, backgroundRepeat: 'no-repeat', backgroundPosition: 'right 14px center', paddingRight: 36 }}
                      >
                        <option value="">手动填写</option>
                        {paymentMethods?.map(pm => (
                          <option key={pm.id} value={pm.id}>{pm.label}</option>
                        ))}
                      </select>
                    </div>

                    {/* Remark */}
                    <div>
                      <label className="block text-xs text-muted uppercase tracking-wider mb-2">备注</label>
                      <textarea
                        value={remark}
                        onChange={e => setRemark(e.target.value)}
                        rows={3}
                        placeholder="备注信息…"
                        className="w-full px-3 py-2 border border-border rounded-sm text-sm text-fg bg-white focus:outline-none focus:border-accent resize-none leading-relaxed"
                      />
                    </div>

                    {/* Remark Images */}
                    <div>
                      <label className="block text-xs text-muted uppercase tracking-wider mb-2">备注图片</label>
                      <FileUploadArea {...paymentImages} />
                    </div>
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
            <div className="text-sm text-muted">{actionHint()}</div>
            <div className="flex gap-3">
              <button
                type="button"
                onClick={resetAll}
                className="px-5 py-2.5 border border-border rounded-sm text-sm font-medium text-fg hover:bg-accent-light transition-colors"
              >
                取消
              </button>
              <button
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
