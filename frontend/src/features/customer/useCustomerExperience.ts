import { useLocation } from 'react-router-dom';
import { useAuthStore } from '../../store/authStore';
import { customerMessages } from './messages';
import { useCustomerPreferences } from './preferences';
import { isCustomerBrowsingPage } from './customerRoutes';

export function useCustomerExperience() {
  const { pathname } = useLocation();
  const user = useAuthStore((state) => state.user);
  const isLoading = useAuthStore((state) => state.isLoading);
  const preferredLocale = useCustomerPreferences((state) => state.locale);
  const enabled = !isLoading && !user?.is_staff && !user?.is_superuser && isCustomerBrowsingPage(pathname);
  const locale = enabled ? preferredLocale : 'zh';
  return { enabled, locale, text: customerMessages[locale] };
}
