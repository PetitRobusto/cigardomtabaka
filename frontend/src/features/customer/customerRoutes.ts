import { matchRoutes } from 'react-router-dom';

// Legacy SPA customer boundary. Keep router code out of shared preferences,
// which are also used by the independently hydrated public storefront.
export function isCustomerBrowsingPage(pathname: string): boolean {
  return matchRoutes([{ path: '/' }, { path: '/brand/:slug' }], pathname) !== null;
}
