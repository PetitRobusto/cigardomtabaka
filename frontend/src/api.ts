import axios from 'axios';
import type {
  PriceSnapshot, PriceHistoryResponse, Source, AggregatedCigar,
  BrandListResponse, BrandDetailResponse, CigarDetailResponse,
  InventoryResponse, PrivnoteResponse,
  PaymentMethod, SearchCigarResult, InventoryViewData,
  CustomerResult, QuoteProduct, RecentChangesResponse,
  SalesOrder, PaymentOrder, SalesOrderPayload, FundAccount, MonthlyProfitReport,
  AccountingSummary, AccountingDashboard, Reconciliation,
  Day1State,
} from './types';
import { writeWithIdempotency } from './api/idempotency';

function getCSRFToken(): string {
  const match = typeof document === 'undefined' ? null : document.cookie.match(/csrftoken=([^;]+)/);
  return match ? match[1] : '';
}

const api = axios.create({
  baseURL: '/api',
  headers: {
    'X-CSRFToken': getCSRFToken(),
  },
});

export function apiErrorMessage(error: unknown, fallback = '操作失败，请稍后重试'): string {
  if (axios.isAxiosError(error)) {
    const message = error.response?.data?.error;
    if (typeof message === 'string' && message) return message;
  }
  return error instanceof Error && error.message ? error.message : fallback;
}

// Price tracker APIs
export const fetchSources = (): Promise<Source[]> =>
  api.get('/prices/sources/').then(r => r.data.results || r.data);

export const fetchLatestPrices = (): Promise<PriceSnapshot[]> =>
  api.get('/prices/snapshots/latest/').then(r => r.data.results || r.data);

export const fetchPriceHistory = (cigarId: string, days = 30): Promise<PriceHistoryResponse> =>
  api.get('/prices/snapshots/history/', { params: { cigar_id: cigarId, days } }).then(r => r.data);

export const fetchAlerts = () => api.get('/prices/alerts/').then(r => r.data);
export const createAlert = (data: unknown) => api.post('/prices/alerts/', data).then(r => r.data);
export const updateAlert = (id: number, data: unknown) => api.patch(`/prices/alerts/${id}/`, data).then(r => r.data);
export const deleteAlert = (id: number) => api.delete(`/prices/alerts/${id}/`).then(r => r.data);

export const fetchAggregatedPrices = (params = {} as Record<string, string>): Promise<AggregatedCigar[]> =>
  api.get('/prices/snapshots/aggregated/', { params }).then(r => r.data || r.data.results);

export const fetchRecentChanges = (): Promise<RecentChangesResponse> =>
  api.get('/prices/snapshots/changes/').then(r => r.data);

// Catalog APIs
export const fetchBrandList = (): Promise<BrandListResponse> =>
  api.get('/brands/').then(r => r.data);

export const fetchBrandDetail = (slug: string): Promise<BrandDetailResponse> =>
  api.get(`/brands/${slug}/`).then(r => r.data);

export const fetchCigarDetail = (id: string | number): Promise<CigarDetailResponse> =>
  api.get(`/cigars/${id}/`).then(r => r.data);

// Inventory API
export const fetchInventory = (params?: { brand?: string; q?: string }): Promise<InventoryResponse> =>
  api.get('/inventory/', { params }).then(r => r.data);

// Sales order workflow APIs. Equivalent pending writes share an idempotency key.
export const fetchSalesOrders = (params?: { q?: string; fulfillment_status?: string; payment_status?: string; limit?: number }): Promise<SalesOrder[]> =>
  api.get('/sales/orders/', { params }).then(r => r.data.results || []);

export const fetchSalesOrder = (id: number): Promise<SalesOrder> =>
  api.get(`/sales/orders/${id}/`).then(r => r.data.sales_order);

export const createSalesOrder = (payload: SalesOrderPayload): Promise<SalesOrder> =>
  writeWithIdempotency('create-sales-order', payload, config =>
    api.post('/sales/orders/', payload, config),
  ).then(r => r.sales_order);

export const updateSalesOrder = (id: number, payload: SalesOrderPayload): Promise<SalesOrder> =>
  writeWithIdempotency(`update-sales-order-${id}`, payload, config =>
    api.patch(`/sales/orders/${id}/`, payload, config),
  ).then(r => r.sales_order);

const salesAction = (id: number, action: string, payload: Record<string, unknown> = {}): Promise<SalesOrder> =>
  writeWithIdempotency(`${action}-sales-order-${id}`, payload, config =>
    api.post(`/sales/orders/${id}/${action}/`, payload, config),
  ).then(r => r.sales_order);

