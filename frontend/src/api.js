import axios from 'axios';

// CSRF cookie (Django sets this)
function getCSRFToken() {
  const match = document.cookie.match(/csrftoken=([^;]+)/);
  return match ? match[1] : '';
}

const api = axios.create({
  baseURL: '/api/prices',
  headers: {
    'X-CSRFToken': getCSRFToken(),
  },
});

// --- Sources ---
export const fetchSources = () => api.get('/sources/').then(r => r.data);

// --- Snapshots ---
export const fetchLatestPrices = (params = {}) =>
  api.get('/snapshots/latest/', { params }).then(r => r.data);

export const fetchPriceHistory = (cigarId, days = 30) =>
  api.get('/snapshots/history/', { params: { cigar_id: cigarId, days } }).then(r => r.data);

// --- Alerts ---
export const fetchAlerts = () => api.get('/alerts/').then(r => r.data);
export const createAlert = (data) => api.post('/alerts/', data).then(r => r.data);
export const updateAlert = (id, data) => api.patch(`/alerts/${id}/`, data).then(r => r.data);
export const deleteAlert = (id) => api.delete(`/alerts/${id}/`).then(r => r.data);

export default api;
