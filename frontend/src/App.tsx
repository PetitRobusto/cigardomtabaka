import { BrowserRouter, Navigate, Routes, Route, useLocation } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { PageMetaProvider } from './contexts/PageMetaContext';
import AppLayout from './components/layout/AppLayout';

// Catalog pages
import BrandListPage from './pages/BrandListPage';
import BrandDetailPage from './pages/BrandDetailPage';
import CigarCatalogDetailPage from './pages/CigarCatalogDetailPage';

// Inventory & Auth
import InventoryPage from './pages/InventoryWorkbenchPage';
import InventoryPurchasesPage from './pages/InventoryPurchasesPage';
import LoginPage from './pages/LoginPage';

// Privnote
import PrivnotePage from './pages/PrivnotePage';
import PrivnoteViewPage from './pages/PrivnoteViewPage';

// Price tracker (existing pages)
import PriceDashboard from './pages/Dashboard';
import PriceCigarDetail from './pages/CigarDetail';
import AlertsPage from './pages/Alerts';
import SalesPage from './pages/SalesPage';
import SalesCustomersPage from './pages/SalesCustomersPage';
import AccountingDashboardPage from './pages/AccountingDashboardPage';
import Day1SetupPage from './pages/Day1SetupPage';
import HelpPage from './pages/HelpPage';
import { decideStaffRoute } from './utils/routeGuard';
import { BUSINESS_STAFF_PATHS, resolveBusinessRoute } from './pages/businessRoutes';
import { useAuthStore } from './store/authStore';

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
    <AnimatePresence mode="sync">
      <motion.div
        key={location.key}
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -8 }}
        transition={{ duration: 0.25, ease: [0.4, 0, 0.2, 1] }}
        style={{ position: 'relative' }}
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
    </AnimatePresence>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <PageMetaProvider>
        <Routes>
          {/* Routes without AppLayout (login, privnote view) */}
          <Route path="/login" element={<LoginPage />} />
          <Route path="/p/:token" element={<PrivnoteViewPage />} />
          {/* All other routes with AppLayout */}
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
