import { BrowserRouter, Navigate, Routes, Route, useLocation } from 'react-router-dom';
import { lazy, Suspense, useEffect, useRef } from 'react';
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion';
import { PageMetaProvider } from './contexts/PageMetaContext';
import AppLayout from './components/layout/AppLayout';
import { DelayedAppSkeleton } from './components/layout/AppSkeleton';
import { appSectionForPath } from './components/layout/appSections';
import { decideStaffRoute, resolveStorefrontTarget } from './utils/routeGuard';
import { BUSINESS_STAFF_PATHS, resolveBusinessRoute } from './pages/businessRoutes';
import { useAuthStore } from './store/authStore';
import { BrandLoader } from './components/shared/BrandLoader';
import CustomerDocumentLanguage from './features/customer/CustomerDocumentLanguage';
import { useCustomerExperience } from './features/customer/useCustomerExperience';
import { NotFoundPage } from './components/site/NotFoundPage';
import { localeForPath, notFoundCopy } from './components/site/notFoundCopy';
import { usePageMetaContext } from './contexts/usePageMetaContext';

// Route components stay out of the startup bundle until their URL is rendered.
const BrandListPage = lazy(() => import('./pages/BrandListPage'));
const BrandDetailPage = lazy(() => import('./pages/BrandDetailPage'));
const CigarCatalogDetailPage = lazy(() => import('./pages/CigarCatalogDetailPage'));

// Inventory & Auth
const InventoryPage = lazy(() => import('./pages/InventoryWorkbenchPage'));
const InventoryPurchasesPage = lazy(() => import('./pages/InventoryPurchasesPage'));
const LoginPage = lazy(() => import('./pages/LoginPage'));

// Privnote
const PrivnotePage = lazy(() => import('./pages/PrivnotePage'));
const PrivnoteViewPage = lazy(() => import('./pages/PrivnoteViewPage'));

// Price tracker (existing pages)
const PriceDashboard = lazy(() => import('./pages/Dashboard'));
const PriceCigarDetail = lazy(() => import('./pages/CigarDetail'));
const AlertsPage = lazy(() => import('./pages/Alerts'));
const SalesPage = lazy(() => import('./pages/SalesPage'));
const SalesCustomersPage = lazy(() => import('./pages/SalesCustomersPage'));
const AccountingDashboardPage = lazy(() => import('./pages/AccountingDashboardPage'));
const MonthlyBusinessReportPage = lazy(() => import('./pages/MonthlyBusinessReportPage'));
const ContributionRankingPage = lazy(() => import('./pages/ContributionRankingPage'));
const Day1SetupPage = lazy(() => import('./pages/Day1SetupPage'));
const HelpPage = lazy(() => import('./pages/HelpPage'));

function StartupLoaderHandoff() {
  useEffect(() => {
    document.documentElement.dataset.cdtAppReady = 'true';
    window.dispatchEvent(new Event('cdt:app-ready'));
    const startup = (window as Window & {
      CDTStartup?: { ready(): void };
    }).CDTStartup;
    startup?.ready();
  }, []);

  return null;
}

function StaffGate({ children }: { children: React.ReactNode }) {
  const { isLoading, isAuthenticated, user } = useAuthStore();
  const location = useLocation();
  const decision = decideStaffRoute({ isLoading, isAuthenticated, isStaff: Boolean(user?.is_staff) });
  if (decision === 'loading') return null;
  if (decision === 'login') {
    const next = `${location.pathname}${location.search}${location.hash}`;
    return <Navigate to={`/login?next=${encodeURIComponent(next)}`} replace />;
  }
  if (decision === 'home') return <NativeStorefrontRoute path="/" />;
  return <>{children}</>;
}

interface AppRuntimeConfig {
  storefrontEnabled: boolean;
  djangoOrigin: string;
  allowConfiguredCrossOrigin: boolean;
}

