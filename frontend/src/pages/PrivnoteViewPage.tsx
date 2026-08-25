import { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  Flame, AlertTriangle, Cigarette,
  Package, CreditCard, MessageSquare, User,
  MapPin, Phone, MessageCircle, FileText
} from 'lucide-react';
import { fetchPrivnote, verifyPrivnotePassword } from '../api';
import { LoadingState } from '../components/shared/LoadingState';
import { usePageMeta } from '../hooks/usePageMeta';
import type { InventoryViewData, PaymentData, MessageData, QuoteData, PrivnoteResponse } from '../types';

const base = import.meta.env.BASE_URL;

/* ── Contact Strip ── */

/* ── Store Header (for payment/inventory/quote) ── */
function StoreHeader() {
  return (
    <div className="bg-accent-light border border-accent/20 rounded-sm px-5 py-5 mb-6 text-center">
      <img src={`${base}logo-512.png`} alt="CigarDomTabaka" className="w-[120px] h-[120px] mx-auto mb-3 object-contain" />
      <h2 className="text-lg font-bold tracking-wide text-fg mb-2">
        莫斯科烟草之家<br />
        <span className="font-normal text-sm text-muted">Москва Сигар дом табака</span>
      </h2>
      <div className="flex flex-wrap gap-x-5 gap-y-1.5 text-xs text-muted justify-center">
        <span className="flex items-center gap-1">
          <MapPin className="w-3.5 h-3.5 text-accent" />
          Москва, Молодёжная ул. 3
        </span>
        <span className="flex items-center gap-1">
          <Phone className="w-3.5 h-3.5 text-accent" />
          +7 929 638-48-78
        </span>
        <span className="flex items-center gap-1">
          <MessageCircle className="w-3.5 h-3.5 text-accent" />
          WeChat: cigardomtabaka
        </span>
      </div>
    </div>
  );
}