export const confirmSalesOrder = (id: number): Promise<SalesOrder> => salesAction(id, 'confirm');
export const cancelSalesOrder = (id: number): Promise<SalesOrder> => salesAction(id, 'cancel');
export const shipSalesOrder = (id: number, business_date: string): Promise<SalesOrder> => salesAction(id, 'ship', { business_date });
export const receiveSalesOrder = (id: number, payload: { amount_cny: string; fund_account_id: number; business_date: string }): Promise<SalesOrder> => salesAction(id, 'receive', payload);
export const refundSalesOrder = (id: number, business_date: string): Promise<SalesOrder> => salesAction(id, 'refund', { business_date });
export const recordSalesTransportCost = (id: number, payload: { actual_cost_cny: string; fund_account_id: number; business_date: string }): Promise<SalesOrder> => salesAction(id, 'transport-cost', payload);

export const fetchAccountingDashboard = (): Promise<AccountingDashboard> =>
  api.get('/accounting/dashboard/').then(r => r.data);

export const fetchDay1State = (): Promise<Day1State> =>
  api.get('/accounting/day1/').then(r => r.data);

export function day1WriteHeaders(version: number, idempotencyKey?: string): Record<string, string> {
  const headers: Record<string, string> = { 'If-Match': String(version) };
  if (idempotencyKey) headers['Idempotency-Key'] = idempotencyKey;
  return headers;
}

export const saveDay1Draft = (payload: unknown, version: number): Promise<Day1State> =>
  api.put('/accounting/day1/draft/', payload, { headers: day1WriteHeaders(version) }).then(r => r.data);

export const confirmDay1 = (version: number, idempotencyKey: string): Promise<Day1State> =>
  api.post('/accounting/day1/confirm/', { version }, { headers: day1WriteHeaders(version, idempotencyKey) }).then(r => r.data);

export function day1ErrorMessage(error: unknown, fallback = 'Day 1 保存失败，请稍后重试'): string {
  if (axios.isAxiosError(error)) {
    if (error.response?.status === 409 && error.response.data?.code === 'version_conflict') return '另一位经营者已更新，请刷新';
    const message = error.response?.data?.error;
    if (typeof message === 'string' && message) return message;
  }
  return error instanceof Error && error.message ? error.message : fallback;
}

export function day1ValidationDetails(error: unknown): Record<string, string> {
  if (!axios.isAxiosError(error)) return {};
  const details = error.response?.data?.details;
  if (!details || typeof details !== 'object' || Array.isArray(details)) return {};
  return Object.fromEntries(Object.entries(details).map(([key, value]) => [
    key,
    Array.isArray(value) ? value.join('、') : String(value),
  ]));
}

export function clearDay1ValidationDetails(details: Record<string, string>, prefix: string): Record<string, string> {
  return Object.fromEntries(Object.entries(details).filter(([key]) => key !== prefix && !key.startsWith(prefix + '[') && !key.startsWith(prefix + '.')));
}

export const fetchAccountingAccounts = (): Promise<FundAccount[]> =>
  api.get('/accounting/accounts/').then(r => r.data.accounts || []);

export const fetchAccountingSummary = (asOf: string): Promise<AccountingSummary> =>
  api.get('/accounting/reports/summary/', { params: { as_of: asOf } }).then(r => r.data);

export const fetchMonthlyProfit = (month: string): Promise<MonthlyProfitReport> =>
  api.get('/accounting/reports/monthly-profit/', { params: { month } }).then(r => r.data);

export const fetchReconciliations = (): Promise<Reconciliation[]> =>
  api.get('/accounting/reconciliations/').then(r => r.data.reconciliations || []);

export const createReconciliation = (payload: { account_id: number; business_date: string; actual_amount: string; note: string }): Promise<Reconciliation> =>
  writeWithIdempotency('create-reconciliation', payload, config =>
    api.post('/accounting/reconciliations/', payload, config),
  ).then(r => r.reconciliation);

export const confirmReconciliation = (id: number): Promise<Reconciliation> =>
  writeWithIdempotency(`confirm-reconciliation-${id}`, {}, config =>
    api.post(`/accounting/reconciliations/${id}/confirm/`, {}, config),
  ).then(r => r.reconciliation);

// Privnote APIs
export const fetchPrivnote = (token: string): Promise<PrivnoteResponse> =>
  api.get(`/privnote/${token}/`).then(r => r.data);

export const verifyPrivnotePassword = (token: string, password: string): Promise<PrivnoteResponse> =>
  api.post(`/privnote/${token}/`, { password }).then(r => r.data);

