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

export type DashboardRegionState = 'error' | 'ready' | 'loading';

export function supportQueryState(query: { isError: boolean; hasData: boolean }): DashboardRegionState {
  if (query.isError) return 'error';
  if (query.hasData) return 'ready';
  return 'loading';
}

export function dashboardRegionStates(queries: Record<string, { isError: boolean; hasData: boolean }>): Record<string, DashboardRegionState> {
  return Object.fromEntries(Object.entries(queries).map(([name, query]) => [name, supportQueryState(query)]));
}

export const BUSINESS_STAFF_PATHS = {
  sales: '/sales',
  salesCustomers: '/sales/customers',
  accounting: '/accounting',
  day1: '/accounting/day1',
} as const;

// Keep the semantic route name while ensuring App and tests share one configuration object.
export const BUSINESS_ROUTE_PATHS = BUSINESS_STAFF_PATHS;
