import axios from 'axios';
import type {
  PriceSnapshot, PriceHistoryResponse, Source, AlertItem, CigarListItem,
  BrandListResponse, BrandDetailResponse, CigarDetailResponse,
  InventoryResponse, PrivnoteResponse,
  PaymentMethod, SearchCigarResult, InventoryViewData,
  CustomerResult, QuoteProduct, RecentChangesResponse,
  SalesOrder, PaymentOrder, SalesOrderPayload, FundAccount, MonthlyProfitReport,
  AccountingSummary, AccountingDashboard, Reconciliation,
  Day1State,
} from './types';
import { writeWithIdempotency } from './api/idempotency';

import type { AccountingActionsResponse, PurchaseAction, PurchaseActionCreatePayload, PurchaseActionUpdatePayload, PurchasePayPayload, PurchaseReceivePayload, PurchaseCancelPayload, ExpenseActionPayload, DividendAction, DividendPreview, DividendCreatePayload, DividendUpdatePayload, DividendConfirmPayload, AccountingApiError } from './types';
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

// DRF 列表可能直接返回数组，也可能包装在 results 中；其他形状安全降级为空数组。
function unwrapResults<T>(value: unknown): T[] {
  if (Array.isArray(value)) return value as T[];
  if (!value || typeof value !== 'object' || !('results' in value)) return [];
  const results = value.results;
  return Array.isArray(results) ? results as T[] : [];
}

// Price tracker APIs
export const fetchSources = (): Promise<Source[]> =>
  api.get<unknown>('/prices/sources/').then(r => unwrapResults<Source>(r.data));

export const fetchLatestPrices = (): Promise<PriceSnapshot[]> =>
  api.get<unknown>('/prices/snapshots/latest/').then(r => unwrapResults<PriceSnapshot>(r.data));

export const fetchPriceHistory = (cigarId: string, days = 30): Promise<PriceHistoryResponse> =>
  api.get<PriceHistoryResponse>('/prices/snapshots/history/', { params: { cigar_id: cigarId, days } }).then(r => r.data);

export const fetchAlerts = (): Promise<AlertItem[]> =>
  api.get<unknown>('/prices/alerts/').then(r => unwrapResults<AlertItem>(r.data));
export const createAlert = (data: unknown) => api.post('/prices/alerts/', data).then(r => r.data);
export const updateAlert = (id: number, data: unknown) => api.patch(`/prices/alerts/${id}/`, data).then(r => r.data);
export const deleteAlert = (id: number) => api.delete(`/prices/alerts/${id}/`).then(r => r.data);

export const fetchAggregatedPrices = (params = {} as Record<string, string>): Promise<CigarListItem[]> =>
  api.get<unknown>('/prices/snapshots/list/', { params }).then(r => unwrapResults<CigarListItem>(r.data));

export const fetchRecentChanges = (): Promise<RecentChangesResponse> =>
  api.get<RecentChangesResponse>('/prices/snapshots/changes/').then(r => r.data);

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
  writeWithIdempotency<{ sales_order: SalesOrder }>('create-sales-order', payload, config =>
    api.post('/sales/orders/', payload, config),
  ).then(r => r.sales_order);

export const updateSalesOrder = (id: number, payload: SalesOrderPayload): Promise<SalesOrder> =>
  writeWithIdempotency<{ sales_order: SalesOrder }>(`update-sales-order-${id}`, payload, config =>
    api.patch(`/sales/orders/${id}/`, payload, config),
  ).then(r => r.sales_order);

const salesAction = (id: number, action: string, payload: Record<string, unknown> = {}): Promise<SalesOrder> =>
  writeWithIdempotency<{ sales_order: SalesOrder }>(`${action}-sales-order-${id}`, payload, config =>
    api.post(`/sales/orders/${id}/${action}/`, payload, config),
  ).then(r => r.sales_order);

