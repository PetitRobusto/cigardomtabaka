import { useState, useEffect, useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Link2, Clock, Lock, Flame, Copy, Check,
  Package, CreditCard, MessageSquare, Search, Plus, Trash2
} from 'lucide-react';
import {
  fetchPaymentMethods, searchCigars, createPrivnote, searchCustomers
} from '../api';
import { useAuthStore } from '../store/authStore';
import type { SearchCigarResult, PaymentItem, CustomerResult, ExtraFee } from '../types';

const DURATIONS = [
  { value: '1', label: '1 小时' },
  { value: '6', label: '6 小时' },
  { value: '24', label: '24 小时' },
  { value: '72', label: '3 天' },
  { value: '168', label: '7 天' },
  { value: '720', label: '30 天' },
];

const TABS = [
  { key: 'inventory' as const, label: '库存报价', icon: Package },
  { key: 'payment' as const, label: '收款单', icon: CreditCard },
  { key: 'message' as const, label: '消息', icon: MessageSquare },
];

type TabKey = typeof TABS[number]['key'];

export default function PrivnotePage() {
  const { user } = useAuthStore();
  const [activeTab, setActiveTab] = useState<TabKey>('inventory');

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
  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const customerTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

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

  // Debounced cigar search (stock_only=0: all cigars, not just in-stock)
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

  const copyUrl = () => {
    if (result?.url) {
      navigator.clipboard.writeText(result.url);
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
      vitola: cigar.vitola,
      thumb_url: cigar.thumb_url,
      quantity: 1,
      unit_price: unitPrice,
      box_size: boxSize,
    }]);
    setSearchQ('');
    setSearchResults([]);
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
    } else if (activeTab === 'message') {
      form.append('text', messageText);
      form.append('attachments', JSON.stringify(attachments));
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
    setSearchQ('');
    setSearchResults([]);
  };

  const canSubmit = () => {
    if (activeTab === 'payment') return paymentItems.length > 0;
    if (activeTab === 'message') return !!messageText.trim() || attachments.length > 0;
    return true;
  };

  return (
    <div className="animate-fade-in max-w-2xl mx-auto">
      <div className="flex items-center gap-3 mb-6">
        <div className="w-10 h-10 rounded-lg bg-accent/10 flex items-center justify-center">
          <Link2 className="w-5 h-5 text-accent" />
        </div>
        <div>
          <h1 className="text-xl font-bold text-fg">生成链接</h1>
          <p className="text-sm text-muted">创建一次性客户文档</p>
        </div>
      </div>

      {result ? (
        <div className="bg-white border border-border rounded-md p-6 text-center">
          <div className="w-12 h-12 rounded-full bg-emerald-50 flex items-center justify-center mx-auto mb-4">
            <Check className="w-6 h-6 text-emerald-600" />
          </div>
          <h3 className="text-lg font-semibold text-fg mb-2">链接已生成</h3>
          <div className="flex items-center gap-2 bg-accent-light rounded-md p-3 mb-4">
            <code className="text-sm text-fg flex-1 break-all">{result.url}</code>
            <button
              onClick={copyUrl}
              className="p-2 rounded-md text-accent hover:bg-accent/10 transition-colors shrink-0"
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
          {/* Tabs */}
          <div className="flex gap-2">
            {TABS.map(tab => (
              <button
                key={tab.key}
                type="button"
                onClick={() => setActiveTab(tab.key)}
                className={`flex-1 flex items-center justify-center gap-2 py-2.5 rounded-md text-sm font-medium transition-all ${
                  activeTab === tab.key
                    ? 'bg-accent text-white'
                    : 'bg-accent-light text-fg hover:bg-accent/10'
                }`}
              >
                <tab.icon className="w-4 h-4" />
                {tab.label}
              </button>
            ))}
          </div>

          {/* Tab Content */}
          <div className="bg-white border border-border rounded-md p-5 space-y-5">
            {activeTab === 'inventory' && (
              <div>
                <p className="text-sm text-muted">
                  生成当前库存的快照链接，客户可查看实时库存与报价。
                </p>
              </div>
            )}

            {activeTab === 'payment' && (
              <div className="space-y-4">
                {/* Customer search */}
                <div>
                  <label className="block text-sm font-medium text-fg mb-1">客户</label>
                  <div className="relative">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted" />
                    <input
                      type="text"
                      value={customerQuery}
                      onChange={e => { setCustomerQuery(e.target.value); setCustomerName(e.target.value); }}
                      placeholder="搜索客户（输入名字，选已有或输入新名）"
                      className="w-full pl-9 pr-4 py-2 bg-white border border-border rounded-md text-sm text-fg placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-accent/20 focus:border-accent"
                    />
                  </div>
                  {customerSearching && <p className="text-xs text-muted mt-1">搜索中…</p>}
                  {Array.isArray(customerResults) && customerResults.length > 0 && (
                    <div className="mt-1 border border-border rounded-md bg-white max-h-36 overflow-y-auto">
                      {customerResults.map(c => (
                        <div
                          key={c.id}
                          className="px-3 py-2 hover:bg-accent-light cursor-pointer border-b border-border last:border-0"
                          onClick={() => { setCustomerName(c.name); setCustomerQuery(c.name); setCustomerResults([]); }}
                        >
                          <div className="text-sm font-medium">{c.name}</div>
                          {c.phone && <div className="text-xs text-muted">{c.phone}</div>}
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* Cigar search */}
                <div>
                  <label className="block text-sm font-medium text-fg mb-1">添加商品</label>
                  <div className="relative">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted" />
                    <input
                      type="text"
                      value={searchQ}
                      onChange={e => setSearchQ(e.target.value)}
                      placeholder="搜索雪茄（品牌+型号，中英文均可）"
                      className="w-full pl-9 pr-4 py-2 bg-white border border-border rounded-md text-sm text-fg placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-accent/20 focus:border-accent"
                    />
                  </div>
                  {searching && <p className="text-xs text-muted mt-1">搜索中…</p>}
                  {Array.isArray(searchResults) && searchResults.length > 0 && (
                    <div className="mt-1 border border-border rounded-md bg-white max-h-48 overflow-y-auto">
                      {searchResults.map(c => (
                        <div
                          key={c.id}
                          className="px-3 py-2 hover:bg-accent-light cursor-pointer border-b border-border last:border-0"
                          onClick={() => addPaymentItem(c)}
                        >
                          <div className="text-sm font-medium">{c.name}</div>
                          <div className="text-xs text-muted">
                            {c.brand} · {c.vitola} · 库存 {c.stock_qty} 支
                          </div>
                          {c.batches.length > 1 && (
                            <div className="flex gap-1 mt-1">
                              {c.batches.map(b => (
                                <button
                                  key={b.batch_id}
                                  type="button"
                                  onClick={ev => { ev.stopPropagation(); addPaymentItem(c, b.batch_id); }}
                                  className="text-[10px] px-1.5 py-0.5 rounded bg-accent/10 text-accent hover:bg-accent/20"
                                >
                                  {b.box_size}支/盒 · 余{b.remaining}
                                </button>
                              ))}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* Items list */}
                {Array.isArray(paymentItems) && paymentItems.length > 0 && (
                  <div className="space-y-2">
                    {paymentItems.map((item, idx) => (
                      <div
                        key={`${item.cigar_id}-${item.batch_id}`}
                        className="flex items-center gap-3 bg-accent-light rounded-md p-3"
                      >
                        <div className="w-10 h-10 rounded bg-white flex items-center justify-center shrink-0 overflow-hidden">
                          {item.thumb_url ? (
                            <img src={item.thumb_url} alt={item.name} className="w-full h-full object-contain p-0.5" />
                          ) : (
                            <Package className="w-4 h-4 text-muted" />
                          )}
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="text-sm font-medium truncate">{item.name}</div>
                          <div className="text-xs text-muted">{item.vitola} · {item.box_size}支/盒</div>
                        </div>
                        <div className="flex items-center gap-2">
                          <input
                            type="number"
                            min={1}
                            value={item.quantity}
                            onChange={e => updatePaymentItem(idx, 'quantity', parseInt(e.target.value) || 1)}
                            className="w-14 px-2 py-1 border border-border rounded text-sm text-center"
                          />
                          <span className="text-xs text-muted">× ¥</span>
                          <input
                            type="number"
                            min={0}
                            value={item.unit_price}
                            onChange={e => updatePaymentItem(idx, 'unit_price', parseInt(e.target.value) || 0)}
                            className="w-20 px-2 py-1 border border-border rounded text-sm text-right"
                          />
                        </div>
                        <button
                          type="button"
                          onClick={() => removePaymentItem(idx)}
                          className="p-1 text-muted hover:text-red-500"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    ))}
                    <div className="text-right text-sm font-medium text-fg">
                      商品合计：¥{paymentItems.reduce((sum, i) => sum + i.quantity * i.unit_price, 0)}
                    </div>
                  </div>
                )}

                {/* Extra fees */}
                <div>
                  <label className="block text-sm font-medium text-fg mb-2">额外费用</label>
                  <div className="space-y-2">
                    <label className="flex items-center gap-2">
                      <input type="checkbox" checked={useShipping} onChange={e => setUseShipping(e.target.checked)} className="checkbox checkbox-sm" />
                      <span className="text-sm">运费</span>
                      {useShipping && (
                        <input type="number" min={0} value={shippingAmount}
                          onChange={e => setShippingAmount(parseInt(e.target.value) || 0)}
                          className="w-20 px-2 py-0.5 border border-border rounded text-sm text-right" />
                      )}
                    </label>
                    <label className="flex items-center gap-2">
                      <input type="checkbox" checked={useCourier} onChange={e => setUseCourier(e.target.checked)} className="checkbox checkbox-sm" />
                      <span className="text-sm">人肉费</span>
                      {useCourier && (
                        <input type="number" min={0} value={courierAmount}
                          onChange={e => setCourierAmount(parseInt(e.target.value) || 0)}
                          className="w-20 px-2 py-0.5 border border-border rounded text-sm text-right" />
                      )}
                    </label>
                    {customFees.map((f, idx) => (
                      <div key={idx} className="flex items-center gap-2">
                        <input type="text" value={f.name}
                          onChange={e => updateCustomFee(idx, 'name', e.target.value)}
                          placeholder="费用名" className="flex-1 px-2 py-0.5 border border-border rounded text-sm" />
                        <input type="number" min={0} value={f.amount}
                          onChange={e => updateCustomFee(idx, 'amount', parseInt(e.target.value) || 0)}
                          placeholder="金额" className="w-20 px-2 py-0.5 border border-border rounded text-sm text-right" />
                        <button type="button" onClick={() => removeCustomFee(idx)} className="p-1 text-muted hover:text-red-500">
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    ))}
                    <button type="button" onClick={addCustomFee} className="text-xs text-accent hover:underline flex items-center gap-1">
                      <Plus className="w-3 h-3" /> 添加费用
                    </button>
                  </div>
                </div>

                {/* Payment method */}
                <div>
                  <label className="block text-sm font-medium text-fg mb-1">收款方式（可选）</label>
                  <select
                    value={paymentMethodId}
                    onChange={e => setPaymentMethodId(e.target.value)}
                    className="w-full px-3 py-2.5 bg-white border border-border rounded-md text-sm text-fg focus:outline-none focus:ring-2 focus:ring-accent/20 focus:border-accent"
                  >
                    <option value="">不选（手动填）</option>
                    {paymentMethods?.map(pm => (
                      <option key={pm.id} value={pm.id}>{pm.label}</option>
                    ))}
                  </select>
                </div>
              </div>
            )}

            {activeTab === 'message' && (
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-fg mb-1">消息内容</label>
                  <textarea
                    value={messageText}
                    onChange={e => setMessageText(e.target.value)}
                    rows={5}
                    placeholder="输入要发送的消息…"
                    className="w-full px-3 py-2.5 bg-white border border-border rounded-md text-sm text-fg placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-accent/20 focus:border-accent resize-none"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-fg mb-1">附件（可选）</label>
                  <div className="flex gap-2 mb-2">
                    <input
                      type="text"
                      value={attachName}
                      onChange={e => setAttachName(e.target.value)}
                      placeholder="附件名称"
                      className="flex-1 px-3 py-2 bg-white border border-border rounded-md text-sm text-fg placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-accent/20 focus:border-accent"
                    />
                    <input
                      type="text"
                      value={attachUrl}
                      onChange={e => setAttachUrl(e.target.value)}
                      placeholder="URL"
                      className="flex-[2] px-3 py-2 bg-white border border-border rounded-md text-sm text-fg placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-accent/20 focus:border-accent"
                    />
                    <button
                      type="button"
                      onClick={addAttachment}
                      className="px-3 py-2 bg-accent text-white rounded-md text-sm hover:bg-accent-hover"
                    >
                      <Plus className="w-4 h-4" />
                    </button>
                  </div>
                  {attachments.length > 0 && (
                    <div className="space-y-1">
                      {attachments.map((att, idx) => (
                        <div
                          key={idx}
                          className="flex items-center justify-between bg-accent-light rounded-md px-3 py-2"
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
                            className="p-1 text-muted hover:text-red-500"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>

          {/* Common Config */}
          <div className="bg-white border border-border rounded-md p-5 space-y-5">
            <div>
              <label className="flex items-center gap-1.5 text-sm font-medium text-fg mb-2">
                <Clock className="w-4 h-4" />
                有效期
              </label>
              <select
                value={duration}
                onChange={e => setDuration(e.target.value)}
                className="w-full px-3 py-2.5 bg-white border border-border rounded-md text-sm text-fg focus:outline-none focus:ring-2 focus:ring-accent/20 focus:border-accent"
              >
                {DURATIONS.map(d => (
                  <option key={d.value} value={d.value}>{d.label}</option>
                ))}
              </select>
            </div>

            <div>
              <label className="flex items-center gap-1.5 text-sm font-medium text-fg mb-2">
                <Lock className="w-4 h-4" />
                密码保护（可选）
              </label>
              <input
                type="text"
                value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder="留空则不设密码"
                className="w-full px-3 py-2.5 bg-white border border-border rounded-md text-sm text-fg placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-accent/20 focus:border-accent"
              />
            </div>

            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1.5">
                <Flame className="w-4 h-4 text-accent" />
                <span className="text-sm font-medium text-fg">阅后即焚</span>
              </div>
              <button
                type="button"
                onClick={() => setBurn(!burn)}
                className={`relative w-11 h-6 rounded-full transition-colors ${burn ? 'bg-accent' : 'bg-border'}`}
              >
                <span
                  className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full shadow transition-transform ${
                    burn ? 'translate-x-5' : 'translate-x-0'
                  }`}
                />
              </button>
            </div>
          </div>

          <button
            type="submit"
            disabled={loading || !canSubmit()}
            className="w-full py-2.5 bg-accent text-white rounded-md text-sm font-medium hover:bg-accent-hover active:scale-[0.98] transition-all disabled:opacity-50"
          >
            {loading ? '生成中…' : '生成链接'}
          </button>
        </form>
      )}
    </div>
  );
}
