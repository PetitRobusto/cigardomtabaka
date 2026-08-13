export function resolveBusinessRoute(pathname: string, hash = ''): string {
  return pathname === '/sales' && hash === '#accounting' ? '/accounting' : pathname;
}