function readAppRuntimeConfig(): AppRuntimeConfig {
  const element = document.getElementById('cdt-app-runtime-config');
  if (element?.textContent) {
    try {
      const config = JSON.parse(element.textContent) as Partial<AppRuntimeConfig>;
      return {
        storefrontEnabled: config.storefrontEnabled === true,
        djangoOrigin: typeof config.djangoOrigin === 'string' ? config.djangoOrigin : '',
        allowConfiguredCrossOrigin: false,
      };
    } catch {
      return { storefrontEnabled: false, djangoOrigin: '', allowConfiguredCrossOrigin: false };
    }
  }

  const djangoOrigin = import.meta.env.DEV ? import.meta.env.VITE_DJANGO_ORIGIN || '' : '';
  return {
    storefrontEnabled: import.meta.env.DEV && import.meta.env.VITE_STOREFRONT_ENABLED === 'true',
    djangoOrigin,
    allowConfiguredCrossOrigin: Boolean(djangoOrigin && import.meta.env.DEV),
  };
}

function NativeStorefrontRoute({ path }: { path: string }) {
  const location = useLocation();
  const runtime = readAppRuntimeConfig();
  const target = resolveStorefrontTarget(`${path}${location.search}${location.hash}`, {
    enabled: runtime.storefrontEnabled,
    djangoOrigin: runtime.djangoOrigin,
    currentOrigin: window.location.origin,
    allowConfiguredCrossOrigin: runtime.allowConfiguredCrossOrigin,
  });

  useEffect(() => {
    if (target) window.location.assign(target);
  }, [target]);

  if (target) return null;
  return (
    <section className="min-h-[50vh] flex flex-col items-center justify-center px-6 text-center" role="status">
      <h1 className="font-display text-2xl font-semibold text-fg">商城暂不可用</h1>
      <p className="max-w-md mt-3 text-sm text-muted">
        {runtime.storefrontEnabled
          ? '请从配置的 Django 站点入口打开商城。'
          : '当前站点未启用预渲染商城。'}
      </p>
      <a href="/login" className="mt-5 text-sm text-accent underline underline-offset-4">前往登录</a>
    </section>
  );
}

function LegacySalesRoute() {
  const location = useLocation();
  // Hash links from the old combined workspace remain valid after the split.
  const destination = resolveBusinessRoute(location.pathname, location.hash);
  return destination !== location.pathname ? <Navigate to={destination} replace /> : <SalesPage />;
}

function StaffHelpRoute() {
  return <StaffGate><HelpPage /></StaffGate>;
}

export function StaffNotFoundRoute() {
  const location = useLocation();
  const locale = localeForPath(location.pathname);
  const { setMeta } = usePageMetaContext();

  useEffect(() => {
    setMeta({ title: notFoundCopy[locale].title, breadcrumbs: [] });
    const previousLanguage = document.documentElement.lang;
    document.documentElement.lang = locale === 'zh' ? 'zh-CN' : locale;
    let robots = document.head.querySelector<HTMLMetaElement>('meta[name="robots"]');
    const previousRobotsContent = robots?.content ?? null;
    if (!robots) {
      robots = document.createElement('meta');
      robots.name = 'robots';
      document.head.append(robots);
    }
    robots.content = 'noindex, nofollow';
    return () => {
      document.documentElement.lang = previousLanguage;
      if (robots?.content === 'noindex, nofollow') {
        if (previousRobotsContent === null) robots.remove();
        else robots.content = previousRobotsContent;
      }
    };
  }, [locale, setMeta]);

  return <NotFoundPage locale={locale} embedded />;
}

