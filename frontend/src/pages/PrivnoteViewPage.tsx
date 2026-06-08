import { useState } from 'react';
import { useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  Lock, Flame, AlertTriangle, Cigarette,
  Package, CreditCard, MessageSquare, User, Banknote,
  Building2, Phone, MessageCircle, MapPin, FileText
} from 'lucide-react';
import { fetchPrivnote, verifyPrivnotePassword } from '../api';
import { LoadingState } from '../components/shared/LoadingState';
import type { InventoryViewData, PaymentData, MessageData, QuoteData } from '../types';

/* ── Store Header ── */
function StoreHeader() {
  return (
    <div className="bg-accent text-white px-4 py-5 rounded-md mb-6">
      <h2 className="text-lg font-bold tracking-wide mb-2">
        莫斯科烟草之家<br />
        <span className="font-normal text-sm opacity-90">Москва Сигар дом табака</span>
      </h2>
      <div className="flex flex-wrap gap-x-5 gap-y-1.5 text-xs opacity-90">
        <span className="flex items-center gap-1">
          <MapPin className="w-3.5 h-3.5" />
          Москва, Молодёжная ул. 3
        </span>
        <span className="flex items-center gap-1">
          <Phone className="w-3.5 h-3.5" />
          +7 929 638-48-78
        </span>
        <span className="flex items-center gap-1">
          <MessageCircle className="w-3.5 h-3.5" />
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
  const [verifiedData, setVerifiedData] = useState<any>(null);

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

  if (isLoading) return <LoadingState text="加载中…" />;

  if (error || data?.error) {
    const reason = data?.reason || 'expired';
    return (
      <div className="min-h-screen flex items-center justify-center bg-cream px-4">
        <div className="text-center max-w-sm">
          <div className="w-16 h-16 rounded-full bg-red-100 flex items-center justify-center mx-auto mb-4">
            <AlertTriangle className="w-8 h-8 text-red-500" />
          </div>
          <h1 className="text-xl font-display font-semibold text-fg mb-2">
            {reason === 'viewed' ? '内容已销毁' : '链接已过期'}
          </h1>
          <p className="text-sm text-muted">
            {reason === 'viewed'
              ? '该内容已被查看并自动销毁。'
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
        <div className="w-full max-w-sm">
          <div className="flex flex-col items-center mb-6">
            <div className="w-12 h-12 rounded-full bg-accent/10 flex items-center justify-center mb-3">
              <Lock className="w-6 h-6 text-accent" />
            </div>
            <h1 className="text-lg font-display font-semibold text-fg">{displayData.title}</h1>
            <p className="text-sm text-muted mt-1">此内容受密码保护</p>
          </div>
          <form onSubmit={handlePasswordSubmit} className="space-y-3">
            <input
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              placeholder="输入密码"
              required
              className="w-full px-4 py-3 bg-white border border-border rounded-md text-sm text-fg placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-accent/20 focus:border-accent"
            />
            {passwordError && <div className="text-sm text-red-500">{passwordError}</div>}
            <button
              type="submit"
              className="w-full py-3 bg-accent text-white rounded-md text-sm font-medium hover:bg-accent-hover transition-colors"
            >
              查看内容
            </button>
          </form>
        </div>
      </div>
    );
  }

  const noteData = displayData?.data;
  const mode = noteData?.mode;

  return (
    <div className="min-h-screen bg-cream text-fg">
      <div className="max-w-3xl mx-auto px-4 py-8">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-2">
            {mode === 'inventory' && <Package className="w-5 h-5 text-accent" />}
            {mode === 'payment' && <CreditCard className="w-5 h-5 text-accent" />}
            {mode === 'message' && <MessageSquare className="w-5 h-5 text-accent" />}
            {mode === 'quote' && <FileText className="w-5 h-5 text-accent" />}
            <h1 className="text-xl font-display font-semibold">{displayData?.title}</h1>
          </div>
          <div className="flex items-center gap-3 text-xs text-muted">
            {displayData?.burn_after_read && (
              <span className="flex items-center gap-1">
                <Flame className="w-3.5 h-3.5" />
                阅后即焚
              </span>
            )}
          </div>
        </div>

        {/* Store info for payment & inventory & quote */}
        {(mode === 'payment' || mode === 'inventory' || mode === 'quote') && <StoreHeader />}

        {/* INVENTORY VIEW */}
        {mode === 'inventory' && noteData && <InventoryView data={noteData as InventoryViewData} />}

        {/* PAYMENT VIEW */}
        {mode === 'payment' && noteData && <PaymentView data={noteData as PaymentData} />}

        {/* MESSAGE VIEW */}
        {mode === 'message' && noteData && <MessageView data={noteData as MessageData} />}

        {/* QUOTE VIEW */}
        {mode === 'quote' && noteData && <QuoteView data={noteData as QuoteData} createdAt={displayData?.expires_at} />}
      </div>
    </div>
  );
}

function InventoryView({ data }: { data: InventoryViewData }) {
  return (
    <>
      {!data.empty && (
        <div className="grid grid-cols-3 gap-3 mb-6">
          <div className="bg-white border border-border rounded-md p-3 text-center">
            <div className="text-lg font-bold text-fg">{data.total_items}</div>
            <div className="text-xs text-muted">款式</div>
          </div>
          <div className="bg-white border border-border rounded-md p-3 text-center">
            <div className="text-lg font-bold text-fg">{data.total_boxes}</div>
            <div className="text-xs text-muted">整盒</div>
          </div>
          <div className="bg-white border border-border rounded-md p-3 text-center">
            <div className="text-lg font-bold text-fg">{data.total_loose}</div>
            <div className="text-xs text-muted">散支</div>
          </div>
        </div>
      )}

      {data.empty ? (
        <div className="text-center py-12 text-muted">暂无库存数据</div>
      ) : (
        <div className="space-y-6">
          {data.brand_groups.map(group => (
            <div key={group.brand}>
              <div className="flex items-center gap-3 mb-3">
                {group.logo_url && (
                  <img src={group.logo_url} alt={group.name} className="w-8 h-8 object-contain" />
                )}
                <h2 className="text-lg font-semibold">{group.name}</h2>
              </div>
              <div className="space-y-2">
                {group.items.map(item => (
                  <div
                    key={item.english_name}
                    className="bg-white border border-border rounded-md p-3 flex items-center gap-3"
                  >
                    <div className="w-12 h-12 rounded bg-cream flex items-center justify-center shrink-0 overflow-hidden">
                      {item.thumb_url ? (
                        <img src={item.thumb_url} alt={item.name} className="w-full h-full object-contain p-1" />
                      ) : (
                        <Cigarette className="w-5 h-5 text-border" />
                      )}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-medium">{item.name}</div>
                      <div className="text-xs text-muted">{item.vitola}</div>
                    </div>
                    <div className="text-right shrink-0">
                      <div className="text-sm font-medium">
                        {item.full_boxes > 0 && <span>{item.full_boxes} 盒</span>}
                        {item.loose > 0 && <span className="ml-2">{item.loose} 散支</span>}
                      </div>
                      <div className="text-xs text-muted">
                        ¥{item.box_price}/盒 · ¥{item.stick_price}/支
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </>
  );
}

function PaymentView({ data }: { data: PaymentData }) {
  const [zoomedQr, setZoomedQr] = useState<string | null>(null);

  return (
    <div className="space-y-6">
      {data.customer_name && (
        <div className="flex items-center gap-2 text-sm text-muted">
          <User className="w-4 h-4" />
          客户：{data.customer_name}
        </div>
      )}

      {/* Order items */}
      <div className="space-y-2">
        {data.items.map((item, idx) => (
          <div key={idx} className="bg-white border border-border rounded-md p-3 flex items-center gap-3">
            <div className="w-12 h-12 rounded bg-cream flex items-center justify-center shrink-0 overflow-hidden">
              {item.thumb_url ? (
                <img src={item.thumb_url} alt={item.name} className="w-full h-full object-contain p-1" />
              ) : (
                <Cigarette className="w-5 h-5 text-border" />
              )}
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-sm font-medium">{item.name}</div>
              <div className="text-xs text-muted">{item.vitola}</div>
            </div>
            <div className="text-right shrink-0">
              <div className="text-sm font-medium">{item.quantity} × ¥{item.unit_price}</div>
              <div className="text-xs text-muted">小计 ¥{item.subtotal}</div>
            </div>
          </div>
        ))}
      </div>

      {/* Total */}
      <div className="bg-white border border-border rounded-md p-4">
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm text-muted">商品合计</span>
          <span className="text-lg font-semibold text-fg">¥{data.total}</span>
        </div>

        {/* Extra fees */}
        {Array.isArray(data.extra_fees) && data.extra_fees.length > 0 && (
          <>
            <div className="border-t border-border my-2 pt-2 space-y-1">
              {data.extra_fees.map((fee, idx) => (
                <div key={idx} className="flex items-center justify-between text-sm">
                  <span className="text-muted">{fee.name}</span>
                  <span className="text-fg">¥{fee.amount}</span>
                </div>
              ))}
            </div>
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted">额外费用合计</span>
              <span className="text-fg">¥{data.extra_total}</span>
            </div>
            <div className="border-t border-border mt-2 pt-2 flex items-center justify-between">
              <span className="text-base font-semibold text-fg">总计</span>
              <span className="text-xl font-bold text-accent">¥{data.grand_total}</span>
            </div>
          </>
        )}

        {(!Array.isArray(data.extra_fees) || data.extra_fees.length === 0) && (
          <div className="border-t border-border mt-2 pt-2 flex items-center justify-between">
            <span className="text-base font-semibold text-fg">总计</span>
            <span className="text-xl font-bold text-accent">¥{data.total}</span>
          </div>
        )}
      </div>

      {/* Remark */}
      {data.remark && (
        <div className="bg-white border border-border rounded-md p-4">
          <div className="text-xs text-muted mb-2">备注</div>
          <div className="text-sm whitespace-pre-wrap leading-relaxed">{data.remark}</div>
        </div>
      )}

      {/* Payment methods */}
      {data.payment_methods.length > 0 && (
        <div className="space-y-3">
          <h3 className="text-sm font-medium text-muted flex items-center gap-2">
            <Banknote className="w-4 h-4" />
            收款方式
          </h3>
          {data.payment_methods.map((pm, idx) => (
            <div key={idx} className="bg-white border border-border rounded-md p-4 space-y-1">
              {pm.bank_name && <div className="text-sm text-muted">银行：{pm.bank_name}</div>}
              {pm.card_number && <div className="text-sm text-fg font-medium tracking-wide">{pm.card_number}</div>}
              {pm.card_holder && <div className="text-xs text-muted">持卡人：{pm.card_holder}</div>}
              {pm.qr_url && (
                <div className="mt-2">
                  <img
                    src={pm.qr_url}
                    alt="收款码"
                    className="w-40 h-40 object-contain rounded border border-border cursor-pointer hover:opacity-80 transition-opacity"
                    onClick={() => setZoomedQr(pm.qr_url!)}
                  />
                </div>
              )}
              {pm.remark && (
                <div className="mt-2 pt-2 border-t border-border text-sm text-fg whitespace-pre-wrap">{pm.remark}</div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* QR zoom overlay */}
      {zoomedQr && (
        <div
          className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4 cursor-pointer"
          onClick={() => setZoomedQr(null)}
        >
          <img src={zoomedQr} alt="收款码" className="max-w-full max-h-full object-contain rounded-lg shadow-2xl" />
        </div>
      )}
    </div>
  );
}

function QuoteView({ data, createdAt }: { data: QuoteData; createdAt?: string }) {
  const formatDate = (iso?: string) => {
    if (!iso) return '';
    const d = new Date(iso);
    return `${d.getFullYear()}年${d.getMonth() + 1}月${d.getDate()}日`;
  };

  return (
    <div className="space-y-6">
      {/* Quote Header */}
      <div className="text-center space-y-2">
        <div className="flex items-center justify-center gap-2">
          <div className="w-8 h-8 rounded-full bg-accent/10 flex items-center justify-center">
            <FileText className="w-4 h-4 text-accent" />
          </div>
          <span className="text-lg font-bold tracking-wide">CigarDomTabaka</span>
        </div>
        <h2 className="text-xl font-bold text-fg">批发报价单</h2>
        {createdAt && (
          <p className="text-xs text-muted">创建日期：{formatDate(createdAt)}</p>
        )}
        <p className="text-xs text-muted">本报价单有效期 7 天，价格以实际成交为准</p>
      </div>

      {/* Contact Strip */}
      <StoreHeader />

      {/* Quote Table */}
      <div className="space-y-4">
        {data.brand_groups.map(group => (
          <div key={group.brand}>
            {/* Brand header */}
            <div className="flex items-center gap-2 px-3 py-2 bg-accent/5 rounded-t-md border border-border border-b-0">
              {group.logo_url && (
                <img src={group.logo_url} alt={group.brand_cn} className="w-6 h-6 object-contain" />
              )}
              <span className="text-sm font-semibold">{group.brand_cn || group.brand}</span>
            </div>

            {/* Table */}
            <div className="border border-border rounded-b-md overflow-hidden">
              {/* Table header */}
              <div className="hidden md:grid grid-cols-12 gap-2 px-3 py-2 bg-accent-light text-xs font-medium text-muted border-b border-border">
                <div className="col-span-4">款式</div>
                <div className="col-span-2">中文名</div>
                <div className="col-span-2 text-right">支数/盒</div>
                <div className="col-span-2 text-right">批发价/盒</div>
                <div className="col-span-2 text-right">折算单价/支</div>
              </div>

              {group.items.map(item => (
                <div
                  key={`${item.cigar_id}-${item.box_size}`}
                  className="grid grid-cols-1 md:grid-cols-12 gap-2 px-3 py-3 border-b border-border last:border-0 items-center hover:bg-accent-light/50"
                >
                  {/* 款式 */}
                  <div className="md:col-span-4 flex items-center gap-2">
                    <div className="w-10 h-10 rounded bg-cream flex items-center justify-center shrink-0 overflow-hidden">
                      {item.thumb_url ? (
                        <img src={item.thumb_url} alt={item.name} className="w-full h-full object-contain p-0.5" />
                      ) : (
                        <Cigarette className="w-4 h-4 text-border" />
                      )}
                    </div>
                    <div className="min-w-0">
                      <div className="text-sm font-medium flex items-center gap-1">
                        {item.english_name}
                        {item.in_stock && (
                          <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-emerald-100 text-emerald-700">
                            现货
                          </span>
                        )}
                      </div>
                      <div className="text-xs text-muted md:hidden">{item.vitola}</div>
                    </div>
                  </div>

                  {/* 中文名 */}
                  <div className="md:col-span-2 text-sm">
                    <span className="md:hidden text-xs text-muted mr-1">中文名:</span>
                    {item.name}
                  </div>

                  {/* 支数/盒 */}
                  <div className="md:col-span-2 md:text-right text-sm">
                    <span className="md:hidden text-xs text-muted mr-1">支数/盒:</span>
                    {item.box_size}
                  </div>

                  {/* 批发价/盒 */}
                  <div className="md:col-span-2 md:text-right text-sm font-medium text-fg">
                    <span className="md:hidden text-xs text-muted mr-1">批发价/盒:</span>
                    ¥{item.wholesale_price.toLocaleString()}
                  </div>

                  {/* 折算单价/支 */}
                  <div className="md:col-span-2 md:text-right text-sm text-accent font-medium">
                    <span className="md:hidden text-xs text-muted mr-1">折算单价/支:</span>
                    ¥{item.per_stick_price}
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>

      {/* Summary */}
      <div className="bg-white border border-border rounded-md p-4 text-center">
        <span className="text-sm text-muted">共 {data.total_items} 款雪茄</span>
      </div>

      {/* Footer */}
      <div className="bg-white border border-border rounded-md p-4 space-y-2">
        <h3 className="text-sm font-semibold text-fg">订货须知</h3>
        <ul className="text-xs text-muted space-y-1 list-disc list-inside">
          <li>以上价格为人民币批发价，不含税费。</li>
          {data.shipping_included ? (
            <li>本报价已含运费，无需额外支付运输费用。</li>
          ) : (
            <li>运费另计，根据实际运输方式及目的地计算。</li>
          )}
          <li>现货商品可立即发货，预售商品需等待到货。</li>
          <li>订货请联系微信：cigardomtabaka 或电话：+7 929 638-48-78。</li>
        </ul>
        <div className="pt-2 border-t border-border text-center text-xs text-muted">
          &copy; {new Date().getFullYear()} CigarDomTabaka · 莫斯科烟草之家
        </div>
      </div>
    </div>
  );
}

function MessageView({ data }: { data: MessageData }) {
  return (
    <div className="space-y-4">
      <div className="bg-white border border-border rounded-md p-4 whitespace-pre-wrap text-sm leading-relaxed">
        {data.text}
      </div>
      {data.attachments.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-sm font-medium text-muted">附件</h3>
          {data.attachments.map((att, idx) => (
            <a
              key={idx}
              href={att.url}
              target="_blank"
              rel="noreferrer"
              className="block bg-white border border-border rounded-md p-3 text-sm text-accent hover:underline"
            >
              {att.name}
            </a>
          ))}
        </div>
      )}
    </div>
  );
}
