import { useQuery } from '@tanstack/react-query';
import { fetchAggregatedPrices } from '../api';
import type { AggregatedCigar } from '../types';

interface AggregatedParams {
  brand?: string;
  in_stock_only?: boolean;
  search?: string;
}

export function useAggregatedPrices(params: AggregatedParams = {}) {
  const queryParams: Record<string, string> = {};
  if (params.brand) queryParams.brand = params.brand;
  if (params.in_stock_only) queryParams.in_stock_only = '1';
  if (params.search) queryParams.search = params.search;

  return useQuery<AggregatedCigar[]>({
    queryKey: ['prices', 'aggregated', params],
    queryFn: () => fetchAggregatedPrices(queryParams),
    staleTime: 5 * 60 * 1000,
  });
}
