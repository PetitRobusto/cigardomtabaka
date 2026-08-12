import axios from 'axios';
import type {
  PriceSnapshot, PriceHistoryResponse, Source, AggregatedCigar,
  BrandListResponse, BrandDetailResponse, CigarDetailResponse,
  InventoryResponse, PrivnoteResponse,
  PaymentMethod, SearchCigarResult, InventoryViewData,
  CustomerResult, QuoteProduct, RecentChangesResponse,
  SalesOrder, SalesOrderPayload, FundAccount, MonthlyProfitReport,
  AccountingSummary, Reconciliation,
} from './types';
import { writeWithIdempotency } from './api/idempotency';

function getCSRFToken(): string {
  const match = document.cookie.match(/csrftoken=([^;]+)/);
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
  }).then(r => r.json());

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
