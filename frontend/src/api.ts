import axios from 'axios';
import type { PriceSnapshot, PriceHistoryResponse, Source } from './types';

function getCSRFToken(): string {
  const match = document.cookie.match(/csrftoken=([^;]+)/);
  return match ? match[1] : '';
}

const api = axios.create({
  baseURL: '/api/prices',
  headers: {
    'X-CSRFToken': getCSRFToken(),
  },
});

export const fetchSources = (): Promise<Source[]> =>
  api.get('/sources/').then(r => r.data.results || r.data);

export const fetchLatestPrices = (): Promise<PriceSnapshot[]> =>
  api.get('/snapshots/latest/').then(r => r.data.results || r.data);

export const fetchPriceHistory = (cigarId: string, days = 30): Promise<PriceHistoryResponse> =>
  api.get('/snapshots/history/', { params: { cigar_id: cigarId, days } }).then(r => r.data);

export const fetchAlerts = () => api.get('/alerts/').then(r => r.data);
export const createAlert = (data: unknown) => api.post('/alerts/', data).then(r => r.data);
export const updateAlert = (id: number, data: unknown) => api.patch(`/alerts/${id}/`, data).then(r => r.data);
export const deleteAlert = (id: number) => api.delete(`/alerts/${id}/`).then(r => r.data);

export default api;