export const confirmSalesOrder = (id: number): Promise<SalesOrder> => salesAction(id, 'confirm');
export const cancelSalesOrder = (id: number): Promise<SalesOrder> => salesAction(id, 'cancel');
export const shipSalesOrder = (id: number, business_date: string): Promise<SalesOrder> => salesAction(id, 'ship', { business_date });
export const receiveSalesOrder = (id: number, payload: { amount_cny: string; fund_account_id: number; business_date: string }): Promise<SalesOrder> => salesAction(id, 'receive', payload);
export const refundSalesOrder = (id: number, business_date: string): Promise<SalesOrder> => salesAction(id, 'refund', { business_date });
export const recordSalesTransportCost = (id: number, payload: { actual_cost_cny: string; fund_account_id: number; business_date: string }): Promise<SalesOrder> => salesAction(id, 'transport-cost', payload);
export const returnSalesOrder = (id: number, payload: { business_date: string; reason: string }): Promise<SalesOrder> => salesAction(id, 'return', payload);

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


export const createAccountingAccount = (payload: { name: string; currency: string }): Promise<FundAccount> =>
  writeWithIdempotency<{ account: FundAccount }>('create-account', payload, config =>
    api.post('/accounting/accounts/', payload, config),
  ).then(r => r.account);

export const updateAccountingAccount = (id: number, payload: { name?: string; is_active?: boolean }): Promise<FundAccount> =>
  writeWithIdempotency<{ account: FundAccount }>(`update-account-${id}`, payload, config =>
    api.patch(`/accounting/accounts/${id}/`, payload, config),
  ).then(r => r.account);
export const fetchAccountingSummary = (asOf: string): Promise<AccountingSummary> =>
  api.get('/accounting/reports/summary/', { params: { as_of: asOf } }).then(r => r.data);

export const fetchMonthlyProfit = (month: string): Promise<MonthlyProfitReport> =>
  api.get('/accounting/reports/monthly-profit/', { params: { month } }).then(r => r.data);

export const fetchReconciliations = (): Promise<Reconciliation[]> =>
  api.get('/accounting/reconciliations/').then(r => r.data.reconciliations || []);

export const createReconciliation = (payload: { account_id: number; business_date: string; actual_amount: string; note: string }): Promise<Reconciliation> =>
  writeWithIdempotency<{ reconciliation: Reconciliation }>('create-reconciliation', payload, config =>
    api.post('/accounting/reconciliations/', payload, config),
  ).then(r => r.reconciliation);

export const confirmReconciliation = (id: number): Promise<Reconciliation> =>
  writeWithIdempotency<{ reconciliation: Reconciliation }>(`confirm-reconciliation-${id}`, {}, config =>
    api.post(`/accounting/reconciliations/${id}/confirm/`, {}, config),
  ).then(r => r.reconciliation);

// Accounting action helpers.
export const fetchAccountingActions = (): Promise<AccountingActionsResponse> =>
  api.get('/accounting/actions/').then(r => r.data);

export const exchangeToRub = (payload: {
  source_account_id: number;
  rub_account_id: number;
  source_amount: string;
  rub_amount: string;
  business_date: string;
}): Promise<unknown> =>
  writeWithIdempotency<{ transaction: unknown }>('exchange-to-rub', payload, config =>
    api.post('/accounting/exchanges/', payload, config),
  ).then(r => r.transaction);

export const createPurchaseOrder = (payload: PurchaseActionCreatePayload): Promise<PurchaseAction> =>
  writeWithIdempotency<{ purchase_order: PurchaseAction }>('create-purchase-order', payload, config =>
    api.post('/accounting/purchases/', payload, config),
  ).then(r => r.purchase_order);

export const updatePurchaseOrder = (id: number, payload: PurchaseActionUpdatePayload): Promise<PurchaseAction> =>
  writeWithIdempotency<{ purchase_order: PurchaseAction }>(`update-purchase-order-${id}`, payload, config =>
    api.patch(`/accounting/purchases/${id}/`, payload, config),
  ).then(r => r.purchase_order);

