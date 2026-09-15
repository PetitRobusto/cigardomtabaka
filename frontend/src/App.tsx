import { BrowserRouter, Navigate, Routes, Route, useLocation } from 'react-router-dom';
import { lazy, Suspense, useEffect } from 'react';
import { PageMetaProvider } from './contexts/PageMetaContext';
import AppLayout from './components/layout/AppLayout';
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
const Day1SetupPage = lazy(() => import('./pages/Day1SetupPage'));
const HelpPage = lazy(() => import('./pages/HelpPage'));

function StartupLoaderHandoff() {
  useEffect(() => {
    const startupLoader = document.getElementById('startup-loader');
    if (!startupLoader) return;

    startupLoader.classList.add('is-leaving');
    document.body.classList.remove('cdt-starting');
    const removeTimer = window.setTimeout(() => startupLoader.remove(), 280);

    return () => window.clearTimeout(removeTimer);
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
  return (
    <div key={location.key} className="animate-fade-in" style={{ position: 'relative' }}>
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
    </div>
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
                <Suspense fallback={<BrandLoader />}>
                  <AnimatedRoutes />
                </Suspense>
              </AppLayout>
            }
          />
        </Routes>
      </PageMetaProvider>
    </BrowserRouter>
  );
}
