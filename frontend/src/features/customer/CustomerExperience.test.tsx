// @vitest-environment jsdom
import { useEffect } from 'react';
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter, useNavigate } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import AppLayout from '../../components/layout/AppLayout';
import { PageMetaProvider } from '../../contexts/PageMetaContext';
import { useAuthStore } from '../../store/authStore';
import BrandListPage from '../../pages/BrandListPage';
import CustomerDocumentLanguage from './CustomerDocumentLanguage';
import { CUSTOMER_LANGUAGE_KEY, readCustomerPreferences, useCustomerPreferences } from './preferences';

vi.mock('../guides/GuideController', () => ({ default: () => null }));
vi.mock('../../api', () => ({ fetchBrandList: vi.fn(async () => ({ total_brands: 2, sections: [{ key: 'global', label: '全球品牌', brands: [
  { slug: 'cohiba', name: '高希霸', english_name: 'Cohiba', cigar_count: 2, origin: 'Cuban', category: 'global', logo_url: null },
  { slug: 'montecristo', name: '蒙特', english_name: 'Montecristo', cigar_count: 1, origin: 'Cuban', category: 'global', logo_url: null },
] }] })) }));

beforeEach(() => {
  window.localStorage.clear(); window.sessionStorage.clear();
  useCustomerPreferences.setState({ locale: 'en', confirmedAt: null, denied: false });
  useAuthStore.setState({ user: null, isAuthenticated: false, isLoading: false, checkAuth: vi.fn(async () => undefined), logout: vi.fn(async () => undefined) });
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

function show(children: React.ReactNode = <div>Catalogue content</div>, path = '/') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<MemoryRouter initialEntries={[path]}><QueryClientProvider client={client}><PageMetaProvider>
    <CustomerDocumentLanguage /><AppLayout>{children}</AppLayout>
  </PageMetaProvider></QueryClientProvider></MemoryRouter>);
}

function selectLanguage(name: string) {
  fireEvent.click(screen.getByRole('button', { name: /^(Language|Язык|语言)$/ }));
  const menu = screen.getByRole('menu');
  expect(within(menu).getAllByRole('menuitemradio')).toHaveLength(3);
  expect(menu.textContent).not.toMatch(/跟随设备|Follow device|Как на устройстве/);
  fireEvent.click(within(menu).getByRole('menuitemradio', { name }));
}