export default function PrivnoteViewPage() {
  const { token } = useParams<{ token: string }>();
  const [password, setPassword] = useState('');
  const [passwordError, setPasswordError] = useState('');
  const [verifiedData, setVerifiedData] = useState<PrivnoteResponse | null>(null);
  const [zoomedImage, setZoomedImage] = useState<string | null>(null);
  const { setMeta } = usePageMeta();

  const { data, isLoading, error } = useQuery({
    queryKey: ['privnote', token],
    queryFn: () => fetchPrivnote(token!),
    enabled: !!token,
    retry: false,
  });

  const handlePasswordSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setPasswordError('');
    try {
      const res = await verifyPrivnotePassword(token!, password);
      if (res.error) {
        setPasswordError(res.error);
      } else {
        setVerifiedData(res);
      }
    } catch {
      setPasswordError('验证失败');
    }
  };

  useEffect(() => {
    const displayData = verifiedData || data;
    if (displayData?.title) {
      setMeta({
        title: displayData.title,
        breadcrumbs: [
          { label: '首页', to: '/' },
          { label: displayData.title },
        ],
      });
    }
  }, [data, verifiedData, setMeta]);

  if (isLoading) return <LoadingState text="加载中…" />;

  if (error || data?.error) {
    const reason = data?.reason || 'expired';
    return (
      <div className="min-h-screen flex items-center justify-center bg-cream px-4">
        <div className="bg-white border border-border rounded-sm p-10 text-center w-full max-w-md">
          <div className="w-16 h-16 rounded-full bg-accent-light flex items-center justify-center mx-auto mb-6">
            <AlertTriangle className="w-8 h-8 text-accent" />
          </div>
          <h1 className="text-xl font-display font-semibold text-fg mb-3">
            {reason === 'viewed' ? '内容已销毁' : reason === 'closed' ? '收款单已关闭' : '链接已过期'}
          </h1>
          <p className="text-sm text-muted leading-relaxed">
            {reason === 'viewed'
              ? '该内容已被查看并自动销毁。'
              : reason === 'closed'
                ? '该订单已经完成收款或无法继续履约，此收款单已关闭。'
                : '该链接已超过有效期限。'}
          </p>
        </div>
      </div>
    );
  }

  const displayData = verifiedData || data;

  if (displayData?.requires_password && !verifiedData) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-cream px-4">
        <div className="bg-white border border-border rounded-sm p-10 text-center w-full max-w-md">
          <div className="flex items-center justify-center mx-auto mb-6 bg-accent-light">
            <img src={`${base}logo-512.png`} alt="CigarDomTabaka" className="w-[120px] h-[120px] object-contain" />
          </div>
          <h1 className="text-xl font-display font-semibold text-fg mb-2">{displayData.title}</h1>
          <p className="text-sm text-muted mb-8">此内容受密码保护</p>
          <form onSubmit={handlePasswordSubmit} className="space-y-4">
            <input
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              placeholder="输入密码"
              required
              className="w-full px-4 py-3 border border-border rounded-sm text-sm text-fg bg-white placeholder:text-border focus:outline-none focus:border-accent text-center tracking-widest"
            />
            {passwordError && <div className="text-sm text-accent">{passwordError}</div>}
            <button
              type="submit"
              className="w-full py-3 bg-accent text-white rounded-sm text-sm font-medium hover:bg-accent-hover transition-colors"
            >
              查看内容
            </button>
          </form>
          <p className="mt-5 text-xs text-muted">此私密链接已设置阅后即焚，关闭页面后将无法再次查看</p>
        </div>
      </div>
    );
  }

  const noteData = displayData?.data;
  const mode = noteData?.mode;
  const formatDate = (iso?: string) => {
    if (!iso) return '';
    const d = new Date(iso);
    return `${d.getFullYear()}年${d.getMonth() + 1}月${d.getDate()}日`;
  };

  return (
    <div className="min-h-screen bg-cream text-fg">
      {/* View Header */}
      <div className="bg-white border-b border-border px-6 py-5 mb-6">
        <div className="max-w-5xl mx-auto flex items-center justify-between gap-4 flex-wrap">
          <div>
            <div className="flex items-center gap-2 mb-1">
              {mode === 'inventory' && <Package className="w-5 h-5 text-accent" />}
              {mode === 'payment' && <CreditCard className="w-5 h-5 text-accent" />}
              {mode === 'message' && <MessageSquare className="w-5 h-5 text-accent" />}
              {mode === 'quote' && <FileText className="w-5 h-5 text-accent" />}
              <h1 className="text-xl font-display font-semibold">{displayData?.title}</h1>
            </div>
            <div className="text-sm text-muted">
              来自 Moscow Cigar{displayData?.created_at ? ` · ${formatDate(displayData.created_at)}` : ''}
            </div>
          </div>
          <div className="flex items-center gap-3">
            {displayData?.burn_after_read && (
              <span className="inline-flex items-center gap-1 px-3 py-1.5 bg-accent text-white rounded-full text-xs font-medium">
                <Flame className="w-3 h-3" />
                阅后即焚
              </span>
            )}
          </div>
        </div>
      </div>

      <div className="max-w-5xl mx-auto px-4 pb-10">
        {/* Store info for payment, inventory & quote */}
        {(mode === 'payment' || mode === 'inventory' || mode === 'quote') && <StoreHeader />}

        {/* INVENTORY VIEW */}
        {mode === 'inventory' && noteData && <InventoryView data={noteData as InventoryViewData} />}

        {/* PAYMENT VIEW */}
        {mode === 'payment' && noteData && <PaymentView data={noteData as PaymentData} onZoom={setZoomedImage} />}

        {/* MESSAGE VIEW */}
        {mode === 'message' && noteData && <MessageView data={noteData as MessageData} onZoom={setZoomedImage} />}

        {/* QUOTE VIEW */}
        {mode === 'quote' && noteData && <QuoteView data={noteData as QuoteData} createdAt={displayData?.created_at} expiresAt={displayData?.expires_at} onZoom={setZoomedImage} />}
      </div>

      {/* Image zoom overlay */}
      {zoomedImage && (
        <div
          className="fixed inset-0 z-50 bg-black/80 flex items-center justify-center p-4 cursor-pointer"
          onClick={() => setZoomedImage(null)}
        >
          <img src={zoomedImage} alt="图片预览" className="max-w-full max-h-[90vh] object-contain rounded-sm shadow-2xl" />
        </div>
      )}
    </div>
  );
}

