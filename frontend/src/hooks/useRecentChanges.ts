import { useQuery } from '@tanstack/react-query';
import { fetchRecentChanges } from '../api';
import type { RecentChangesResponse } from '../types';

export function useRecentChanges() {
  return useQuery<RecentChangesResponse>({
    queryKey: ['prices', 'changes'],
    queryFn: fetchRecentChanges,
    staleTime: 5 * 60 * 1000,
  });
}
