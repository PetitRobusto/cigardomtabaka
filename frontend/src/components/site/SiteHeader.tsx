import { useEffect, useRef, useState, type MouseEvent, type ReactNode } from 'react';
import { ChevronDown, LayoutGrid, Package, CircleDollarSign, ClipboardList, Menu, Search, Globe, LogIn, LogOut } from 'lucide-react';
import type { User } from '../../store/authStore';
import { siteDockLogoUrl as brandDockLogoUrl } from './siteAssets';
import { customerMessages, languageNames, type CustomerLocale } from '../../features/customer/messages';
import { useCustomerPreferences } from '../../features/customer/preferences';
import { mobileNavItems } from '../layout/mobileNav';
import { isAppNavPathActive } from '../layout/appSections';
import './site-header.css';

const labels = {
  zh: { store: '商城', tools: '管理工具', search: '搜索商城商品', submit: '搜索' },
  en: { store: 'Shop', tools: 'Management', search: 'Search the shop', submit: 'Search' },
  ru: { store: 'Магазин', tools: 'Управление', search: 'Поиск сигар в магазине', submit: 'Найти' },
};
const managementLinks = [
  { path: '/inventory', label: '库存' }, { path: '/sales', label: '订单' },
  { path: '/accounting', label: '账务' }, { path: '/prices', label: '价格' },
  { path: '/privnote', label: '链接' }, { path: '/library', label: '资料库' },
  { path: '/help', label: '帮助' },
];
type LanguageLink = { locale: CustomerLocale; path: string };
type Navigate = (path: string) => void;

