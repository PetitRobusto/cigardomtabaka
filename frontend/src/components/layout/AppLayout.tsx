import { NavLink, useLocation, useNavigate } from 'react-router-dom';
import { useEffect } from 'react';
import { useAuthStore } from '../../store/authStore';
import { usePageMetaContext } from '../../contexts/PageMetaContext';
import Breadcrumb from './Breadcrumb';
import { isSalesAccountingNavActive } from '../sales/salesState';
import {
  LayoutGrid, Package, TrendingUp, Link2, Settings, LogIn, LogOut, User, Menu, X,
  CircleDollarSign, ClipboardList,
  MapPin, Phone, MessageCircle
} from 'lucide-react';
import { useState } from 'react';

const base = import.meta.env.BASE_URL;

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const { user, isAuthenticated, isLoading, logout } = useAuthStore();
  const location = useLocation();
  const navigate = useNavigate();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const { meta } = usePageMetaContext();

  useEffect(() => {
    useAuthStore.getState().checkAuth();
  }, []);

  useEffect(() => {
    if (meta.title) {
      document.title = meta.title;
    }
  }, [meta.title]);

  const navItems = [
    { to: '/', label: '品牌', icon: LayoutGrid, public: true },
    ...(user?.is_staff ? [
      { to: '/inventory', label: '库存', icon: Package },
      { to: '/sales', label: '销售', icon: CircleDollarSign },
      { to: '/sales#accounting', label: '账务', icon: ClipboardList },
      { to: '/prices', label: '价格', icon: TrendingUp },
      { to: '/privnote', label: '链接', icon: Link2 },
      { to: '/admin/', label: '管理', icon: Settings, external: true },
    ] : []),
  ];

  const isActive = (path: string) => {
    if (path === '/') return location.pathname === '/';
    if (path === '/sales' || path === '/sales#accounting') return location.pathname === '/sales' && isSalesAccountingNavActive(path, location.hash.replace('#', ''));
    return location.pathname.startsWith(path);
  };

  useEffect(() => {
    if (location.pathname === '/sales' && location.hash === '#accounting') {
      window.setTimeout(() => document.getElementById('accounting')?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 0);
    }
  }, [location.pathname, location.hash]);

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
          <div className="flex items-center justify-between h-16">
            {/* Logo */}
            <div className="flex items-center gap-3">
              <img
                src={`${base}logo-512.png`}
                alt="CigarDomTabaka"
                className="w-[45px] h-[45px] cursor-pointer object-contain"
                onClick={() => navigate('/')}
              />
              <span className="font-display text-lg font-semibold text-fg tracking-tight hidden sm:inline">
                CigarDomTabaka
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
                aria-label="打开导航菜单"
                aria-expanded={mobileMenuOpen}
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
        <div className="max-w-[1480px] mx-auto px-4 sm:px-6 py-6 pb-24 md:pb-6">
          <Breadcrumb />
          {children}
        </div>
      </main>

      {/* ===== FOOTER ===== */}
      <footer className="bg-accent-light border-t-2 border-accent mt-auto">
        <div className="max-w-7xl mx-auto px-6 sm:px-8 py-10 md:py-12">
          {/* Top row */}
          <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-5 md:gap-8 pb-8 border-b border-border">
            {/* Brand */}
            <div className="flex items-center gap-4">
              <img src={`${base}logo-512.png`} alt="CigarDomTabaka" className="w-[120px] h-[120px] object-contain shrink-0 mr-4" />
              <div>
                <div className="font-display text-[22px] font-semibold tracking-wide text-fg">
                  CigarDomTabaka
                </div>
                <div className="text-[13px] text-muted italic font-display mt-1">
                  Премиум сигары · Прямые поставки из Москвы
                </div>
              </div>
            </div>

            {/* Contact — horizontal row */}
            <div className="flex flex-col sm:flex-row gap-3 sm:gap-7">
              <div className="flex items-center gap-2 text-[13px] text-fg">
                <MapPin className="w-[15px] h-[15px] text-accent shrink-0" />
                <span>Москва, Молодёжная ул. 3</span>
              </div>
              <div className="flex items-center gap-2 text-[13px] text-fg">
                <Phone className="w-[15px] h-[15px] text-accent shrink-0" />
                <span>+7 929 638-48-78</span>
              </div>
              <div className="flex items-center gap-2 text-[13px] text-fg">
                <MessageCircle className="w-[15px] h-[15px] text-accent shrink-0" />
                <span>WeChat: cigardomtabaka</span>
              </div>
            </div>
          </div>

          {/* Bottom row */}
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 sm:gap-6 pt-6">
            <div className="text-xs text-muted">
              &copy; CigarDomTabaka. Все права защищены.
            </div>
            <div className="flex gap-3">
              {/* Telegram */}
              <a href="https://t.me/+79296384878" target="_blank" rel="noopener noreferrer" className="grid place-items-center w-[38px] h-[38px] rounded-full bg-fg border border-fg hover:bg-accent hover:border-accent hover:-translate-y-0.5 transition-all" aria-label="Telegram: +79296384878" title="Telegram">
                <svg className="w-[18px] h-[18px] fill-accent-light" viewBox="0 0 24 24"><path d="M11.944 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 12-12A12 12 0 0 0 12 0a12 12 0 0 0-.056 0zm4.962 7.224c.1-.002.321.023.465.14a.506.506 0 0 1 .171.325c.016.093.036.306.02.472-.18 1.898-.962 6.502-1.36 8.627-.168.9-.499 1.201-.82 1.23-.696.065-1.225-.46-1.9-.902-1.056-.693-1.653-1.124-2.678-1.8-1.185-.78-.417-1.21.258-1.91.177-.184 3.247-2.977 3.307-3.23.007-.032.014-.15-.056-.212s-.174-.041-.249-.024c-.106.024-1.793 1.14-5.061 3.345-.479.33-.913.49-1.302.48-.428-.008-1.252-.241-1.865-.44-.752-.245-1.349-.374-1.297-.789.027-.216.325-.437.893-.663 3.498-1.524 5.83-2.529 6.998-3.014 3.332-1.386 4.025-1.627 4.476-1.635z"/></svg>
              </a>
              {/* WhatsApp */}
              <a href="https://wa.me/79296384878" target="_blank" rel="noopener noreferrer" className="grid place-items-center w-[38px] h-[38px] rounded-full bg-fg border border-fg hover:bg-accent hover:border-accent hover:-translate-y-0.5 transition-all" aria-label="WhatsApp: +79296384878" title="WhatsApp">
                <svg className="w-[18px] h-[18px] fill-accent-light" viewBox="0 0 24 24"><path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z"/></svg>
              </a>
              {/* WeChat */}
              <a href="#" className="grid place-items-center w-[38px] h-[38px] rounded-full bg-fg border border-fg hover:bg-accent hover:border-accent hover:-translate-y-0.5 transition-all" aria-label="WeChat" title="WeChat: cigardomtabaka">
                <svg className="w-[18px] h-[18px] fill-accent-light" viewBox="0 0 24 24"><path d="M8.691 2.188C3.891 2.188 0 5.476 0 9.53c0 2.212 1.17 4.203 3.002 5.55a.59.59 0 0 1 .213.665l-.39 1.48c-.019.07-.048.141-.048.213 0 .163.13.295.29.295a.326.326 0 0 0 .167-.054l1.903-1.114a.864.864 0 0 1 .717-.098 10.16 10.16 0 0 0 2.837.403c.276 0 .543-.027.811-.05-.857-2.578.157-4.972 1.932-6.446 1.703-1.415 3.882-1.98 5.853-1.838-.576-3.583-4.196-6.348-8.596-6.348zM5.785 5.991c.642 0 1.162.529 1.162 1.18a1.17 1.17 0 0 1-1.162 1.178A1.17 1.17 0 0 1 4.623 7.17c0-.651.52-1.18 1.162-1.18zm5.813 0c.642 0 1.162.529 1.162 1.18a1.17 1.17 0 0 1-1.162 1.178 1.17 1.17 0 0 1-1.162-1.178c0-.651.52-1.18 1.162-1.18zm5.34 2.867c-1.797-.052-3.746.512-5.28 1.786-1.72 1.428-2.687 3.72-1.78 6.22.942 2.453 3.666 4.229 6.884 4.229.826 0 1.622-.12 2.361-.336a.722.722 0 0 1 .598.082l1.584.926a.272.272 0 0 0 .14.047c.134 0 .24-.111.24-.247 0-.06-.023-.12-.038-.177l-.327-1.233a.582.582 0 0 1-.023-.156.49.49 0 0 1 .201-.398C23.024 18.48 24 16.82 24 14.98c0-3.21-2.931-5.837-6.656-6.088V8.89c-.135-.01-.27-.027-.407-.03zm-2.53 3.274c.535 0 .969.44.969.982a.976.976 0 0 1-.969.983.976.976 0 0 1-.969-.983c0-.542.434-.982.97-.982zm4.844 0c.535 0 .969.44.969.982a.976.976 0 0 1-.969.983.976.976 0 0 1-.969-.983c0-.542.434-.982.969-.982z"/></svg>
              </a>
            </div>
          </div>
        </div>
      </footer>

      {/* ===== MOBILE BOTTOM NAV ===== */}
      <nav className="md:hidden fixed bottom-0 left-0 right-0 bg-cream/95 backdrop-blur-sm border-t border-border z-50">
        <div className="flex items-center justify-around h-14">
          {[
            { to: '/', label: '品牌', icon: LayoutGrid },
            ...(user?.is_staff ? [
              { to: '/inventory', label: '库存', icon: Package },
              { to: '/sales', label: '销售', icon: CircleDollarSign },
              { to: '/sales#accounting', label: '账务', icon: ClipboardList },
              { to: '/prices', label: '更多', icon: Menu },
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
