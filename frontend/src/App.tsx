import { BrowserRouter, Navigate, Routes, Route, useLocation } from 'react-router-dom';
import { lazy, Suspense, useEffect, useRef } from 'react';
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion';
import { PageMetaProvider } from './contexts/PageMetaContext';
import AppLayout from './components/layout/AppLayout';
import { DelayedAppSkeleton } from './components/layout/AppSkeleton';
import { appSectionForPath } from './components/layout/appSections';
import { decideStaffRoute } from './utils/routeGuard';
import { BUSINESS_STAFF_PATHS, resolveBusinessRoute } from './pages/businessRoutes';
import { useAuthStore } from './store/authStore';
import { BrandLoader } from './components/shared/BrandLoader';

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
  const decision = decideStaffRoute({ isLoading, isAuthenticated, isStaff: Boolean(user?.is_staff) });
  if (decision === 'loading') return null;
  if (decision === 'login') return <Navigate to="/login" replace />;
  if (decision === 'home') return <Navigate to="/" replace />;
  return <>{children}</>;
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

function AnimatedRoutes() {
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
        <Suspense fallback={<DelayedAppSkeleton path={location.pathname} />}>
          <motion.div
            initial={reduceMotion ? { opacity: 1 } : { opacity: 0, y: 4 }}
            animate={reduceMotion
              ? { opacity: 1, transition: { duration: 0 } }
              : { opacity: 1, y: 0, transition: { opacity: { duration: 0.15, ease: 'easeOut' }, y: { duration: 0.15, ease: [0.2, 0, 0, 1] } } }}
          >
            <Routes location={location}>
          {/* Catalog */}
          <Route path="/" element={<BrandListPage />} />
          <Route path="/brand/:slug" element={<BrandDetailPage />} />
          <Route path="/cigar/:id/:slug?" element={<CigarCatalogDetailPage />} />

          {/* Inventory */}
          <Route path={BUSINESS_STAFF_PATHS.inventory} element={<InventoryPage />} />
          <Route path={BUSINESS_STAFF_PATHS.inventoryPurchases} element={<StaffGate><InventoryPurchasesPage /></StaffGate>} />
          <Route path={BUSINESS_STAFF_PATHS.sales} element={<StaffGate><LegacySalesRoute /></StaffGate>} />
          <Route path={BUSINESS_STAFF_PATHS.salesReceipts} element={<StaffGate><Navigate to={BUSINESS_STAFF_PATHS.sales} replace /></StaffGate>} />
          <Route path={BUSINESS_STAFF_PATHS.salesCustomers} element={<StaffGate><SalesCustomersPage /></StaffGate>} />
          <Route path={BUSINESS_STAFF_PATHS.accounting} element={<StaffGate><AccountingDashboardPage /></StaffGate>} />
          <Route path={BUSINESS_STAFF_PATHS.day1} element={<StaffGate><Day1SetupPage /></StaffGate>} />
          <Route path={BUSINESS_STAFF_PATHS.monthlyReport} element={<StaffGate><MonthlyBusinessReportPage /></StaffGate>} />
          <Route path={BUSINESS_STAFF_PATHS.contributionRanking} element={<StaffGate><ContributionRankingPage /></StaffGate>} />
          <Route path="/help" element={<StaffHelpRoute />} />

          {/* Price Tracker */}
          <Route path="/prices" element={<PriceDashboard />} />
          <Route path="/prices/cigar/:id/:slug?" element={<PriceCigarDetail />} />
          <Route path="/prices/alerts" element={<AlertsPage />} />

          {/* Privnote */}
          <Route path="/privnote" element={<PrivnotePage />} />
          <Route path="/p/:token" element={<PrivnoteViewPage />} />

          {/* Auth */}
          <Route path="/login" element={<LoginPage />} />
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