function AnimatedRoutes() {
  const { text } = useCustomerExperience();
  const location = useLocation();
  const reduceMotion = useReducedMotion();
  const section = appSectionForPath(location.pathname);
  const previousSection = useRef(section);

  useEffect(() => {
    if (previousSection.current !== section) {
      window.scrollTo({ top: 0, left: 0, behavior: 'auto' });
      previousSection.current = section;
    }
  }, [section]);

  return (
    <AnimatePresence mode="wait" initial={false}>
      <motion.div
        key={section}
        initial={{ opacity: 1 }}
        animate={{ opacity: 1 }}
        exit={reduceMotion
          ? { opacity: 1, transition: { duration: 0 } }
          : { opacity: 0, transition: { duration: 0.08, ease: 'easeOut' } }}
        style={{ position: 'relative' }}
      >
        <Suspense fallback={<DelayedAppSkeleton path={location.pathname} label={text.loading} />}>
          <motion.div
            initial={reduceMotion ? { opacity: 1 } : { opacity: 0, y: 4 }}
            animate={reduceMotion
              ? { opacity: 1, transition: { duration: 0 } }
              : { opacity: 1, y: 0, transition: { opacity: { duration: 0.15, ease: 'easeOut' }, y: { duration: 0.15, ease: [0.2, 0, 0, 1] } } }}
          >
            <Routes location={location}>
          {/* Public storefront pages are rendered by Django; always cross the app boundary natively. */}
          <Route path="/" element={<NativeStorefrontRoute path="/" />} />
          <Route path="/catalog" element={<NativeStorefrontRoute path="/catalog" />} />
          <Route path="/brand/:slug" element={<NativeStorefrontRoute path={location.pathname} />} />
          <Route path="/cigar/:id/:slug?" element={<NativeStorefrontRoute path={location.pathname} />} />

          {/* Legacy full directory remains staff only under /library. */}
          <Route path="/library" element={<StaffGate><BrandListPage /></StaffGate>} />
          <Route path="/library/brand/:slug" element={<StaffGate><BrandDetailPage /></StaffGate>} />
          <Route path="/library/cigar/:id/:slug?" element={<StaffGate><CigarCatalogDetailPage /></StaffGate>} />

          {/* Inventory */}
          <Route path={BUSINESS_STAFF_PATHS.inventory} element={<StaffGate><InventoryPage /></StaffGate>} />
          <Route path={BUSINESS_STAFF_PATHS.inventoryPurchases} element={<StaffGate><InventoryPurchasesPage /></StaffGate>} />
          <Route path={BUSINESS_STAFF_PATHS.sales} element={<StaffGate><LegacySalesRoute /></StaffGate>} />
          <Route path={BUSINESS_STAFF_PATHS.salesReceipts} element={<StaffGate><Navigate to={BUSINESS_STAFF_PATHS.sales} replace /></StaffGate>} />
          <Route path={BUSINESS_STAFF_PATHS.salesCustomers} element={<StaffGate><SalesCustomersPage /></StaffGate>} />
          <Route path={BUSINESS_STAFF_PATHS.accounting} element={<StaffGate><AccountingDashboardPage /></StaffGate>} />
          <Route path={BUSINESS_STAFF_PATHS.day1} element={<StaffGate><Day1SetupPage /></StaffGate>} />
          <Route path={BUSINESS_STAFF_PATHS.monthlyReport} element={<StaffGate><MonthlyBusinessReportPage /></StaffGate>} />
          <Route path={BUSINESS_STAFF_PATHS.contributionRanking} element={<StaffGate><ContributionRankingPage /></StaffGate>} />
          <Route path="/reports/monthly" element={<StaffGate><Navigate to={`${BUSINESS_STAFF_PATHS.monthlyReport}${location.search}`} replace /></StaffGate>} />
          <Route path="/reports/contributions" element={<StaffGate><Navigate to={`${BUSINESS_STAFF_PATHS.contributionRanking}${location.search}`} replace /></StaffGate>} />
          <Route path="/help" element={<StaffHelpRoute />} />

          {/* Price Tracker */}
          <Route path="/prices" element={<StaffGate><PriceDashboard /></StaffGate>} />
          <Route path="/prices/cigar/:id/:slug?" element={<StaffGate><PriceCigarDetail /></StaffGate>} />
          <Route path="/prices/alerts" element={<StaffGate><AlertsPage /></StaffGate>} />

          {/* Privnote */}
          <Route path="/privnote" element={<StaffGate><PrivnotePage /></StaffGate>} />
          <Route path="/p/:token" element={<PrivnoteViewPage />} />

          {/* Auth */}
          <Route path="/login" element={<LoginPage />} />
          <Route path="*" element={<StaffNotFoundRoute />} />
            </Routes>
          </motion.div>
        </Suspense>
      </motion.div>
    </AnimatePresence>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <PageMetaProvider>
        <CustomerDocumentLanguage />
        <StartupLoaderHandoff />
        <Routes>
          {/* Routes without AppLayout keep a full-screen initial fallback. */}
          <Route path="/login" element={<Suspense fallback={<BrandLoader fullScreen />}><LoginPage /></Suspense>} />
          <Route path="/p/:token" element={<Suspense fallback={<BrandLoader fullScreen />}><PrivnoteViewPage /></Suspense>} />
          {/* In-app route chunks load inside the content area without replacing navigation. */}
          <Route
            path="/*"
            element={
              <AppLayout>
                <AnimatedRoutes />
              </AppLayout>
            }
          />
        </Routes>
      </PageMetaProvider>
    </BrowserRouter>
  );
}
