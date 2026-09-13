import { useQuery } from '@tanstack/react-query';
import { fetchPriceHistory } from '../api';
import type { PriceHistoryResponse, HistoryRange } from '../types';

export function usePriceHistory(cigarId: string | undefined, days: HistoryRange) {
  return useQuery<PriceHistoryResponse>({
    queryKey: ['prices', 'history', cigarId, days],
    queryFn: () => fetchPriceHistory(cigarId!, days),
    enabled: !!cigarId && cigarId !== 'undefined',
    staleTime: 5 * 60 * 1000,
  });
}