describe('consumer language and age flow', () => {
  it.each(['/Brand/cohiba', '/brand/cohiba//', '/%62rand/cohiba'])('blocks catalogue content for router-equivalent path %s', (path) => {
    show(undefined, path);
    expect(screen.getByRole('dialog')).not.toBeNull();
    expect(screen.queryByText('Catalogue content')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'I am under 18' }));
    expect(screen.queryByText('Catalogue content')).toBeNull();
  });

  it('does not mount catalogue content before confirmation or after declining', () => {
    const mounted = vi.fn();
    function Content() { useEffect(mounted, []); return <div>Catalogue content</div>; }
    show(<Content />);
    expect(screen.getByRole('dialog').textContent).toContain('Are you 18 or older?');
    expect(mounted).not.toHaveBeenCalled();
    fireEvent.keyDown(document, { key: 'Escape' });
    fireEvent.click(screen.getByRole('dialog').parentElement!);
    expect(screen.getByRole('dialog')).not.toBeNull();
    selectLanguage('Русский');
    expect(document.documentElement.lang).toBe('ru');
    fireEvent.click(screen.getByRole('button', { name: 'Мне нет 18 лет' }));
    expect(screen.getByRole('heading', { name: 'Доступ ограничен' })).not.toBeNull();
    selectLanguage('English');
    expect(screen.getByRole('heading', { name: 'Content not available' })).not.toBeNull();
    expect(mounted).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Back to age confirmation' }));
    fireEvent.click(screen.getByRole('button', { name: 'Yes, I am 18 or older' }));
    expect(screen.getByText('Catalogue content')).not.toBeNull();
    expect(mounted).toHaveBeenCalledOnce();
    expect(document.body.style.overflow).not.toBe('hidden');
    expect(readCustomerPreferences().confirmedAt).not.toBeNull();
  });

  it('remembers language and age across remounts for an ordinary logged-in user', () => {
    useAuthStore.setState({ user: { username: 'customer', is_staff: false, is_superuser: false }, isAuthenticated: true });
    const first = show();
    selectLanguage('简体中文');
    fireEvent.click(screen.getByRole('button', { name: '是的，我已满18岁' }));
    expect(window.localStorage.getItem(CUSTOMER_LANGUAGE_KEY)).toBe('zh');
    first.unmount();
    useCustomerPreferences.setState(readCustomerPreferences());
    show();
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(screen.getByRole('button', { name: '语言' }).textContent).toContain('简体中文');
    expect(screen.getByText('customer')).not.toBeNull();
  });

  it('supports keyboard dropdown selection and outside dismissal', () => {
    show();
    const trigger = screen.getByRole('button', { name: 'Language' });
    fireEvent.keyDown(trigger, { key: 'ArrowDown' });
    expect(document.activeElement?.textContent).toBe('English');
    fireEvent.keyDown(document.activeElement!, { key: 'ArrowDown' });
    expect(document.activeElement?.textContent).toBe('Русский');
    fireEvent.keyDown(document.activeElement!, { key: 'Escape' });
    expect(screen.queryByRole('menu')).toBeNull();
    expect(document.activeElement).toBe(trigger);
    expect(screen.getByRole('dialog')).not.toBeNull();
    fireEvent.click(trigger);
    fireEvent.pointerDown(screen.getByRole('dialog'));
    expect(screen.queryByRole('menu')).toBeNull();
  });

  it.each([{ is_staff: true, is_superuser: false }, { is_staff: false, is_superuser: true }])('keeps administrator views unchanged: %j', (flags) => {
    useAuthStore.setState({ user: { username: 'admin', ...flags }, isAuthenticated: true });
    show();
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(screen.queryByRole('button', { name: /Language|语言|Язык/ })).toBeNull();
    expect(screen.getByText('Catalogue content')).not.toBeNull();
    expect(document.documentElement.lang).toBe('zh-CN');
  });

  it.each(['/cigar/1/cohiba', '/p/token', '/privnote', '/sales', '/prices', '/login'])('does not add the experience to excluded route %s', (path) => {
    show(undefined, path);
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(screen.queryByRole('button', { name: /Language|语言|Язык/ })).toBeNull();
    expect(screen.getByText('Catalogue content')).not.toBeNull();
  });

  it('keeps search and metadata in sync when switching language, including mobile navigation', async () => {
    useCustomerPreferences.setState({ confirmedAt: Date.now() });
    show(<BrandListPage />);
    const search = await screen.findByRole('textbox', { name: 'Search brand names…' });
    fireEvent.change(search, { target: { value: 'Cohiba' } });
    selectLanguage('Русский');
    expect(screen.getByRole('textbox', { name: 'Поиск по названию бренда…' }).getAttribute('value')).toBe('Cohiba');
    expect(screen.getByRole('heading', { name: 'Каталог кубинских сигар' })).not.toBeNull();
    expect(screen.queryByText('Montecristo')).toBeNull();
    expect(document.title).toBe('Каталог кубинских сигар · CigarDomTabaka');
    expect(within(screen.getByRole('navigation', { name: 'Мобильная навигация' })).getByRole('link', { name: 'Бренды' })).not.toBeNull();
    act(() => useAuthStore.setState({ user: { username: 'staff', is_staff: true, is_superuser: false }, isAuthenticated: true }));
    expect(screen.queryByRole('button', { name: 'Язык' })).toBeNull();
    expect(screen.getByRole('heading', { name: '古巴雪茄目录' })).not.toBeNull();
    expect(document.documentElement.lang).toBe('zh-CN');
  });

  it('restores Chinese document language on excluded routes', () => {
    useCustomerPreferences.setState({ confirmedAt: Date.now(), locale: 'ru' });
    function NavigateAway() { const navigate = useNavigate(); return <button onClick={() => navigate('/cigar/1')}>Product detail</button>; }
    show(<NavigateAway />);
    expect(document.documentElement.lang).toBe('ru');
    fireEvent.click(screen.getByRole('button', { name: 'Product detail' }));
    expect(document.documentElement.lang).toBe('zh-CN');
    expect(screen.queryByRole('button', { name: 'Язык' })).toBeNull();
  });
});
