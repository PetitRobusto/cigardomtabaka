export type StaffRouteDecision = 'loading' | 'login' | 'home' | 'allow';

export interface StaffRouteAuthState {
  isLoading: boolean;
  isAuthenticated: boolean;
  isStaff: boolean;
}

export function decideStaffRoute(state: StaffRouteAuthState): StaffRouteDecision {
  if (state.isLoading) return 'loading';
  if (!state.isAuthenticated) return 'login';
  if (!state.isStaff) return 'home';
  return 'allow';
}

const STAFF_PATH_PREFIXES = [
  '/library', '/inventory', '/sales', '/accounting', '/reports',
  '/help', '/prices', '/privnote',
];

export function isStaffPath(pathname: string): boolean {
  let canonicalPath = pathname;
  try {
    canonicalPath = decodeURIComponent(pathname);
  } catch {
    // An invalid escape cannot be a valid management route.
  }
  return STAFF_PATH_PREFIXES.some(prefix => canonicalPath === prefix || canonicalPath.startsWith(`${prefix}/`));
}

export function safeLoginDestination(rawNext: string | null, isStaff: boolean): string {
  if (!rawNext || !rawNext.startsWith('/') || rawNext.startsWith('//') || rawNext.startsWith('/\\')) return '/';
  // eslint-disable-next-line no-control-regex -- Reject URL control characters before parsing normalizes them.
  if (/[\\\u0000-\u001f]/.test(rawNext)) return '/';

  try {
    const origin = typeof window === 'undefined' ? 'http://localhost' : window.location.origin;
    const target = new URL(rawNext, origin);
    if (target.origin !== origin || !target.pathname.startsWith('/')) return '/';
    if (target.pathname === '/login' || target.pathname.startsWith('/login/')) return '/';
    if (isStaffPath(target.pathname) && !isStaff) return '/';
    return `${target.pathname}${target.search}${target.hash}`;
  } catch {
    return '/';
  }
}

export interface StorefrontBridgeOptions {
  enabled: boolean;
  djangoOrigin: string;
  currentOrigin: string;
  allowConfiguredCrossOrigin?: boolean;
}

export function resolveStorefrontTarget(path: string, options: StorefrontBridgeOptions): string | null {
  if (!options.enabled || !path.startsWith('/') || path.startsWith('//') || path.startsWith('/\\')) return null;
  // eslint-disable-next-line no-control-regex -- Reject URL control characters before parsing normalizes them.
  if (/[\\\u0000-\u001f]/.test(path)) return null;

  try {
    const current = new URL(options.currentOrigin);
    const django = new URL(options.djangoOrigin);
    if (!['http:', 'https:'].includes(current.protocol) || !['http:', 'https:'].includes(django.protocol)) return null;
    if (django.username || django.password || django.pathname !== '/' || django.search || django.hash) return null;
    if (django.origin !== current.origin && !options.allowConfiguredCrossOrigin) return null;

    const target = new URL(path, django.origin);
    if (target.origin !== django.origin) return null;
    return target.href;
  } catch {
    return null;
  }
}
