import { BrowserRouter, Routes, Route, NavLink, useLocation } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { LayoutDashboard, Bell, Flame } from 'lucide-react';
import Dashboard from './pages/Dashboard';
import CigarDetail from './pages/CigarDetail';
import Alerts from './pages/Alerts';
import './styles/globals.css';

function AnimatedRoutes() {
  const location = useLocation();
  return (
    <AnimatePresence mode="wait">
      <motion.div
        key={location.pathname}
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -8 }}
        transition={{ duration: 0.25, ease: [0.4, 0, 0.2, 1] }}
      >
        <Routes location={location}>
          <Route path="/" element={<Dashboard />} />
          <Route path="/cigar/:id" element={<CigarDetail />} />
          <Route path="/alerts" element={<Alerts />} />
        </Routes>
      </motion.div>
    </AnimatePresence>
  );
}

export default function App() {
  return (
    <BrowserRouter basename="/prices">
      <div className="app">
        <header className="app-header">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-accent flex items-center justify-center shadow-md">
              <Flame className="w-5 h-5 text-white" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-fg tracking-tight leading-none">
                市场价格监控
              </h1>
              <p className="text-[0.7rem] text-muted mt-0.5 tracking-wide uppercase">
                Moscow Cigar Price Tracker
              </p>
            </div>
          </div>
          <nav>
            <NavLink
              to="/"
              end
              className={({ isActive }) =>
                `inline-flex items-center gap-1.5 px-4 py-2 rounded-full text-sm font-medium transition-all duration-200 ${
                  isActive
                    ? 'bg-accent text-white shadow-sm'
                    : 'text-muted hover:text-accent hover:bg-accent-light'
                }`
              }
            >
              <LayoutDashboard className="w-4 h-4" />
              <span>仪表盘</span>
            </NavLink>
            <NavLink
              to="/alerts"
              className={({ isActive }) =>
                `inline-flex items-center gap-1.5 px-4 py-2 rounded-full text-sm font-medium transition-all duration-200 ${
                  isActive
                    ? 'bg-accent text-white shadow-sm'
                    : 'text-muted hover:text-accent hover:bg-accent-light'
                }`
              }
            >
              <Bell className="w-4 h-4" />
              <span>预警管理</span>
            </NavLink>
          </nav>
        </header>
        <main>
          <AnimatedRoutes />
        </main>
        <footer className="mt-16 py-6 border-t border-border text-center">
          <p className="text-xs text-muted">
            Moscow Cigar · 价格数据仅供参考
          </p>
        </footer>
      </div>
    </BrowserRouter>
  );
}
