import { BrowserRouter, Routes, Route, useLocation } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { PageMetaProvider } from './contexts/PageMetaContext';
import AppLayout from './components/layout/AppLayout';

// Catalog pages
import BrandListPage from './pages/BrandListPage';
import BrandDetailPage from './pages/BrandDetailPage';
import CigarCatalogDetailPage from './pages/CigarCatalogDetailPage';

// Inventory & Auth
import InventoryPage from './pages/InventoryPage';
import LoginPage from './pages/LoginPage';

// Privnote
import PrivnotePage from './pages/PrivnotePage';
import PrivnoteViewPage from './pages/PrivnoteViewPage';

// Price tracker (existing pages)
import PriceDashboard from './pages/Dashboard';
import PriceCigarDetail from './pages/CigarDetail';
import AlertsPage from './pages/Alerts';

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
          <Route path="/inventory" element={<InventoryPage />} />

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
