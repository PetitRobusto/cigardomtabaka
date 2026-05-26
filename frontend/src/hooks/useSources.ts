import { useQuery } from '@tanstack/react-query';
import { fetchSources } from '../api';
import type { Source } from '../types';

export function useSources() {
  return useQuery<Source[]>({
    queryKey: ['sources'],
    queryFn: fetchSources,
    staleTime: 30 * 60 * 1000,
  });
}
