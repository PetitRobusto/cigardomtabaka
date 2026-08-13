export function resolveBusinessRoute(pathname: string, hash = ''): string {
  return pathname === '/sales' && hash === '#accounting' ? '/accounting' : pathname;
}


export function dashboardDay1Action(status: string): 'start' | 'continue' | null {
  if (status === 'completed') return null;
  return status === 'draft' ? 'continue' : 'start';
}

export function dashboardStatDisplay(value: string | null | undefined): string {
  return value == null ? '—' : value;
}

export function supportQueryState(query: { isError: boolean; hasData: boolean }): 'error' | 'ready' | 'loading' {
  if (query.isError) return 'error';
  if (query.hasData) return 'ready';
  return 'loading';
}


export const BUSINESS_ROUTE_PATHS = {
  sales: '/sales',
  accounting: '/accounting',
  day1: '/accounting/day1',
} as const;
