import { useQuery } from '@tanstack/react-query';
import axios from 'axios';
import type { CigarListItem } from '../types';

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

export const fetchCigarList = (): Promise<CigarListItem[]> =>
  api.get('/snapshots/list/').then(r => r.data);

export function useLatestPrices() {
  return useQuery<CigarListItem[]>({
    queryKey: ['prices', 'list'],
    queryFn: fetchCigarList,
    staleTime: 5 * 60 * 1000,
  });
}
