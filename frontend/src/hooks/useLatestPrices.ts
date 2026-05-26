import { useQuery } from '@tanstack/react-query';
import { fetchLatestPrices } from '../api';
import type { PriceSnapshot } from '../types';

export function useLatestPrices() {
  return useQuery<PriceSnapshot[]>({
    queryKey: ['prices', 'latest'],
    queryFn: fetchLatestPrices,
    staleTime: 5 * 60 * 1000,
  });
}