export const payPurchaseOrder = (id: number, payload: PurchasePayPayload): Promise<PurchaseAction> =>
  writeWithIdempotency<{ purchase_order: PurchaseAction }>(`pay-purchase-order-${id}`, payload, config =>
    api.post(`/accounting/purchases/${id}/pay/`, payload, config),
  ).then(r => r.purchase_order);

export const receivePurchaseOrder = (id: number, payload: PurchaseReceivePayload): Promise<number[]> =>
  writeWithIdempotency<{ purchase_batches: number[] }>(`receive-purchase-order-${id}`, payload, config =>
    api.post(`/accounting/purchases/${id}/receive/`, payload, config),
  ).then(r => r.purchase_batches);

export const cancelPurchaseOrder = (id: number, payload: PurchaseCancelPayload): Promise<PurchaseAction> =>
  writeWithIdempotency<{ purchase_order: PurchaseAction }>(`cancel-purchase-order-${id}`, payload, config =>
    api.post(`/accounting/purchases/${id}/cancel/`, payload, config),
  ).then(r => r.purchase_order);

export const reverseReceivedPurchaseOrder = (id: number, payload: { business_date: string; note: string }): Promise<PurchaseAction> =>
  writeWithIdempotency<{ purchase_order: PurchaseAction }>(`reverse-receive-purchase-order-${id}`, payload, config =>
    api.post(`/accounting/purchases/${id}/reverse-receive/`, payload, config),
  ).then(r => r.purchase_order);

export const reverseInventoryAdjustment = (id: number, payload: { business_date: string; reason: string }): Promise<unknown> =>
  writeWithIdempotency<{ adjustment: unknown }>(`reverse-inventory-adjustment-${id}`, payload, config =>
    api.post(`/inventory/adjustments/${id}/reverse/`, payload, config),
  ).then(r => r.adjustment);

export interface InventoryAuditIssue {
  batch_id?: number;
  code?: string;
  message?: string;
  [key: string]: unknown;
}

export interface InventoryAuditResult {
  ok: boolean;
  issue_count: number;
  issues: InventoryAuditIssue[];
  recent_adjustments?: InventoryAdjustmentSummary[];
}

export interface InventoryAdjustmentSummary {
  id: number;
  cigar_id: number;
  cigar_name: string;
  quantity_delta: number;
  inventory_form: string;
  business_date: string;
  reason: string;
  reversed_at: string | null;
  can_reverse: boolean;
}

export const fetchInventoryAudit = (): Promise<InventoryAuditResult> =>
  api.get<InventoryAuditResult>('/inventory/audit/').then(r => r.data);

export const recordExpense = (payload: ExpenseActionPayload): Promise<unknown> =>
  writeWithIdempotency<{ expense: unknown }>('record-expense', payload, config =>
    api.post('/accounting/expenses/', payload, config),
  ).then(r => r.expense);

export const createDividend = (payload: DividendCreatePayload): Promise<DividendAction> =>
  writeWithIdempotency<{ dividend: DividendAction }>('create-dividend', payload, config =>
    api.post('/accounting/dividends/', payload, config),
  ).then(r => r.dividend);

export const updateDividend = (id: number, payload: DividendUpdatePayload): Promise<DividendAction> =>
  writeWithIdempotency<{ dividend: DividendAction }>(`update-dividend-${id}`, payload, config =>
    api.patch(`/accounting/dividends/${id}/`, payload, config),
  ).then(r => r.dividend);

export const previewDividend = (id: number): Promise<DividendPreview> =>
  writeWithIdempotency<{ preview: DividendPreview }>(`preview-dividend-${id}`, {}, config =>
    api.post(`/accounting/dividends/${id}/preview/`, {}, config),
  ).then(r => r.preview);

export const confirmDividend = (id: number, payload: DividendConfirmPayload): Promise<DividendAction> =>
  writeWithIdempotency<{ dividend: DividendAction }>(`confirm-dividend-${id}`, payload, config =>
    api.post(`/accounting/dividends/${id}/confirm/`, payload, config),
  ).then(r => r.dividend);