function SiteLink({ href, onNavigate, children, ...props }: {
  href: string; onNavigate?: Navigate; children: ReactNode; className?: string; 'aria-current'?: 'page';
}) {
  const click = (event: MouseEvent<HTMLAnchorElement>) => {
    if (!onNavigate || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    if (!managementLinks.some((item) => href === item.path || href.startsWith(item.path + '/'))) return;
    event.preventDefault(); onNavigate(href);
  };
  return <a href={href} onClick={click} {...props}>{children}</a>;
}

export function SiteHeader({ locale = 'zh', user = null, pathname = '/', languages = [], query = '',
  searchFields = [], inert = false, onLogout, onNavigate, children, storeLocale = locale }: {
  locale?: CustomerLocale; storeLocale?: CustomerLocale; user?: User | null; pathname?: string; languages?: LanguageLink[];
  query?: string; searchFields?: Array<{ name: string; value: string }>; inert?: boolean;
  onLogout?: () => void; onNavigate?: Navigate; children?: ReactNode;
}) {
  const copy = labels[locale]; const text = customerMessages[locale];
  const home = storeLocale === 'zh' ? '/' : `/${storeLocale}/`;
  const [openedMenu, setOpenedMenu] = useState<{ kind: 'tools' | 'language'; path: string } | null>(null);
  const menu = openedMenu?.path === pathname ? openedMenu.kind : null;
  const setMenu = (kind: 'tools' | 'language' | null) => setOpenedMenu(kind ? { kind, path: pathname } : null);
  const root = useRef<HTMLElement>(null);
  const toolsButton = useRef<HTMLButtonElement>(null);
  const languageButton = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!menu) return;
    const close = (event: PointerEvent) => { if (!root.current?.contains(event.target as Node)) setOpenedMenu(null); };
    document.addEventListener('pointerdown', close);
    return () => document.removeEventListener('pointerdown', close);
  }, [menu]);
  return <header ref={root} className="site-header" inert={inert || undefined} onKeyDown={(event) => {
    if (event.key === 'Escape' && menu) { (menu === 'tools' ? toolsButton : languageButton).current?.focus(); setMenu(null); }
  }}>
    <div className="site-header-main">
      <a className="site-brand" href={home} aria-label="CigarDomTabaka"><img src={brandDockLogoUrl} data-startup-logo-target width="45" height="45" alt="" /><span>CigarDomTabaka</span></a>
      <nav className="site-app-nav" aria-label={text.navigation}>
        <a className={!managementLinks.some((item) => pathname.startsWith(item.path)) ? 'active' : undefined} href={home}><LayoutGrid aria-hidden="true" /><span>{copy.store}</span></a>
        {user?.is_staff && <div className="site-menu-wrap">
          <button ref={toolsButton} type="button" aria-expanded={menu === 'tools'} aria-controls="site-management-menu" onClick={() => setMenu(menu === 'tools' ? null : 'tools')}><Menu aria-hidden="true" /><span>{copy.tools}</span><ChevronDown aria-hidden="true" /></button>
          {menu === 'tools' && <div id="site-management-menu" className="site-menu" onClick={() => setMenu(null)}>{managementLinks.map((item) => <SiteLink key={item.path} href={item.path} onNavigate={onNavigate} aria-current={isAppNavPathActive(pathname, item.path) ? 'page' : undefined}>{item.label}</SiteLink>)}</div>}
        </div>}
      </nav>
      <form className="site-search" role="search" method="get" action={`${storeLocale === 'zh' ? '' : `/${storeLocale}`}/catalog`}>
        <Search aria-hidden="true" /><input type="search" aria-label={copy.search} name="q" placeholder={copy.search} defaultValue={query} key={query} />
        {searchFields.map((field, index) => <input type="hidden" key={`${field.name}-${index}`} name={field.name} value={field.value} />)}
        <button type="submit">{copy.submit}</button>
      </form>
      <div className="site-account">
        {languages.length > 0 && <div className="site-menu-wrap" data-customer-language>
          <button ref={languageButton} className="site-language-button" type="button" aria-label={text.language} aria-expanded={menu === 'language'} aria-controls="site-language-menu" onClick={() => setMenu(menu === 'language' ? null : 'language')}><Globe aria-hidden="true" /><span>{languageNames[locale]}</span><ChevronDown aria-hidden="true" /></button>
          {menu === 'language' && <div id="site-language-menu" className="site-menu site-language-menu">{languages.map((item) => <a key={item.locale} href={item.path} lang={item.locale === 'zh' ? 'zh-CN' : item.locale} aria-current={locale === item.locale ? 'page' : undefined} onClick={() => { useCustomerPreferences.getState().selectLocale(item.locale); setMenu(null); }}>{languageNames[item.locale]}</a>)}</div>}
        </div>}
        {user ? <><span className="site-username">{user.username}</span><button type="button" aria-label={text.logout} onClick={onLogout}><LogOut aria-hidden="true" /></button></> : <a className="site-login" href={`/login?${new URLSearchParams({ next: pathname })}`} aria-label={text.login}><LogIn aria-hidden="true" /><span>{text.login}</span></a>}
      </div>
    </div>
    {children && <div className="site-header-extra">{children}</div>}
  </header>;
}

export function StaffDock({ user, pathname, onNavigate, inert = false, storeLocale = 'zh' }: { user: User | null; pathname: string; onNavigate?: Navigate; inert?: boolean; storeLocale?: CustomerLocale }) {
  const [open, setOpen] = useState(false);
  if (!user?.is_staff) return null;
  const icons = { '/': LayoutGrid, '/inventory': Package, '/sales': CircleDollarSign, '/accounting': ClipboardList };
  const items = mobileNavItems(true).filter((item) => item.kind === 'link').map((item) => ({
    path: item.to, label: item.label, icon: icons[item.to as keyof typeof icons],
  }));
  return <div className="site-staff-dock" inert={inert || undefined}>
    {open && <div className="site-dock-more" id="site-dock-more" onClick={() => setOpen(false)}>{managementLinks.slice(3).map((item) => <SiteLink key={item.path} href={item.path} onNavigate={onNavigate}>{item.label}</SiteLink>)}</div>}
    <nav aria-label="移动应用导航">{items.map((item) => <SiteLink key={item.path} href={item.path === '/' && storeLocale !== 'zh' ? `/${storeLocale}/` : item.path} onNavigate={onNavigate} aria-current={isAppNavPathActive(pathname, item.path) ? 'page' : undefined}><item.icon aria-hidden="true" /><span>{item.label}</span></SiteLink>)}<button type="button" aria-expanded={open} aria-controls="site-dock-more" onClick={() => setOpen(!open)}><Menu aria-hidden="true" /><span>更多</span></button></nav>
  </div>;
}