export const createPrivnote = (data: FormData) =>
  fetch('/privnote/create/', {
    method: 'POST',
    body: data,
    credentials: 'same-origin',
    headers: { 'X-CSRFToken': getCSRFToken() },
  }).then(async r => {
    let body: { error?: string; [key: string]: unknown } = {};
    try {
      body = await r.json();
    } catch {
      if (!r.ok) throw new Error('私密链接创建失败，请稍后重试');
    }
    if (!r.ok) {
      const message = typeof body?.error === 'string' ? body.error : '私密链接创建失败';
      throw new Error(message);
    }
    return body;
  });

// ── Privnote upgrade APIs (NOT under /api/ prefix) ──

export const searchCigars = (q: string, stockOnly = false): Promise<SearchCigarResult[]> =>
  fetch(`/privnote/api/search-cigars/?q=${encodeURIComponent(q)}&stock_only=${stockOnly ? '1' : '0'}`, {
    credentials: 'same-origin',
    headers: { 'X-CSRFToken': getCSRFToken() },
  })
    .then(r => { if (!r.ok) throw new Error('雪茄搜索失败'); return r.json(); })
    .then(d => Array.isArray(d?.results) ? d.results : []);

export const fetchPaymentMethods = (): Promise<PaymentMethod[]> =>
  fetch('/privnote/api/payment-methods/', {
    credentials: 'same-origin',
    headers: { 'X-CSRFToken': getCSRFToken() },
  })
    .then(r => { if (!r.ok) throw new Error('收款方式加载失败'); return r.json(); })
    .then(d => Array.isArray(d?.methods) ? d.methods : []);

export const fetchEligiblePaymentOrders = (): Promise<PaymentOrder[]> =>
  fetch('/privnote/api/payment-orders/', {
    credentials: 'same-origin',
    headers: { 'X-CSRFToken': getCSRFToken() },
  })
    .then(r => { if (!r.ok) throw new Error('待收款销售单加载失败'); return r.json(); })
    .then(d => Array.isArray(d?.orders) ? d.orders : []);

export const previewInventoryPrivnote = (): Promise<{ preview: InventoryViewData }> =>
  fetch('/privnote/create/', {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'X-CSRFToken': getCSRFToken(), 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({ note_type: 'inventory', preview: '1' }),
  }).then(r => r.json());

export const searchCustomers = (q: string): Promise<CustomerResult[]> =>
  fetch(`/privnote/api/search-customers/?q=${encodeURIComponent(q)}`, {
    credentials: 'same-origin',
    headers: { 'X-CSRFToken': getCSRFToken() },
  })
    .then(r => r.json())
    .then(d => Array.isArray(d?.results) ? d.results : []);

export const fetchQuoteProducts = (): Promise<QuoteProduct[]> =>
  fetch('/privnote/api/quote-products/', {
    credentials: 'same-origin',
    headers: { 'X-CSRFToken': getCSRFToken() },
  })
    .then(r => r.json())
    .then(d => Array.isArray(d?.products) ? d.products : []);

export const uploadPrivnoteImage = (file: File): Promise<{ url: string; name: string }> => {
  const form = new FormData();
  form.append('image', file);
  return fetch('/privnote/api/upload-image/', {
    method: 'POST',
    body: form,
    credentials: 'same-origin',
    headers: { 'X-CSRFToken': getCSRFToken() },
  }).then(r => r.json());
};
export interface GuideSummary {
  version: number;
  auto_show_enabled: boolean;
  should_show: boolean;
  completed_version: number;
  force_show_next_time: boolean;
}

async function fetchGuideEndpoint(path: string, method: 'GET' | 'POST'): Promise<GuideSummary> {
  const response = await fetch(path, {
    method,
    credentials: 'same-origin',
    headers: { 'X-CSRFToken': getCSRFToken() },
  });
  let data: GuideSummary & { error?: string } = {} as GuideSummary & { error?: string };
  try {
    data = await response.json() as GuideSummary & { error?: string };
  } catch {
    throw new Error('引导状态加载失败');
  }
  if (!response.ok) throw new Error(data.error || '引导状态加载失败');
  return data;
}

export const fetchGuideStatus = (): Promise<GuideSummary> => fetchGuideEndpoint('/api/guides/status/', 'GET');
export const completeGuide = (): Promise<GuideSummary> => fetchGuideEndpoint('/api/guides/complete/', 'POST');
export const replayGuide = (): Promise<GuideSummary> => fetchGuideEndpoint('/api/guides/replay/', 'POST');
