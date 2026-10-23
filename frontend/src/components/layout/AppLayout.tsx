import { useLocation, useNavigate } from 'react-router-dom';
import { lazy, Suspense, useEffect, useRef } from 'react';
import { useAuthStore } from '../../store/authStore';
import { usePageMetaContext } from '../../contexts/usePageMetaContext';
import Breadcrumb from './Breadcrumb';
import { BrandLoader } from '../shared/BrandLoader';
import CustomerAgeGate from '../../features/customer/CustomerAgeGate';
import { useCustomerExperience } from '../../features/customer/useCustomerExperience';
import { isAgeConfirmationValid, useCustomerPreferences } from '../../features/customer/preferences';
import { SiteHeader, StaffDock } from '../site/SiteHeader';
import { SiteFooter } from '../site/SiteFooter';

const GuideController = lazy(() => import('../../features/guides/GuideController'));

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const { user, isLoading, logout, checkAuth } = useAuthStore();
  const location = useLocation();
  const navigate = useNavigate();
  const { meta } = usePageMetaContext();
  const { enabled: customerPage, locale, text } = useCustomerExperience();
  const storeLocale = useCustomerPreferences((state) => state.locale);
  const confirmedAt = useCustomerPreferences((state) => state.confirmedAt);
  const denied = useCustomerPreferences((state) => state.denied);
  const ageBlocked = customerPage && (denied || !isAgeConfirmationValid(confirmedAt));
  const customerScope = useRef<HTMLDivElement>(null);
  useEffect(() => { void checkAuth(); }, [checkAuth]);
  useEffect(() => {
    if (ageBlocked) document.title = `${denied ? text.deniedTitle : text.ageTitle} · CigarDomTabaka`;
    else if (meta.title) document.title = meta.title;
  }, [meta.title, ageBlocked, denied, text.deniedTitle, text.ageTitle]);
  if (isLoading) return <BrandLoader fullScreen />;
  return <div ref={customerScope} className="min-h-screen flex flex-col bg-cream">
    <SiteHeader locale={locale} storeLocale={storeLocale} user={user} pathname={location.pathname} onLogout={logout} onNavigate={navigate} inert={ageBlocked} />
    {ageBlocked ? <CustomerAgeGate scope={customerScope} /> : <>
      <main className="flex-1"><div className="max-w-[1480px] mx-auto px-4 sm:px-6 py-6"><Breadcrumb />{children}</div></main>
      <SiteFooter locale={locale} customerPage={customerPage} />
      <StaffDock storeLocale={storeLocale} user={user} pathname={location.pathname} onNavigate={navigate} />
      {user?.is_staff && <Suspense fallback={null}><GuideController /></Suspense>}
    </>}
  </div>;
}
