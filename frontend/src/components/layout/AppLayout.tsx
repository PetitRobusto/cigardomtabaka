import { NavLink, useLocation, useNavigate } from 'react-router-dom';
import { useEffect } from 'react';
import { useAuthStore } from '../../store/authStore';
import {
  Flame, LayoutGrid, Package, TrendingUp, Link2, Settings, LogIn, LogOut, User, Menu, X
} from 'lucide-react';
import { useState } from 'react';

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const { user, isAuthenticated, isLoading, logout } = useAuthStore();
  const location = useLocation();
  const navigate = useNavigate();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  useEffect(() => {
    useAuthStore.getState().checkAuth();
  }, []);

  const navItems = [
    { to: '/', label: '品牌', icon: LayoutGrid, public: true },
    ...(user?.is_staff ? [
      { to: '/inventory', label: '库存', icon: Package },
      { to: '/prices', label: '价格', icon: TrendingUp },
      { to: '/privnote', label: '链接', icon: Link2 },
      { to: '/admin/', label: '管理', icon: Settings, external: true },
    ] : []),
  ];

  const isActive = (path: string) => {
    if (path === '/') return location.pathname === '/';
    return location.pathname.startsWith(path);
  };

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-cream">
        <div className="animate-spin w-8 h-8 border-2 border-accent border-t-transparent rounded-full" />
      </div>
    );
  }

  return (
    <div className="min-h-screen flex flex-col bg-cream">
      {/* ===== TOPBAR ===== */}
      <header className="sticky top-0 z-50 bg-cream/90 backdrop-blur-sm border-b border-border">
        <div className="max-w-7xl mx-auto px-4 sm:px-6">
          <div className="flex items-center justify-between h-14">
            {/* Logo */}
            <div className="flex items-center gap-3">
              <div
                className="w-8 h-8 rounded bg-accent flex items-center justify-center cursor-pointer"
                onClick={() => navigate('/')}
              >
                <Flame className="w-4 h-4 text-white" />
              </div>
              <span className="font-display text-lg font-semibold text-fg tracking-tight hidden sm:inline">
                Moscow Cigar
              </span>
            </div>

            {/* Desktop Nav */}
            <nav className="hidden md:flex items-center gap-1">
              {navItems.map((item) =>
                item.external ? (
                  <a
                    key={item.to}
                    href={item.to}
                    className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                      isActive(item.to)
                        ? 'text-accent bg-accent-light'
                        : 'text-muted hover:text-fg hover:bg-white/60'
                    }`}
                  >
                    <item.icon className="w-4 h-4" />
                    <span>{item.label}</span>
                  </a>
                ) : (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    className={() =>
                      `inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                        isActive(item.to)
                          ? 'text-accent bg-accent-light'
                          : 'text-muted hover:text-fg hover:bg-white/60'
                      }`
                    }
                  >
                    <item.icon className="w-4 h-4" />
                    <span>{item.label}</span>
                  </NavLink>
                )
              )}
            </nav>

            {/* Auth */}
            <div className="flex items-center gap-2">
              {isAuthenticated ? (
                <>
                  <div className="hidden sm:flex items-center gap-2">
                    <div className="w-7 h-7 rounded-full bg-accent text-white flex items-center justify-center text-xs font-medium">
                      {user?.username?.[0]?.toUpperCase()}
                    </div>
                    <span className="text-sm text-fg">{user?.username}</span>
                  </div>
                  <button
                    onClick={() => logout()}
                    className="p-2 rounded-md text-muted hover:text-accent hover:bg-accent-light transition-colors"
                    title="退出"
                  >
                    <LogOut className="w-4 h-4" />
                  </button>
                </>
              ) : (
                <NavLink
                  to="/login"
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium text-accent hover:bg-accent-light transition-colors"
                >
                  <LogIn className="w-4 h-4" />
                  <span>登录</span>
                </NavLink>
              )}

              {/* Mobile menu button */}
              <button
                className="md:hidden p-2 rounded-md text-muted hover:text-fg"
                onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              >
                {mobileMenuOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
              </button>
            </div>
          </div>
        </div>

        {/* Mobile Nav */}
        {mobileMenuOpen && (
          <div className="md:hidden border-t border-border bg-cream">
            <div className="px-4 py-2 space-y-1">
              {navItems.map((item) =>
                item.external ? (
                  <a
                    key={item.to}
                    href={item.to}
                    className="flex items-center gap-2 px-3 py-2 rounded-md text-sm text-fg hover:bg-white/60"
                  >
                    <item.icon className="w-4 h-4" />
                    {item.label}
                  </a>
                ) : (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    onClick={() => setMobileMenuOpen(false)}
                    className={({ isActive: a }) =>
                      `flex items-center gap-2 px-3 py-2 rounded-md text-sm ${
                        a ? 'text-accent bg-accent-light font-medium' : 'text-fg hover:bg-white/60'
                      }`
                    }
                  >
                    <item.icon className="w-4 h-4" />
                    {item.label}
                  </NavLink>
                )
              )}
            </div>
          </div>
        )}
      </header>

      {/* ===== MAIN CONTENT ===== */}
      <main className="flex-1">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 py-6 pb-24 md:pb-6">
          {children}
        </div>
      </main>

      {/* ===== FOOTER ===== */}
      <footer className="hidden md:block border-t border-border py-4">
        <p className="text-center text-xs text-muted">
          CigarDomTabaka · 仅供内部参考
        </p>
      </footer>

      {/* ===== MOBILE BOTTOM NAV ===== */}
      <nav className="md:hidden fixed bottom-0 left-0 right-0 bg-cream/95 backdrop-blur-sm border-t border-border z-50">
        <div className="flex items-center justify-around h-14">
          {[
            { to: '/', label: '品牌', icon: LayoutGrid },
            ...(user?.is_staff ? [
              { to: '/inventory', label: '库存', icon: Package },
              { to: '/prices', label: '价格', icon: TrendingUp },
              { to: '/privnote', label: '链接', icon: Link2 },
            ] : []),
          ].map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive: a }) =>
                `flex flex-col items-center justify-center gap-0.5 w-full h-full text-[10px] font-medium ${
                  a ? 'text-accent' : 'text-muted'
                }`
              }
            >
              <item.icon className="w-5 h-5" />
              <span>{item.label}</span>
            </NavLink>
          ))}
        </div>
      </nav>
    </div>
  );
}