function InventoryView({ data }: { data: InventoryViewData }) {
  if (data.empty) {
    return <div className="text-center py-12 text-muted">暂无库存数据</div>;
  }

  return (
    <div className="space-y-5">
      {data.brand_groups.map(group => (
        <div key={group.brand} className="bg-white border border-border rounded-sm overflow-hidden">
          <div className="px-5 py-4 border-b border-border flex items-center justify-between">
            <span className="text-xs text-muted uppercase tracking-wider font-medium">{group.name}</span>
            <span className="text-sm text-muted">{group.items.length} 款</span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr className="bg-accent-light">
                  <th className="px-4 py-3 text-left text-xs text-muted uppercase tracking-wider font-medium">雪茄</th>
                  <th className="px-4 py-3 text-left text-xs text-muted uppercase tracking-wider font-medium">型号</th>
                  <th className="px-4 py-3 text-right text-xs text-muted uppercase tracking-wider font-medium">盒装</th>
                  <th className="px-4 py-3 text-right text-xs text-muted uppercase tracking-wider font-medium">散支</th>
                  <th className="px-4 py-3 text-right text-xs text-muted uppercase tracking-wider font-medium">盒价</th>
                  <th className="px-4 py-3 text-right text-xs text-muted uppercase tracking-wider font-medium">支价</th>
                </tr>
              </thead>
              <tbody>
                {group.items.map(item => (
                  <tr key={item.english_name} className="border-b border-border hover:bg-accent-light/30">
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-sm bg-accent-light flex items-center justify-center shrink-0 overflow-hidden">
                          {item.thumb_url ? (
                            <img src={item.thumb_url} alt={item.name} className="w-full h-full object-contain p-0.5" />
                          ) : (
                            <Cigarette className="w-4 h-4 text-border" />
                          )}
                        </div>
                        <span className="font-medium">{item.name}</span>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-muted">{item.vitola}</td>
                    <td className="px-4 py-3 text-right font-mono">{item.full_boxes}</td>
                    <td className="px-4 py-3 text-right font-mono">{item.loose}</td>
                    <td className="px-4 py-3 text-right font-mono">¥{item.box_price.toLocaleString()}</td>
                    <td className="px-4 py-3 text-right font-mono">¥{item.stick_price.toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ))}
      <div className="text-center py-6 text-muted text-xs">
        共 {data.brand_groups.length} 个品牌 · {data.total_items} 款雪茄 · 数据更新于实时库存
      </div>
    </div>
  );
}

function PaymentView({ data, onZoom }: { data: PaymentData; onZoom: (url: string) => void }) {
  const [zoomedQr, setZoomedQr] = useState<string | null>(null);

  return (
    <div className="space-y-5">
      {data.customer_name && (
        <div className="inline-flex items-center gap-2 px-4 py-2 bg-accent-light rounded-full text-sm font-medium">
          <User className="w-4 h-4 text-muted" />
          客户：{data.customer_name}
        </div>
      )}

      {/* Order items */}
      <div className="bg-white border border-border rounded-sm overflow-hidden">
        <div className="px-5 py-4 border-b border-border flex items-center justify-between">
          <span className="text-xs text-muted uppercase tracking-wider font-medium">订单商品</span>
          <span className="text-sm text-muted">{data.items.length} 项</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="bg-accent-light">
                <th className="px-4 py-3 text-left text-xs text-muted uppercase tracking-wider font-medium">雪茄</th>
                <th className="px-4 py-3 text-left text-xs text-muted uppercase tracking-wider font-medium">型号</th>
                <th className="px-4 py-3 text-right text-xs text-muted uppercase tracking-wider font-medium">数量</th>
                <th className="px-4 py-3 text-right text-xs text-muted uppercase tracking-wider font-medium">单价</th>
                <th className="px-4 py-3 text-right text-xs text-muted uppercase tracking-wider font-medium">小计</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((item, idx) => (
                <tr key={idx} className="border-b border-border hover:bg-accent-light/30">
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-sm bg-accent-light flex items-center justify-center shrink-0 overflow-hidden">
                        {item.thumb_url ? (
                          <img src={item.thumb_url} alt={item.name} className="w-full h-full object-contain p-0.5" />
                        ) : (
                          <Cigarette className="w-4 h-4 text-border" />
                        )}
                      </div>
                      <span className="font-medium">{item.name}</span>
                    </div>
                  </td>
                  <td className="px-4 py-3 text-muted">{item.vitola}</td>
                  <td className="px-4 py-3 text-right font-mono">{item.quantity}</td>
                  <td className="px-4 py-3 text-right font-mono">¥{item.unit_price.toLocaleString()}</td>
                  <td className="px-4 py-3 text-right font-mono font-semibold">¥{item.subtotal.toLocaleString()}</td>
                </tr>
              ))}
              <tr className="bg-accent-light font-semibold">
                <td colSpan={4} className="px-4 py-3 text-right text-sm text-muted">合计</td>
                <td className="px-4 py-3 text-right font-display text-lg text-accent">¥{data.total.toLocaleString()}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      {/* Total with extra fees */}
      {(Array.isArray(data.extra_fees) && data.extra_fees.length > 0) && (
        <div className="bg-white border border-border rounded-sm p-5 space-y-2">
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted">商品合计</span>
            <span className="font-semibold">¥{data.total.toLocaleString()}</span>
          </div>
          <div className="border-t border-border pt-2 space-y-1.5">
            {data.extra_fees.map((fee, idx) => (
              <div key={idx} className="flex items-center justify-between text-sm">
                <span className="text-muted">{fee.name}</span>
                <span>¥{fee.amount.toLocaleString()}</span>
              </div>
            ))}
          </div>
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted">额外费用合计</span>
            <span>¥{data.extra_total.toLocaleString()}</span>
          </div>
          <div className="border-t border-border pt-2 flex items-center justify-between">
            <span className="text-base font-semibold">总计</span>
            <span className="text-2xl font-display font-bold text-accent">¥{data.grand_total.toLocaleString()}</span>
          </div>
        </div>
      )}

      {/* Remark */}
      {data.remark && (
        <div className="bg-white border border-border rounded-sm p-5">
          <div className="text-xs text-muted uppercase tracking-wider font-medium mb-3">备注</div>
          <div className="text-sm whitespace-pre-wrap leading-relaxed">{data.remark}</div>
        </div>
      )}

      {/* Remark Images */}
      {Array.isArray(data.images) && data.images.length > 0 && (
        <div className="bg-white border border-border rounded-sm p-5">
          <div className="text-xs text-muted uppercase tracking-wider font-medium mb-3">备注图片</div>
          <div className="grid grid-cols-4 gap-3">
            {data.images.map((img, idx) => (
              <div
                key={idx}
                className="aspect-square rounded-sm overflow-hidden cursor-pointer border border-border bg-accent-light hover:opacity-80 transition-opacity"
                onClick={() => onZoom(img.url)}
              >
                <img src={img.url} alt={img.name} className="w-full h-full object-cover" />
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Payment methods */}
      {data.payment_methods.length > 0 && (
        <div className="bg-white border border-border rounded-sm overflow-hidden">
          <div className="px-5 py-4 border-b border-border">
            <span className="text-xs text-muted uppercase tracking-wider font-medium">收款方式</span>
          </div>
          <div className="p-5 space-y-3">
            {data.payment_methods.map((pm, idx) => (
              <div key={idx} className="bg-white border border-border rounded-sm p-5 flex items-center gap-4 hover:shadow-md transition-shadow">
                <div className="w-12 h-12 rounded-sm bg-accent-light flex items-center justify-center shrink-0 font-display text-lg font-semibold text-accent">
                  {pm.method_type === 'bank_card' ? '银' : pm.method_type === 'wechat' ? '微' : '支'}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-semibold">{pm.label || pm.bank_name || '收款方式'}</div>
                  <div className="text-xs text-muted mt-0.5">
                    {pm.card_number && <span>卡号 {pm.card_number}</span>}
                    {pm.card_holder && <span> · 持卡人 {pm.card_holder}</span>}
                    {pm.remark && <div className="mt-1 whitespace-pre-wrap">{pm.remark}</div>}
                  </div>
                </div>
                {pm.qr_url && (
                  <div
                    className="w-20 h-20 rounded-sm bg-accent-light flex items-center justify-center shrink-0 overflow-hidden cursor-pointer hover:opacity-80 transition-opacity"
                    onClick={() => setZoomedQr(pm.qr_url!)}
                  >
                    <img src={pm.qr_url} alt="收款码" className="w-full h-full object-contain" />
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* QR zoom overlay */}
      {zoomedQr && (
        <div
          className="fixed inset-0 z-50 bg-black/80 flex items-center justify-center p-4 cursor-pointer"
          onClick={() => setZoomedQr(null)}
        >
          <img src={zoomedQr} alt="收款码" className="max-w-full max-h-[90vh] object-contain rounded-sm shadow-2xl" />
        </div>
      )}

      <div className="text-center py-6 text-muted text-xs">
        此私密链接已设置阅后即焚，关闭页面后将无法再次查看
      </div>
    </div>
  );
}

function QuoteView({ data, createdAt, expiresAt, onZoom }: { data: QuoteData; createdAt?: string; expiresAt?: string; onZoom?: (url: string) => void }) {
  const formatDate = (iso?: string) => {
    if (!iso) return '';
    const d = new Date(iso);
    return `${d.getFullYear()}年${d.getMonth() + 1}月${d.getDate()}日`;
  };

  const formatDateTime = (iso?: string) => {
    if (!iso) return '';
    const d = new Date(iso);
    return `${d.getFullYear()}年${d.getMonth() + 1}月${d.getDate()}日 ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
  };

  return (
    <div className="space-y-5">
      {/* Quote Header */}
      <div className="bg-white border border-border rounded-sm p-6">
        <div className="flex items-start justify-between gap-6 flex-wrap">
          <div>
            <div className="font-display text-2xl font-semibold">批发报价单</div>
            {data.shipping_included && data.shipping_fee_per_stick ? (
              <div className="text-sm text-emerald-700 mt-1.5">
                价格已包含运费，每支加¥{data.shipping_fee_per_stick}
              </div>
            ) : (
              <div className="text-sm text-muted mt-1.5">价格不含运费，运费另行计算</div>
            )}
            <div className="text-sm text-muted mt-1">{formatDate(createdAt)}</div>
            {expiresAt && (
              <div className="inline-block mt-2 px-3 py-1 bg-accent-light rounded-sm text-xs text-muted">
                有效期至 {formatDateTime(expiresAt)}
              </div>
            )}
          </div>
        </div>
      </div>

      {data.customer_name && (
        <div className="inline-flex items-center gap-2 px-4 py-2 bg-accent-light rounded-full text-sm font-medium">
          <User className="w-4 h-4 text-muted" />
          客户：{data.customer_name}
        </div>
      )}

      {/* Quote Table — Desktop */}
      <div className="bg-white border border-border rounded-sm overflow-hidden hidden md:block">
        <div className="px-5 py-4 border-b border-border flex items-center justify-between">
          <span className="text-xs text-muted uppercase tracking-wider font-medium">全部产品报价</span>
          <span className="text-sm text-muted">单位：人民币 ¥</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="bg-accent-light">
                <th className="px-4 py-3 text-left text-xs text-muted uppercase tracking-wider font-medium w-[36%]">款式</th>
                <th className="px-4 py-3 text-left text-xs text-muted uppercase tracking-wider font-medium w-[24%]">中文名</th>
                <th className="px-4 py-3 text-center text-xs text-muted uppercase tracking-wider font-medium w-[10%]">支数/盒</th>
                <th className="px-4 py-3 text-right text-xs text-muted uppercase tracking-wider font-medium w-[15%]">批发价/盒</th>
                <th className="px-4 py-3 text-right text-xs text-muted uppercase tracking-wider font-medium w-[15%]">折算单价/支</th>
              </tr>
            </thead>
            <tbody>
              {data.brand_groups.map(group => (
                <>
                  <tr key={group.brand} className="bg-accent-light/60">
                    <td colSpan={5} className="px-4 py-2">
                      <div className="flex items-center gap-2">
                        {group.logo_url && (
                          <img src={group.logo_url} alt={group.brand} className="w-7 h-7 object-contain" />
                        )}
                        <span className="text-sm font-semibold text-fg">{group.brand_cn || group.brand}</span>
                      </div>
                    </td>
                  </tr>
                  {group.items.map(item => (
                    <tr key={`${item.cigar_id}-${item.box_size}`} className="border-b border-border hover:bg-accent-light/30">
                      <td className="px-4 py-3">
                        <div className="space-y-2">
                          <div className="flex items-center gap-2">
                            <span className="font-medium">{item.english_name}</span>
                            {item.in_stock && (
                              <span className="inline-flex items-center gap-1 text-[10px] font-semibold text-accent bg-accent-light px-2 py-0.5 rounded-full">
                                <svg viewBox="0 0 24 24" className="w-2.5 h-2.5" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
                                现货
                              </span>
                            )}
                          </div>
                          <div className="text-xs text-muted font-display italic">{item.vitola}</div>
                          <div
                            className="rounded-sm bg-accent-light inline-block shrink-0 cursor-pointer hover:opacity-80 transition-opacity"
                            onClick={() => item.thumb_url && onZoom?.(item.thumb_url)}
                          >
                            {item.thumb_url ? (
                              <img src={item.thumb_url} alt={item.name} className="h-12 inline-block w-auto object-contain p-1" />
                            ) : (
                              <div className="h-12 flex items-center px-3">
                                <Cigarette className="w-5 h-5 text-border" />
                              </div>
                            )}
                          </div>
                        </div>
                      </td>
                      <td className="px-4 py-3">{item.name}</td>
                      <td className="px-4 py-3 text-center font-mono">{item.box_size}</td>
                      <td className="px-4 py-3 text-right font-mono font-medium">¥{item.wholesale_price.toLocaleString()}</td>
                      <td className="px-4 py-3 text-right font-mono text-gold">¥{item.per_stick_price.toLocaleString()}</td>
                    </tr>
                  ))}
                </>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Quote Cards — Mobile */}
      <div className="md:hidden space-y-4">
        {data.brand_groups.map(group => (
          <div key={group.brand} className="bg-white border border-border rounded-sm overflow-hidden">
            <div className="px-4 py-3 bg-accent-light border-b border-border">
              <div className="flex items-center gap-2">
                {group.logo_url && (
                  <img src={group.logo_url} alt={group.brand} className="w-7 h-7 object-contain" />
                )}
                <span className="font-semibold text-fg">{group.brand_cn || group.brand}</span>
              </div>
              <div className="text-xs text-muted mt-0.5">{group.brand}</div>
            </div>
            <div>
              {group.items.map(item => (
                <div key={`${item.cigar_id}-${item.box_size}`} className="border-b border-border last:border-0 py-3 px-4">
                  <div className="flex justify-between items-start gap-2">
                    <span className="font-medium break-words max-w-[70%]">{item.name}</span>
                    {item.in_stock && (
                      <span className="inline-flex items-center gap-1 text-[10px] font-semibold text-accent bg-accent-light px-2 py-0.5 rounded-full shrink-0">
                        <svg viewBox="0 0 24 24" className="w-2.5 h-2.5" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
                        现货
                      </span>
                    )}
                  </div>
                  <div className="text-xs text-muted mt-0.5">
                    {item.english_name} · {item.vitola}
                  </div>
                  <div className="flex justify-between items-baseline mt-2">
                    <span className="text-xs text-muted">{item.box_size}支/盒</span>
                    <div className="text-right">
                      <span className="text-lg font-mono text-accent">¥{item.wholesale_price.toLocaleString()}</span>
                      <span className="text-xs text-gold ml-1.5">~¥{item.per_stick_price.toLocaleString()}/支</span>
                    </div>
                  </div>
                  {/* Cigar Image */}
                  <div
                    className="mt-2 rounded-sm bg-accent-light cursor-pointer hover:opacity-80 transition-opacity inline-block"
                    onClick={() => item.thumb_url && onZoom?.(item.thumb_url)}
                  >
                    {item.thumb_url ? (
                      <img src={item.thumb_url} alt={item.name} className="!h-12 !inline-block w-auto object-contain p-1" />
                    ) : (
                      <div className="h-20 flex items-center px-3">
                        <Cigarette className="w-6 h-6 text-border" />
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>

      {/* Summary */}
      <div className="bg-white border border-border rounded-sm p-5 text-center">
        <span className="text-sm text-muted">共 {data.total_items} 款雪茄</span>
      </div>

      {/* Footer Note */}
      <div className="bg-white border border-border rounded-sm p-6">
        <div className="text-xs text-muted uppercase tracking-wider font-medium mb-4">订货须知</div>
        <div className="text-sm text-fg leading-relaxed space-y-2">
          <p>1. 以上价格为批发价，货币单位为人民币（CNY）。</p>
          <p>2. 价格可能因市场波动而调整，请以实际下单时价格为准。</p>
          <p>{data.shipping_included ? '3. 以上价格已包含运费，无需额外支付。' : '3. 运费根据订单金额和目的地另行计算，具体请联系确认。'}</p>
          <p>4. 欢迎通过 Telegram、WhatsApp 或微信咨询详情与下单。</p>
        </div>
      </div>

      <div className="text-center py-5 text-muted text-xs border-t border-border">
        CigarDomTabaka · Москва, Молодёжная ул. 3 · +7 929 638-48-78 · WeChat: cigardomtabaka
      </div>
    </div>
  );
}

function MessageView({ data, onZoom }: { data: MessageData; onZoom: (url: string) => void }) {
  return (
    <div className="max-w-3xl mx-auto space-y-5">
      <div className="bg-white border border-border rounded-sm p-8 text-[15px] leading-relaxed whitespace-pre-wrap">
        {data.text}
      </div>

      {data.attachments.length > 0 && (
        <div className="bg-white border border-border rounded-sm p-5">
          <div className="text-xs text-muted uppercase tracking-wider font-medium mb-3">附件</div>
          <div className="space-y-2">
            {data.attachments.map((att, idx) => (
              <a
                key={idx}
                href={att.url}
                target="_blank"
                rel="noreferrer"
                className="block px-4 py-3 border border-border rounded-sm text-sm text-accent hover:bg-accent-light transition-colors"
              >
                {att.name}
              </a>
            ))}
          </div>
        </div>
      )}

      {Array.isArray(data.images) && data.images.length > 0 && (
        <div>
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs text-muted uppercase tracking-wider font-medium">附件图片</span>
            <span className="text-xs text-muted">{data.images.length} 张</span>
          </div>
          <div className="grid grid-cols-4 gap-3">
            {data.images.map((img, idx) => (
              <div
                key={idx}
                className="aspect-square rounded-sm overflow-hidden cursor-pointer border border-border bg-accent-light hover:opacity-80 transition-opacity"
                onClick={() => onZoom(img.url)}
              >
                <img src={img.url} alt={img.name} className="w-full h-full object-cover" />
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="text-center py-6 text-muted text-xs border-t border-border">
        此私密链接已设置阅后即焚，关闭页面后将无法再次查看
      </div>
    </div>
  );
}
