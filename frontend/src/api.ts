import axios from 'axios';
import type {
  PriceSnapshot, PriceHistoryResponse, Source, AggregatedCigar,
  BrandListResponse, BrandDetailResponse, CigarDetailResponse,
  InventoryResponse, PrivnoteResponse,
} from './types';

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