export function parseAccountingApiError(error: unknown): AccountingApiError {
  if (axios.isAxiosError(error)) {
    const response = error.response;
    const data = response?.data as { error?: unknown; code?: unknown; details?: unknown } | undefined;
    const details = data?.details && typeof data.details === 'object' && !Array.isArray(data.details)
      ? data.details as Record<string, unknown> : undefined;
    return {
      code: typeof data?.code === 'string' && data.code ? data.code : 'unknown',
      message: typeof data?.error === 'string' && data.error ? data.error : '账务动作失败，请稍后重试',
      ...(details ? { details } : {}),
      ...(typeof response?.status === 'number' ? { status: response.status } : {}),
    };
  }
  return {
    code: 'unknown',
    message: error instanceof Error && error.message ? error.message : '账务动作失败，请稍后重试',
  };
}

// Privnote APIs
interface CreatePrivnoteResponse {
  url: string;
  token: string;
}

function isCreatePrivnoteResponse(value: unknown): value is CreatePrivnoteResponse {
  return Boolean(
    value
    && typeof value === 'object'
    && 'url' in value
    && typeof value.url === 'string'
    && 'token' in value
    && typeof value.token === 'string',
  );
}

function privnoteErrorMessage(value: unknown): string | null {
  if (!value || typeof value !== 'object' || !('error' in value)) return null;
  return typeof value.error === 'string' && value.error ? value.error : null;
}

export const fetchPrivnote = (token: string): Promise<PrivnoteResponse> =>
  api.get(`/privnote/${token}/`).then(r => r.data);

export const verifyPrivnotePassword = (token: string, password: string): Promise<PrivnoteResponse> =>
  api.post(`/privnote/${token}/`, { password }).then(r => r.data);

export const createPrivnote = async (data: FormData): Promise<CreatePrivnoteResponse> => {
  const response = await fetch('/privnote/create/', {
    method: 'POST',
    body: data,
    credentials: 'same-origin',
    headers: { 'X-CSRFToken': getCSRFToken() },
  });
  let body: unknown;
  try {
    body = await response.json();
  } catch {
    if (!response.ok) throw new Error('私密链接创建失败，请稍后重试');
    throw new Error('服务器返回格式错误');
  }
  if (!response.ok) throw new Error(privnoteErrorMessage(body) || '私密链接创建失败');
  // 页面只消费通过运行时校验的完整创建结果。
  if (!isCreatePrivnoteResponse(body)) throw new Error('服务器返回格式错误');
  return body;
};

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

// 引导状态控制自动展示，必须在写入全局状态前验证完整布尔契约。
function isGuideSummary(value: unknown): value is GuideSummary {
  if (!value || typeof value !== 'object') return false;
  const record = value as Record<string, unknown>;
  return (
    typeof record.version === 'number'
    && typeof record.auto_show_enabled === 'boolean'
    && typeof record.should_show === 'boolean'
    && typeof record.completed_version === 'number'
    && typeof record.force_show_next_time === 'boolean'
  );
}

function guideErrorMessage(value: unknown): string | null {
  if (!value || typeof value !== 'object' || !('error' in value)) return null;
  const error = value.error;
  return typeof error === 'string' && error ? error : null;
}

async function fetchGuideEndpoint(path: string, method: 'GET' | 'POST'): Promise<GuideSummary> {
  const response = await fetch(path, {
    method,
    credentials: 'same-origin',
    headers: { 'X-CSRFToken': getCSRFToken() },
  });
  let data: unknown;
  try {
    data = await response.json();
  } catch {
    throw new Error('引导状态加载失败');
  }
  if (!response.ok) throw new Error(guideErrorMessage(data) || '引导状态加载失败');
  if (!isGuideSummary(data)) throw new Error('引导状态返回格式错误');
  return data;
}

export const fetchGuideStatus = (): Promise<GuideSummary> => fetchGuideEndpoint('/api/guides/status/', 'GET');
export const completeGuide = (): Promise<GuideSummary> => fetchGuideEndpoint('/api/guides/complete/', 'POST');
export const replayGuide = (): Promise<GuideSummary> => fetchGuideEndpoint('/api/guides/replay/', 'POST');
